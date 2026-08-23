"""Aggregate sharded fixed-support H2+V shadow evaluations."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

# GitHub Actions invokes this file directly (``python scripts/...py``).  In
# that mode Python puts ``scripts/`` rather than the repository root on
# ``sys.path``, so the package-qualified import below would fail on Linux.
if __package__ in {None, ""}:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.evaluate_self_play_value_shadow import (
    compare_shadow_rows,
    render_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--expected-roots", type=int, default=58)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(args.root.rglob("value-shadow-shard-*.json"))
    ]
    if not payloads or any(row.get("complete") is not True for row in payloads):
        raise SystemExit("missing or incomplete value-shadow shards")
    rows = [row for payload in payloads for row in payload.get("rows", [])]
    identifiers = [str(row["root_id"]) for row in rows]
    if len(identifiers) != args.expected_roots:
        raise SystemExit(f"expected {args.expected_roots} roots, got {len(identifiers)}")
    if len(set(identifiers)) != len(identifiers):
        raise SystemExit("duplicate value-shadow root IDs")
    result = compare_shadow_rows(sorted(rows, key=lambda row: row["root_id"]))
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
