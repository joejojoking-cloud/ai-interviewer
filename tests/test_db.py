"""SQLite 会话层：增删查改 + 级联删除（用内存库，不碰真实 interviewer.db）"""
import sqlite3

import pytest

import main


class TestSessionLifecycle:
    def test_create_and_list(self, fresh_db):
        main.create_session("s1", name="张三 - 面试", jd_text="后端", resume_text="简历")
        sessions = main.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s1"
        assert sessions[0]["msg_count"] == 0

    def test_create_idempotent(self, fresh_db):
        main.create_session("s1")
        main.create_session("s1")
        assert len(main.list_sessions()) == 1

    def test_get_session_info(self, fresh_db):
        main.create_session("s1", jd_text="JD 内容", resume_text="简历内容")
        info = main.get_session_info("s1")
        assert info["jd_text"] == "JD 内容"
        assert info["resume_text"] == "简历内容"

    def test_get_session_info_missing_returns_none(self, fresh_db):
        assert main.get_session_info("nope") is None

    def test_delete_cascades_messages(self, fresh_db):
        main.create_session("s1")
        main.save_message("s1", "user", "你好")
        main.save_message("s1", "assistant", "你好，我是面试官")
        main.delete_session("s1")
        assert main.list_sessions() == []
        assert main.load_history("s1") == []


class TestMessages:
    def test_save_and_load_order(self, fresh_db):
        main.create_session("s1")
        main.save_message("s1", "user", "第一条")
        main.save_message("s1", "assistant", "第二条")
        main.save_message("s1", "user", "第三条")
        history = main.load_history("s1")
        assert [m["content"] for m in history] == ["第一条", "第二条", "第三条"]
        assert history[0]["role"] == "user"

    def test_load_history_limits_turns(self, fresh_db):
        main.create_session("s1")
        for i in range(30):
            main.save_message("s1", "user", f"u{i}")
            main.save_message("s1", "assistant", f"a{i}")
        # max_turns=5 = 10 条消息
        history = main.load_history("s1", max_turns=5)
        assert len(history) == 10
        assert history[-1]["content"] == "a29"


class TestHelpers:
    def test_trim_history(self):
        history = [{"role": "user", "content": str(i)} for i in range(20)]
        trimmed = main.trim_history(history, max_turns=3)
        assert len(trimmed) == 6

    def test_format_history_marks_speakers(self):
        history = [
            {"role": "assistant", "content": "问题"},
            {"role": "user", "content": "回答"},
        ]
        text = main.format_history(history)
        assert "面试官" in text and "候选人" in text
