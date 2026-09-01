const BASE = "/api";
const BACKEND = "http://127.0.0.1:8000"; // 流式请求直连后端，绕过 Next.js 代理缓冲

// 类型定义
interface ResumeAnalysis {
  basic: {
    name: string;
    school: string;
    major: string;
    degree: string;
  };
  skills: string[];
  projects: Array<{
    name: string;
    tech: string;
    achievement: string;
  }>;
  highlights: string[];
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

interface Session {
  session_id: string;
  name: string;
  jd_text: string;
  created_at: string;
  msg_count: number;
}

export interface JdAnalysis {
  position: string;
  requirements: {
    skills: string[];
    experience: string;
    education: string;
  };
  responsibilities: string[];
  bonus: string[];
}

// ── LLM 插槽设置（追问/解析、评分） ──
export interface LlmSlotSettings {
  provider: string;
  base_url: string;
  model: string;
  api_key_masked: string | null;
  api_key_set: boolean;
}

export interface LlmSettingsResponse {
  main: LlmSlotSettings;
  score: LlmSlotSettings;
}

export interface LlmSlotUpdate {
  api_key?: string;
  base_url?: string;
  model?: string;
}

// 通用请求函数
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`请求失败: ${res.status}`);
  return res.json();
}

// 直连后端的请求函数：LLM 调用要 30 秒以上，Next dev 代理会超时掐断
// （日志报 socket hang up），必须绕过代理；后端已配置 CORS 允许所有来源
async function requestDirect<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BACKEND}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = `请求失败: ${res.status}`;
    try {
      const data = await res.json();
      if (data && data.detail) detail = data.detail;
    } catch {
      // 非 JSON 响应，用默认提示
    }
    throw new Error(detail);
  }
  return res.json();
}

// 后端接口对应的函数
export const api = {
  // 简历解析
  parseResume: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE}/parse-resume`, { method: "POST", body: form });
    if (!res.ok) {
      let detail = `请求失败: ${res.status}`;
      try {
        const data = await res.json();
        if (data && data.detail) detail = data.detail;
      } catch {
        // 非 JSON 响应，保留默认提示
      }
      throw new Error(detail);
    }
    return res.json();
  },

  // 简历 AI 识别
  analyzeResume: (resume_text: string) =>
    requestDirect<{ parsed?: ResumeAnalysis; error?: string }>("/analyze-resume", {
      method: "POST",
      body: JSON.stringify({ resume_text }),
    }),

  // JD AI 解析
  analyzeJd: (jd_text: string) =>
    requestDirect<{ parsed?: JdAnalysis; error?: string }>("/analyze-jd", {
      method: "POST",
      body: JSON.stringify({ jd_text }),
    }),

  // 开始面试
  startInterview: (data: {
    resume_text: string;
    jd_text?: string;
    jd_parsed?: JdAnalysis | null;
    candidate_name?: string;
  }) =>
    requestDirect<{ session_id: string; ai_reply: string }>("/interview/start", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // 面试对话
  interviewChat: (data: {
    session_id: string;
    answer: string;
    is_finished?: boolean;
  }) =>
    requestDirect<{ session_id: string; ai: string; report?: InterviewReport }>(
      "/interview/chat",
      {
        method: "POST",
        body: JSON.stringify(data),
      }
    ),

  // 会话列表
  getSessions: () => request<{ sessions: Session[] }>("/sessions"),

  // 会话消息
  getSessionMessages: (session_id: string) =>
    request<{ session_id: string; messages: { role: string; content: string }[] }>(
      `/sessions/${session_id}/messages`
    ),

  // 删除会话
  deleteSession: async (session_id: string) => {
    const res = await fetch(`${BASE}/sessions/${session_id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`删除失败: ${res.status}`);
    return res.json();
  },

  // 落库的评分报告（历史回看优先用这个，不用再从消息里猜 JSON）
  getReport: (session_id: string) =>
    requestDirect<{ session_id: string; report: InterviewReport | null; raw?: string }>(
      `/sessions/${session_id}/report`
    ),

  // 当前 LLM 插槽配置（Key 脱敏）
  getSettingsKeys: () => request<LlmSettingsResponse>("/settings/keys"),

  // 更新插槽配置（未传字段保持不变）
  updateSettingsKeys: (data: { main?: LlmSlotUpdate; score?: LlmSlotUpdate }) =>
    request<LlmSettingsResponse>("/settings/keys", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // 流式面试对话
  interviewChatStream: async function* (
    data: {
      session_id: string;
      answer: string;
      is_finished?: boolean;
    },
    signal?: AbortSignal
  ) {
    const res = await fetch(`${BACKEND}/interview/chat-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
      signal,
    });

    if (!res.ok) {
      throw new Error(`请求失败: ${res.status}`);
    }
    if (!res.body) {
      throw new Error("响应体为空");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const parseEvent = (block: string) => {
      // 兼容 SSE 标准 \r\n\r\n 与 \n\n 分隔；坏块跳过，不中断整条流
      const line = block.trim();
      if (!line.startsWith("data: ")) return null;
      try {
        return JSON.parse(line.slice(6));
      } catch {
        return null;
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() || ""; // 未到边界的残留块留给下一轮

      for (const block of blocks) {
        const parsed = parseEvent(block);
        if (parsed !== null) yield parsed;
      }
    }

    // 收尾 flush：残余块里可能还有一个完整事件
    const tail = parseEvent(buffer);
    if (tail !== null) yield tail;
  },
};
