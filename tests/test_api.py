"""API 冒烟测试：全部 mock 掉 LLM 调用，不消耗 API 额度"""
import json

import main

CHEER = "你好，我是面试官。第一个问题：能介绍一下你的秒杀项目吗？"
REPORT_JSON = json.dumps({
    "score": {"technical": 80, "communication": 70, "logic": 75},
    "strengths": ["有数据支撑", "表达清晰"],
    "improvements": ["逻辑可以更严谨"],
    "overall_comment": "整体不错",
}, ensure_ascii=False)


def patch_llm(monkeypatch, reply=CHEER, tools_reply=None, score_reply=None):
    async def fake_call_llm(messages, timeout=120.0):
        return reply

    async def fake_call_llm_with_tools(messages, tools=None, resume_text="", jd_skills="", timeout=120.0):
        return tools_reply or {
            "content": "追问内容",
            "tool_calls_log": [],
        }

    async def fake_call_llm_score(messages, timeout=120.0):
        return score_reply or REPORT_JSON

    monkeypatch.setattr(main, "call_llm", fake_call_llm)
    monkeypatch.setattr(main, "call_llm_with_tools", fake_call_llm_with_tools)
    monkeypatch.setattr(main, "call_llm_score", fake_call_llm_score)


class TestStatus:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

    def test_chat_simple(self, client, monkeypatch):
        patch_llm(monkeypatch)
        resp = client.get("/chat", params={"message": "你好"})
        assert resp.status_code == 200
        assert resp.json()["ai"] == CHEER


class TestAnalyzeResume:
    def test_strips_code_fence(self, client, monkeypatch):
        patch_llm(monkeypatch, reply='```json\n{"basic": {"name": "张三"}, "skills": ["Python"], "projects": [], "highlights": []}\n```')
        resp = client.post("/analyze-resume", json={"resume_text": "张三\nPython 开发"})
        assert resp.status_code == 200
        assert resp.json()["parsed"]["basic"]["name"] == "张三"

    def test_invalid_json_returns_error(self, client, monkeypatch):
        patch_llm(monkeypatch, reply="抱歉，我无法解析这份简历。")
        resp = client.post("/analyze-resume", json={"resume_text": "...".join(["x"] * 100)})
        assert resp.status_code == 200
        assert "error" in resp.json()


class TestInterviewFlow:
    def test_start_creates_session(self, client, monkeypatch):
        patch_llm(monkeypatch)
        resp = client.post("/interview/start", json={
            "resume_text": "有秒杀项目经验", "jd_text": "后端", "candidate_name": "张三",
        })
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]
        assert session_id.startswith("interview-")
        messages = client.get(f"/sessions/{session_id}/messages").json()["messages"]
        assert any(m["content"] == CHEER for m in messages)

    def test_chat_unknown_session_404(self, client, monkeypatch):
        patch_llm(monkeypatch)
        resp = client.post("/interview/chat", json={"session_id": "nope", "answer": "我做过秒杀"})
        assert resp.status_code == 404

    def test_chat_returns_reply(self, client, monkeypatch):
        patch_llm(monkeypatch)
        resp = client.post("/interview/start", json={"resume_text": "秒杀项目", "candidate_name": "张三"})
        session_id = resp.json()["session_id"]
        resp = client.post("/interview/chat", json={"session_id": session_id, "answer": "我用 Redis 做库存扣减"})
        assert resp.status_code == 200
        assert resp.json()["ai"] == "追问内容"

    def test_chat_finished_returns_report(self, client, monkeypatch):
        patch_llm(monkeypatch)
        resp = client.post("/interview/start", json={"resume_text": "秒杀项目", "candidate_name": "张三"})
        session_id = resp.json()["session_id"]
        resp = client.post("/interview/chat", json={"session_id": session_id, "answer": "结束了", "is_finished": True})
        assert resp.status_code == 200
        report = resp.json()["report"]
        assert report["score"]["technical"] == 80

    def test_chat_finished_uses_score_model(self, client, monkeypatch):
        calls = []

        async def spy_score(messages, timeout=120.0):
            calls.append(messages)
            return REPORT_JSON

        patch_llm(monkeypatch)
        monkeypatch.setattr(main, "call_llm_score", spy_score)
        session_id = client.post("/interview/start", json={"resume_text": "秒杀项目", "candidate_name": "张三"}).json()["session_id"]
        client.post("/interview/chat", json={"session_id": session_id, "answer": "结束了", "is_finished": True})
        assert len(calls) == 1  # 评分走评分模型，而不是 MiMo

    def test_interview_chat_stream(self, client, monkeypatch):
        patch_llm(monkeypatch)
        resp = client.post("/interview/start", json={"resume_text": "秒杀项目", "candidate_name": "张三"})
        session_id = resp.json()["session_id"]
        resp = client.post("/interview/chat-stream", json={"session_id": session_id, "answer": "我用 Redis 实现"})
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        assert "data:" in resp.text
        assert "done" in resp.text


class TestHistory:
    def test_sessions_list(self, client, monkeypatch):
        patch_llm(monkeypatch)
        client.post("/interview/start", json={"resume_text": "x", "candidate_name": "张三"})
        resp = client.get("/sessions")
        assert len(resp.json()["sessions"]) == 1

    def test_delete_session(self, client, monkeypatch):
        patch_llm(monkeypatch)
        session_id = client.post("/interview/start", json={"resume_text": "x", "candidate_name": "张三"}).json()["session_id"]
        resp = client.delete(f"/sessions/{session_id}")
        assert resp.status_code == 200
        assert client.get("/sessions").json()["sessions"] == []
