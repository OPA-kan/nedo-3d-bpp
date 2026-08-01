"""Offline visible-pool rollout shadow for Ranker divergence snapshots."""
from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measure_anchor_recall import (  # noqa: E402
    load_agent_module,
    policy_indexed_items,
)

SCHEMA_VERSION = 1


def selected_rollout_rows(
    rows: list[dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    """Immediate top-K plus both observed divergence actions."""
    ordered = sorted(
        rows,
        key=lambda row: (
            float(row.get("q_active", -float("inf"))),
            str(row.get("candidate_id", "")),
        ),
        reverse=True,
    )
    chosen: dict[str, dict[str, Any]] = {}
    for row in ordered[: max(0, int(top_k))]:
        chosen[str(row["candidate_id"])] = row
    for row in rows:
        if row.get("left_selected") or row.get("right_selected"):
            chosen[str(row["candidate_id"])] = row
    return sorted(
        chosen.values(),
        key=lambda row: (
            float(row.get("q_active", -float("inf"))),
            str(row.get("candidate_id", "")),
        ),
        reverse=True,
    )


def decision_from_row(agent_module, row: dict[str, Any]):
    candidate = agent_module.AABB(
        tuple(float(value) for value in row["center"]),
        tuple(float(value) for value in row["size"]),
        str(row["kind"]),
    )
    return agent_module.PlacementDecision(
        action={
            "item_idx": int(row["pool_index"]),
            "container_idx": int(row["container_index"]),
            "place_pos": np.asarray(
                row.get("action_center", row["center"]),
                dtype=np.float32,
            ),
            "orientation": int(row["orientation"]),
        },
        candidate=candidate,
        score=float(row["q_active"]),
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Visible-pool rollout shadow",
        "",
        f"- snapshot: `{report['snapshot']}`",
        f"- depth: {report['settings']['depth']}",
        "- attempts per future step: "
        f"{report['settings']['attempts_per_step']}",
        "- initial release transitions use the settled proxy and are marked; "
        "future release transitions stop the branch before application.",
        "",
        "| rollout rank | item | immediate rank | Q_live | placed | "
        "added volume | P_rot sum | P_slide sum | terminal | observed |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in report["rows"]:
        observed = "/".join(
            label
            for label, enabled in (
                ("left", row["left_selected"]),
                ("right", row["right_selected"]),
            )
            if enabled
        ) or "-"
        lines.append(
            "| {rollout_rank} | {item_index} | {immediate_rank} | "
            "{q_active:.4f} | {placed_count} | {added_volume:.4f} | "
            "{cumulative_rotation_risk:.4f} | "
            "{cumulative_slide_risk:.4f} | {terminal_reason} | "
            "{observed} |".format(observed=observed, **row)
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "This is a deterministic static-proxy rollout over the currently "
            "visible pool. It is not a value over unknown future arrivals and "
            "does not claim physical validity for a release settle.",
            "",
        ]
    )
    return "\n".join(lines)


def build_report(
    snapshot_path: pathlib.Path,
    divergence_path: pathlib.Path,
    *,
    top_k: int,
    depth: int,
    attempts_per_step: int,
) -> dict[str, Any]:
    agent_module = load_agent_module()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    divergence = json.loads(divergence_path.read_text(encoding="utf-8"))
    observation = snapshot["observation"]
    population = divergence.get("candidates", divergence.get("rows", []))
    selected = selected_rollout_rows(population, top_k)
    indexed_items = policy_indexed_items(agent_module, observation)
    risk_lambda = (
        agent_module.RELEASE_RISK_RERANK_LAMBDA
        if agent_module.RELEASE_RISK_LIVE_RERANK
        else None
    )
    rows = []
    for source in selected:
        decision = decision_from_row(agent_module, source)
        value = agent_module.visible_pool_rollout_value(
            observation,
            indexed_items,
            decision,
            depth=depth,
            attempts_per_step=attempts_per_step,
            risk_lambda=risk_lambda,
        )
        row = {
            "candidate_id": source["candidate_id"],
            "item_index": int(source["item_index"]),
            "pool_index": int(source["pool_index"]),
            "kind": str(source["kind"]),
            "immediate_rank": int(source["across_candidate_rank"]),
            "q_active": float(source["q_active"]),
            "left_selected": bool(source.get("left_selected", False)),
            "right_selected": bool(source.get("right_selected", False)),
            **dataclasses.asdict(value),
        }
        row["rollout_key"] = list(
            agent_module.visible_pool_rollout_rank_key(value)
        )
        rows.append(row)
    rows.sort(
        key=lambda row: (tuple(row["rollout_key"]), row["q_active"]),
        reverse=True,
    )
    for rank, row in enumerate(rows, start=1):
        row["rollout_rank"] = rank
    return {
        "schema_version": SCHEMA_VERSION,
        "snapshot": snapshot_path.as_posix(),
        "divergence_report": divergence_path.as_posix(),
        "case_id": snapshot.get("case_id"),
        "step": snapshot.get("step"),
        "settings": {
            "top_k": int(top_k),
            "depth": int(depth),
            "attempts_per_step": int(attempts_per_step),
            "indexed_item_count": len(indexed_items),
            "forced_observed_actions": True,
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument(
        "--divergence-report", type=pathlib.Path, required=True
    )
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--attempts-per-step", type=int, default=512)
    args = parser.parse_args()
    report = build_report(
        args.snapshot,
        args.divergence_report,
        top_k=args.top_k,
        depth=args.depth,
        attempts_per_step=args.attempts_per_step,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "report.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    print(json.dumps({
        "rows": len(report["rows"]),
        "best_item": report["rows"][0]["item_index"] if report["rows"] else None,
        "output": args.output_dir.as_posix(),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
