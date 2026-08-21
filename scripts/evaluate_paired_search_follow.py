"""Aggregate confidence-gated paired search-follow experiments."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def aggregate_manifests(manifests: list[dict[str, Any]]) -> dict[str, Any]:
    followed = [row for row in manifests if row.get("gate", {}).get("status") == "follow"]
    held = [row for row in manifests if row.get("gate", {}).get("status") == "hold"]
    valid = [row for row in followed if row.get("execution", {}).get("valid")]
    reasons = collections.Counter(
        reason for row in held for reason in row.get("gate", {}).get("reasons", [])
    )
    comparisons = [row["comparison"] for row in valid if row.get("comparison")]

    def signs(name: str) -> tuple[int, int, int]:
        values = [row.get(name) for row in comparisons]
        numeric = [float(value) for value in values if isinstance(value, (int, float))]
        return (
            sum(value > 1e-12 for value in numeric),
            sum(value < -1e-12 for value in numeric),
            sum(abs(value) <= 1e-12 for value in numeric),
        )

    fill_wins, fill_losses, fill_ties = signs("fill_delta")
    placed_wins, placed_losses, placed_ties = signs("placed_delta")
    return {
        "schema_version": 1,
        "experiment": "confidence-gated paired search-follow aggregate",
        "gate": {
            "total": len(manifests),
            "followed": len(followed),
            "held": len(held),
            "hold_reasons": dict(sorted(reasons.items())),
        },
        "fresh_outcome": {
            "valid_pairs": len(valid),
            "fill_wins": fill_wins,
            "fill_losses": fill_losses,
            "fill_ties": fill_ties,
            "placed_wins": placed_wins,
            "placed_losses": placed_losses,
            "placed_ties": placed_ties,
            "search_pareto_wins": sum(
                row.get("pareto_relation") == "search_dominates"
                for row in comparisons
            ),
            "baseline_pareto_wins": sum(
                row.get("pareto_relation") == "baseline_dominates"
                for row in comparisons
            ),
            "incomparable": sum(
                row.get("pareto_relation") == "incomparable"
                for row in comparisons
            ),
        },
        "distribution": {
            "new_downstream_states": sum(
                int(row.get("new_downstream_state_count", 0))
                for row in comparisons
            ),
            "pairs_with_new_downstream_state": sum(
                int(row.get("new_downstream_state_count", 0)) > 0
                for row in comparisons
            ),
        },
    }


def markdown_report(result: dict[str, Any]) -> str:
    gate = result["gate"]
    fresh = result["fresh_outcome"]
    distribution = result["distribution"]
    return "\n".join([
        "# Paired search-follow result", "",
        f"- roots: {gate['total']}",
        f"- confidence gate: {gate['followed']} follow / {gate['held']} hold",
        f"- fresh valid pairs: {fresh['valid_pairs']}",
        f"- fresh fill: {fresh['fill_wins']} win / {fresh['fill_losses']} loss / {fresh['fill_ties']} tie",
        f"- placed gate: {fresh['placed_wins']} win / {fresh['placed_losses']} loss / {fresh['placed_ties']} tie",
        f"- Pareto: search {fresh['search_pareto_wins']} / baseline {fresh['baseline_pareto_wins']} / incomparable {fresh['incomparable']}",
        f"- new downstream model-visible states: {distribution['new_downstream_states']}",
        "", "## Hold reasons", "",
        *(
            [f"- `{name}`: {count}" for name, count in gate["hold_reasons"].items()]
            or ["- none"]
        ),
        "",
        "A gate pass is only permission to run the paired fork. The fresh paired outcome, not the bounded-search label, decides whether search-follow earned more dataset weight.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, action="append")
    parser.add_argument("--manifest-root", type=pathlib.Path)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    paths = list(args.manifest or [])
    if args.manifest_root:
        paths.extend(sorted(args.manifest_root.rglob("manifest.json")))
    unique_paths = list(dict.fromkeys(path.resolve() for path in paths))
    if not unique_paths:
        raise SystemExit("no paired search-follow manifests found")
    result = aggregate_manifests([
        json.loads(path.read_text(encoding="utf-8")) for path in unique_paths
    ])
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(markdown_report(result), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
