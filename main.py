import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import sqlite3

# 加载 .env 文件里的环境变量
load_dotenv()

# 从环境变量读取 API Key
QWEN_API_KEY = os.getenv("QWEN_API_KEY")

# 检查 Key 是否存在
if not QWEN_API_KEY:
    raise ValueError("未找到 QWEN_API_KEY，请检查 .env 文件")

app = FastAPI()

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
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {QWEN_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "qwen-plus",
                "messages": [{"role": "user", "content": message}]
            },
            timeout=120.0
        )
        result = response.json()
        ai_reply = result["choices"][0]["message"]["content"]
        return {"user": message, "ai": ai_reply}
    

class ChatRequest(BaseModel):
    message: str
    history: list = []  # 多轮对话历史，默认为空

@app.post("/chat-with-history")
async def chat_with_history(req: ChatRequest):
    """支持多轮对话的接口"""
    messages = req.history + [{"role": "user", "content": req.message}]
    
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
            timeout=120.0
        )
        result = response.json()
        ai_reply = result["choices"][0]["message"]["content"]
        return {
            "user": req.message,
            "ai": ai_reply,
            "history": messages + [{"role": "assistant", "content": ai_reply}]
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
            timeout=120.0
        )
        result = response.json()
        ai_reply = result["choices"][0]["message"]["content"]
        return {
            "user": req.message,
            "ai": ai_reply,
            "role": req.role
        }
from fastapi import UploadFile, File
from PyPDF2 import PdfReader
from docx import Document
import io

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
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {QWEN_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "qwen-plus",
                "messages": [
                    {"role": "system", "content": "你是专业面试官"},
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=30.0
        )
        result = response.json()
        first_question = result["choices"][0]["message"]["content"]
        return {
            "first_question": first_question,
            "resume_parsed": True
        }
DB_PATH = "interviewer.db"

def init_db():
    """启动时建表（如果不存在）"""
    conn = sqlite3.connect(DB_PATH)
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

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {QWEN_API_KEY}",
                "Content-Type": "application/json"
            },
            json={"model": "qwen-plus", "messages": messages},
            timeout=30.0
        )
        result = response.json()
        ai_reply = result["choices"][0]["message"]["content"]

    save_message(req.session_id, "assistant", ai_reply)  # 再存 AI 的回答
    return {"session_id": req.session_id, "ai": ai_reply}