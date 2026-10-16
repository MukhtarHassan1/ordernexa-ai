#!/usr/bin/env python3
"""Validate OrderNexa evaluation datasets without running a model.

Generated draft labels are never treated as curated evidence. The CLI supports
both human-readable output and a stable JSON report for CI/preflight scripts.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REQUIRED = {"id", "category", "source_text", "expected"}


def validate(path: Path) -> dict:
    rows: list[dict] = []
    errors: list[str] = []
    if not path.is_file():
        return {
            "dataset": str(path), "cases": 0, "case_count": 0,
            "errors": ["dataset file does not exist"], "categories": {},
            "prompt_injection_cases": 0, "must_review_cases": 0,
            "unreviewed_generated_labels": 0, "release_claim_eligible": False,
        }

    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {n}: invalid JSON: {exc}")
            continue
        if not isinstance(obj, dict):
            errors.append(f"line {n}: case must be an object")
            continue
        missing = REQUIRED - set(obj)
        if missing:
            errors.append(f"line {n}: missing {sorted(missing)}")
        if not isinstance(obj.get("expected"), dict):
            errors.append(f"line {n}: expected must be object")
        rows.append(obj)

    ids = [str(x.get("id")) for x in rows]
    if len(ids) != len(set(ids)):
        errors.append("duplicate case IDs")
    unreviewed = sum(x.get("requires_human_label_review") is True for x in rows)
    categories = Counter(str(x.get("category")) for x in rows)
    injections = sum(bool(x.get("must_flag_injection")) for x in rows)
    reviews = sum(bool(x.get("must_request_review")) for x in rows)
    count = len(rows)
    return {
        "dataset": str(path),
        "cases": count,
        "case_count": count,  # backwards-compatible CI key
        "errors": errors,
        "categories": dict(categories),
        "prompt_injection_cases": injections,
        "must_review_cases": reviews,
        "unreviewed_generated_labels": unreviewed,
        "release_claim_eligible": bool(rows) and not errors and unreviewed == 0,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    ap.add_argument("--json", action="store_true", help="print report as JSON")
    ap.add_argument("--json-out", type=Path, help="also write report to this JSON file")
    args = ap.parse_args()
    report = validate(args.dataset)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n".join([
            f"Dataset: {report['dataset']}",
            f"Cases: {report['cases']}",
            f"Unreviewed generated labels: {report['unreviewed_generated_labels']}",
            f"Release-claim eligible: {report['release_claim_eligible']}",
            f"Categories: {report['categories']}",
            *(f"ERROR: {x}" for x in report["errors"]),
        ]))
    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    sys.exit(main())
