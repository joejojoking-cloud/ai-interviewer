"""
AI 面试官 自动评估脚本（v3：LLM 扮演候选人）
==========================================
方法论升级：不再用固定模板回答。候选人由 LLM 按三种水平人设扮演，
针对面试官**真实提问**动态作答——这样评分模型能看到对齐的回答，
才能测出真实的区分度（v2 教训：固定答案 vs 个性化追问 = 答非所问）。

流程：简历 → 面试官开场(含第一问) → 候选人生成回答1 → 面试官追问 → 回答2 → 结束评分
每场 6 次 LLM 调用，30 场约 180 次。

用法：
    python eval/run_evaluation.py            # 全量 30 场
    python eval/run_evaluation.py --limit 1  # 只跑前 1 份简历（3 场）
    python eval/run_evaluation.py --resume   # 跳过已有评分的场次

注意：真实调用 LLM API，消耗额度。结果写入 eval/results.json，eval.db 隔离。
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
from experience_metrics import experience_summary  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")

# 候选人三种水平人设（生成回答时的 system prompt）
PERSONAS = {
    "优秀": (
        "你是一位经验丰富的资深候选人（8 年工龄），应聘技术岗。"
        "回答风格：直接对题，技术细节扎实，有架构设计、具体数据和踩坑复盘，"
        "能主动展开追问的深度。回答 150-250 字。"
    ),
    "一般": (
        "你是一位普通候选人（2 年工龄），应聘技术岗。"
        "回答风格：能正常作答但有深度有限，知道基本概念，数据说不全，"
        "遇到不会的会含糊带过。回答 80-150 字。"
    ),
    "差": (
        "你是一位基础较弱的候选人（应届/转行），应聘技术岗。"
        "回答风格：大部分内容不熟悉，只能用模糊词汇（大概、应该、我记得），"
        "回避原理性问题，直接承认不了解。回答 40-80 字。"
    ),
}

ANALYSIS_ROUNDS = 2  # 每场回答轮数（默认 2；调大可以让面试官更可能走到"话题问透→get_interview_plan 推进"）


def setup_eval_db():
    """把 main 的数据库连接切到 eval.db（旧库备份而不是删除）"""
    db_path = Path(__file__).resolve().parent / "eval.db"
    if db_path.exists():
        import time
        backup = db_path.with_suffix(f".bak.{int(time.time())}")
        db_path.rename(backup)
        print(f"[setup] 旧 eval.db 已备份为 {backup.name}")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    main._db_conn = conn
    main._db_lock = threading.Lock()
    main.init_db()
    return conn


async def gen_candidate_answer(resume_text: str, interviewer_msg: str, strategy: str) -> str:
    """候选人角色扮演：根据面试官的话生成回答（走 DeepSeek 评分模型通道，不出工具）"""
    prompt = f"""【我的简历】
{resume_text[:1500]}

【面试官对我说】
{interviewer_msg}

请以你的人物设定直接作答（只输出回答正文，不要任何前缀）。"""
    msg = [
        {"role": "system", "content": PERSONAS[strategy]},
        {"role": "user", "content": prompt},
    ]
    try:
        return await main.call_llm_score(msg, timeout=60)
    except Exception as e:
        return f"（候选人生成失败：{type(e).__name__}）"


async def _run_one_interview(resume_text: str, strategy: str, session_id: str, rounds: int) -> dict:
    """跑一场面试：开场 + N 轮（候选人作答 → 面试官追问）+ 结束评分"""
    try:
        start = await main.interview_start(
            main.StartInterviewRequest(
                resume_text=resume_text, jd_text="技术岗",
                session_id=session_id, candidate_name="评估候选人",
            )
        )
        sid = start["session_id"]
        tool_stats = {"search_resume": 0, "evaluate_answer": 0, "generate_report": 0}
        dialogue = []

        for _ in range(rounds):
            # 面试官说了什么（开场白或上轮追问）
            history = main.load_history(sid)
            msg = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), "")
            # 候选人生成回答
            answer = await gen_candidate_answer(resume_text, msg, strategy)
            dialogue.append(answer)
            # 面试官追问
            result = await main.interview_chat(
                main.InterviewChatRequest(session_id=sid, answer=answer)
            )
            for tc in result.get("tool_calls", []):
                if tc["tool"] in tool_stats:
                    tool_stats[tc["tool"]] += 1

        finish = await main.interview_chat(
            main.InterviewChatRequest(session_id=sid, answer="我答完了，可以结束了。", is_finished=True)
        )
        for tc in finish.get("tool_calls", []):
            if tc["tool"] in tool_stats:
                tool_stats[tc["tool"]] += 1

        base = {"resume": "", "strategy": strategy, "tool_calls": tool_stats, "answers": dialogue}
        report = finish.get("report")
        if not report:
            base["error"] = "评分报告 JSON 解析失败"
            base["raw"] = finish.get("ai", "")[:200]
            return base

        return {
            **base,
            "scores": report.get("score", {}),
            "strengths": report.get("strengths", []),
            "improvements": report.get("improvements", []),
            "overall_comment": report.get("overall_comment", ""),
            "experience": collect_experience(sid, dialogue),
        }
    except Exception as e:
        return {"resume": "", "strategy": strategy, "error": f"{type(e).__name__}: {e}"}


def run_one_interview(resume_text: str, strategy: str, session_id: str, rounds: int = ANALYSIS_ROUNDS) -> dict:
    """同步包装，内部 asyncio 跑 async 接口"""
    return asyncio.run(_run_one_interview(resume_text, strategy, session_id, rounds))


def collect_experience(session_id: str, answers: list[str]) -> dict:
    """从会话消息里抽取'面试官提问'序列，与候选人回答一起算体感代理指标。

    - 提问：assistant 消息，剔除评分报告 JSON（含 "score"）
    - 回答：user 消息，剔除开场占位和"结束面试"指令（前者是平台注入，后者不体现回答质量）
    """
    msgs = main.load_history(session_id)
    questions = [
        m["content"] for m in msgs
        if m["role"] == "assistant"
        and '"score"' not in m["content"]
    ]
    real_answers = [
        m["content"] for m in msgs
        if m["role"] == "user"
        and m["content"] != "（面试开始，候选人准备回答）"
        and "答完了" not in m["content"]
    ]
    return experience_summary(questions, real_answers)


def export_transcript(session_id: str, tag: str, strategy: str):
    """把一场面试的完整对话导出为 txt（人工评分盲评用，不附带 AI 分数）"""
    msgs = main.load_history(session_id)
    if not msgs:
        return
    # 盲评：过滤掉评分报告 JSON（结束消息），避免评分锚定
    msgs = [m for m in msgs if not (m["role"] == "assistant" and '"score"' in m["content"])]
    out_dir = Path(__file__).resolve().parent / "human_scoring"
    out_dir.mkdir(exist_ok=True)
    lines = [f"# 面试记录", f"# 简历：{tag}    策略：{strategy}", f"# 会话：{session_id}", "#", "# 说明：面试官为 AI，候选人为 LLM 扮演的应聘者", "#" "=" * 30, ""]
    for m in msgs:
        who = "面试官" if m["role"] == "assistant" else "候选人"
        lines.append(f"[{who}]")
        lines.append(m["content"])
        lines.append("")
    out = out_dir / f"{session_id}.txt"
    out.write_text("\n".join(lines), encoding="utf-8")


def save_results(results):
    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def main_run(limit: int, resume: bool, rounds: int = ANALYSIS_ROUNDS, workers: int = 3):
    resume_files = sorted(Path(main.__file__).parent.joinpath("test_resumes").glob("*.docx"))
    if not resume_files:
        print("test_resumes 下没有简历")
        sys.exit(1)

    results = []
    done_ids = set()
    if resume:
        result_path = Path(__file__).resolve().parent / "results.json"
        if result_path.exists():
            results = json.loads(result_path.read_text(encoding="utf-8"))
            done_ids = {r["session_id"] for r in results if "scores" in r}
            print(f"[resume] 已加载 {len(results)} 场，跳过 {len(done_ids)} 场已完成")
        else:
            print("[resume] 没有找到 results.json，按全量跑")

    planned = len(resume_files[:limit] if limit else resume_files) * 3
    tasks = []
    for rf in resume_files[:limit] if limit else resume_files:
        text = main.parse_docx(rf.read_bytes())
        tag = rf.stem
        for strategy in ["优秀", "一般", "差"]:
            session_id = f"eval-{tag}-{strategy}"
            if resume and session_id in done_ids:
                continue
            tasks.append({"tag": tag, "strategy": strategy, "text": text, "session_id": session_id})

    if not tasks:
        print("没有需要跑的场次（全部已完成）")
        return results

    batch = list(results)

    async def run_batch():
        sem = asyncio.Semaphore(workers)
        counter = {"n": 0}

        async def do(work):
            async with sem:
                counter["n"] += 1
                idx = counter["n"]
                print(f"[{idx}/{len(tasks)}] {work['tag']} / {work['strategy']}（并发起跑）", flush=True)
                r = await _run_one_interview(work["text"], work["strategy"], work["session_id"], rounds)
                r["session_id"] = work["session_id"]
                r["resume"] = work["tag"]
                batch.append(r)
                # 每场完成：写结果 + 导出对话转录（与 db 解耦，中断不丢）
                save_results(batch)
                export_transcript(work["session_id"], work["tag"], work["strategy"])
                scores = r.get("scores", {})
                if scores:
                    exp = r.get("experience", {})
                    print(
                        f"    -> 技术 {scores.get('technical', '-')} | 表达 {scores.get('communication', '-')} | 逻辑 {scores.get('logic', '-')}"
                        f" | 重复提问率 {exp.get('repeated_question_rate', '-')} | 追问引用率 {exp.get('follower_overlap_rate', '-')}"
                        f" | 材料泄漏 {exp.get('leaked_material_hits', '-')}",
                        flush=True,
                    )
                else:
                    print(f"    -> 失败: {r.get('error', '')}", flush=True)

        await asyncio.gather(*[do(t) for t in tasks], return_exceptions=True)

    asyncio.run(run_batch())
    final_results = json.loads((Path(__file__).resolve().parent / "results.json").read_text(encoding="utf-8"))
    print(f"\n结果已写入 results.json，共 {len(final_results)} 场（本次新跑 {len(tasks)} 场）")
    return final_results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 份简历（默认全量）")
    parser.add_argument("--resume", action="store_true", help="跳过 results.json 中已有评分的场次")
    parser.add_argument("--rounds", type=int, default=ANALYSIS_ROUNDS, help="每场回答轮数（默认 2）")
    parser.add_argument("--workers", type=int, default=3, help="并发场次数（默认 3）")
    args = parser.parse_args()

    setup_eval_db()
    results = main_run(args.limit, args.resume, args.rounds, args.workers)

    ok = [r for r in results if "scores" in r]
    if ok:
        avg = {
            s: sum(r["scores"].get(s, 0) for r in ok) / len(ok)
            for s in ["technical", "communication", "logic"]
        }
        print("\n=== 平均分 ===")
        print(json.dumps(avg, ensure_ascii=False, indent=2))

        exps = [r["experience"] for r in ok if r.get("experience")]
        if exps:
            exp_avg = {
                "repeated_question_rate": round(
                    sum(e["repeated_question_rate"] for e in exps) / len(exps), 3
                ),
                "follower_overlap_rate": round(
                    sum(e["follower_overlap_rate"] for e in exps) / len(exps), 3
                ),
                "leaked_material_hits": sum(e["leaked_material_hits"] for e in exps),
            }
            print("\n=== 体感代理指标（30 场均值） ===")
            print(json.dumps(exp_avg, ensure_ascii=False, indent=2))
