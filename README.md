# 🎙️ AI 模拟面试官

> 上传简历，AI 扮演面试官进行多轮追问，基于对话生成结构化评分报告。不是简单的 API 调用——面试官是一个 Agent，会主动搜索简历、评估回答、决定追问还是推进。

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org)
[![Ant Design](https://img.shields.io/badge/Ant%20Design-5-blue.svg)](https://ant.design)
[![MiMo](https://img.shields.io/badge/Xiaomi%20MiMo-V2.5--Pro-orange.svg)](https://mimo.mi.com)

---

## ✨ 它能做什么

```
你上传简历 → AI 读懂你的经历
你点击开始 → AI 生成开场白 + 第一个针对性问题
你回答问题 → AI 根据你的回答动态追问（不是固定题库）
你结束面试 → AI 输出三维评分报告 + 雷达图
```

### 核心特性

| 特性 | 说明 |
|------|------|
| **Agent 架构** | 面试官不是裸 LLM，而是一个有工具的 Agent（详见下方架构图） |
| **动态追问** | 根据候选人回答实时追问——有漏洞就深挖，回答好就推进 |
| **简历搜索工具** | 候选人提到某个项目时，Agent 自动搜索简历中的对应细节再追问 |
| **JD 结构化定制** | 上传/粘贴 JD → AI 解析为岗位/技能/职责/加分项，生成确定性面试指令，全程围绕 JD 必考技能追问 |
| **结构化评分** | 技术深度 / 表达能力 / 逻辑性三维评分 + 雷达图可视化 |
| **流式输出** | SSE 逐字渲染，体验流畅 |
| **上下文管理** | 对话超过 6 轮自动压缩早期历史为摘要，控制 token 消耗 |
| **历史回看** | 侧边栏查看所有历史面试，点击恢复对话或查看评分报告 |
| **移动端适配** | 响应式布局，侧边栏可折叠 |

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Next.js + Ant Design)            │
│  上传简历/JD → 面试对话 → 评分报告 + 雷达图                  │
│  侧边栏：历史会话 / 搜索 / 删除                             │
└────────────────────────┬────────────────────────────────┘
                         │ SSE + REST API
┌────────────────────────┴────────────────────────────────┐
│                 后端 (FastAPI + SQLite)                    │
│                                                          │
│  ┌──────────────────────────────────────────────┐       │
│  │           Agent 工具调用层                      │       │
│  │                                                │       │
│  │  候选人回答 → LLM 决策 → 调用工具 → 生成回复     │       │
│  │                                                │       │
│  │  工具：                                        │       │
│  │  ├── search_resume(keyword)  搜索简历细节       │       │
│  │  ├── evaluate_answer(answer) 评估回答质量       │       │
│  │  ├── get_interview_plan(topic) 获取下一阶段     │       │
│  │  └── generate_report(history) 生成评分报告      │       │
│  └──────────────────────────────────────────────┘       │
│                          │                               │
│  ┌───────────────────────┴───────────────────────┐      │
│  │  LLM: 双模型 MiMo-V2.5-Pro(追问) + DeepSeek(评分) │  │
│  │  上下文管理：对话摘要压缩 (超过6轮自动触发)       │      │
│  │  JD 指令：build_jd_directive 确定性生成(无LLM)   │      │
│  └───────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────┘
```

### Agent 工作流程

```
候选人："我做过秒杀系统，用 FastAPI + Redis"
    │
    ▼
LLM 分析：提到了"秒杀系统"、"FastAPI"、"Redis"
    │
    ▼
调用 search_resume("秒杀")
    │
    ▼
返回：找到简历中 "电商秒杀系统 - FastAPI + Redis 预减库存，QPS 200→3000+"
    │
    ▼
LLM 基于简历细节生成追问：
"你提到用 Redis 预减库存解决超卖问题，能详细讲讲这个机制是如何实现的吗？"

—— 若回答已充分，则改调 get_interview_plan 按 JD 技能优先级推进下一话题
```

### 追问决策树

```
搜索命中简历细节 → 基于细节追问（问实现原理、踩过的坑、量化数据）
搜索未命中       → 基于回答本身追问（问思路、权衡、替代方案）
回答已经很充分   → 调用 get_interview_plan 按 JD 必考技能推进下一阶段
候选人不了解     → 不追问该点，换一个方向
```

---

## 🛠️ 技术栈

| 层 | 技术 | 选型理由 |
|----|------|---------|
| 后端 | Python + FastAPI | 异步框架，原生 SSE 支持 |
| 前端 | Next.js 16 + TypeScript + Ant Design | App Router，组件化 UI |
| LLM | 双模型：MiMo-V2.5-Pro（追问）+ DeepSeek-V4（评分） | 追问便宜、评分判分准（30场评估验证） |
| 数据库 | SQLite + WAL 模式 | 零运维，并发读写安全，jd_parsed 列幂等迁移 |
| AI 集成 | 裸 API + Function Calling | 不套 LangChain，展示底层能力 |

### 为什么不用 LangChain？

裸 API + 自写 Prompt 更可控、更好调试，也更能展示对 LLM 底层的理解。面试时能讲清楚每一层的设计决策。

### 为什么用 Agent 而不是直接调 LLM？

直接调 LLM = 把整份简历塞进 Prompt，浪费 token，且无法根据对话动态获取信息。Agent 架构让 LLM 自己决定什么时候需要查简历、什么时候直接回答，更接近真实面试官的工作方式。

---

## 📊 评估结果

跑了 **30 场**自动化评估（10 份简历 × 3 种回答策略：优秀/一般/差，LLM 扮演候选人）：

| 策略 | 场数 | 技术 | 表达 | 逻辑 | 均分 |
|------|------|------|------|------|------|
| 优秀 | 10 | 60.8 | 51.0 | 56.5 | **56.1** |
| 一般 | 10 | 47.5 | 53.0 | 48.5 | **49.7** |
| 差 | 10 | 16.5 | 27.0 | 18.5 | **20.7** |

**优秀-差区分度：35.4 分（≥20 通过）| 0 失败 | 人工盲评 30 场对话转录：分层方向与 AI 一致**

> 双模型：追问 MiMo-V2.5-Pro + 评分 DeepSeek（v1 证明 qwen/DeepSeek 系判分更准）。评分 Prompt 铁律：只看面试对话表现，不能凭简历推测。详见 `docs/evaluation_report.md`

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- LLM API Key（支持 [Xiaomi MiMo](https://mimo.mi.com)、DeepSeek 等 OpenAI 兼容 API）

### 1. 后端

```bash
cd ai-interviewer

python -m venv venv
.\venv\Scripts\activate     # Windows
# source venv/bin/activate  # macOS/Linux

pip install fastapi uvicorn httpx python-dotenv PyPDF2 python-docx

# 创建 .env 文件
echo LLM_API_KEY=你的MiMo密钥 > .env
echo DEEPSEEK_API_KEY=你的DeepSeek密钥 >> .env

uvicorn main:app --reload --port 8000
```

后端：`http://127.0.0.1:8000` | API 文档：`http://127.0.0.1:8000/docs`

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

前端：`http://localhost:3000`

### 3. 使用

1. 打开 `http://localhost:3000`
2. 上传简历（PDF/Word）+ 上传/粘贴 JD（PDF/Word/txt/md，可选）
3. JD 自动解析为岗位/技能/职责/加分项卡片（可折叠）
4. 填写名字 → 点击“开始面试”
5. 回答 AI 的问题，AI 会围绕 JD 必考技能动态追问
6. 点击“结束面试”，查看三维评分报告 + 雷达图

---

## 📁 项目结构

```
ai-interviewer/
├── main.py              # FastAPI 主程序（15 个接口 + 4 工具 Agent + JD 指令）
├── .env                 # API Key（不提交）
├── interviewer.db       # SQLite 数据库（不提交）
├── test_resumes/        # 10 份测试简历
├── eval/                # 评估体系（30 场自动化测试）
│   ├── run_evaluation.py
│   ├── results_v3_final.json
│   ├── human_scores.csv
│   └── human_scoring/   # 30 场对话转录（盲评）
├── tests/               # pytest 测试集（49 用例）
├── test.http            # 接口测试集
├── .gitignore
└── README.md

frontend/                # Next.js 前端
├── src/app/
│   ├── page.tsx         # 主页面（上传/对话/报告/侧边栏/JD卡片）
│   ├── api.ts           # API 调用层（含 SSE 流式 + JdAnalysis 类型）
│   └── layout.tsx
├── next.config.ts       # API 代理配置
└── package.json
```

---

## 📡 API 接口

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/interview/start` | 开始面试（创建会话 + 生成开场白，支持 `jd_parsed`） |
| POST | `/interview/chat` | 面试追问 / 结束评分（Agent 模式，4 工具） |
| POST | `/interview/chat-stream` | SSE 流式版追问 |
| POST | `/parse-resume` | 简历/JD 文件解析（PDF/Word/txt/md） |
| POST | `/analyze-resume` | 简历 AI 识别（结构化 JSON） |
| POST | `/analyze-jd` | JD AI 识别（岗位/技能/经验/职责/加分项） |
| GET | `/sessions` | 会话列表 |
| GET | `/sessions/{id}/messages` | 会话消息 |
| DELETE | `/sessions/{id}` | 删除会话 |
| GET | `/` | 服务状态 |

---

## 🎯 Prompt 设计

### 追问 Prompt（核心）

```
system: 你是资深技术面试官。风格：专业、直接、不刁难。
        铁律：只能基于候选人实际回答和简历提问，不能编造。

user:   【岗位面试指令】build_jd_directive(jd_parsed) → 【岗位】+【必考技能】+【职责场景】...
        【面试历史】...（超过6轮自动压缩为摘要）
        【候选人本轮回答】...
        【决策树】命中→追问细节 / 未命中→追问思路 / 充分→调 get_interview_plan 推进 / 不了解→换方向
        【追问风格】引用原话关键词、问"怎么做的"、一次一问
```

### 评分报告 Prompt

```
面试已结束。输出 JSON 评分报告。
【铁律】评分只看面试对话表现，不能凭简历推测。
【评分尺度】85-100 有原理+数据+复盘 / 70-85 扎实 / 55-70 一般 / 40-55 简单 / 20-40 含糊 / 0-20 无有效内容
{"score": {"technical": 0, "communication": 0, "logic": 0},
 "strengths": [...], "improvements": [...], "overall_comment": "..."}
```

---

## 🔧 关键设计决策

| 决策 | 原因 | 面试话术 |
|------|------|---------|
| 裸 API 而非 LangChain | 更可控，展示底层能力 | "我直接调 API + 自写 Prompt，不依赖框架" |
| Agent 而非直接调 LLM | 按需检索，节省 token | "面试官是 Agent，会主动搜索简历再追问" |
| 双模型（MiMo追问 + DeepSeek评分） | 追问便宜、评分准 | "追问用 MiMo 省钱，评分用 DeepSeek 判分更准，30场评估验证" |
| JD 确定性指令 | 一次解析后纯拼接，无额外 LLM 调用，稳定≤500字 | "jd_parsed 解析一次，每轮用代码拼接指令，不再花钱" |
| SSE 而非 WebSocket | 单向推送够用，实现简单 | "流式输出用 SSE，比 WebSocket 轻量" |
| SQLite WAL 模式 | 零运维，并发安全 | "WAL 模式解决 SQLite 并发写入问题" |
| 对话摘要压缩 | 控制 token，保留关键信息 | "超过 6 轮自动压缩早期历史" |

---

## 📝 开发日志

| 阶段 | 内容 |
|------|------|
| Day 1-2 | 环境搭建 + 多轮对话 + 简历解析 + SQLite 持久化 |
| Day 3 | 会话系统 + 追问机制 + 评分报告 + Prompt 调优 |
| Day 4 | Next.js 前端 + 流式输出 + 雷达图 + 历史会话 |
| Day 5 | 交互打磨 + 响应式 + 删除确认 + 搜索 |
| 升级 | Agent 4 工具 + 双模型 30 场评估 + 上下文管理 + Bug 修复 |
| 2026-08-29 | JD 结构化定制：/analyze-jd + jd_parsed 持久化 + 确定性面试指令 + 前端 JD 卡片 |

---

## 📄 License

MIT
