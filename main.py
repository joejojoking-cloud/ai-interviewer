import os
import io
import json
import uuid
import sqlite3
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from PyPDF2 import PdfReader
from docx import Document

# 加载 .env 文件里的环境变量
load_dotenv()

# 从环境变量读取 API Key
QWEN_API_KEY = os.getenv("QWEN_API_KEY")

# 检查 Key 是否存在
if not QWEN_API_KEY:
    raise ValueError("未找到 QWEN_API_KEY，请检查 .env 文件")


async def call_llm(messages: list, timeout: float = 120.0) -> str:
    """
    调用通义千问的公共函数。所有接口都复用这一个。
    传入完整的 messages 列表，返回 AI 的文字回复。
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {QWEN_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "qwen-plus",
                "messages": messages
            },
            timeout=timeout
        )
        result = response.json()
        # 注意：这里加了错误处理，防止返回异常时报"看不懂"的错误
        if "choices" not in result:
            raise ValueError(f"通义千问返回异常: {result}")
        return result["choices"][0]["message"]["content"]


app = FastAPI()

# 允许前端跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        text += page.extract_text() + "\n"
    return text.strip()


def parse_docx(content: bytes) -> str:
    """解析 Word 文件，提取文本"""
    doc = Document(io.BytesIO(content))
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text.strip()


@app.post("/parse-resume")
async def parse_resume(file: UploadFile = File(...)):
    """上传简历（PDF 或 Word），返回纯文本"""
    # 读取文件内容
    content = await file.read()

    # 根据文件类型选解析器
    if file.filename.endswith(".pdf"):
        text = parse_pdf(content)
    elif file.filename.endswith(".docx"):
        text = parse_docx(content)
    else:
        return {"error": "只支持 PDF 和 Word 文件"}

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


DB_PATH = "interviewer.db"


def init_db():
    """启动时建表（如果不存在）"""
    conn = sqlite3.connect(DB_PATH)

    # 会话表：记录每场面试的基本信息
    conn.execute("""
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

    # 消息表：记录每场面试里的对话（Day 2 的）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_message(session_id: str, role: str, content: str):
    """存一条消息"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content),
    )
    conn.commit()
    conn.close()


def load_history(session_id: str, max_turns: int = 10) -> list:
    """从数据库读最近的对话历史"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
        (session_id, max_turns * 2),
    ).fetchall()
    conn.close()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def create_session(session_id: str, name: str = "未命名面试",
                   jd_text: str = "", resume_text: str = ""):
    """创建一场面试会话"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO sessions (session_id, name, jd_text, resume_text) VALUES (?, ?, ?, ?)",
        (session_id, name, jd_text, resume_text),
    )
    conn.commit()
    conn.close()


def list_sessions() -> list:
    """列出所有面试会话（按时间倒序）"""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT session_id, name, jd_text, created_at,
               (SELECT COUNT(*) FROM messages WHERE messages.session_id = sessions.session_id) as msg_count
        FROM sessions
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return [
        {"session_id": r[0], "name": r[1], "jd_text": r[2], "created_at": r[3], "msg_count": r[4]}
        for r in rows
    ]


def delete_session(session_id: str):
    """删除一场面试（连带它的所有消息）"""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    conn.commit()
    conn.close()


def format_history(history: list) -> str:
    """把消息列表格式化成可读文本，方便塞进 Prompt"""
    lines = []
    for msg in history:
        speaker = "面试官" if msg["role"] == "assistant" else "候选人"
        lines.append(f"{speaker}：{msg['content'][:200]}")
    return "\n".join(lines)


init_db()  # 服务启动时执行一次，建好表


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

    messages = [
        {"role": "system", "content": "你是简历解析专家，只输出 JSON 数据。"},
        {"role": "user", "content": prompt},
    ]
    ai_reply = await call_llm(messages)

    # 防止 AI 输出 JSON 时带了多余的 ```json 标记
    cleaned = ai_reply.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # 解析失败就原样返回文本，方便排查
        return {"error": "AI 返回的不是合法 JSON", "raw": ai_reply}

    return {"parsed": data}


class StartInterviewRequest(BaseModel):
    resume_text: str   # 简历纯文本
    jd_text: str = ""  # 岗位描述
    session_id: str = ""  # 留空则自动生成
    candidate_name: str = "候选人"  # 候选人名字，用于称呼


@app.post("/interview/start")
async def interview_start(req: StartInterviewRequest):
    """开始一场面试：创建会话 + 生成开场白 + 生成第一个问题"""
    # 没有 session_id 就自动生成
    session_id = req.session_id or f"interview-{uuid.uuid4().hex[:8]}"

    # 存会话信息（简历、JD 都存进 sessions 表）
    create_session(
        session_id=session_id,
        name=f"{req.candidate_name} - 面试",
        jd_text=req.jd_text[:1000],
        resume_text=req.resume_text[:3000],
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
    # 从数据库读出这场面试的全部历史 + 简历 + JD
    history = load_history(req.session_id)
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT jd_text, resume_text FROM sessions WHERE session_id = ?",
        (req.session_id,),
    ).fetchone()
    conn.close()

    jd_text = row[0] if row else ""
    resume_text = row[1] if row else ""

    # 先把候选人这轮的答案存进去
    save_message(req.session_id, "user", req.answer)

    # 构造追问 Prompt
    if req.is_finished:
        # 候选人想结束：输出结构化评分报告
        prompt = f"""面试已结束。请根据整场对话输出一份 JSON 面试报告：

【岗位 JD】{jd_text[:500]}
【面试历史】
{format_history(history) + chr(10) + '候选人最后回答：' + req.answer}

【输出格式】
{{
  "score": {{
    "technical": 0,
    "communication": 0,
    "logic": 0
  }},
  "strengths": ["优点1", "优点2", "优点3"],
  "improvements": ["不足1", "不足2"],
  "overall_comment": "综合评语（3句话）"
}}
评分都是 0-100 的整数。只输出 JSON，不要输出其他文字。"""
    else:
        prompt = f"""你是面试官。候选人刚回答了你的问题，请根据他的回答**追问**。

【岗位 JD】{jd_text[:500]}
【候选人简历】
{resume_text[:1200]}

【面试历史（最近几轮）】
{format_history(history[-6:])}

【候选人本轮回答】
{req.answer}

【追问要求】
1. 如果回答里有技术漏洞、含糊、没展开的细节 → 追着这个点问，问细节
2. 如果回答很完整 → 推进到下一个相关问题（基于简历/JD）
3. 问题要具体、有追问感，体现你真的听了他刚才说的话
4. 只输出追问内容，不超过 80 字，不要寒暄"""

    messages = [
        {"role": "system", "content": "你是专业的技术面试官，追问犀利但友好。"},
        {"role": "user", "content": prompt},
    ]
    ai_reply = await call_llm(messages)

    save_message(req.session_id, "assistant", ai_reply)

    # 结束面试时，解析评分报告 JSON
    if req.is_finished:
        cleaned = ai_reply.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            report = json.loads(cleaned)
        except json.JSONDecodeError:
            report = None
        return {
            "session_id": req.session_id,
            "ai": ai_reply,
            "report": report,
        }

    return {"session_id": req.session_id, "ai": ai_reply}
