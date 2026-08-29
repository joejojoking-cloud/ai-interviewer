"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import {
  Button,
  Input,
  Card,
  Typography,
  Space,
  Divider,
  message,
  Popconfirm,
  Tooltip,
  Upload,
} from "antd";
import {
  PlusOutlined,
  DeleteOutlined,
  MenuOutlined,
  SearchOutlined,
  UserOutlined,
  RobotOutlined,
  SendOutlined,
  StopOutlined,
} from "@ant-design/icons";
import { Radar } from "@ant-design/charts";
import { api, JdAnalysis } from "./api";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

/* ═══════════════════════════════════════════════════════════
   SVG 图标组件（Lucide / Iconoir 风格：1.5-2px stroke、圆角端点）
   ═══════════════════════════════════════════════════════════ */

const IconUploadCloud = ({ size = 24, color = "currentColor", ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" />
    <path d="M12 12v9" />
    <path d="m16 16-4-4-4 4" />
  </svg>
);

const IconMessagesSquare = ({ size = 24, color = "currentColor", ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M14 9a2 2 0 0 1-2 2H6l-4 4V4c0-1.1.9-2 2-2h8a2 2 0 0 1 2 2z" />
    <path d="M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1" />
  </svg>
);

const IconClipboardCheck = ({ size = 24, color = "currentColor", ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <rect width="8" height="4" x="8" y="2" rx="1" ry="1" />
    <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    <path d="m9 14 2 2 4-4" />
  </svg>
);

const IconFileText = ({ size = 24, color = "currentColor", ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
    <path d="M14 2v4a2 2 0 0 0 2 2h4" />
    <path d="M10 9H8" />
    <path d="M16 13H8" />
    <path d="M16 17H8" />
  </svg>
);

const IconBriefcase = ({ size = 24, color = "currentColor", ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
    <rect width="20" height="14" x="2" y="6" rx="2" />
  </svg>
);

const IconUser = ({ size = 24, color = "currentColor", ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <circle cx="12" cy="8" r="5" />
    <path d="M20 21a8 8 0 0 0-16 0" />
  </svg>
);

const IconX = ({ size = 24, color = "currentColor", ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M18 6 6 18" />
    <path d="m6 6 12 12" />
  </svg>
);

const IconCheck = ({ size = 24, color = "currentColor", ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M20 6 9 17l-5-5" />
  </svg>
);

const IconSpinner = ({ size = 24, color = "currentColor", ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" {...props} className="loading-spin">
    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
  </svg>
);

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

interface InterviewReport {
  score: {
    technical: number;
    communication: number;
    logic: number;
  };
  strengths: string[];
  improvements: string[];
  overall_comment: string;
}

/* ═══════════════════════════════════════════════════════════
   步骤指示器组件
   ═══════════════════════════════════════════════════════════ */

function StepIndicator({ current }: { current: "upload" | "interview" | "report" }) {
  const steps = [
    { key: "upload", label: "上传简历", icon: <IconUploadCloud size={16} /> },
    { key: "interview", label: "模拟面试", icon: <IconMessagesSquare size={16} /> },
    { key: "report", label: "评分报告", icon: <IconClipboardCheck size={16} /> },
  ];

  const currentIndex = steps.findIndex((s) => s.key === current);

  return (
    <div className="step-indicator">
      {steps.map((step, index) => {
        const status = index < currentIndex ? "completed" : index === currentIndex ? "active" : "pending";
        return (
          <div key={step.key} style={{ display: "flex", alignItems: "center" }}>
            <div className={`step-item ${status}`}>
              <div className="step-icon-wrapper">
                {status === "completed" ? <IconCheck size={14} /> : step.icon}
              </div>
              <span className="step-label">{step.label}</span>
            </div>
            {index < steps.length - 1 && (
              <div className={`step-connector ${index < currentIndex ? "completed" : ""}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   侧边栏空状态图标
   ═══════════════════════════════════════════════════════════ */

function SidebarEmptyIcon() {
  return (
    <div className="sidebar-empty-icon">
      <svg width="96" height="96" viewBox="0 0 96 96" fill="none">
        {/* 主圆形背景 */}
        <circle cx="48" cy="48" r="40" fill="rgba(37, 99, 235, 0.1)" />
        {/* 文件图标 */}
        <g transform="translate(32, 28)">
          <path
            d="M24 2H10a4 4 0 0 0-4 4v28a4 4 0 0 0 4 4h16a4 4 0 0 0 4-4V10Z"
            stroke="#2563EB"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
          <path
            d="M24 2v8a4 4 0 0 0 4 4h0"
            stroke="#2563EB"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
          <path d="M16 18h-4" stroke="#2563EB" strokeWidth="2" strokeLinecap="round" />
          <path d="M24 24H12" stroke="#2563EB" strokeWidth="2" strokeLinecap="round" />
          <path d="M24 30H12" stroke="#2563EB" strokeWidth="2" strokeLinecap="round" />
        </g>
        {/* 装饰圆点 */}
        <circle cx="72" cy="28" r="4" fill="#60A5FA" />
        <circle cx="76" cy="44" r="3" fill="#93C5FD" />
        <circle cx="68" cy="60" r="3" fill="#D1D5DB" />
        {/* ＋小徽章 */}
        <circle cx="68" cy="68" r="10" fill="#2563EB" />
        <path d="M68 63v10M63 68h10" stroke="white" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   JD 卡片组件
   ═══════════════════════════════════════════════════════════ */

function JdCard({ jdParsed, collapsed, onToggle }: { 
  jdParsed: JdAnalysis; 
  collapsed: boolean; 
  onToggle: () => void;
}) {
  return (
    <div className="jd-card">
      <div className="jd-card-header" onClick={onToggle}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <IconBriefcase size={16} color="var(--color-primary)" />
          <span style={{ fontWeight: 600 }}>{jdParsed.position}</span>
        </div>
        <span style={{ fontSize: 12, color: "var(--color-text-tertiary)" }}>
          {collapsed ? "展开" : "收起"}
        </span>
      </div>
      
      {!collapsed && (
        <div className="jd-card-content">
          {jdParsed.requirements.skills.length > 0 && (
            <div className="jd-section">
              <div className="jd-label">核心技能</div>
              <div className="jd-tags">
                {jdParsed.requirements.skills.map((skill: string, i: number) => (
                  <span key={i} className="jd-tag">{skill}</span>
                ))}
              </div>
            </div>
          )}
          
          {jdParsed.requirements.experience && (
            <div className="jd-section">
              <div className="jd-label">经验要求</div>
              <div className="jd-value">{jdParsed.requirements.experience}</div>
            </div>
          )}
          
          {jdParsed.responsibilities.length > 0 && (
            <div className="jd-section">
              <div className="jd-label">岗位职责</div>
              <ul className="jd-list">
                {jdParsed.responsibilities.map((item: string, i: number) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          
          {jdParsed.bonus.length > 0 && (
            <div className="jd-section">
              <div className="jd-label">加分项</div>
              <div className="jd-tags">
                {jdParsed.bonus.map((item: string, i: number) => (
                  <span key={i} className="jd-tag bonus">{item}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════
   主页面组件
   ═══════════════════════════════════════════════════════════ */

export default function Home() {
  // ── 状态 ──
  const [step, setStep] = useState<"upload" | "interview" | "report">("upload");
  const [resumeText, setResumeText] = useState("");
  const [resumeFileName, setResumeFileName] = useState("");
  const [resumeFileSize, setResumeFileSize] = useState(0);
  const [jdText, setJdText] = useState("");
  const [jdParsed, setJdParsed] = useState<JdAnalysis | null>(null);
  const [jdLoading, setJdLoading] = useState(false);
  const [jdCardCollapsed, setJdCardCollapsed] = useState(false);
  const [candidateName, setCandidateName] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<InterviewReport | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isMobile, setIsMobile] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ── 自动滚动到底部 ──
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── 移动端检测 ──
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  // ── 加载会话列表 ──
  const loadSessions = useCallback(async () => {
    try {
      const data = await api.getSessions();
      setSessions(data.sessions);
    } catch {
      message.error("无法连接后端，请确认服务已启动");
    }
  }, []);

  // 初始化加载会话
  const initializedRef = useRef(false);
  useEffect(() => {
    if (!initializedRef.current) {
      initializedRef.current = true;
      loadSessions();
    }
  }, [loadSessions]);

  // ── JD 解析（手动触发） ──
  const analyzeJd = async () => {
    if (!jdText.trim()) {
      message.warning("请先输入或上传 JD 内容");
      return;
    }
    setJdLoading(true);
    setJdParsed(null);
    try {
      const result = await api.analyzeJd(jdText);
      if (result.parsed) {
        setJdParsed(result.parsed);
        message.success("JD 解析成功！");
      } else {
        message.error("JD 解析失败，请检查内容后重试");
      }
    } catch (err) {
      message.error("JD 解析失败，请检查网络或稍后重试");
      console.error("JD 解析出错:", err);
    }
    setJdLoading(false);
  };

  // ── JD 文件上传 ──
  const handleJdUpload = async (file: File) => {
    try {
      const result = await api.parseResume(file);
      if (result.error) {
        message.error(result.error);
      } else {
        setJdText(result.content);
        message.success("JD 文件已上传，请点击「解析 JD」按钮");
      }
    } catch {
      message.error("JD 文件读取失败");
    }
  };

  // ── 上传简历 ──
  const handleUpload = async (file: File) => {
    setLoading(true);
    try {
      const result = await api.parseResume(file);
      if (result.error) {
        message.error(result.error);
      } else {
        setResumeText(result.content);
        setResumeFileName(file.name);
        setResumeFileSize(file.size);
        message.success("简历解析成功");
      }
    } catch {
      message.error("简历解析失败");
    }
    setLoading(false);
  };

  // ── 拖拽处理 ──
  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith(".pdf") || file.name.endsWith(".docx"))) {
      handleUpload(file);
    } else {
      message.error("请上传 PDF 或 Word 文件");
    }
  }, []);

  // ── 删除已上传文件 ──
  const handleRemoveFile = () => {
    setResumeText("");
    setResumeFileName("");
    setResumeFileSize(0);
  };

  // ── 格式化文件大小 ──
  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  };

  // ── 开始面试 ──
  const handleStart = async () => {
    if (!resumeText) {
      message.warning("请先上传简历");
      return;
    }
    
    // 如果用户输入了JD但没有解析，提示先解析
    if (jdText.trim() && !jdParsed) {
      message.warning("请先点击「解析 JD」按钮，AI 需要分析岗位要求才能生成针对性问题");
      return;
    }
    
    setLoading(true);
    try {
      const result = await api.startInterview({
        resume_text: resumeText,
        jd_text: jdText,
        jd_parsed: jdParsed,
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
      setMessages((prev) => [
        ...prev,
        { role: "user", content: answer, time: new Date().toLocaleTimeString() },
        { role: "assistant", content: "" },
      ]);
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
              ...updated[updated.length - 1],
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
      const filtered = data.messages.filter((m) => m.content !== "（面试开始，候选人准备回答）");

      const lastMsg = filtered[filtered.length - 1];
      let isReport = false;
      if (lastMsg?.role === "assistant") {
        const raw = lastMsg.content;
        let parsed: InterviewReport | null = null;
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
          setMessages(filtered.slice(0, -1) as Message[]);
          isReport = true;
        }
      }

      if (!isReport) {
        setStep("interview");
        setMessages(filtered as Message[]);
      }
    } catch {
      message.error("加载历史失败");
    }
    setLoading(false);
  };

  // ── 删除会话 ──
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
    setResumeFileName("");
    setResumeFileSize(0);
    setSessionId("");
    setInputValue("");
    if (isMobile) setSidebarOpen(false);
  };

  // ── 过滤会话列表 ──
  const filteredSessions = sessions.filter((s) =>
    searchQuery ? s.name.toLowerCase().includes(searchQuery.toLowerCase()) : true
  );

  return (
    <div className="page-container">
      {/* ── 移动端汉堡按钮 ── */}
      {isMobile && !sidebarOpen && (
        <Button
          icon={<MenuOutlined />}
          onClick={() => setSidebarOpen(true)}
          style={{
            position: "fixed",
            top: 12,
            left: 12,
            zIndex: 1000,
            width: 40,
            height: 40,
            borderRadius: "50%",
            boxShadow: "var(--shadow-elevated)",
            background: "var(--color-bg-sidebar)",
            color: "white",
            border: "none",
          }}
        />
      )}

      {/* ─── 左侧边栏 ─── */}
      <div
        className="sidebar"
        style={{
          width: isMobile ? (sidebarOpen ? 260 : 0) : 260,
          padding: sidebarOpen || !isMobile ? "20px 16px" : 0,
          overflowY: "auto",
          flexShrink: 0,
          transition: "all 250ms ease",
          position: isMobile ? "fixed" : "relative",
          height: "100vh",
          zIndex: 999,
        }}
      >
        {(sidebarOpen || !isMobile) && (
          <>
            {/* Logo 区 */}
            <div className="sidebar-logo">
              <div className="sidebar-logo-icon">
                <IconMessagesSquare size={18} color="white" />
              </div>
              <div>
                <div className="sidebar-title">AI面试</div>
                <div className="sidebar-subtitle">面试记录</div>
              </div>
            </div>

            {/* 新面试按钮 */}
            <Button
              type="primary"
              block
              icon={<PlusOutlined />}
              className="sidebar-new-btn"
              onClick={handleReset}
            >
              新面试
            </Button>

            {/* 搜索框 */}
            <div className="sidebar-search">
              <Input
                placeholder="搜索面试记录…"
                allowClear
                prefix={<SearchOutlined />}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            {/* 会话列表 */}
            <div style={{ display: "flex", flexDirection: "column" }}>
              {filteredSessions.map((s) => (
                <div
                  key={s.session_id}
                  onClick={() => loadSession(s.session_id)}
                  className={`sidebar-item ${sessionId === s.session_id ? "active" : ""}`}
                  style={{ position: "relative" }}
                >
                  <div className="sidebar-item-title">{s.name}</div>
                  <div className="sidebar-item-meta">
                    {s.msg_count} 条消息 · {new Date(s.created_at).toLocaleDateString()}
                  </div>
                  <Popconfirm
                    title="确定删除这场面试？"
                    description="删除后无法恢复"
                    onConfirm={() => handleDelete(s.session_id)}
                    onCancel={(e) => e?.stopPropagation()}
                    okButtonProps={{ danger: true }}
                  >
                    <Tooltip title="删除">
                      <DeleteOutlined
                        className="sidebar-item-delete"
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Tooltip>
                  </Popconfirm>
                </div>
              ))}
            </div>

            {/* 空状态 */}
            {sessions.length === 0 && (
              <div className="sidebar-empty">
                <SidebarEmptyIcon />
                <div className="sidebar-empty-title">还没有面试记录</div>
                <div className="sidebar-empty-desc">点击上方「新面试」开始第一场</div>
              </div>
            )}

            {sessions.length > 0 && filteredSessions.length === 0 && (
              <div style={{ textAlign: "center", padding: "20px 0", color: "var(--sidebar-text-secondary)", fontSize: 13 }}>
                没有匹配的面试
              </div>
            )}
          </>
        )}
      </div>

      {/* 移动端遮罩 */}
      {isMobile && sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.5)",
            zIndex: 998,
            backdropFilter: "blur(4px)",
          }}
        />
      )}

      {/* ─── 右侧主内容区 ─── */}
      <div className="main-content">
        <div className="content-wrapper">
          {/* 步骤指示器 */}
          <StepIndicator current={step} />

          {/* ─── 步骤 1：上传简历/JD ─── */}
          {step === "upload" && (
            <Card className="upload-card" loading={loading}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <IconFileText size={18} color="var(--color-primary)" />
                <span style={{ fontSize: 18, fontWeight: 600, color: "var(--color-text-title)" }}>
                  上传简历和岗位信息
                </span>
              </div>

              {/* 简历上传 */}
              <div className="form-section">
                <div className="form-label">
                  <IconFileText size={16} className="form-label-icon" />
                  上传简历
                </div>

                {!resumeText ? (
                  <div
                    className={`dropzone ${isDragOver ? "dragover" : ""}`}
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={() => {
                      const input = document.createElement("input");
                      input.type = "file";
                      input.accept = ".pdf,.docx";
                      input.onchange = (e) => {
                        const file = (e.target as HTMLInputElement).files?.[0];
                        if (file) handleUpload(file);
                      };
                      input.click();
                    }}
                  >
                    <IconUploadCloud size={56} className="dropzone-icon" />
                    <div className="dropzone-text">拖拽文件到这里，或点击选择</div>
                    <div className="dropzone-hint">支持 PDF / Word 格式</div>
                  </div>
                ) : (
                  <div className="file-card">
                    <div className="file-icon">
                      <IconFileText size={20} />
                    </div>
                    <div className="file-info">
                      <div className="file-name">{resumeFileName}</div>
                      <div className="file-meta">
                        {formatFileSize(resumeFileSize)} · {resumeText.length} 字
                      </div>
                    </div>
                    <button className="file-delete" onClick={handleRemoveFile} title="删除文件">
                      <IconX size={16} />
                    </button>
                  </div>
                )}
              </div>

              {/* 岗位 JD */}
              <div className="form-section">
                <div className="form-label">
                  <IconBriefcase size={16} className="form-label-icon" />
                  岗位 JD（选填）
                </div>
                
                {/* 文件上传入口 */}
                <div style={{ marginBottom: 12 }}>
                  <Upload
                    accept=".pdf,.docx,.txt,.md"
                    beforeUpload={(file) => {
                      handleJdUpload(file);
                      return false;
                    }}
                    showUploadList={false}
                  >
                    <Button icon={<IconUploadCloud size={16} />} size="small">
                      上传 JD 文件
                    </Button>
                  </Upload>
                  <span style={{ marginLeft: 8, fontSize: 12, color: "var(--color-text-tertiary)" }}>
                    支持 PDF / Word / txt / md
                  </span>
                </div>
                
                {/* 文本框入口 */}
                <TextArea
                  rows={3}
                  placeholder="或直接粘贴岗位描述..."
                  value={jdText}
                  onChange={(e) => setJdText(e.target.value)}
                  style={{ borderRadius: "var(--radius-input)", resize: "vertical" }}
                />
                
                {/* 解析按钮 */}
                <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 12 }}>
                  <Button
                    type="primary"
                    onClick={analyzeJd}
                    loading={jdLoading}
                    disabled={!jdText.trim()}
                    icon={!jdLoading ? <IconFileText size={16} /> : undefined}
                  >
                    {jdLoading ? "解析中..." : "解析 JD"}
                  </Button>
                  {jdParsed && (
                    <span style={{ fontSize: 13, color: "var(--color-success)" }}>
                      ✓ 解析成功
                    </span>
                  )}
                </div>
                
                {/* JD 解析状态 */}
                {jdLoading && (
                  <div style={{ 
                    marginTop: 12, 
                    padding: "12px 16px",
                    background: "var(--color-primary-bg)",
                    borderRadius: "8px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: 8
                  }}>
                    <IconSpinner size={16} color="var(--color-primary)" />
                    <span style={{ color: "var(--color-primary)", fontSize: 13 }}>
                      AI 正在分析 JD，请稍候（可能需要 10-30 秒）...
                    </span>
                  </div>
                )}
                
                {/* JD 卡片 */}
                {jdParsed && !jdLoading && (
                  <JdCard 
                    jdParsed={jdParsed} 
                    collapsed={jdCardCollapsed}
                    onToggle={() => setJdCardCollapsed(!jdCardCollapsed)}
                  />
                )}
              </div>

              {/* 候选人名字 */}
              <div className="form-section">
                <div className="form-label">
                  <IconUser size={16} className="form-label-icon" />
                  你的名字
                </div>
                <div style={{ display: "flex", alignItems: "center" }}>
                  <Input
                    placeholder="怎么称呼你？"
                    value={candidateName}
                    onChange={(e) => setCandidateName(e.target.value)}
                    prefix={<UserOutlined style={{ color: "var(--color-text-tertiary)", marginRight: 4 }} />}
                    style={{ 
                      width: "100%",
                      borderRadius: "8px",
                      textAlign: "left"
                    }}
                  />
                </div>
              </div>

              {/* 开始面试按钮 */}
              <Button
                type="primary"
                block
                className="start-btn"
                onClick={handleStart}
                disabled={!resumeText}
                loading={loading}
              >
                开始面试
              </Button>

              {/* 隐私说明 */}
              <div className="privacy-note">
                您的资料仅用于本次面试分析
              </div>
            </Card>
          )}

          {/* ─── 步骤 2：面试对话 ─── */}
          {step === "interview" && (
            <Card
              title={
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <IconMessagesSquare size={18} color="var(--color-primary)" />
                  <span>面试进行中 — {candidateName || "候选人"}</span>
                </div>
              }
              extra={
                <Button danger icon={<StopOutlined />} onClick={() => handleSend(true)}>
                  结束面试
                </Button>
              }
              style={{ marginBottom: 24 }}
            >
              <div
                style={{
                  height: "calc(100vh - 320px)",
                  minHeight: 400,
                  overflowY: "auto",
                  padding: 16,
                  background: "var(--color-bg-page)",
                  borderRadius: "var(--radius-card)",
                  marginBottom: 16,
                }}
              >
                {messages.length === 0 && (
                  <div className="empty-state">
                    <IconMessagesSquare size={64} className="empty-state-icon" />
                    <div className="empty-state-title">面试即将开始</div>
                    <div className="empty-state-desc">AI 面试官会根据你的简历提出问题</div>
                  </div>
                )}

                {messages.map((msg, i) => (
                  <div
                    key={i}
                    style={{
                      display: "flex",
                      justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                      marginBottom: 16,
                    }}
                  >
                    <div className={`message-bubble ${msg.role}`}>
                      <div
                        style={{
                          fontSize: 11,
                          marginBottom: 4,
                          opacity: 0.7,
                          display: "flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                      >
                        {msg.role === "user" ? (
                          <>
                            <UserOutlined />
                            <span>你</span>
                          </>
                        ) : (
                          <>
                            <RobotOutlined />
                            <span>面试官</span>
                          </>
                        )}
                        {msg.time && (
                          <span style={{ marginLeft: 8, fontSize: 10 }}>{msg.time}</span>
                        )}
                      </div>
                      <div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>
                    </div>
                  </div>
                ))}

                {loading && (
                  <div style={{ display: "flex", justifyContent: "flex-start", marginBottom: 16 }}>
                    <div className="message-bubble assistant">
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <IconSpinner size={16} />
                        <span style={{ color: "var(--color-text-secondary)" }}>AI 正在思考...</span>
                      </div>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>

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
                  style={{ borderRadius: "var(--radius-input)", resize: "none" }}
                />
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={() => handleSend()}
                  loading={loading}
                  style={{ height: "auto", borderRadius: "var(--radius-input)", padding: "0 20px" }}
                >
                  发送
                </Button>
              </div>
            </Card>
          )}

          {/* ─── 步骤 3：评分报告 ─── */}
          {step === "report" && report && (
            <Card
              title={
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <IconClipboardCheck size={18} color="var(--color-primary)" />
                  <span>面试评分报告</span>
                </div>
              }
              style={{ marginBottom: 24 }}
            >
              <Space direction="vertical" size="large" style={{ width: "100%" }}>
                <div>
                  <Title level={4} style={{ marginBottom: 16, color: "var(--color-text-title)" }}>
                    评分概览
                  </Title>
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
                      <div className="score-card">
                        <div className="score-value">{report.score?.technical || 0}</div>
                        <div className="score-label">技术深度</div>
                      </div>
                      <div className="score-card">
                        <div className="score-value">{report.score?.communication || 0}</div>
                        <div className="score-label">表达能力</div>
                      </div>
                      <div className="score-card">
                        <div className="score-value">{report.score?.logic || 0}</div>
                        <div className="score-label">逻辑性</div>
                      </div>
                    </Space>
                  </div>
                </div>

                <Divider />

                <div>
                  <Title level={4} style={{ marginBottom: 12, color: "var(--color-text-title)" }}>
                    <span style={{ color: "var(--color-success)" }}>✓</span> 优点
                  </Title>
                  <ul style={{ paddingLeft: 20 }}>
                    {report.strengths?.map((s: string, i: number) => (
                      <li key={i} style={{ marginBottom: 8, lineHeight: 1.6 }}>
                        <Text>{s}</Text>
                      </li>
                    ))}
                  </ul>
                </div>

                <div>
                  <Title level={4} style={{ marginBottom: 12, color: "var(--color-text-title)" }}>
                    <span style={{ color: "var(--color-warning)" }}>!</span> 待改进
                  </Title>
                  <ul style={{ paddingLeft: 20 }}>
                    {report.improvements?.map((s: string, i: number) => (
                      <li key={i} style={{ marginBottom: 8, lineHeight: 1.6 }}>
                        <Text>{s}</Text>
                      </li>
                    ))}
                  </ul>
                </div>

                <div>
                  <Title level={4} style={{ marginBottom: 12, color: "var(--color-text-title)" }}>
                    综合评语
                  </Title>
                  <Card style={{ background: "var(--color-bg-page)", borderColor: "var(--color-border)" }}>
                    <Paragraph style={{ margin: 0, lineHeight: 1.8, color: "var(--color-text-primary)" }}>
                      {report.overall_comment}
                    </Paragraph>
                  </Card>
                </div>

                <Button
                  type="primary"
                  block
                  className="start-btn"
                  onClick={handleReset}
                >
                  再来一场面试
                </Button>
              </Space>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
