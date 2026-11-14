"""Retrieval evaluation: Hit@1, Evidence Hit@3 and full top-3 traces.

Definitions follow GUIDE exactly:

* A **hit** is a retrieved chunk that comes from the gold source *and* page and
  contains the recorded evidence, or a documented equivalent. Page-only matches
  do not count, because retrieving the right page with the wrong passage does not
  let an agent answer.
* **Hit@1** = questions whose rank-1 chunk is a hit / questions.
* **Evidence Hit@3** = questions with at least one hit in the top 3 / questions.

Counts are always reported as n/N, never as a bare percentage.
"""
from __future__ import annotations

import unicodedata
from typing import Any


def fold(text: str) -> str:
    """Casefold and collapse whitespace so only formatting differences are ignored."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def is_hit(question: dict[str, Any], chunk: dict[str, Any]) -> tuple[bool, str]:
    """Return whether one retrieved chunk satisfies the gold evidence.

    Every gold entry is checked, because a question may legitimately be answered
    from more than one location. A page that matches the gold page but not the
    recorded evidence is reported as such instead of being treated as a hit.
    """
    page = chunk.get("page")
    text = fold(chunk.get("text", ""))
    golds = question.get("gold", [])

    same_page = []
    for gold in golds:
        if gold["physical_page"] != page:
            continue
        same_page.append(gold)
        if fold(gold["evidence"]) in text:
            return True, f"page {page} contains gold evidence"

    if same_page:
        return False, f"page {page} matches but evidence text absent (split across chunks)"

    gold_pages = sorted({gold["physical_page"] for gold in golds})
    return False, f"page {page} is not a gold page ({gold_pages})"


def evaluate_query(
    question: dict[str, Any],
    hits: list[dict[str, Any]],
    strategy: str,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score one question and keep the full top-k trace for auditing."""
    evaluated = []
    for rank, chunk in enumerate(hits, start=1):
        hit, reason = is_hit(question, chunk)
        evaluated.append(
            {
                "rank": rank,
                "chunk_id": chunk.get("chunk_id"),
                "score": chunk.get("score"),
                "page": chunk.get("page"),
                "printed_page": chunk.get("printed_page"),
                "article": chunk.get("article"),
                "chapter": chunk.get("chapter"),
                "page_type": chunk.get("page_type"),
                "form": chunk.get("form"),
                "source": chunk.get("source"),
                "char_count": len(chunk.get("text", "")),
                "hit": hit,
                "reason": reason,
                "text": chunk.get("text", ""),
            }
        )

    hit_at_1 = bool(evaluated) and evaluated[0]["hit"]
    hit_at_3 = any(item["hit"] for item in evaluated[:3])

    filter_ok = None
    filter_detail = ""
    if filters:
        mismatches = []
        for item in evaluated:
            for key, wanted in filters.items():
                if item.get(key) != wanted:
                    mismatches.append(f"{key}={item.get(key)} != {wanted}")
        filter_ok = not mismatches
        filter_detail = "; ".join(sorted(set(mismatches)))

    return {
        "id": question["id"],
        "split": question["split"],
        "kind": question["kind"],
        "strategy": strategy,
        "question": question["question"],
        "answer": question["answer"],
        "filter": filters,
        "hit_at_1": hit_at_1,
        "hit_at_3": hit_at_3,
        "filter_compliant": filter_ok,
        "filter_mismatches": filter_detail,
        "gold": question["gold"],
        "trace": evaluated,
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate Hit@1 / Evidence Hit@3 by strategy and split."""
    summary: dict[str, Any] = {}
    for strategy in sorted({trace["strategy"] for trace in traces}):
        summary[strategy] = {}
        for split in ("dev", "test", "all"):
            subset = [
                trace
                for trace in traces
                if trace["strategy"] == strategy and (split == "all" or trace["split"] == split)
            ]
            if not subset:
                continue
            total = len(subset)
            hit1 = sum(1 for trace in subset if trace["hit_at_1"])
            hit3 = sum(1 for trace in subset if trace["hit_at_3"])
            filtered = [trace for trace in subset if trace["filter"]]
            compliant = [trace for trace in filtered if trace["filter_compliant"]]
            summary[strategy][split] = {
                "n": total,
                "hit_at_1": hit1,
                "hit_at_3": hit3,
                "hit_at_1_rate": round(hit1 / total, 4),
                "hit_at_3_rate": round(hit3 / total, 4),
                "filter_questions": len(filtered),
                "filter_compliant": len(compliant),
                "missing_ids": [trace["id"] for trace in subset if not trace["hit_at_3"]],
            }
    return summary
