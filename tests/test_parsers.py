"""简历解析：PDF / Docx 真实文件 + 非法格式防护"""
import main


class TestParsePdf:
    def test_pdf_returns_nonempty_text(self, resume_pdf):
        content = resume_pdf.read_bytes()
        text = main.parse_pdf(content)
        assert isinstance(text, str)
        assert len(text) > 50  # 真实 PDF 应能提取出内容


class TestParseDocx:
    def test_docx_returns_nonempty_text(self, resume_docx):
        content = resume_docx.read_bytes()
        text = main.parse_docx(content)
        assert isinstance(text, str)
        assert len(text) > 50


class TestParseResumeEndpoint:
    def test_upload_docx(self, client, resume_docx):
        with resume_docx.open("rb") as f:
            resp = client.post(
                "/parse-resume",
                files={"file": (resume_docx.name, f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == resume_docx.name
        assert data["length"] == len(data["content"]) > 0

    def test_upload_pdf(self, client, resume_pdf):
        with resume_pdf.open("rb") as f:
            resp = client.post("/parse-resume", files={"file": ("resume.pdf", f, "application/pdf")})
        assert resp.status_code == 200
        assert len(resp.json()["content"]) > 0

    def test_unsupported_format(self, client):
        resp = client.post(
            "/parse-resume",
            files={"file": ("resume.exe", b"MZ...", "application/octet-stream")},
        )
        assert resp.status_code == 200
        assert "error" in resp.json()
