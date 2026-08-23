"""Aggregate sharded paired component-value continuation evidence."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib


def _summarize(records: list[dict], *, beta: float, proposal_count: int) -> dict:
    """Pure-stdlib summary; aggregate runners need no simulator stack."""
    valid = [row for row in records if row.get("execution_valid")]
    relations = collections.Counter(
        row["comparison"]["pareto_relation"] for row in valid
    )
    deltas = [row["comparison"]["raw_deltas"] for row in valid]

    def mean(name: str) -> float | None:
        values = [float(row[name]) for row in deltas if row.get(name) is not None]
        return sum(values) / len(values) if values else None

    return {
        "schema_version": 1,
        "experiment": "paired_component_value_continuation",
        "scalarization": False,
        "discovery_beta": float(beta),
        "proposal_count": int(proposal_count),
        "executed_records": len(records),
        "valid_records": len(valid),
        "pareto_relations": dict(sorted(relations.items())),
        "mean_candidate_minus_incumbent": {
            name: mean(name) for name in (
                "fill", "cog", "placement", "soft", "gate",
                "stability.max_shift", "stability.peak_kinetic_energy",
                "stability.items_shifted", "stability.items_toppled",
            )
        },
        "official_score_claim": False,
        "reason": (
            "official component normalization and weights are unpublished; "
            "local stability is a deterministic proxy"
        ),
        "records": records,
    }


def aggregate(
    shards: list[dict], *, expected_proposals: int | None = None,
) -> dict:
    if not shards:
        raise ValueError("no paired-continuation shards")
    beta = float(shards[0]["discovery_beta"])
    proposal_count = int(shards[0]["proposal_count"])
    if any(float(row["discovery_beta"]) != beta for row in shards):
        raise ValueError("shards use different discovery beta values")
    if any(int(row["proposal_count"]) != proposal_count for row in shards):
        raise ValueError("shards disagree on proposal count")
    if expected_proposals is not None and proposal_count != expected_proposals:
        raise ValueError(
            f"expected {expected_proposals} proposals, observed {proposal_count}"
        )
    records = [record for shard in shards for record in shard.get("records", [])]
    keys = [(row["pair_id"], int(row["step"])) for row in records]
    if len(keys) != len(set(keys)):
        raise ValueError("paired root appears in multiple shards")
    if len(records) != proposal_count:
        raise ValueError(
            f"expected {proposal_count} executed proposals, observed {len(records)}"
        )
    return _summarize(records, beta=beta, proposal_count=proposal_count)


def render_markdown(result: dict) -> str:
    relations = ", ".join(
        f"{name}={count}"
        for name, count in result["pareto_relations"].items()
    ) or "none"
    means = result["mean_candidate_minus_incumbent"]
    return "\n".join([
        "# Paired component-value continuation",
        "",
        f"- discovery beta: {result['discovery_beta']}",
        f"- proposals / valid: {result['proposal_count']} / {result['valid_records']}",
        f"- Pareto relations: {relations}",
        f"- mean fill delta: {means['fill']}",
        f"- mean CoG-z delta: {means['cog']}",
        f"- mean soft delta: {means['soft']}",
        f"- mean priority delta: {means['placement']}",
        f"- mean placed-gate delta: {means['gate']}",
        f"- mean shake peak-KE delta: {means['stability.peak_kinetic_energy']}",
        "- cross-axis scalarization: **disabled**",
        "- official score improvement claim: **disabled**",
        "",
        "> These are deterministic local paired measurements; official normalization and weights remain unpublished.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--expected-proposals", type=int)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.root.rglob("shard-*.json"))
    result = aggregate(
        [json.loads(path.read_text(encoding="utf-8")) for path in paths],
        expected_proposals=args.expected_proposals,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
