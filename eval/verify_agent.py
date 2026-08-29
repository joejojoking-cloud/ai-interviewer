"""
Agent 链路联调脚本
==================
验证追问 Agent 的工具调用链路（search_resume / evaluate_answer / get_interview_plan）。
候选人也由 LLM 扮演（资深人设），对话至少跑 4 轮，确保走到
"话题问透 → get_interview_plan 推进"的真实场景。

用法：
    python eval/verify_agent.py            # 用第一份简历跑 4 轮
    python eval/verify_agent.py --resume 张伟_后端开发.docx --rounds 5

注意：真实调用 LLM、消耗额度；用内存库，不污染任何数据库。
"""
import argparse
import asyncio
import json
import sqlite3
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

PERSONA = (
    "你是一位经验丰富的资深候选人（8 年工龄），应聘技术岗。"
    "回答风格：直接对题，技术细节扎实，有架构设计、具体数据和踩坑复盘，能主动展开。回答 150-250 字。"
)


def setup_memory_db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    main._db_conn = conn
    main._db_lock = threading.Lock()
    main.init_db()
    return conn


async def gen_answer(resume: str, interviewer_msg: str) -> str:
    prompt = f"【我的简历】\n{resume[:1500]}\n\n【面试官对我说】\n{interviewer_msg}\n\n请以你的人物设定直接作答（只输出回答正文）。"
    return await main.call_llm_score([
        {"role": "system", "content": PERSONA},
        {"role": "user", "content": prompt},
    ], timeout=60)


async def run(resume_name: str, rounds: int):
    if resume_name:
        rf = Path(main.__file__).parent.joinpath("test_resumes", resume_name)
    else:
        rf = min(Path(main.__file__).parent.joinpath("test_resumes").glob("*.docx"), key=lambda p: p.name)
    resume = main.parse_docx(rf.read_bytes())

    start = await main.interview_start(
        main.StartInterviewRequest(resume_text=resume, jd_text="技术岗",
                                   session_id="smoke-agent", candidate_name="联调")
    )
    sid = start["session_id"]
    print("== 开场 ==")
    print(start["ai_reply"][:300])

    plan_called = 0
    for i in range(rounds):
        history = main.load_history(sid)
        msg = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
        answer = await gen_answer(resume, msg)
        print("\n---- 候选人第%d轮 ----" % (i + 1), answer[:200])
        r = await main.interview_chat(main.InterviewChatRequest(session_id=sid, answer=answer))
        tools = [t["tool"] for t in r.get("tool_calls", [])]
        plan_called += tools.count("get_interview_plan")
        print(f">> 第{i + 1}轮 tools:", tools)
        print("面试官:", r["ai"][:200])

    print(f"\n=== 结论：get_interview_plan 在 {rounds} 轮中被调用 {plan_called} 次 ===")
    print("Agent 工具链路可用" if plan_called >= 1 else "注意：未触发 plan（可增加 --rounds 轮数或更换简历重试）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", default="", help="指定简历文件名（test_resumes 下）")
    parser.add_argument("--rounds", type=int, default=4, help="对话轮数（默认 4）")
    args = parser.parse_args()

    setup_memory_db()
    asyncio.run(run(args.resume, args.rounds))
