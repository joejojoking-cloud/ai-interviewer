"""Prompt 单源一致性：chat / chat-stream 两条入口必须从 prompts.py 构建，
防止"双份硬编码拷贝漂移"。任何改 prompt 的人会直接在这里被拦下。"""
import pytest

import main
from prompts import (
    SYSTEM_INTERVIEWER,
    build_followup_prompt,
    build_report_prompt,
)


def patch_llm(monkeypatch, recorded=None, score_reply_fn=None):
    async def fake_call_llm_with_tools(messages, tools=None, resume_text="", jd_skills="", timeout=120.0):
        if recorded is not None:
            recorded.append(messages)
        return {"content": "追问内容", "tool_calls_log": []}

    async def fake_call_llm(messages, timeout=120.0):
        return "追问内容"

    async def fake_call_llm_score(messages, timeout=120.0):
        if recorded is not None:
            recorded.append(messages)
        if score_reply_fn:
            return score_reply_fn()
        return '{"score": {"technical": 80, "communication": 70, "logic": 75}, "strengths": [], "improvements": [], "overall_comment": "ok"}'

    monkeypatch.setattr(main, "call_llm_with_tools", fake_call_llm_with_tools)
    monkeypatch.setattr(main, "call_llm", fake_call_llm)
    monkeypatch.setattr(main, "call_llm_score", fake_call_llm_score)


class TestPromptConsistency:
    def _new_session(self, client, resume_text="秒杀项目"):
        return client.post("/interview/start", json={"resume_text": resume_text, "candidate_name": "张三"}).json()["session_id"]

    def test_chat_and_stream_use_same_followup_prompt(self, client, monkeypatch):
        # 两条入口各自跑一个独立会话（避免消息库互相污染），prompt 应完全一致
        recorded = []
        patch_llm(monkeypatch, recorded=recorded)

        sid_chat = self._new_session(client)
        sid_stream = self._new_session(client)
        assert client.post("/interview/chat", json={"session_id": sid_chat, "answer": "我用 Redis 做的"}).status_code == 200
        assert client.post("/interview/chat-stream", json={"session_id": sid_stream, "answer": "我用 Redis 做的"}).status_code == 200

        followup_prompts = [m[1]["content"] for m in recorded if m[1]["role"] == "user"]
        assert len(followup_prompts) == 2, f"应记录两条追问 prompt，实际 {len(followup_prompts)}"
        # 单源化：两条入口构造出的 prompt 完全一致
        assert followup_prompts[0] == followup_prompts[1]

    def test_both_use_same_system_prompt(self, client, monkeypatch):
        recorded = []
        patch_llm(monkeypatch, recorded=recorded)
        sid_chat = self._new_session(client)
        sid_stream = self._new_session(client)
        client.post("/interview/chat", json={"session_id": sid_chat, "answer": "我用 Redis 做的"})
        client.post("/interview/chat-stream", json={"session_id": sid_stream, "answer": "我用 Redis 做的"})
        systems = {m[0]["content"] for m in recorded}
        assert systems == {SYSTEM_INTERVIEWER}

    def test_report_prompt_single_source(self, client, monkeypatch):
        recorded = []
        patch_llm(monkeypatch, recorded=recorded)
        sid_chat = self._new_session(client)
        sid_stream = self._new_session(client)
        client.post("/interview/chat", json={"session_id": sid_chat, "answer": "结束了", "is_finished": True})
        client.post("/interview/chat-stream", json={"session_id": sid_stream, "answer": "结束了", "is_finished": True})
        report_prompts = [m[1]["content"] for m in recorded if m[1]["role"] == "user"]
        assert len(report_prompts) == 2
        assert report_prompts[0] == report_prompts[1]

    def test_followup_prompt_contains_all_branches(self):
        p = build_followup_prompt("【岗位】后端", "面试历史", "我正在学 Redis")
        for branch in ["A. 搜索命中", "B. 搜索未命中", "C. 候选人回答已经很充分", "D. 候选人明确表示不了解", "E. 候选人回答与问题无关"]:
            assert branch in p

    def test_report_prompt_contains_anchors_and_rules(self):
        p = build_report_prompt("【岗位】后端", "面试历史")
        assert "三条" not in p or "铁律" in p
        assert "不能凭简历推测" in p
        assert "85-100" in p
        assert "0-20" in p
