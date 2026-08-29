const BASE = "/api";
const BACKEND = "http://127.0.0.1:8000"; // 流式请求直连后端，绕过 Next.js 代理缓冲

// 通用请求函数
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`请求失败: ${res.status}`);
  return res.json();
}

// 后端接口对应的函数
export const api = {
  // 简历解析
  parseResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${BASE}/parse-resume`, { method: "POST", body: form }).then(
      (r) => r.json()
    );
  },

  // 简历 AI 识别
  analyzeResume: (resume_text: string) =>
    request<{ parsed: any }>("/analyze-resume", {
      method: "POST",
      body: JSON.stringify({ resume_text }),
    }),

  // 开始面试
  startInterview: (data: {
    resume_text: string;
    jd_text?: string;
    candidate_name?: string;
  }) =>
    request<{ session_id: string; ai_reply: string }>("/interview/start", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // 面试对话
  interviewChat: (data: {
    session_id: string;
    answer: string;
    is_finished?: boolean;
  }) =>
    request<{ session_id: string; ai: string; report?: any }>(
      "/interview/chat",
      {
        method: "POST",
        body: JSON.stringify(data),
      }
    ),

  // 会话列表
  getSessions: () => request<{ sessions: any[] }>("/sessions"),

  // 会话消息
  getSessionMessages: (session_id: string) =>
    request<{ session_id: string; messages: { role: string; content: string }[] }>(
      `/sessions/${session_id}/messages`
    ),

  // 删除会话
  deleteSession: (session_id: string) =>
    fetch(`${BASE}/sessions/${session_id}`, { method: "DELETE" }).then((r) =>
      r.json()
    ),

  // 流式面试对话
  interviewChatStream: async function* (data: {
    session_id: string;
    answer: string;
    is_finished?: boolean;
  }) {
    const res = await fetch(`${BACKEND}/interview/chat-stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
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

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const parsed = JSON.parse(line.slice(6));
            yield parsed;
          } catch {
            // skip malformed chunks
          }
        }
      }
    }
  },
};
