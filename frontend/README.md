# AI 模拟面试官 - 前端

基于 Next.js 16（App Router）+ TypeScript + Ant Design 6 的前端应用。

## 功能

- 简历 / JD 上传与解析（PDF / Word / txt / md），JD 解析结果卡片化展示
- 面试对话界面，SSE 流式逐字渲染（原生 `fetch` + `ReadableStream` 解析，绕过代理缓冲）
- 三维评分报告（技术深度 / 表达能力 / 逻辑性）+ 雷达图可视化
- 历史会话侧边栏（搜索、删除二次确认、移动端折叠），可恢复历史对话

## 开发

```bash
npm install
npm run dev
```

默认通过 `next.config.ts` 的 rewrites 将 `/api/*` 代理到 `http://127.0.0.1:8000`；
流式接口直接连接后端（避免代理缓冲破坏流式体验）。

完整说明见仓库根目录 README。
