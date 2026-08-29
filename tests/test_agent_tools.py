"""Agent 工具层：search_resume / evaluate_answer / generate_report / get_interview_plan"""
import asyncio
import json

import main

RESUME = """张三
曾参与秒杀系统开发，负责 Redis 缓存与库存扣减，QPS 峰值 5000。
电商后台项目：使用 FastAPI + MySQL，实现订单异步处理。"""


class TestSearchResume:
    def test_hit_returns_context(self):
        result = main.tool_search_resume("秒杀", RESUME)
        assert "找到 1 处匹配" in result
        assert "Redis" in result

    def test_multiple_hits_limited(self):
        result = main.tool_search_resume("项目", RESUME)
        assert "找到" in result

    def test_miss_returns_not_found(self):
        result = main.tool_search_resume("区块链", RESUME)
        assert "未找到" in result

    def test_empty_keyword(self):
        result = main.tool_search_resume("", RESUME)
        assert "为空" in result

    def test_empty_resume(self):
        result = main.tool_search_resume("秒杀", "")
        assert "为空" in result

    def test_case_insensitive(self):
        result = main.tool_search_resume("redis", RESUME)
        assert "找到" in result


class TestEvaluateAnswer:
    def test_good_answer_scores_high(self):
        answer = (
            "首先介绍一下架构，我们用了 Redis 缓存和消息队列。"
            "针对并发超卖问题，我们在数据库层面加了乐观锁，实现上还做了分布式限流，"
            "性能优化后 QPS 从 1000 提升到 5000，上线后监控日志显示错误率低于 0.1%。"
        )
        data = json.loads(main.tool_evaluate_answer(answer, "技术深度"))
        assert data["score"] >= 70

    def test_vague_answer_scores_low(self):
        data = json.loads(main.tool_evaluate_answer("这个项目我了解一些，但细节记不清楚了", "技术深度"))
        assert data["score"] < 50

    def test_short_answer_penalized(self):
        data = json.loads(main.tool_evaluate_answer("做过的。", "技术深度"))
        assert data["score"] < 60

    def test_admits_unknown_penalized(self):
        data = json.loads(main.tool_evaluate_answer("这个技术我确实不了解，没有实际做过。", "技术深度"))
        assert data["score"] < 60

    def test_score_in_range(self):
        for answer in ["好。", "a" * 300 + "架构 性能 优化 数据库 缓存 并发 设计"]:
            data = json.loads(main.tool_evaluate_answer(answer, "技术深度"))
            assert 0 <= data["score"] <= 100

    def test_output_contains_criteria(self):
        data = json.loads(main.tool_evaluate_answer("详细回答" * 50, "技术深度"))
        assert data["criteria"] == "技术深度"
        assert isinstance(data["reasons"], list)


class TestGenerateReport:
    def test_returns_prompt_with_history_and_schema(self):
        result = main.tool_generate_report("面试历史摘要")
        assert "面试历史摘要" in result
        assert '"score"' in result
        assert "technical" in result


class TestInterviewPlan:
    def test_returns_json_with_all_fields(self):
        result = json.loads(main.tool_get_interview_plan("秒杀系统", "自我介绍;项目深挖"))
        assert "next_phase" in result
        assert "next_direction" in result
        assert "current_phase" in result
        assert result["current_phase"] == "项目深挖"

    def test_classifies_tech_depth(self):
        result = json.loads(main.tool_get_interview_plan("Redis 缓存原理", ""))
        assert result["current_phase"] == "技术深度"
        assert result["next_phase"] == "场景/设计题"

    def test_empty_topic_defaults(self):
        result = json.loads(main.tool_get_interview_plan("", ""))
        assert result["current_phase"] == "技术深度"
        assert result["advice"]  # 非空建议

    def test_last_phase_ends_interview(self):
        result = json.loads(main.tool_get_interview_plan("你有什么要问我的吗", ""))
        assert result["next_phase"] == "面试收尾"

    def test_blueprint_lists_remaining_phases(self):
        result = json.loads(main.tool_get_interview_plan("秒杀系统", ""))
        assert len(result["blueprint"]) >= 3


class TestToolRegistry:
    def test_all_plan_tools_present_in_schema(self):
        names = [t["function"]["name"] for t in main.AGENT_TOOLS]
        assert set(names) >= {"search_resume", "evaluate_answer", "generate_report", "get_interview_plan"}


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class FakeAsyncClient:
    """按顺序返回预设响应的假 httpx 客户端"""
    def __init__(self, responses):
        self._responses = list(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kwargs):
        return FakeResponse(200, self._responses.pop(0))


def tool_calls_message(name, args: dict, tool_call_id="call_1"):
    return {"choices": [{"message": {
        "role": "assistant",
        "tool_calls": [{"id": tool_call_id, "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}],
    }}]}


def final_message(content: str):
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class TestDispatcher:
    """call_llm_with_tools 的真实工具分发（mock httpx，不发真实请求）"""

    def test_dispatches_get_interview_plan(self, monkeypatch):
        responses = [
            tool_calls_message("get_interview_plan", {"current_topic": "秒杀系统", "covered_topics": "自我介绍"}),
            final_message("好，那接下来我们聊聊系统设计"),
        ]
        client = FakeAsyncClient(responses)
        monkeypatch.setattr(main.httpx, "AsyncClient", lambda: client)
        result = asyncio.run(main.call_llm_with_tools([{"role": "user", "content": "hi"}], tools=main.AGENT_TOOLS))
        assert result["content"] == "好，那接下来我们聊聊系统设计"
        assert len(result["tool_calls_log"]) == 1
        assert result["tool_calls_log"][0]["tool"] == "get_interview_plan"
        assert "next_phase" in result["tool_calls_log"][0]["result"]

    def test_dispatches_search_resume_with_context(self, monkeypatch):
        responses = [
            tool_calls_message("search_resume", {"keyword": "秒杀"}),
            final_message("你提到了秒杀系统，内存库存扣减怎么保证原子性的？"),
        ]
        client = FakeAsyncClient(responses)
        monkeypatch.setattr(main.httpx, "AsyncClient", lambda: client)
        result = asyncio.run(main.call_llm_with_tools(
            [{"role": "user", "content": "hi"}], tools=main.AGENT_TOOLS, resume_text="做过秒杀系统，Redis 库存扣减")
        )
        assert "秒杀系统" in result["tool_calls_log"][0]["result"]
        assert result["content"].startswith("你提到了秒杀系统")

    def test_unknown_tool_is_tolerated(self, monkeypatch):
        responses = [
            tool_calls_message("json_loader", {}),
            final_message("ok"),
        ]
        client = FakeAsyncClient(responses)
        monkeypatch.setattr(main.httpx, "AsyncClient", lambda: client)
        result = asyncio.run(main.call_llm_with_tools([{"role": "user", "content": "hi"}], tools=main.AGENT_TOOLS))
        assert "未知工具" in result["tool_calls_log"][0]["result"]

    def test_loop_stops_after_5_rounds(self, monkeypatch):
        responses = []
        for i in range(8):
            responses.append(tool_calls_message("evaluate_answer", {"answer": "x", "criteria": "y"}, tool_call_id=f"c{i}"))
        client = FakeAsyncClient(responses)
        monkeypatch.setattr(main.httpx, "AsyncClient", lambda: client)
        result = asyncio.run(main.call_llm_with_tools([{"role": "user", "content": "hi"}], tools=main.AGENT_TOOLS))
        assert len(result["tool_calls_log"]) == 5  # for 循环 5 次封顶
        assert all(tc["tool"] == "evaluate_answer" for tc in result["tool_calls_log"])

