import os
import io
import json
import uuid
import sqlite3
import threading
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import httpx
from PyPDF2 import PdfReader
from docx import Document

from prompts import SYSTEM_INTERVIEWER, build_followup_prompt, build_report_prompt

# 加载 .env 文件里的环境变量
load_dotenv()

# 从环境变量读取 API Key
LLM_API_KEY = os.getenv("LLM_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

# 检查 Key 是否存在
if not LLM_API_KEY:
    raise ValueError("未找到 LLM_API_KEY，请检查 .env 文件")

# 追问/解析插槽（默认 MiMo）：地址、模型、Key 一起配置，避免 Key 与提供商不匹配
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.xiaomimimo.com/v1/chat/completions")
LLM_MODEL = os.getenv("LLM_MODEL", "mimo-v2.5-pro")

# 评分插槽（默认 DeepSeek）：地址、模型、Key 一起配置
SCORE_MODEL = os.getenv("SCORE_MODEL", "deepseek-v4-flash-vision-exp")
SCORE_BASE_URL = os.getenv("SCORE_BASE_URL", "https://api.deepseek.com/v1/chat/completions")

# 内置提供商预设（选项 → 地址 + 模型）
LLM_PROVIDER_PRESETS = {
    "MiMo": {
        "base_url": "https://api.xiaomimimo.com/v1/chat/completions",
        "model": "mimo-v2.5-pro",
    },
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-v4-flash-vision-exp",
    },
    "OpenAI": {
        "base_url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
    },
}


def provider_of(base_url: str) -> str:
    """从 base_url 判断提供商预设，匹配不到返回「自定义」"""
    for name, preset in LLM_PROVIDER_PRESETS.items():
        if preset["base_url"] == base_url:
            return name
    return "自定义"


# ═══════════════════════════════════════════════════════
#  API Key 运行时更新：设置入口改 Key，立即生效且无需重启
#  调用函数在请求时读取全局变量，因此直接赋值即可生效
# ═══════════════════════════════════════════════════════


def mask_key(key: str) -> str | None:
    """把 Key 脱敏（sk-****xxxx），未配置返回 None"""
    if not key:
        return None
    if len(key) <= 8:
        return key[:2] + "****"
    return f"{key[:6]}****{key[-4:]}"


def save_env_setting(key_name: str, value: str) -> None:
    """把配置项写回 .env（保留其他行），重启后依然生效。"""
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    prefix = f"{key_name}="
    for i, line in enumerate(lines):
        if line.strip().startswith(prefix):
            lines[i] = f"{key_name}={value}"
            break
    else:
        lines.append(f"{key_name}={value}")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


async def call_llm(messages: list, timeout: float = 120.0) -> str:
    """调用追问/解析插槽的 LLM（默认 MiMo），返回文字回复。"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            LLM_BASE_URL,
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": LLM_MODEL,
                "messages": messages
            },
            timeout=timeout
        )
        if response.status_code == 401:
            raise HTTPException(status_code=500, detail="LLM API Key 无效或已过期")
        if response.status_code == 429:
            raise HTTPException(status_code=503, detail="LLM API 限流，请稍后重试")
        if response.status_code >= 500:
            raise HTTPException(status_code=502, detail=f"LLM API 服务异常: {response.status_code}")
        result = response.json()
        if "choices" not in result:
            raise HTTPException(status_code=502, detail=f"LLM API 返回格式异常: {str(result)[:200]}")
        return result["choices"][0]["message"]["content"]


async def call_llm_score(messages: list, timeout: float = 120.0) -> str:
    """调用评分模型（DeepSeek）。未配置 DeepSeek Key 时回退到 MiMo。"""
    if not DEEPSEEK_API_KEY:
        return await call_llm(messages, timeout)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            SCORE_BASE_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": SCORE_MODEL,
                "messages": messages
            },
            timeout=timeout
        )
        if response.status_code == 401:
            raise HTTPException(status_code=500, detail="评分模型 API Key 无效或已过期")
        if response.status_code == 429:
            raise HTTPException(status_code=503, detail="评分模型 API 限流，请稍后重试")
        if response.status_code >= 500:
            raise HTTPException(status_code=502, detail=f"评分模型 API 服务异常: {response.status_code}")
        result = response.json()
        if "choices" not in result:
            raise HTTPException(status_code=502, detail=f"评分模型 API 返回格式异常: {str(result)[:200]}")
        return result["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════
#  Agent 工具层：让面试官从"裸 LLM"变成"有工具的 Agent"
# ═══════════════════════════════════════════════════════

# 工具 schema（OpenAI Function Calling 格式）
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_resume",
            "description": "根据关键词搜索候选人简历中的相关段落。当候选人提到某个项目、技术或经历时，用这个工具获取简历中的详细信息，以便追问细节。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如项目名、技术名（例如：秒杀、FastAPI、Redis）"
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_answer",
            "description": "评估候选人当前回答的质量。当需要判断回答深度、决定是追问还是推进时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "候选人的回答内容"
                    },
                    "criteria": {
                        "type": "string",
                        "description": "评估标准，如：技术深度、逻辑清晰度、实战经验"
                    }
                },
                "required": ["answer", "criteria"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_interview_plan",
            "description": "获取面试的阶段计划。当某个话题回答已充分、需要推进到下一个话题，或刚开始面试不知道问什么时调用，返回当前阶段建议和下一阶段方向。",
            "parameters": {
                "type": "object",
                "properties": {
                    "current_topic": {
                        "type": "string",
                        "description": "当前正在问的话题（如：秒杀系统、Redis 原理、自我介绍）"
                    },
                    "covered_topics": {
                        "type": "string",
                        "description": "已经覆盖的话题，用分号分隔；不知道就传空字符串"
                    }
                },
                "required": ["current_topic", "covered_topics"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_report",
            "description": "面试结束时，根据整场对话生成结构化评分报告。仅在候选人明确表示结束面试或对话已充分展开时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_summary": {
                        "type": "string",
                        "description": "整场面试的对话摘要"
                    }
                },
                "required": ["history_summary"]
            }
        }
    }
]


def tool_search_resume(keyword: str, resume_text: str) -> str:
    """从简历中搜索包含关键词的段落（去换行匹配，避免 PDF 断行/截断导致漏检）"""
    if not resume_text:
        return "简历内容为空，无法搜索。"
    kw = (keyword or "").strip().lower()
    if not kw:
        return "关键词为空，无法搜索。请提供具体的项目名或技术名。"

    # 构建"去换行"后的全文 + 原文索引映射：跨行关键词（如"秒杀系\n统"）也能命中
    flat_chars = []
    orig_index = []  # orig_index[i] = flat 第 i 个字符在原文中的下标
    for i, ch in enumerate(resume_text):
        if ch in "\r\n":
            continue
        flat_chars.append(ch.lower())
        orig_index.append(i)
    flat = "".join(flat_chars)

    def _context(orig_start: int, orig_end: int) -> str:
        # 关键词原文保持连续（方便模型识别），命中标记放在段落开头
        matched_text = resume_text[orig_start:orig_end]
        left = resume_text[max(0, orig_start - 120):orig_start]
        right = resume_text[orig_end:orig_end + 120]
        return ("〔命中〕" + left + matched_text + right).strip()

    matched = []
    pos = flat.find(kw)
    while pos != -1 and len(matched) < 3:
        orig_start = orig_index[pos]
        orig_end = orig_index[pos + len(kw) - 1] + 1
        matched.append(_context(orig_start, orig_end))
        pos = flat.find(kw, pos + 1)

    if matched:
        return f"找到 {len(matched)} 处匹配「{keyword}」：\n" + "\n---\n".join(matched)
    return (
        f"未找到与「{keyword}」完全匹配的段落。"
        "注意：未找到只代表关键词与简历原文写法不一致，不代表简历中不存在该项目；"
        "请基于候选人已说出的内容继续追问，不要断言其不存在。"
    )


def tool_evaluate_answer(answer: str, criteria: str) -> str:
    """评估候选人回答的质量（本地规则 + 启发式）"""
    score = 50  # 基准分
    reasons = []

    # 长度评估
    if len(answer) > 200:
        score += 10
        reasons.append("回答较详细")
    elif len(answer) < 30:
        score -= 15
        reasons.append("回答过于简短")

    # 技术关键词密度
    tech_keywords = ["架构", "性能", "优化", "设计", "实现", "原理", "底层",
                     "并发", "缓存", "数据库", "算法", "复杂度", "分布式",
                     "测试", "部署", "监控", "日志", "异常", "容错"]
    tech_count = sum(1 for kw in tech_keywords if kw in answer)
    if tech_count >= 3:
        score += 15
        reasons.append(f"包含 {tech_count} 个技术关键词")
    elif tech_count == 0:
        score -= 10
        reasons.append("缺少技术深度词汇")

    # 结构化表达
    if any(marker in answer for marker in ["首先", "其次", "最后", "第一", "第二", "1.", "2."]):
        score += 10
        reasons.append("回答有条理")

    # 不知道/不了解
    if any(phrase in answer for phrase in ["不知道", "不了解", "没做过", "不清楚"]):
        score -= 20
        reasons.append("坦诚承认不了解")

    score = max(0, min(100, score))
    return json.dumps({"score": score, "reasons": reasons, "criteria": criteria}, ensure_ascii=False)


def tool_generate_report(history_summary: str) -> str:
    """返回提示，让 LLM 基于历史生成报告"""
    return (
        f"请根据以下面试摘要生成 JSON 评分报告：\n{history_summary}\n"
        "输出格式：{\"score\":{\"technical\":0,\"communication\":0,\"logic\":0},"
        "\"strengths\":[\"...\"],\"improvements\":[\"...\"],\"overall_comment\":\"...\"}"
    )


# 面试阶段蓝图：规划工具输出下一步该问什么
INTERVIEW_BLUEPRINT = [
    {"phase": "项目深挖", "focus": "验证简历真实性：项目背景、技术选型权衡、量化成果、踩坑复盘"},
    {"phase": "技术深度", "focus": "核心技术栈原理：底层实现、复杂度分析、性能优化"},
    {"phase": "场景/设计题", "focus": "开放性问题：系统设计、故障排查、边界情况处理"},
    {"phase": "软素质", "focus": "团队协作、压力场景、主动性、学习能力"},
    {"phase": "反问环节", "focus": "给候选人提问机会，考察关注点"},
]


def tool_get_interview_plan(current_topic: str, covered_topics: str = "", 
                            jd_skills: str = "") -> str:
    """根据当前话题和已覆盖话题，返回面试阶段计划和下一步方向"""
    current_topic = (current_topic or "").strip()
    covered = covered_topics or ""

    def match_phase(topic: str) -> str:
        """粗分类：按关键词判断话题属于哪个阶段"""
        if any(k in topic for k in ["项目", "简历", "实习", "架构", "系统"]):
            return "项目深挖"
        if any(k in topic for k in ["原理", "底层", "算法", "优化", "并发", "实现", "数据库", "缓存"]):
            return "技术深度"
        if any(k in topic for k in ["设计", "场景", "故障", "排查", "模拟", "麻烦"]):
            return "场景/设计题"
        if any(k in topic for k in ["团队", "沟通", "协作", "冲突", "成长", "学习", "离职"]):
            return "软素质"
        if any(k in topic for k in ["有什么要问", "反问", "提问"]):
            return "反问环节"
        return "技术深度"

    current_phase = match_phase(current_topic)

    # 根据粗分类列举已完成阶段，输出当前阶段建议 + 下一阶段
    phases = [p["phase"] for p in INTERVIEW_BLUEPRINT]
    current_idx = phases.index(current_phase) if current_phase in phases else 0
    next_phase = phases[current_idx + 1] if current_idx + 1 < len(phases) else "面试收尾"

    remaining = [p for p in INTERVIEW_BLUEPRINT if p["phase"] not in current_phase and p["phase"] != "反问环节"]
    result = {
        "current_phase": current_phase,
        "focus": next((p["focus"] for p in INTERVIEW_BLUEPRINT if p["phase"] == current_phase), ""),
        "advice": f"当前话题「{current_topic}」围绕「{current_phase}」阶段展开；如该话题已问透，建议推进到「{next_phase}」阶段。",
        "covered_topics": covered,
        "next_phase": next_phase,
        "next_direction": next((p["focus"] for p in INTERVIEW_BLUEPRINT if p["phase"] == next_phase), "综合评估并安排反问"),
        "blueprint": remaining,
    }
    
    # 添加 JD 技能优先级
    if jd_skills:
        result["jd_skills_priority"] = jd_skills
        result["advice"] += f"\n优先考察 JD 要求的技能：{jd_skills}"
    
    return json.dumps(result, ensure_ascii=False)


async def call_llm_with_tools(messages: list, tools: list = None,
                               resume_text: str = "", jd_skills: str = "",
                               timeout: float = 120.0) -> dict:
    """
    支持 Function Calling 的 LLM 调用。
    自动处理工具调用循环：LLM 返回 tool_calls → 执行工具 → 结果喂回 → 直到生成最终回复。
    返回 {"content": str, "tool_calls_log": list}
    """
    tool_calls_log = []

    for _ in range(5):
        payload = {"model": LLM_MODEL, "messages": messages}
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient() as client:
            response = await client.post(
                LLM_BASE_URL,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=timeout
            )
            if response.status_code == 401:
                raise HTTPException(status_code=500, detail="LLM API Key 无效或已过期")
            if response.status_code == 429:
                raise HTTPException(status_code=503, detail="LLM API 限流，请稍后重试")
            if response.status_code >= 500:
                raise HTTPException(status_code=502, detail=f"LLM API 服务异常: {response.status_code}")
            result = response.json()

        if "choices" not in result:
            raise HTTPException(status_code=502, detail=f"LLM API 返回格式异常: {str(result)[:200]}")

        message = result["choices"][0]["message"]

        if not message.get("tool_calls"):
            return {"content": message.get("content", ""), "tool_calls_log": tool_calls_log}

        messages.append(message)

        for tc in message["tool_calls"]:
            func_name = tc["function"]["name"]
            try:
                func_args = json.loads(tc["function"]["arguments"])
            except (json.JSONDecodeError, KeyError):
                func_args = {}

            if func_name == "search_resume":
                keyword = func_args.get("keyword", "")
                result_text = tool_search_resume(keyword, resume_text) if keyword else "关键词为空，无法搜索。"
            elif func_name == "evaluate_answer":
                result_text = tool_evaluate_answer(func_args.get("answer", ""), func_args.get("criteria", ""))
            elif func_name == "get_interview_plan":
                result_text = tool_get_interview_plan(
                    func_args.get("current_topic", ""), func_args.get("covered_topics", ""),
                    jd_skills=jd_skills
                )
            elif func_name == "generate_report":
                result_text = tool_generate_report(func_args.get("history_summary", ""))
            else:
                result_text = f"未知工具：{func_name}"

            tool_calls_log.append({"tool": func_name, "args": func_args, "result": result_text[:200]})
            # 工具结果是给模型的"后台材料"：明确标记严禁输出，防止模型把检索原文复述给候选人
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": f"【后台检索材料·仅供你生成追问参考，严禁把原文输出给候选人】\n{result_text}",
            })

    return {"content": messages[-1].get("content", "（工具调用超限）"), "tool_calls_log": tool_calls_log}


async def _guard_agent_reply(agent_messages: list, final_reply: str) -> str:
    """兜底：模型若把检索材料原样复述成回复（含〔命中〕标记），纠正重试一次"""
    if not final_reply or "〔命中〕" not in final_reply:
        return final_reply
    retry_messages = agent_messages + [
        {"role": "assistant", "content": final_reply},
        {
            "role": "user",
            "content": (
                "你刚才把后台检索材料原样输出给了候选人。请忽略上面的引用，"
                "只输出基于该材料生成的追问（1-2 句话），必须是你自己组织的语言，不要复述材料原文。"
            ),
        },
    ]
    try:
        retry = await call_llm(retry_messages, timeout=60)
    except HTTPException:
        return final_reply  # 兜底失败时保持原回复，宁可提示错误也不要静默丢失
    if retry and "〔命中〕" not in retry:
        return retry
    return final_reply


app = FastAPI()

# 允许前端跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SlotSettings(BaseModel):
    """单个 LLM 插槽的设置（留空的字段表示不修改）"""
    api_key: str = ""    # 该插槽的 API Key
    base_url: str = ""   # OpenAI 兼容的 chat/completions 地址
    model: str = ""      # 模型名


class UpdateKeysRequest(BaseModel):
    main: SlotSettings = Field(default_factory=SlotSettings)   # 追问/解析插槽（默认 MiMo）
    score: SlotSettings = Field(default_factory=SlotSettings)  # 评分插槽（默认 DeepSeek）


def _slot_status(base_url: str, model: str, api_key: str) -> dict:
    """生成单个插槽的状态描述（Key 脱敏）"""
    return {
        "provider": provider_of(base_url),
        "base_url": base_url,
        "model": model,
        "api_key_masked": mask_key(api_key),
        "api_key_set": bool(api_key),
    }


@app.get("/settings/keys")
async def get_settings_keys():
    """返回两个插槽的当前配置（Key 脱敏），供设置页展示"""
    return {
        "main": _slot_status(LLM_BASE_URL, LLM_MODEL, LLM_API_KEY),
        "score": _slot_status(SCORE_BASE_URL, SCORE_MODEL, DEEPSEEK_API_KEY),
    }


@app.post("/settings/keys")
async def update_settings_keys(req: UpdateKeysRequest):
    """更新插槽配置：Key/地址/模型与插槽绑定保存，立即生效并写回 .env（重启后保留）"""
    global LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, DEEPSEEK_API_KEY, SCORE_BASE_URL, SCORE_MODEL

    m, s = req.main, req.score
    if m.api_key.strip():
        LLM_API_KEY = m.api_key.strip()
        save_env_setting("LLM_API_KEY", m.api_key.strip())
    if m.base_url.strip():
        LLM_BASE_URL = m.base_url.strip()
        save_env_setting("LLM_BASE_URL", m.base_url.strip())
    if m.model.strip():
        LLM_MODEL = m.model.strip()
        save_env_setting("LLM_MODEL", m.model.strip())
    if s.api_key.strip():
        DEEPSEEK_API_KEY = s.api_key.strip()
        save_env_setting("DEEPSEEK_API_KEY", s.api_key.strip())
    if s.base_url.strip():
        SCORE_BASE_URL = s.base_url.strip()
        save_env_setting("SCORE_BASE_URL", s.base_url.strip())
    if s.model.strip():
        SCORE_MODEL = s.model.strip()
        save_env_setting("SCORE_MODEL", s.model.strip())
    return await get_settings_keys()


@app.get("/")
def read_root():
    return {"message": "你好，我是你的 AI 面试官！", "status": "running"}


@app.get("/chat")
async def chat(message: str):
    """简单调用（保留昨天的功能）"""
    messages = [{"role": "user", "content": message}]
    ai_reply = await call_llm(messages)
    return {"user": message, "ai": ai_reply}


class ChatRequest(BaseModel):
    message: str
    history: list = []  # 多轮对话历史，默认为空


@app.post("/chat-with-history")
async def chat_with_history(req: ChatRequest):
    """支持多轮对话的接口"""
    messages = req.history + [{"role": "user", "content": req.message}]
    ai_reply = await call_llm(messages)
    return {
        "user": req.message,
        "ai": ai_reply,
        "history": messages + [{"role": "assistant", "content": ai_reply}],
    }


def trim_history(history: list, max_turns: int = 10) -> list:
    """只保留最近 max_turns 轮对话，避免历史过长"""
    # 每轮对话包含 user + assistant 两条
    max_messages = max_turns * 2
    if len(history) > max_messages:
        return history[-max_messages:]
    return history


def add_system_prompt(history: list, role: str = "interviewer") -> list:
    """在历史最前面加一个系统提示，告诉 AI 它是谁"""
    system_messages = {
        "interviewer": "你是一位专业的技术面试官，正在面试候选人。问题犀利但不刁难，引导候选人展现真实能力。",
        "career_coach": "你是一位资深职业规划师，帮助用户分析职业发展问题，给出具体可执行的建议。"
    }
    return [{"role": "system", "content": system_messages[role]}] + history


class ChatWithRoleRequest(BaseModel):
    message: str
    history: list = []
    role: str = "interviewer"


@app.post("/chat-role")
async def chat_role(req: ChatWithRoleRequest):
    """带角色设定的多轮对话接口"""
    # 压缩历史
    trimmed = trim_history(req.history)
    # 加系统提示
    messages = add_system_prompt(trimmed, req.role)
    # 加上当前问题
    messages.append({"role": "user", "content": req.message})

    ai_reply = await call_llm(messages)
    return {"user": req.message, "ai": ai_reply, "role": req.role}


def parse_pdf(content: bytes) -> str:
    """解析 PDF 文件，提取文本"""
    reader = PdfReader(io.BytesIO(content))
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:  # 扫描版 PDF 的 extract_text() 可能返回 None
            text += page_text + "\n"
    return text.strip()


def parse_docx(content: bytes) -> str:
    """解析 Word 文件，提取文本"""
    doc = Document(io.BytesIO(content))
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text.strip()


def parse_text(content: bytes) -> str:
    """解析纯文本文件"""
    return content.decode("utf-8", errors="ignore").strip()


@app.post("/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    """上传简历/JD（PDF、Word、txt、md），返回纯文本"""
    # 读取文件内容
    content = await file.read()

    # 根据文件类型选解析器
    if file.filename.endswith(".pdf"):
        text = parse_pdf(content)
    elif file.filename.endswith(".docx"):
        text = parse_docx(content)
    elif file.filename.endswith((".txt", ".md")):
        text = parse_text(content)
    else:
        return {"error": "只支持 PDF、Word、txt、md 文件"}

    return {
        "filename": file.filename,
        "length": len(text),
        "content": text
    }


class InterviewStartRequest(BaseModel):
    resume_text: str
    jd_text: str = ""  # 职位描述，可选


@app.post("/start-interview")
async def start_interview(req: InterviewStartRequest):
    """根据简历和 JD 生成第一个面试问题"""
    prompt = f"""你是一位专业的技术面试官。请根据以下信息生成**第一个**面试问题：

【候选人简历】
{req.resume_text[:1500]}

【目标岗位 JD】
{req.jd_text[:1000] if req.jd_text else "通用技术岗"}

【要求】
1. 问题要紧扣简历中的项目经验或技术栈
2. 难度适中，能让候选人展开回答
3. 直接给出问题，不要寒暄
4. 问题不超过 50 字
"""
    messages = [
        {"role": "system", "content": "你是专业面试官"},
        {"role": "user", "content": prompt},
    ]
    first_question = await call_llm(messages)
    return {"first_question": first_question, "resume_parsed": True}


def build_jd_directive(jd_parsed, jd_text: str) -> str:
    """根据解析后的 JD 生成确定性面试指令（无 LLM 调用）"""
    # jd_parsed 可能是 dict（内存）或 JSON 字符串（数据库），统一成 dict
    if isinstance(jd_parsed, str):
        try:
            jd_parsed = json.loads(jd_parsed)
        except (json.JSONDecodeError, TypeError):
            jd_parsed = None
    if not jd_parsed:
        return jd_text[:500] or "通用技术岗"
    
    position = jd_parsed.get("position", "通用技术岗")
    requirements = jd_parsed.get("requirements", {})
    skills = requirements.get("skills", [])[:6]  # 最多6个技能
    experience = requirements.get("experience", "不限")
    responsibilities = jd_parsed.get("responsibilities", [])[:4]  # 最多4条职责
    bonus = jd_parsed.get("bonus", [])[:3]  # 最多3条加分项
    
    directive = f"【岗位】{position}\n"
    if skills:
        directive += f"【必考技能】{', '.join(skills)}\n"
    if experience:
        directive += f"【经验要求】{experience}\n"
    if responsibilities:
        directive += f"【职责场景】{'; '.join(responsibilities)}\n"
    if bonus:
        directive += f"【加分深挖】{'; '.join(bonus)}"
    
    return directive[:500]


DB_PATH = "interviewer.db"

# 模块级连接 + 线程锁，解决 SQLite 并发写入问题
_db_lock = threading.Lock()
_db_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_db_conn.execute("PRAGMA journal_mode=WAL")  # WAL 模式支持并发读写


def init_db():
    """启动时建表（如果不存在）+ 幂等迁移"""
    with _db_lock:
        _db_conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL DEFAULT '未命名面试',
                jd_text TEXT DEFAULT '',
                resume_text TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        _db_conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        _db_conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL UNIQUE,
                report TEXT NOT NULL,
                raw TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 幂等迁移：检查并添加 jd_parsed 列
        cursor = _db_conn.execute("PRAGMA table_info(sessions)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'jd_parsed' not in columns:
            _db_conn.execute("ALTER TABLE sessions ADD COLUMN jd_parsed TEXT")
        
        _db_conn.commit()


def save_message(session_id: str, role: str, content: str):
    """存一条消息"""
    with _db_lock:
        _db_conn.execute(
            "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        _db_conn.commit()


def load_history(session_id: str, max_turns: int = 100) -> list:
    """从数据库读最近的对话历史"""
    with _db_lock:
        rows = _db_conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, max_turns * 2),
        ).fetchall()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def create_session(session_id: str, name: str = "未命名面试",
                   jd_text: str = "", resume_text: str = "",
                   jd_parsed: str | None = None):
    """创建一场面试会话"""
    with _db_lock:
        _db_conn.execute(
            "INSERT OR IGNORE INTO sessions (session_id, name, jd_text, resume_text, jd_parsed) VALUES (?, ?, ?, ?, ?)",
            (session_id, name, jd_text, resume_text, jd_parsed),
        )
        _db_conn.commit()


def list_sessions() -> list:
    """列出所有面试会话（按时间倒序）"""
    with _db_lock:
        rows = _db_conn.execute("""
            SELECT session_id, name, jd_text, created_at,
                   (SELECT COUNT(*) FROM messages WHERE messages.session_id = sessions.session_id) as msg_count
            FROM sessions
            ORDER BY created_at DESC
        """).fetchall()
    return [
        {"session_id": r[0], "name": r[1], "jd_text": r[2], "created_at": r[3], "msg_count": r[4]}
        for r in rows
    ]


def delete_session(session_id: str):
    """删除一场面试（连带它的所有消息和评分报告）"""
    with _db_lock:
        _db_conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        _db_conn.execute("DELETE FROM reports WHERE session_id = ?", (session_id,))
        _db_conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        _db_conn.commit()


def save_report(session_id: str, report: dict, raw: str):
    """保存一场面试的评分报告（含解析失败的原始回复），报告落库供历史回看/审计"""
    with _db_lock:
        _db_conn.execute(
            "INSERT INTO reports (session_id, report, raw) VALUES (?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET report = excluded.report, raw = excluded.raw",
            (session_id, json.dumps(report, ensure_ascii=False), raw[:5000]),
        )
        _db_conn.commit()


def get_report(session_id: str) -> dict | None:
    """读取一个会话的落库报告：返回 {"report": dict|None, "raw": str}；没有返回 None"""
    with _db_lock:
        row = _db_conn.execute(
            "SELECT report, raw FROM reports WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    try:
        report = json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        report = None
    return {"report": report, "raw": row[1] or ""}


def get_session_info(session_id: str) -> dict | None:
    """获取单个会话信息"""
    with _db_lock:
        row = _db_conn.execute(
            "SELECT jd_text, resume_text, jd_parsed FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    if not row:
        return None
    return {"jd_text": row[0], "resume_text": row[1], "jd_parsed": row[2]}


def format_history(history: list) -> str:
    """把消息列表格式化成可读文本，方便塞进 Prompt"""
    lines = []
    for msg in history:
        speaker = "面试官" if msg["role"] == "assistant" else "候选人"
        lines.append(f"{speaker}：{msg['content'][:200]}")
    return "\n".join(lines)


async def summarize_history(history: list) -> str:
    """用 LLM 把早期对话压缩成摘要，控制 token 数量"""
    if len(history) <= 6:
        return ""
    # 取前 N-3 轮压缩（保留最近 3 轮原文）
    early = history[:-3]
    prompt = f"""请将以下面试对话压缩成一段简洁的摘要（不超过 150 字），保留：
- 候选人提到的关键技术、项目、回答要点
- 面试官追问的核心问题
- 候选人暴露的优点和不足

对话内容：
{format_history(early)}

只输出摘要，不要其他文字。"""
    try:
        summary = await call_llm([{"role": "user", "content": prompt}], timeout=30)
        return f"【早期对话摘要】{summary}"
    except Exception as e:
        # 摘要失败时返回明确提示，而不是空字符串
        return f"【早期对话摘要生成失败：{type(e).__name__}，请基于最近对话内容继续】"


init_db()  # 服务启动时执行一次，建好表


async def extract_structured_llm(prompt: str, system: str = "你是结构化解析专家，只输出 JSON 数据。", 
                                  max_len: int = 3000) -> dict:
    """调用 LLM 提取结构化 JSON，复用 JSON 清洗逻辑"""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt[:max_len]},
    ]
    ai_reply = await call_llm(messages)
    
    # 清洗 ```json 标记
    cleaned = ai_reply.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return {"error": "AI 返回的不是合法 JSON", "raw": ai_reply}
    
    return {"parsed": data}


class ChatSessionRequest(BaseModel):
    session_id: str  # 每次面试生成一个 id，比如 "interview-001"
    message: str


@app.post("/chat-session")
async def chat_session(req: ChatSessionRequest):
    """带持久化的多轮对话：历史存进 SQLite，重启也不丢"""
    history = load_history(req.session_id)  # 从数据库读历史
    messages = add_system_prompt(history) + [{"role": "user", "content": req.message}]

    save_message(req.session_id, "user", req.message)  # 先存用户的问题

    ai_reply = await call_llm(messages)

    save_message(req.session_id, "assistant", ai_reply)  # 再存 AI 的回答
    return {"session_id": req.session_id, "ai": ai_reply}


@app.get("/sessions")
async def get_sessions():
    """获取所有面试会话列表"""
    return {"sessions": list_sessions()}


@app.delete("/sessions/{session_id}")
async def remove_session(session_id: str):
    """删除一场面试会话"""
    delete_session(session_id)
    return {"deleted": session_id}


class AnalyzeResumeRequest(BaseModel):
    resume_text: str  # 简历纯文本（来自 /parse-resume 的结果）


@app.post("/analyze-resume")
async def analyze_resume(req: AnalyzeResumeRequest):
    """让 AI 自动识别简历里的关键信息，输出结构化 JSON"""
    prompt = f"""请分析下面这份简历，提取关键信息，**只输出 JSON，不要输出任何其他文字**。

【简历内容】
{req.resume_text[:3000]}

【输出格式（严格按这个结构）】
{{
  "basic": {{
    "name": "姓名（没有就写 未知）",
    "school": "最高学历学校",
    "major": "专业",
    "degree": "学位（本科/硕士等）"
  }},
  "skills": ["技能1", "技能2", "技能3"],
  "projects": [
    {{
      "name": "项目名",
      "tech": "用到的技术",
      "achievement": "一句话成果"
    }}
  ],
  "highlights": ["简历里最值得展开的3个亮点，每个一句话"]
}}
"""
    return await extract_structured_llm(prompt, "你是简历解析专家，只输出 JSON 数据。")


class AnalyzeJdRequest(BaseModel):
    jd_text: str


@app.post("/analyze-jd")
async def analyze_jd(req: AnalyzeJdRequest):
    """解析 JD，输出结构化 JSON"""
    prompt = f"""请分析下面这份岗位描述（JD），提取关键信息，**只输出 JSON，不要输出任何其他文字**。

【岗位描述】
{req.jd_text[:2000]}

【输出格式（严格按这个结构）】
{{
  "position": "岗位名称",
  "requirements": {{
    "skills": ["技能1", "技能2", "技能3"],
    "experience": "经验要求（如：3年以上）",
    "education": "学历要求（如：本科及以上）"
  }},
  "responsibilities": ["职责1", "职责2", "职责3"],
  "bonus": ["加分项1", "加分项2"]
}}

【注意】
- skills 数组最多 6 个核心技能
- responsibilities 数组最多 5 条主要职责
- bonus 数组最多 3 个加分项
- 如果某项信息未提及，使用空数组 []
"""
    return await extract_structured_llm(prompt, "你是岗位分析专家，只输出 JSON 数据。")


class StartInterviewRequest(BaseModel):
    resume_text: str   # 简历纯文本
    jd_text: str = ""  # 岗位描述
    jd_parsed: dict | None = None  # JD 结构化解析结果（from /analyze-jd）
    session_id: str = ""  # 留空则自动生成
    candidate_name: str = "候选人"  # 候选人名字，用于称呼


@app.post("/interview/start")
async def interview_start(req: StartInterviewRequest):
    """开始一场面试：创建会话 + 生成开场白 + 生成第一个问题"""
    # 没有 session_id 就自动生成
    session_id = req.session_id or f"interview-{uuid.uuid4().hex[:8]}"

    # 存会话信息（完整简历供 Agent 搜索、JD 结构化结果供 build_jd_directive 使用）
    create_session(
        session_id=session_id,
        name=f"{req.candidate_name} - 面试",
        jd_text=req.jd_text[:1000],
        resume_text=req.resume_text,  # 存全文：搜索工具要用原文，截断会导致真实项目搜不到
        jd_parsed=json.dumps(req.jd_parsed, ensure_ascii=False) if req.jd_parsed else None,
    )

    # 让 AI 生成：开场白 + 第一个问题
    prompt = f"""你是一位专业的技术面试官，正在面试 {req.candidate_name}。
请根据候选人的简历和目标岗位，输出**开场白**和**第一个面试问题**。

【简历】
{req.resume_text[:1500]}

【目标岗位 JD】
{req.jd_text[:1000] if req.jd_text else "通用技术岗"}

【要求】
1. 开场白 1-2 句话：简单自我介绍 + 说明面试流程，语气专业友好
2. 第一个问题要紧扣简历里的项目经验或技术栈
3. 问题能展开讨论，不要是"是/否"题
4. 用以下格式输出：
开场白：<内容>
第一个问题：<内容>
"""

    messages = [
        {"role": "system", "content": "你是专业的技术面试官。"},
        {"role": "user", "content": prompt},
    ]
    ai_reply = await call_llm(messages)

    # 把 AI 回复存进数据库（开场白和第一问都算面试内容）
    save_message(session_id, "assistant", ai_reply)
    save_message(session_id, "user", "（面试开始，候选人准备回答）")

    return {
        "session_id": session_id,
        "ai_reply": ai_reply,
    }


class InterviewChatRequest(BaseModel):
    session_id: str    # 这场面试的 id
    answer: str        # 候选人刚回答的内容
    is_finished: bool = False  # 候选人是否想结束面试


@app.post("/interview/chat")
async def interview_chat(req: InterviewChatRequest):
    """继续面试：AI 根据候选人的回答进行追问"""
    # 检查 session 是否存在
    session_info = get_session_info(req.session_id)
    if not session_info:
        raise HTTPException(status_code=404, detail=f"会话 {req.session_id} 不存在")

    history = load_history(req.session_id)
    jd_text = session_info["jd_text"]
    resume_text = session_info["resume_text"]

    # 构造追问 Prompt（先不存消息，等 LLM 返回后再存）
    if req.is_finished:
        # 把用户回答加到 history 里，让 Prompt 里的历史是完整的
        history = history + [{"role": "user", "content": req.answer}]
        # 候选人想结束：输出结构化评分报告
        jd_directive = build_jd_directive(session_info.get("jd_parsed"), jd_text)
        prompt = build_report_prompt(jd_directive, format_history(history))
    else:
        # 上下文管理：对话超过 6 轮时压缩早期历史
        if len(history) > 6:
            summary = await summarize_history(history)
            history_text = summary + "\n" + format_history(history[-3:])
        else:
            history_text = format_history(history[-6:])

        jd_directive = build_jd_directive(session_info.get("jd_parsed"), jd_text)
        prompt = build_followup_prompt(jd_directive, history_text, req.answer)

    messages = [
        {"role": "system", "content": SYSTEM_INTERVIEWER},
        {"role": "user", "content": prompt},
    ]

    # 结束面试走评分模型：任务专用（评分无需工具，见 call_llm_score）
    if req.is_finished:
        ai_reply = await call_llm_score(messages)
        tool_calls_log = []
    else:
        # Agent 模式：带工具调用
        jd_parsed = session_info.get("jd_parsed")
        jd_skills = ""
        if jd_parsed:
            try:
                jd_data = json.loads(jd_parsed) if isinstance(jd_parsed, str) else jd_parsed
                jd_skills = ", ".join(jd_data.get("requirements", {}).get("skills", [])[:6])
            except (json.JSONDecodeError, AttributeError):
                pass
        
        result = await call_llm_with_tools(
            messages, tools=AGENT_TOOLS, resume_text=resume_text,
            jd_skills=jd_skills
        )
        ai_reply = await _guard_agent_reply(messages, result["content"])
        tool_calls_log = result["tool_calls_log"]

    # LLM 成功后再存消息（避免 LLM 失败时留下孤儿数据）
    save_message(req.session_id, "user", req.answer)
    save_message(req.session_id, "assistant", ai_reply)

    # 结束面试时，解析评分报告 JSON 并落库（报告来源可审计，历史回看不依赖消息解析）
    if req.is_finished:
        cleaned = ai_reply.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            report = json.loads(cleaned)
        except json.JSONDecodeError:
            report = None
        save_report(req.session_id, report if report else {"_parse_failed": True}, ai_reply)
        return {
            "session_id": req.session_id,
            "ai": ai_reply,
            "report": report,
            "tool_calls": tool_calls_log,
        }

    return {
        "session_id": req.session_id,
        "ai": ai_reply,
        "tool_calls": tool_calls_log,
    }


@app.post("/interview/chat-stream")
async def interview_chat_stream(req: InterviewChatRequest):
    """SSE 流式版本的面试追问（Agent 模式：先执行工具，再流式输出）"""
    # 检查 session 是否存在
    session_info = get_session_info(req.session_id)
    if not session_info:
        raise HTTPException(status_code=404, detail=f"会话 {req.session_id} 不存在")

    history = load_history(req.session_id)
    jd_text = session_info["jd_text"]
    resume_text = session_info["resume_text"]

    if req.is_finished:
        history = history + [{"role": "user", "content": req.answer}]
        jd_directive = build_jd_directive(session_info.get("jd_parsed"), jd_text)
        prompt = build_report_prompt(jd_directive, format_history(history))
    else:
        # 上下文管理：对话超过 6 轮时压缩早期历史
        if len(history) > 6:
            summary = await summarize_history(history)
            history_text = summary + "\n" + format_history(history[-3:])
        else:
            history_text = format_history(history[-6:])

        jd_directive = build_jd_directive(session_info.get("jd_parsed"), jd_text)
        prompt = build_followup_prompt(jd_directive, history_text, req.answer)

    # 结束面试走评分模型；否则 Agent 模式带工具调用
    if req.is_finished:
        agent_messages = [
            {"role": "system", "content": (
                "你是一位资深技术面试官。你的目标是通过追问判断候选人的真实技术水平。"
                "风格：专业、直接、不刁难。不要说'很好的回答'之类的客套话。"
                "铁律：只能基于候选人的实际回答和简历内容提问，不能编造候选人没有提到的细节。搜索未命中时不得断言某项目/技术不存在，必要时可向候选人求证。"
            )},
            {"role": "user", "content": prompt},
        ]
        final_reply = await call_llm_score(agent_messages)
        tool_calls_log = []
    else:
        agent_messages = [
            {"role": "system", "content": (
                "你是一位资深技术面试官。你的目标是通过追问判断候选人的真实技术水平。"
                "风格：专业、直接、不刁难。不要说'很好的回答'之类的客套话。"
                "铁律：只能基于候选人的实际回答和简历内容提问，不能编造候选人没有提到的细节。搜索未命中时不得断言某项目/技术不存在，必要时可向候选人求证。"
            )},
            {"role": "user", "content": prompt},
        ]
        
        # 提取 JD 技能列表
        jd_parsed = session_info.get("jd_parsed")
        jd_skills = ""
        if jd_parsed:
            try:
                jd_data = json.loads(jd_parsed) if isinstance(jd_parsed, str) else jd_parsed
                jd_skills = ", ".join(jd_data.get("requirements", {}).get("skills", [])[:6])
            except (json.JSONDecodeError, AttributeError):
                pass
        
        agent_result = await call_llm_with_tools(
            agent_messages, tools=AGENT_TOOLS, resume_text=resume_text,
            jd_skills=jd_skills
        )
        final_reply = await _guard_agent_reply(agent_messages, agent_result["content"])
        tool_calls_log = agent_result["tool_calls_log"]

    # LLM 成功后再存消息
    save_message(req.session_id, "user", req.answer)
    save_message(req.session_id, "assistant", final_reply)

    # 结束面试时：解析评分报告 JSON 并落库
    if req.is_finished:
        cleaned = final_reply.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            report = json.loads(cleaned)
        except json.JSONDecodeError:
            report = None
        save_report(req.session_id, report if report else {"_parse_failed": True}, final_reply)

    # 流式推送给前端（按词推送，比逐字符高效）
    async def generate():
        words = list(final_reply)  # 中文按字分割
        chunk_size = 3  # 每次推 3 个字
        for i in range(0, len(words), chunk_size):
            chunk = "".join(words[i:i + chunk_size])
            yield f"data: {json.dumps({'text': chunk})}\n\n"
        yield f"data: {json.dumps({'done': True, 'full_reply': final_reply, 'tool_calls': tool_calls_log})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取某场面试的所有消息"""
    history = load_history(session_id, max_turns=100)
    return {"session_id": session_id, "messages": history}


@app.get("/sessions/{session_id}/report")
async def get_session_report(session_id: str):
    """读取落库的评分报告（用于历史回看，避免再从消息里猜 JSON）"""
    result = get_report(session_id)
    if result is None:
        return {"session_id": session_id, "report": None, "raw": None}
    return {"session_id": session_id, **result}
