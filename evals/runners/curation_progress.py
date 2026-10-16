#!/usr/bin/env python3
"""Report human-curation progress for the 500-case evaluation draft.

This tool never edits labels and never converts generated labels into gold data.
A reviewer must explicitly clear `requires_human_label_review` after checking a
case against the intended truth.
"""
from __future__ import annotations
import argparse, json
from collections import Counter
from pathlib import Path


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("dataset", type=Path)
    args=ap.parse_args()
    rows=[json.loads(x) for x in args.dataset.read_text(encoding="utf-8").splitlines() if x.strip()]
    pending=[r for r in rows if r.get("requires_human_label_review") is True]
    reviewed=[r for r in rows if r.get("requires_human_label_review") is not True]
    print(json.dumps({
        "dataset": str(args.dataset),
        "total": len(rows),
        "reviewed": len(reviewed),
        "pending": len(pending),
        "progress_percent": round((len(reviewed)/len(rows)*100) if rows else 0, 2),
        "pending_by_category": dict(Counter(str(r.get("category")) for r in pending)),
        "truth_boundary": "Only explicit human review can clear requires_human_label_review.",
    }, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
