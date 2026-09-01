"""体感代理指标模块的单元测试（纯函数，无 LLM 依赖）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from experience_metrics import (
    term_set,
    jaccard,
    repeated_question_rate,
    citation_overlap,
    follower_overlap_rate,
    leaked_material_hits,
    experience_summary,
)


class TestTermSet:
    def test_chinese_bigrams(self):
        terms = term_set("秒杀系统")
        assert "秒杀" in terms
        assert "杀系" in terms

    def test_english_words(self):
        terms = term_set("Redis in-memory cache")
        assert "redis" in terms
        assert "cache" in terms

    def test_empty(self):
        assert term_set("") == set()

    def test_stopwords_excluded(self):
        terms = term_set("的 了 是 吗")
        assert len(terms) == 0


class TestJaccard:
    def test_identical(self):
        assert jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint(self):
        assert jaccard({"a"}, {"b"}) == 0.0

    def test_empty(self):
        assert jaccard(set(), set()) == 0.0


class TestRepeatedQuestionRate:
    def test_no_repeat(self):
        questions = ["讲一下项目背景", "技术上用过什么缓存"]
        assert repeated_question_rate(questions) == 0.0

    def test_identical_repeat(self):
        # 首个提问本身不算重复（无"更早"的对象），第二问等于第一问 → 1/2
        questions = ["再详细讲讲秒杀系统", "再详细讲讲秒杀系统"]
        assert repeated_question_rate(questions) == 0.5

    def test_near_rewrite_is_repeat(self):
        # 近义改写：仅少量词不同，bigram Jaccard 仍 >0.5
        questions = ["介绍一下你做过的秒杀系统", "介绍你做过的秒杀系统"]
        assert repeated_question_rate(questions) == 0.5

    def test_partial_repeat(self):
        questions = ["介绍一下你做过的秒杀系统", "讲一下项目背景", "介绍你做过的秒杀系统"]
        assert repeated_question_rate(questions) == 1 / 3

    def test_empty(self):
        assert repeated_question_rate([]) == 0.0


class TestFollowerOverlap:
    def test_follows_answer(self):
        answers = ["我用 Redis 做了库存扣减，还有本地缓存"]
        questions = ["开场白：你好，第一问是，说说秒杀项目", "Redis 缓存数据一致性怎么保证？"]
        rate = follower_overlap_rate(questions, answers)
        assert rate > 0  # "redis"/"缓存" 被引用

    def test_ignores(self):
        questions = ["开场：你好", "今天天气怎么样？"]
        answers = ["我用 Redis 做了库存扣减"]
        assert follower_overlap_rate(questions, answers) < 0.1

    def test_no_pairs(self):
        assert follower_overlap_rate([], []) == 0.0


class TestLeakCheck:
    def test_leak_detected(self):
        assert leaked_material_hits(["〔命中〕Redis 介绍", "正常追问"]) == 1

    def test_clean(self):
        assert leaked_material_hits(["正常追问"]) == 0


class TestSummary:
    def test_summary_shape(self):
        s = experience_summary(["问题一", "问题二"], ["回答一"])
        assert set(s.keys()) == {
            "repeated_question_rate",
            "follower_overlap_rate",
            "leaked_material_hits",
            "n_questions",
            "n_answers",
        }
        assert s["n_questions"] == 2

    def test_citation_cost(self):
        assert 0 <= experience_summary(["问题"], ["回答"])["follower_overlap_rate"] <= 1
