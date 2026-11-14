"""Cross-check the hand-written manifest against generated evidence.

Fails loudly when data/manifest.json drifts from the audit and structure
artifacts, so recorded page counts, totals and hashes cannot silently become
stale. Every number the manifest states about the corpus is compared against
starter/results/page_audit.json rather than trusted as prose.

Run from starter/:  python scripts/verify_manifest.py
(or from the repo root:  python starter/scripts/verify_manifest.py)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
MANIFEST = ROOT / "data" / "manifest.json"
AUDIT = STARTER / "results" / "page_audit.json"
STRUCTURE = STARTER / "results" / "structure.json"
PDF = STARTER / "data" / "nghi_dinh_13_2023_nd_cp.pdf"

REQUIRED_KEYS = (
    "source_id",
    "title",
    "source_path_or_url",
    "license_or_permission",
    "snapshot",
    "extraction",
)
REQUIRED_LICENSE_KEYS = ("classification", "basis", "accessed_at", "redistribution")
REQUIRED_RULE_KEYS = (
    "unit",
    "counted",
    "min_content_chars",
    "required_content_pages",
    "total_content_chars",
    "chars_all_pages",
    "main_body_chars",
    "appendix_chars",
    "chars_with_whitespace",
)


def main() -> int:
    problems: list[str] = []

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    structure = json.loads(STRUCTURE.read_text(encoding="utf-8"))
    document = manifest["documents"][0]

    for key in REQUIRED_KEYS:
        if key not in document:
            problems.append(f"manifest missing required key: {key}")
    for key in REQUIRED_LICENSE_KEYS:
        if not document.get("license_or_permission", {}).get(key):
            problems.append(f"license_or_permission missing: {key}")

    digest = hashlib.sha256(PDF.read_bytes()).hexdigest()
    if document["snapshot"]["sha256"] != digest:
        problems.append(f"sha256 mismatch: manifest={document['snapshot']['sha256']} file={digest}")
    if audit["sha256"] != digest:
        problems.append("page_audit.json is stale: sha256 differs from the PDF")

    if document["physical_pages"] != audit["physical_pages"]:
        problems.append(f"physical_pages: manifest={document['physical_pages']} audit={audit['physical_pages']}")
    if document["content_pages"] != audit["content_pages"]:
        problems.append(f"content_pages: manifest={document['content_pages']} audit={audit['content_pages']}")
    if document["content_page_numbers"] != audit["content_page_numbers"]:
        problems.append("content_page_numbers differ from page_audit.json")

    rule = document["page_counting_rule"]
    for key in REQUIRED_RULE_KEYS:
        if key not in rule:
            problems.append(f"page_counting_rule missing: {key}")

    comparisons = (
        ("min_content_chars", "min_content_chars"),
        ("required_content_pages", "required_content_pages"),
        ("total_content_chars", "chars_body_content_pages"),
        ("chars_all_pages", "chars_all_pages"),
        ("main_body_chars", "main_body_chars"),
        ("appendix_chars", "appendix_chars"),
        ("chars_with_whitespace", "chars_with_whitespace_all_pages"),
    )
    for manifest_key, audit_key in comparisons:
        if rule.get(manifest_key) != audit.get(audit_key):
            problems.append(
                f"page_counting_rule.{manifest_key}: manifest={rule.get(manifest_key)} "
                f"audit={audit.get(audit_key)}"
            )

    if audit["main_body_chars"] + audit["appendix_chars"] > audit["chars_all_pages"]:
        problems.append("main_body_chars + appendix_chars exceeds chars_all_pages")
    if audit["chars_body_content_pages"] > audit["chars_all_pages"]:
        problems.append("content-page chars exceed all-page chars")

    excluded_manifest = [item["physical_page"] for item in document["excluded_pages"]]
    excluded_audit = [item["physical_page"] for item in audit["excluded_pages"]]
    if excluded_manifest != excluded_audit:
        problems.append(f"excluded_pages: manifest={excluded_manifest} audit={excluded_audit}")

    if document["structure"]["articles"] != structure["article_count"]:
        problems.append(
            f"articles: manifest={document['structure']['articles']} structure={structure['article_count']}"
        )
    if document["structure"]["chapters"] != len(structure["chapters"]):
        problems.append("chapters count differs from structure.json")
    if document["structure"]["sections"] != len(structure["sections"]):
        problems.append("sections count differs from structure.json")
    if not structure["articles_contiguous_from_1"]:
        problems.append("structure.json reports non-contiguous article numbers")

    page_types = audit["page_type_counts"]
    if sum(page_types.values()) != audit["physical_pages"]:
        problems.append("page_type_counts do not add up to physical_pages")
    if document["structure"].get("appendix_form_pages") != page_types.get("phu_luc_bieu_mau"):
        problems.append(
            f"appendix_form_pages: manifest={document['structure'].get('appendix_form_pages')} "
            f"audit={page_types.get('phu_luc_bieu_mau')}"
        )

    filler_manifest = document["structure"].get("filler_heavy_pages")
    if filler_manifest != audit["filler_heavy_pages"]:
        problems.append(
            f"filler_heavy_pages: manifest={filler_manifest} audit={audit['filler_heavy_pages']}"
        )

    if audit["content_pages"] < audit["required_content_pages"]:
        problems.append(
            f"content pages below lab minimum: {audit['content_pages']} < {audit['required_content_pages']}"
        )
    if not audit["meets_required_content_pages"]:
        problems.append("page_audit.json reports meets_required_content_pages=false")

    for problem in problems:
        print(f"FAIL: {problem}")

    if problems:
        print(f"\n{len(problems)} problem(s) found")
        return 1

    print("manifest OK")
    print(f"  sha256          {digest}")
    print(f"  pages           {document['content_pages']}/{document['physical_pages']} content "
          f"(min {rule['required_content_pages']})")
    print(f"  chars           {rule['total_content_chars']} content, {rule['chars_all_pages']} all")
    print(f"  structure       {document['structure']['chapters']} chương, "
          f"{document['structure']['sections']} mục, {document['structure']['articles']} điều")
    print(f"  form pages      {document['structure']['appendix_form_pages']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
