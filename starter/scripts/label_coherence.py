"""Fill the hand-scored coherence labels into results/coherence_samples.csv.

Scores are the author's manual judgement against the rubric:
  0 = cut mid-idea or missing subject, unreadable on its own
  1 = partly understandable, missing context
  2 = understandable alone and keeps the whole idea

The positions were frozen by pick_coherence_samples.py before any chunk was
scored, so this script only adds labels, never moves a sample.

Run from starter/:  python scripts/label_coherence.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
RESULTS = STARTER / "results"
SAMPLES = RESULTS / "coherence_samples.csv"

# A: fixed 500/150 windows. B: paragraph-aligned 700 with breadcrumb.
LABELS = {
    "C01": (
        2,
        "Cắt đúng ranh giới đoạn văn bản; giữ tiêu đề, số văn bản và toàn bộ đoạn căn cứ nên tự hiểu được.",
        2,
        "Giống A nhưng trọn cả cụm mở đầu văn bản, cùng một ý.",
    ),
    "C02": (
        1,
        "Đoạn định nghĩa bị cắt ở giữa ('dạng tương …') và chunk mở đầu bằng đoạn d) của Điều 1 nên thiếu mạch; vẫn thấy tiêu đề Điều 2.",
        2,
        "Giữ trọn định nghĩa 'Dữ liệu cá nhân là…' và có breadcrumb Chương I + Điều 2.",
    ),
    "C03": (
        1,
        "Chunk mở đầu giữa cụm 'đến nguồn gốc chủng tộc' (mất chữ 'c) Thông tin liên quan'), danh sách điểm bị cắt giữa chừng.",
        2,
        "Trọn khoản h) dài nhất của Điều 2, có breadcrumb cho biết đang ở Điều nào; các điểm g)–i) liền mạch.",
    ),
    "C04": (
        1,
        "Chunk bắt đầu giữa từ ('ên Kiểm soát'), chứa khoản 13 và cắt khoản 14 — đúng đoạn mẫu nằm ở chunk khác nên ngữ cảnh bị lệch.",
        2,
        "Khoản 14 nằm trọn trong chunk cùng breadcrumb Điều 2; tự hiểu được.",
    ),
    "C05": (
        1,
        "Mở đầu bằng ', Bên Kiểm soát…' — mất chủ ngữ của khoản 3; đoạn mẫu (khoản 6) chỉ xuất hiện ở chunk sau.",
        2,
        "Khoản 6 nằm trọn, có breadcrumb Điều 3 và tiếp nối khoản 7 cùng điều.",
    ),
    "C06": (
        1,
        "Chunk mở giữa câu ('hiện theo quy định…'), rồi mới sang Điều 7; khoản 2 mẫu bị cắt cuối chunk.",
        2,
        "Trọn Điều 7 với breadcrumb; khoản 2 mẫu nằm nguyên trong chunk.",
    ),
    "C07": (
        2,
        "Đoạn mẫu (khoản 3) nằm trọn trong chunk, cùng các khoản 4–5 và tiêu đề Điều 8; mạch đọc liền.",
        2,
        "Trọn Điều 8 từ tiêu đề đến khoản 3, có breadcrumb; tốt hơn A vì không lẫn khoản 4–5 của Điều 7.",
    ),
    "C08": (
        2,
        "Đoạn mẫu nằm trọn; chunk có tiêu đề '8. Quyền phản đối xử lý dữ liệu' làm ngữ cảnh, dù mở đầu bằng đuôi khoản 7.",
        2,
        "Trọn quyền phản đối với breadcrumb Điều 9; mạch rõ nhất.",
    ),
    "C09": (
        2,
        "Chunk chứa trọn quyền tự bảo vệ và tiêu đề Điều 10 kế tiếp; đọc hiểu được.",
        2,
        "Chỉ chứa đúng quyền tự bảo vệ + breadcrumb; gọn và trọn ý nhất.",
    ),
    "C10": (
        1,
        "Mở đầu giữa từ ('ng ý của chủ thể'), khoản 11 mẫu bị cắt ngay sau 'chủ thể'; phải đọc chunk sau mới đủ.",
        2,
        "Khoản 11 nằm trọn trong chunk riêng có breadcrumb Điều 11; tự hiểu được.",
    ),
}


def main() -> int:
    rows = list(csv.DictReader(SAMPLES.open(encoding="utf-8")))
    fieldnames = list(rows[0].keys())

    for row in rows:
        score_a, reason_a, score_b, reason_b = LABELS[row["sample_id"]]
        row["score_A"] = score_a
        row["reason_A"] = reason_a
        row["score_B"] = score_b
        row["reason_B"] = reason_b

    with SAMPLES.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    scores_a = [int(row["score_A"]) for row in rows]
    scores_b = [int(row["score_B"]) for row in rows]
    summary = {
        "samples": len(rows),
        "A_fixed": {
            "scores": scores_a,
            "mean": round(sum(scores_a) / len(scores_a), 2),
            "count_0": scores_a.count(0),
            "count_1": scores_a.count(1),
            "count_2": scores_a.count(2),
        },
        "B_para": {
            "scores": scores_b,
            "mean": round(sum(scores_b) / len(scores_b), 2),
            "count_0": scores_b.count(0),
            "count_1": scores_b.count(1),
            "count_2": scores_b.count(2),
        },
        "scorer": "tác giả (Đào Ngọc Hân) — tự chấm, có nguy cơ thiên lệch",
        "positions_frozen_before_scoring": True,
        "artifact": "starter/results/coherence_samples.csv",
        "generator": "starter/scripts/label_coherence.py",
    }
    (RESULTS / "coherence_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"A_fixed mean {summary['A_fixed']['mean']}/2  scores {scores_a}")
    print(f"B_para  mean {summary['B_para']['mean']}/2  scores {scores_b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
