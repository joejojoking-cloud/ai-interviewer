"""
评估结果分析
============
读取 eval/results.json，输出：
1. 策略分组平均分 + 区分度报告（markdown 表格，可直接贴进 evaluation_report.md）
2. 如果存在 eval/human_scores.csv（列: session_id,human_technical,human_communication,human_logic,human_avg），
   计算 AI 评分 vs 人工评分的皮尔逊相关系数

用法：
    python eval/analyze.py                 # 只看 AI 分组分析
    python eval/analyze.py --human         # 附带人工评分相关性
"""
import argparse
import csv
import json
import math
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else None


def main(with_human: bool):
    results = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
    ok = [r for r in results if "scores" in r]
    failed = [r for r in results if "scores" not in r]

    print(f"有评分 {len(ok)} / {len(results)} 场（失败 {len(failed)} 场）")

    rows = []
    for strategy in ["优秀", "一般", "差"]:
        rs = [r for r in ok if r["strategy"] == strategy]
        if not rs:
            continue
        avg_all = mean_all = mean(
            [(r["scores"].get("technical", 0) + r["scores"].get("communication", 0)
              + r["scores"].get("logic", 0)) / 3 for r in rs]
        )
        t = mean(r["scores"].get("technical", 0) for r in rs)
        c = mean(r["scores"].get("communication", 0) for r in rs)
        l = mean(r["scores"].get("logic", 0) for r in rs)
        rows.append((strategy, len(rs), t, c, l, mean_all))

    print("\n| 策略 | 场数 | 技术 | 表达 | 逻辑 | 均分 |")
    print("|------|------|------|------|------|------|")
    for s, n, t, c, l, avg in rows:
        print(f"| {s} | {n} | {t:.1f} | {c:.1f} | {l:.1f} | {avg:.1f} |")

    if len(rows) == 3:
        diff = rows[0][5] - rows[2][5]
        print(f"\n区分度（优秀-差）：{diff:.1f} 分")
        print("通过(>=20 分)" if diff >= 20 else "区分度偏小，需优化评分 Prompt")

    if with_human:
        human_path = ROOT / "human_scores.csv"
        if not human_path.exists():
            print("\n未找到 eval/human_scores.csv，跳过相关性分析")
            return
        with human_path.open(encoding="utf-8-sig") as f:
            human = {row["session_id"]: row for row in csv.DictReader(f)}
        ai_x, human_y, human_avg_y = [], [], []
        for r in ok:
            sid = r.get("session_id") or f"eval-{r['resume']}-{r['strategy']}"
            if sid not in human:
                continue
            ai_avg = (r["scores"].get("technical", 0) + r["scores"].get("communication", 0)
                      + r["scores"].get("logic", 0)) / 3
            ai_x.append(ai_avg)
            human_avg_y.append(float(human[sid]["human_avg"]))
            human_y.extend([float(human[sid][k]) for k in ["human_technical", "human_communication", "human_logic"]])
        if len(ai_x) >= 3:
            r1 = pearson(ai_x, human_avg_y)
            r2 = pearson([v for v in ai_x for _ in range(3)], human_y)
            print(f"\n总均分 AI vs 人工：n={len(ai_x)}，皮尔逊 r = {r1:.3f}" if r1 else "样本不足")
            print(f"细粒度（每维）AI vs 人工：n={len(human_y)}，皮尔逊 r = {r2:.3f}" if r2 else "样本不足")
        else:
            print("\n人工评分样本不足（至少 3 份），跳过相关性")


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--human", action="store_true", help="附带人工评分相关性分析")
    main(parser.parse_args().human)
