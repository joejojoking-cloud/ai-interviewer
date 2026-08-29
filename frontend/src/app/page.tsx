"use client";
import { useState, useEffect, useRef } from "react";
import {
  Button,
  Input,
  Upload,
  Card,
  Typography,
  Space,
  Divider,
  message,
  Spin,
  Popconfirm,
} from "antd";
import {
  UploadOutlined,
  SendOutlined,
  StopOutlined,
  PlusOutlined,
  DeleteOutlined,
  MenuOutlined,
} from "@ant-design/icons";
import { Radar } from "@ant-design/charts";
import { api } from "./api";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

interface Message {
  role: "user" | "assistant";
  content: string;
  time?: string;
}

interface Session {
  session_id: string;
  name: string;
  jd_text: string;
  created_at: string;
  msg_count: number;
}

export default function Home() {
  // ── 状态 ──
  const [step, setStep] = useState<"upload" | "interview" | "report">("upload");
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [candidateName, setCandidateName] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isMobile, setIsMobile] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ── 任务 1：自动滚动到底部 ──
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── 任务 5：移动端检测 ──
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  // ── 任务 6：加载会话 + 错误处理 ──
  const loadSessions = async () => {
    try {
      const data = await api.getSessions();
      setSessions(data.sessions);
    } catch {
      message.error("无法连接后端，请确认服务已启动");
    }
  };

  useEffect(() => {
    loadSessions();
  }, []);

  // ── 上传简历 ──
  const handleUpload = async (file: File) => {
    setLoading(true);
    try {
      const result = await api.parseResume(file);
      if (result.error) {
        message.error(result.error);
      } else {
        setResumeText(result.content);
        message.success(`简历解析成功，共 ${result.length} 字`);
      }
    } catch {
      message.error("简历解析失败");
    }
    setLoading(false);
  };

  // ── 开始面试 ──
  const handleStart = async () => {
    if (!resumeText) {
      message.warning("请先上传简历");
      return;
    }
    setLoading(true);
    try {
      const result = await api.startInterview({
        resume_text: resumeText,
        jd_text: jdText,
        candidate_name: candidateName || "候选人",
      });
      setSessionId(result.session_id);
      setMessages([{ role: "assistant", content: result.ai_reply, time: new Date().toLocaleTimeString() }]);
      setStep("interview");
      if (isMobile) setSidebarOpen(false);
      loadSessions();
    } catch {
      message.error("开始面试失败");
    }
    setLoading(false);
  };

  // ── 发送回答（流式输出） ──
  const handleSend = async (isFinished = false) => {
    if (!inputValue.trim() && !isFinished) return;
    const answer = isFinished ? "我想结束了" : inputValue.trim();

    if (!isFinished) {
      setMessages((prev) => [...prev, { role: "user", content: answer, time: new Date().toLocaleTimeString() }, { role: "assistant", content: "" }]);
    } else {
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
    }
    setInputValue("");
    setLoading(true);

    try {
      const stream = api.interviewChatStream({
        session_id: sessionId,
        answer,
        is_finished: isFinished,
      });

      let fullReply = "";
      for await (const chunk of stream) {
        if (chunk.done) {
          // 任务 3：流结束后加时间戳
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              time: new Date().toLocaleTimeString(),
            };
            return updated;
          });
          if (isFinished && chunk.full_reply) {
            try {
              const cleaned = chunk.full_reply
                .replace(/```json\n?/g, "")
                .replace(/```\n?/g, "")
                .trim();
              const reportData = JSON.parse(cleaned);
              setReport(reportData);
              setStep("report");
              loadSessions();
            } catch {
              // JSON 解析失败
            }
          }
          break;
        }
        if (chunk.text) {
          fullReply += chunk.text;
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],  // 保留 time 等已有字段
              role: "assistant",
              content: fullReply,
            };
            return updated;
          });
        }
      }
    } catch {
      message.error("发送失败");
    }
    setLoading(false);
  };

  // ── 加载历史会话 ──
  const loadSession = async (sid: string) => {
    setSessionId(sid);
    setReport(null);
    setLoading(true);
    if (isMobile) setSidebarOpen(false);
    try {
      const data = await api.getSessionMessages(sid);
      const filtered = data.messages.filter(
        (m) => m.content !== "（面试开始，候选人准备回答）"
      );

      const lastMsg = filtered[filtered.length - 1];
      let isReport = false;
      if (lastMsg?.role === "assistant") {
        const raw = lastMsg.content;
        let parsed: any = null;
        try {
          parsed = JSON.parse(raw.trim());
        } catch {
          try {
            const cleaned = raw
              .replace(/^```(?:json)?\s*\n?/gm, "")
              .replace(/\n?```\s*$/gm, "")
              .trim();
            parsed = JSON.parse(cleaned);
          } catch {
            try {
              const start = raw.indexOf("{");
              const end = raw.lastIndexOf("}");
              if (start !== -1 && end > start) {
                parsed = JSON.parse(raw.slice(start, end + 1));
              }
            } catch {
              // not JSON
            }
          }
        }
        if (parsed && typeof parsed === "object" && "score" in parsed) {
          setReport(parsed);
          setStep("report");
          setMessages(filtered.slice(0, -1));
          isReport = true;
        }
      }

      if (!isReport) {
        setStep("interview");
        setMessages(filtered);
      }
    } catch {
      message.error("加载历史失败");
    }
    setLoading(false);
  };

  // ── 任务 2：删除会话（Popconfirm 处理） ──
  const handleDelete = async (sid: string) => {
    try {
      await api.deleteSession(sid);
      message.success("已删除");
      loadSessions();
      if (sid === sessionId) {
        handleReset();
      }
    } catch {
      message.error("删除失败");
    }
  };

  // ── 新面试 ──
  const handleReset = () => {
    setStep("upload");
    setMessages([]);
    setReport(null);
    setResumeText("");
    setSessionId("");
    setInputValue("");
    if (isMobile) setSidebarOpen(false);
  };

  // ── 任务 4：过滤会话列表 ──
  const filteredSessions = sessions.filter((s) =>
    searchQuery
      ? s.name.toLowerCase().includes(searchQuery.toLowerCase())
      : true
  );

  return (
    <div style={{ display: "flex", height: "100vh" }}>
      {/* ── 任务 5：移动端汉堡按钮 ── */}
      {isMobile && !sidebarOpen && (
        <Button
          icon={<MenuOutlined />}
          onClick={() => setSidebarOpen(true)}
          style={{ position: "fixed", top: 8, left: 8, zIndex: 1000 }}
        />
      )}

      {/* ─── 左侧：历史会话 ─── */}
      <div
        style={{
          width: isMobile ? (sidebarOpen ? 280 : 0) : 280,
          background: "#001529",
          color: "#fff",
          padding: sidebarOpen || !isMobile ? 16 : 0,
          overflowY: "auto",
          flexShrink: 0,
          transition: "width 0.3s, padding 0.3s",
          position: isMobile ? "fixed" : "relative",
          height: "100vh",
          zIndex: 999,
        }}
      >
        {(sidebarOpen || !isMobile) && (
          <>
            <Title level={4} style={{ color: "#fff", marginBottom: 16 }}>
              📋 历史面试
            </Title>
            <Button
              type="primary"
              block
              icon={<PlusOutlined />}
              style={{ marginBottom: 12 }}
              onClick={handleReset}
            >
              新面试
            </Button>
            {/* 任务 4：搜索框 */}
            <Input.Search
              placeholder="搜索面试..."
              allowClear
              size="small"
              style={{ marginBottom: 12 }}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {filteredSessions.map((s) => (
              <div
                key={s.session_id}
                onClick={() => loadSession(s.session_id)}
                style={{
                  padding: "10px 12px",
                  marginBottom: 8,
                  borderRadius: 8,
                  cursor: "pointer",
                  background:
                    sessionId === s.session_id
                      ? "#1890ff"
                      : "rgba(255,255,255,0.08)",
                  transition: "background 0.2s",
                  position: "relative",
                }}
              >
                <div style={{ fontWeight: 500, fontSize: 14, paddingRight: 24 }}>
                  {s.name}
                </div>
                <div style={{ fontSize: 12, opacity: 0.6, marginTop: 4 }}>
                  {s.msg_count} 条消息 ·{" "}
                  {new Date(s.created_at).toLocaleDateString()}
                </div>
                {/* 任务 2：Popconfirm 二次确认 */}
                <Popconfirm
                  title="确定删除这场面试？"
                  description="删除后无法恢复"
                  onConfirm={() => handleDelete(s.session_id)}
                  onCancel={(e) => e?.stopPropagation()}
                >
                  <DeleteOutlined
                    style={{
                      position: "absolute",
                      top: 10,
                      right: 10,
                      opacity: 0.4,
                      fontSize: 14,
                    }}
                    onClick={(e) => e.stopPropagation()}
                  />
                </Popconfirm>
              </div>
            ))}
            {/* 任务 4：空状态优化 */}
            {sessions.length === 0 && (
              <div style={{ opacity: 0.5, textAlign: "center", marginTop: 40 }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>📝</div>
                <div>还没有面试记录</div>
                <div style={{ fontSize: 12, marginTop: 4 }}>
                  点击上方"新面试"开始第一场
                </div>
              </div>
            )}
            {sessions.length > 0 && filteredSessions.length === 0 && (
              <div style={{ opacity: 0.4, textAlign: "center", marginTop: 20 }}>
                没有匹配的面试
              </div>
            )}
          </>
        )}
      </div>

      {/* 移动端点击遮罩关闭侧边栏 */}
      {isMobile && sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.3)",
            zIndex: 998,
          }}
        />
      )}

      {/* ─── 右侧：主内容区 ─── */}
      <div style={{ flex: 1, padding: isMobile ? 12 : 24, overflowY: "auto" }}>
        {/* ─── 步骤 1：上传简历/JD ─── */}
        {step === "upload" && (
          <div style={{ width: "100%", maxWidth: 900, margin: "0 auto" }}>
            <Title level={2} style={{ textAlign: "center", marginBottom: 24 }}>
              🎙️ AI 面试官
            </Title>
            <Card title="上传简历和岗位信息" loading={loading}>
              <Space orientation="vertical" size="large" style={{ width: "100%" }}>
                <div>
                  <Text strong>📄 上传简历</Text>
                  <div style={{ marginTop: 8 }}>
                    <Upload
                      accept=".pdf,.docx"
                      beforeUpload={(file) => {
                        handleUpload(file);
                        return false;
                      }}
                      showUploadList={false}
                    >
                      <Button icon={<UploadOutlined />}>
                        选择 PDF 或 Word 文件
                      </Button>
                    </Upload>
                    {resumeText && (
                      <Text type="success" style={{ marginLeft: 12 }}>
                        ✅ 已解析（{resumeText.length} 字）
                      </Text>
                    )}
                  </div>
                </div>

                <div>
                  <Text strong>📝 岗位 JD（选填）</Text>
                  <TextArea
                    rows={4}
                    placeholder="粘贴岗位描述，AI 会根据 JD 生成更有针对性的问题"
                    value={jdText}
                    onChange={(e) => setJdText(e.target.value)}
                    style={{ marginTop: 8 }}
                  />
                </div>

                <div>
                  <Text strong>👤 你的名字</Text>
                  <Input
                    placeholder="怎么称呼你？"
                    value={candidateName}
                    onChange={(e) => setCandidateName(e.target.value)}
                    style={{ marginTop: 8 }}
                  />
                </div>

                <Button
                  type="primary"
                  size="large"
                  block
                  onClick={handleStart}
                  disabled={!resumeText}
                >
                  🎤 开始面试
                </Button>
              </Space>
            </Card>
          </div>
        )}

        {/* ─── 步骤 2：面试对话 ─── */}
        {step === "interview" && (
          <div style={{ width: "100%", maxWidth: 900, margin: "0 auto" }}>
            <Card
              title={`面试进行中 — ${candidateName || "候选人"}`}
              extra={
                <Button
                  danger
                  icon={<StopOutlined />}
                  onClick={() => handleSend(true)}
                >
                  结束面试
                </Button>
              }
            >
              {/* 消息区域 */}
              <div
                style={{
                  height: "calc(100vh - 280px)",
                  minHeight: 400,
                  overflowY: "auto",
                  padding: 16,
                  background: "#fafafa",
                  borderRadius: 8,
                  marginBottom: 16,
                }}
              >
                {messages.map((msg, i) => (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      justifyContent:
                        msg.role === "user" ? "flex-end" : "flex-start",
                      marginBottom: 12,
                    }}
                  >
                    <div
                      style={{
                        maxWidth: "80%",
                        padding: "10px 16px",
                        borderRadius: 12,
                        background: msg.role === "user" ? "#1890ff" : "#fff",
                        color: msg.role === "user" ? "#fff" : "#333",
                        border:
                          msg.role === "user" ? "none" : "1px solid #e8e8e8",
                      }}
                    >
                      <div style={{ fontSize: 12, marginBottom: 4, opacity: 0.7 }}>
                        {msg.role === "user" ? "👤 你" : "🤖 面试官"}
                        {/* 任务 3：时间戳 */}
                        {msg.time && (
                          <span style={{ marginLeft: 8 }}>{msg.time}</span>
                        )}
                      </div>
                      <div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>
                    </div>
                  </div>
                ))}
                {loading && (
                  <div style={{ textAlign: "center", padding: 16 }}>
                    <Spin description="AI 正在思考..." />
                  </div>
                )}
                {/* 任务 1：自动滚动锚点 */}
                <div ref={messagesEndRef} />
              </div>

              {/* 输入区域 */}
              <div style={{ display: "flex", gap: 8 }}>
                <TextArea
                  rows={2}
                  placeholder="输入你的回答...（Shift+Enter 换行，Enter 发送）"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onPressEnter={(e) => {
                    if (!e.shiftKey) {
                      e.preventDefault();
                      handleSend();
                    }
                  }}
                  disabled={loading}
                />
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={() => handleSend()}
                  loading={loading}
                  style={{ height: "auto" }}
                >
                  发送
                </Button>
              </div>
            </Card>
          </div>
        )}

        {/* ─── 步骤 3：评分报告 ─── */}
        {step === "report" && report && (
          <div style={{ width: "100%", maxWidth: 900, margin: "0 auto" }}>
            <Card title="📊 面试评分报告">
              <Space orientation="vertical" size="large" style={{ width: "100%" }}>
                <div>
                  <Title level={4}>评分</Title>
                  <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
                    <div style={{ flex: "1 1 300px", minWidth: 280 }}>
                      <Radar
                        data={[
                          { name: "技术深度", score: report.score?.technical || 0 },
                          { name: "表达能力", score: report.score?.communication || 0 },
                          { name: "逻辑性", score: report.score?.logic || 0 },
                        ]}
                        xField="name"
                        yField="score"
                        meta={{ score: { min: 0, max: 100 } }}
                        area={{ visible: true, style: { fillOpacity: 0.2 } }}
                        point={{ visible: true }}
                        scale={{ y: { domainMax: 100 } }}
                        style={{ height: 260 }}
                      />
                    </div>
                    <Space size="middle" wrap>
                      <Card size="small" style={{ textAlign: "center", minWidth: 100 }}>
                        <Text>技术深度</Text>
                        <Title level={3} style={{ margin: "8px 0 0" }}>
                          {report.score?.technical}
                        </Title>
                      </Card>
                      <Card size="small" style={{ textAlign: "center", minWidth: 100 }}>
                        <Text>表达能力</Text>
                        <Title level={3} style={{ margin: "8px 0 0" }}>
                          {report.score?.communication}
                        </Title>
                      </Card>
                      <Card size="small" style={{ textAlign: "center", minWidth: 100 }}>
                        <Text>逻辑性</Text>
                        <Title level={3} style={{ margin: "8px 0 0" }}>
                          {report.score?.logic}
                        </Title>
                      </Card>
                    </Space>
                  </div>
                </div>

                <Divider />

                <div>
                  <Title level={4}>✅ 优点</Title>
                  <ul style={{ paddingLeft: 20 }}>
                    {report.strengths?.map((s: string, i: number) => (
                      <li key={i} style={{ marginBottom: 4 }}>
                        <Text>{s}</Text>
                      </li>
                    ))}
                  </ul>
                </div>

                <div>
                  <Title level={4}>⚠️ 待改进</Title>
                  <ul style={{ paddingLeft: 20 }}>
                    {report.improvements?.map((s: string, i: number) => (
                      <li key={i} style={{ marginBottom: 4 }}>
                        <Text>{s}</Text>
                      </li>
                    ))}
                  </ul>
                </div>

                <div>
                  <Title level={4}>💬 综合评语</Title>
                  <Paragraph>{report.overall_comment}</Paragraph>
                </div>

                <Button type="primary" block size="large" onClick={handleReset}>
                  再来一场面试
                </Button>
              </Space>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
