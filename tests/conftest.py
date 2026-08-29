import os
import sqlite3
import sys
import threading
from pathlib import Path

# 防止 import main 时因缺少 API Key 直接报错（测试用 mock，不会真调 LLM）
os.environ.setdefault("LLM_API_KEY", "stub-key-for-tests")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import main

# 每个测试都用独立的内存数据库，不污染 interviewer.db
@pytest.fixture()
def fresh_db(monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    monkeypatch.setattr(main, "_db_conn", conn)
    monkeypatch.setattr(main, "_db_lock", threading.Lock())
    main.init_db()
    yield conn
    conn.close()


@pytest.fixture()
def client(fresh_db):
    return TestClient(main.app)


@pytest.fixture()
def resume_docx():
    """取一份真实测试简历（test_resumes 下任意 docx）"""
    resumes = sorted(
        Path(main.__file__).parent.joinpath("test_resumes").glob("*.docx")
    )
    assert resumes, "test_resumes 目录下没有 docx 简历"
    return resumes[0]


@pytest.fixture()
def resume_pdf():
    """真实 PDF 测试简历"""
    pdf = Path(main.__file__).parent.joinpath("test_files", "test_resume.pdf")
    assert pdf.exists(), "test_files/test_resume.pdf 不存在"
    return pdf
