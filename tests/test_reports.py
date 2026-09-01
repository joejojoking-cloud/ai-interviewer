"""报告落库测试：结束面试后报告可查、可随会话删除"""
import json

import pytest

import main

REPORT_JSON = json.dumps({
    "score": {"technical": 82, "communication": 71, "logic": 76},
    "strengths": ["有数据支撑"],
    "improvements": ["深度不足"],
    "overall_comment": "整体不错",
}, ensure_ascii=False)


def patch_llm(monkeypatch, score_reply=None):
    async def fake_call_llm(messages, timeout=120.0):
        return "追问内容"

    async def fake_call_llm_with_tools(messages, tools=None, resume_text="", jd_skills="", timeout=120.0):
        return {"content": "追问内容", "tool_calls_log": []}

    async def fake_call_llm_score(messages, timeout=120.0):
        return score_reply or REPORT_JSON

    monkeypatch.setattr(main, "call_llm", fake_call_llm)
    monkeypatch.setattr(main, "call_llm_with_tools", fake_call_llm_with_tools)
    monkeypatch.setattr(main, "call_llm_score", fake_call_llm_score)


@pytest.fixture()
def finished_session(client, monkeypatch):
    patch_llm(monkeypatch)
    resp = client.post("/interview/start", json={"resume_text": "秒杀项目", "candidate_name": "张三"})
    sid = resp.json()["session_id"]
    client.post("/interview/chat", json={"session_id": sid, "answer": "我用 Redis 做的", "is_finished": True})
    return sid


class TestReportPersistence:
    def test_report_saved_and_queryable(self, client, finished_session):
        resp = client.get(f"/sessions/{finished_session}/report")
        assert resp.status_code == 200
        body = resp.json()
        assert body["report"]["score"]["technical"] == 82
        assert body["raw"]

    def test_report_missing(self, client):
        resp = client.get("/sessions/does-not-exist/report")
        assert resp.status_code == 200
        assert resp.json()["report"] is None

    def test_report_deleted_with_session(self, client, finished_session):
        client.delete(f"/sessions/{finished_session}")
        resp = client.get(f"/sessions/{finished_session}/report")
        assert resp.json()["report"] is None

    def test_save_report_upsert(self, fresh_db):
        main.save_report("s1", {"score": {"technical": 1}}, "raw-a")
        main.save_report("s1", {"score": {"technical": 99}}, "raw-b")
        got = main.get_report("s1")
        assert got["report"]["score"]["technical"] == 99
        assert got["raw"] == "raw-b"

    def test_save_report_parse_failed(self, fresh_db):
        main.save_report("s2", {"_parse_failed": True}, "模型没输出 JSON")
        got = main.get_report("s2")
        assert got["report"] == {"_parse_failed": True}
