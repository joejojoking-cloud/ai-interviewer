"""
体感代理指标 v0.5（纯函数，零外部依赖）
========================================
把"被听懂"翻译成三个可计算的信号（对应 Q24 设计稿的第一批落地）：
1. 重复提问率：本轮提问与之前提问的主题重合度过高 → "没在听"
2. 追问引用度：追问文本与候选人上轮回答的关键词重合 → "在听，还在引用"
3. 提示词合规：追问是否复述了后台检索材料（〔命中〕标记）→ 泄漏兜底检查

指标口径是"方法内可比"的代理指标，不是统计显著性推断（Q24/Q28 已知边界）。

阈值说明：中文用 bigram 分词下 Jaccard 天然被稀释（长文本分母大），
重复判定阈值默认 0.5（全文相同=1.0，近义改写≈0.9，主题无关≈0）。
"""

import re

# 中英文 token 提取：连续的 ASCII 字母数字串 + 连续中文（用于生成二元组）
_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")

# 停用词：语气词/无信息量词，防止歪曲主题重合度
_STOP = {
    "的", "了", "是", "吗", "呢", "吧", "啊", "呀", "嗯", "然后", "就是", "这个",
    "那个", "我", "你", "他", "她", "我们", "你们", "什么", "怎么", "为什么",
    "如何", "还是", "可以", "没有", "不是", "已经", "现在", "一个", "进行",
    "the", "and", "that", "have", "would", "you", "with", "for", "should",
}


def term_set(text: str) -> set:
    """文本 → 关键词集合：英文单词 + 中文 bigram（零依赖的轻量分词）。"""
    terms = set()
    if not text:
        return terms
    for chunk in _TOKEN_RE.findall(text.lower()):
        if chunk in _STOP:
            continue
        if re.match(r"[a-z0-9_]+$", chunk):
            if len(chunk) >= 2 and chunk not in _STOP:
                terms.add(chunk)
        else:  # 中文串 → bigram
            for i in range(len(chunk) - 1):
                big = chunk[i:i + 2]
                if big not in _STOP:
                    terms.add(big)
    return terms


def jaccard(a: set, b: set) -> float:
    """Jaccard 相似度；两边为空返回 0。"""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def repeated_question_rate(questions: list[str], threshold: float = 0.5) -> float:
    """重复提问率 = 与之前任一提问 Jaccard > threshold 的提问占比。"""
    if not questions:
        return 0.0
    terms_list = [term_set(q) for q in questions]
    dup = 0
    for i, terms in enumerate(terms_list):
        if any(jaccard(terms, terms_list[j]) > threshold for j in range(i)):
            dup += 1
    return dup / len(questions)


def citation_overlap(question: str, answer: str) -> float:
    """引用重合度 = 提问关键词中出现在候选人上一轮回答里的占比（0-1）。"""
    q_terms = term_set(question)
    a_terms = term_set(answer)
    if not q_terms:
        return 0.0
    return len(q_terms & a_terms) / len(q_terms)


def follower_overlap_rate(questions: list[str], answers: list[str]) -> float:
    """追问引用率：每一轮"追问 vs 上一轮回答"引用重合度的均值。"""
    # questions[0] 通常是开场白+第一问（无上文），从 questions[1] 开始配对
    pairs = [
        (questions[i], answers[i - 1])
        for i in range(1, len(questions))
        if i - 1 < len(answers)
    ]
    if not pairs:
        return 0.0
    return sum(citation_overlap(q, a) for q, a in pairs) / len(pairs)


def leaked_material_hits(questions: list[str]) -> int:
    """泄漏检查：追问里出现了后台检索标记（〔命中〕）的次数，应为 0。"""
    return sum(1 for q in questions if "〔命中〕" in q)


def experience_summary(questions: list[str], answers: list[str]) -> dict:
    """汇总一路的体感代理指标。"""
    return {
        "repeated_question_rate": round(repeated_question_rate(questions), 3),
        "follower_overlap_rate": round(follower_overlap_rate(questions, answers), 3),
        "leaked_material_hits": leaked_material_hits(questions),
        "n_questions": len(questions),
        "n_answers": len(answers),
    }
