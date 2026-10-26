"""
Bộ đánh giá định lượng AI 1 (Text-to-SQL) trên 50 câu hỏi (eval/text2sql_gold_50.json).

So sánh 2 cấu hình:
  - "Chỉ luật"  : bộ luật regex (tắt dự phòng học máy).
  - "Luật + ML" : bộ luật regex + bộ phân loại TF-IDF/Logistic Regression dự phòng.

Chỉ số:
  - Intent Accuracy: tỷ lệ dự đoán đúng intent (câu ngoài phạm vi đúng khi trả UNKNOWN).
  - Execution Accuracy (tùy chọn, cần PostgreSQL): SQL sinh ra chạy thành công.
  - Tỷ lệ hỏi lại (clarification): câu hệ thống chủ động hỏi lại thay vì trả lời sai.

Chạy:  python eval/eval_text2sql.py            (chỉ đánh giá intent, không cần DB)
       python eval/eval_text2sql.py --execute  (chạy thêm SQL trên DB thật)
"""
import argparse
import json
import os
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import intent_classifier  # noqa: E402
from app.pipeline import interpret  # noqa: E402

GOLD_PATH = os.path.join(ROOT, "eval", "text2sql_gold_50.json")
REPORT_PATH = os.path.join(ROOT, "eval", "report_text2sql.md")


def run(cases, use_ml: bool, execute: bool):
    intent_classifier.ML_FALLBACK_ENABLED = use_ml
    rows = []
    for c in cases:
        res = interpret(c["q"])
        predicted = res.intent if res.success else "UNKNOWN"
        correct = predicted == c["intent"]
        exec_ok = None
        if execute and res.success and res.sql:
            from app.db import execute_query
            exec_ok = bool(execute_query(res.sql, res.params).get("success"))
        rows.append({
            **c,
            "pred": predicted,
            "raw_intent": res.intent,
            "confidence": res.confidence,
            "rule": res.matched_rule,
            "correct": correct,
            "clarify": (not res.success) and res.needs_clarification and c["intent"] != "UNKNOWN",
            "exec_ok": exec_ok,
        })
    return rows


def summarize(rows):
    by_group = defaultdict(lambda: [0, 0])
    for r in rows:
        by_group[r["nhom"]][0] += int(r["correct"])
        by_group[r["nhom"]][1] += 1
    total_ok = sum(int(r["correct"]) for r in rows)
    clarify = sum(int(r["clarify"]) for r in rows)
    executed = [r for r in rows if r["exec_ok"] is not None]
    exec_acc = (sum(int(r["exec_ok"]) for r in executed) / len(executed)) if executed else None
    return {
        "accuracy": total_ok / len(rows),
        "groups": {g: v[0] / v[1] for g, v in by_group.items()},
        "group_counts": {g: v for g, v in by_group.items()},
        "clarify": clarify,
        "exec_acc": exec_acc,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="Chạy SQL trên PostgreSQL để đo Execution Accuracy")
    args = ap.parse_args()

    with open(GOLD_PATH, encoding="utf-8") as f:
        cases = json.load(f)["cases"]

    rule_rows = run(cases, use_ml=False, execute=args.execute)
    hybrid_rows = run(cases, use_ml=True, execute=args.execute)
    s_rule, s_hyb = summarize(rule_rows), summarize(hybrid_rows)
    intent_classifier.ML_FALLBACK_ENABLED = True

    def pct(x):
        return "—" if x is None else f"{x * 100:.1f}%"

    lines = [
        "# BÁO CÁO ĐÁNH GIÁ AI 1: TEXT-TO-SQL (LUẬT + HỌC MÁY)",
        "",
        f"**Bộ kiểm thử:** `eval/text2sql_gold_50.json` ({len(cases)} câu: 20 câu gốc, 25 câu diễn đạt lại không có trong dữ liệu huấn luyện, 5 câu ngoài phạm vi)",
        "",
        "## 1. So sánh tổng hợp",
        "",
        "| Chỉ số | Chỉ luật regex | Luật + ML dự phòng |",
        "|---|---|---|",
        f"| Intent Accuracy (50 câu) | {pct(s_rule['accuracy'])} | **{pct(s_hyb['accuracy'])}** |",
        f"| Câu gốc (20) | {pct(s_rule['groups'].get('goc'))} | {pct(s_hyb['groups'].get('goc'))} |",
        f"| Câu diễn đạt lại (25) | {pct(s_rule['groups'].get('dien_dat_lai'))} | **{pct(s_hyb['groups'].get('dien_dat_lai'))}** |",
        f"| Từ chối đúng câu ngoài phạm vi (5) | {pct(s_rule['groups'].get('ngoai_pham_vi'))} | {pct(s_hyb['groups'].get('ngoai_pham_vi'))} |",
        f"| Số câu chưa trả lời được (hệ thống hỏi lại) | {s_rule['clarify']} | {s_hyb['clarify']} |",
        f"| Execution Accuracy (cần DB) | {pct(s_rule['exec_acc'])} | {pct(s_hyb['exec_acc'])} |",
        "",
        "## 2. Chi tiết từng câu (cấu hình Luật + ML)",
        "",
        "| # | Câu hỏi | Kỳ vọng | Dự đoán | Độ tin cậy | Cơ chế | Đúng |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(hybrid_rows, 1):
        mark = "✅" if r["correct"] else ("❓ hỏi lại" if r["clarify"] else "❌")
        lines.append(
            f"| {i} | {r['q']} | `{r['intent']}` | `{r['pred']}` | {r['confidence']:.2f} | `{r['rule']}` | {mark} |"
        )
    report = "\n".join(lines) + "\n"
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Chỉ luật   : {pct(s_rule['accuracy'])}  {s_rule['group_counts']}")
    print(f"Luật + ML  : {pct(s_hyb['accuracy'])}  {s_hyb['group_counts']}")
    print(f"Đã ghi báo cáo: {REPORT_PATH}")
    for r in hybrid_rows:
        if not r["correct"]:
            print("  SAI:", r["q"], "->", r["pred"], r["raw_intent"], r["confidence"], r["rule"])


if __name__ == "__main__":
    main()
