"""
Does the late-episode rollout silence come from a coverage hole?

The rollout enforce ablation (Actions run 30716558143) measured rollout
non-degeneracy at 138/240 (57.5%) for steps 0-9 and 2/166 (1.2%) from step 10
onward. Two mechanisms produce that number and they demand opposite
responses:

* *saturation* - the container really is full, no future placement exists,
  and every Top-K action has the same consequence. Nothing to fix.
* *coverage hole* - future placements do exist, but the per-step anchor
  budget is spent on the dense infeasible prefix of the anchor scan and
  never reaches them. Every rollout returns `placed_count = 0`, the keys
  tie, and the tie is an artefact of the measurement.

This script separates them on saved snapshots, offline and deterministically.
Three arm families are evaluated on the same reconstructed Top-K:

* `baseline` - the shipped shadow setting (stride 1, 64 attempts/step).
* `stride-S` - the same attempt budget, systematically subsampling every
  S-th anchor. Same cost, wider reach.
* `budget-N` - stride 1 with N attempts/step, up to the offline analysis
  default of 512. This is the reach oracle: whatever `budget-512` cannot
  find is evidence for real saturation, not for a hole.

If `stride-S` recovers a large part of what `budget-N` recovers, the late
silence is a coverage hole and it is cheap to close. If both stay degenerate
the endgame is genuinely saturated and the enforce failure has to be
explained somewhere else.

The immediate Top-K is reconstructed with a fixed attempt budget rather than
a wall-clock deadline, so a rerun on another machine produces the same rows.
It is a deterministic stand-in for the live `VisiblePoolRolloutCollector`,
not a replay of any particular deadline-limited live search.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import pathlib
import statistics
import sys
import time
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
DEFAULT_LATE_STEP = 10
DEFAULT_IMMEDIATE_BUDGET = 4096


def build_arms(
    strides: list[int],
    budgets: list[int],
    base_attempts: int,
    offsets: list[int] | None = None,
) -> list[dict[str, Any]]:
    arms = [
        {
            "name": "baseline",
            "family": "baseline",
            "stride": 1,
            "stride_offset": 0,
            "attempts_per_step": int(base_attempts),
        }
    ]
    # A single stride phase can be lucky. Every requested offset that is a
    # valid phase for that stride is measured separately so the spread
    # across phases is visible instead of assumed away.
    phases = [0] if not offsets else sorted({int(o) for o in offsets})
    for stride in strides:
        stride = int(stride)
        if stride <= 1:
            continue
        for offset in phases:
            if offset >= stride:
                continue
            suffix = "" if offset == 0 else f"+{offset}"
            arms.append(
                {
                    "name": f"stride-{stride}{suffix}",
                    "family": "stride",
                    "stride": stride,
                    "stride_offset": offset,
                    "attempts_per_step": int(base_attempts),
                }
            )
    arms.extend(
        {
            "name": f"budget-{budget}",
            "family": "budget",
            "stride": 1,
            "stride_offset": 0,
            "attempts_per_step": int(budget),
        }
        for budget in budgets
        if int(budget) != int(base_attempts)
    )
    return arms


def reconstruct_top_k(
    agent_module,
    observation: dict[str, Any],
    indexed_items: list[tuple[int, dict[str, Any]]],
    *,
    immediate_budget: int,
    risk_lambda: float | None,
) -> tuple[list[Any], Any, int]:
    """
    Deterministic stand-in for the live collector's class-diverse Top-K.

    The live observer keeps the best accepted candidate per stable item from
    whatever the deadline-limited search happened to visit. Here the same
    stream is consumed under a fixed attempt budget, so the set is
    reproducible. Stride is deliberately *not* applied: this reconstructs the
    actions under comparison, and the experiment is about how their
    consequences are searched, not about changing the comparison set.
    """
    containers = observation.get("container_list", [])
    has_priority_container = any(
        bool(container.get("is_prioritized", False))
        for container in containers
    )
    collector = agent_module.VisiblePoolRolloutCollector()
    observed = 0
    stream = agent_module.iter_prioritized_candidates(
        observation,
        indexed_items,
        attempt_budget=int(immediate_budget),
    )
    for item_idx, item, container_idx, orientation, candidate in stream:
        container = containers[container_idx]
        score = agent_module.Ranker.score(
            candidate, item, container, has_priority_container
        )
        score, _probability = agent_module.risk_adjusted_score(
            score,
            candidate,
            item,
            container,
            orientation,
            risk_lambda,
        )
        decision = agent_module.PlacementDecision(
            action={
                "item_idx": int(item_idx),
                "container_idx": int(container_idx),
                "place_pos": np.asarray(
                    agent_module.simulator_action_center(
                        candidate, container
                    ),
                    dtype=np.float32,
                ),
                "orientation": int(orientation),
            },
            candidate=candidate,
            score=float(score),
        )
        collector.observe(
            item_idx, item, container_idx, orientation, decision
        )
        observed += 1
    top_k = collector.snapshot(agent_module.VISIBLE_POOL_ROLLOUT_TOP_K)
    selected = max(
        collector.snapshot(),
        key=lambda decision: float(decision.score),
        default=None,
    )
    return top_k, selected, observed


def measure_snapshot(
    agent_module,
    snapshot_path: pathlib.Path,
    arms: list[dict[str, Any]],
    *,
    depth: int,
    immediate_budget: int,
) -> dict[str, Any]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    observation = snapshot["observation"]
    indexed_items = policy_indexed_items(agent_module, observation)
    risk_lambda = (
        agent_module.RELEASE_RISK_RERANK_LAMBDA
        if agent_module.RELEASE_RISK_LIVE_RERANK
        else None
    )
    top_k, selected, observed = reconstruct_top_k(
        agent_module,
        observation,
        indexed_items,
        immediate_budget=immediate_budget,
        risk_lambda=risk_lambda,
    )
    packed = sum(
        len(container.get("packed_items", []))
        for container in observation.get("container_list", [])
    )
    result: dict[str, Any] = {
        "snapshot": snapshot_path.as_posix(),
        "case_id": snapshot.get("case_id"),
        "step": int(snapshot.get("step", -1)),
        "pool_size": len(observation.get("pool_list", [])),
        "packed_items": int(packed),
        "searched_items": len(indexed_items),
        "immediate_attempts_observed": int(observed),
        "top_k_size": len(top_k),
        "arms": {},
    }
    if selected is None or not top_k:
        result["skipped_reason"] = "no immediate candidate reconstructed"
        return result
    for arm in arms:
        started = time.perf_counter()
        record, _proposal = agent_module.visible_pool_rollout_evaluation(
            observation,
            indexed_items,
            top_k,
            selected,
            depth=depth,
            attempts_per_step=arm["attempts_per_step"],
            stride=arm["stride"],
            stride_offset=arm["stride_offset"],
            risk_lambda=risk_lambda,
        )
        elapsed = time.perf_counter() - started
        candidates = record.get("candidates", [])
        placed = [int(row["value"]["placed_count"]) for row in candidates]
        attempts = [int(row["value"]["attempts_used"]) for row in candidates]
        terminal = sorted(
            {str(row["value"]["terminal_reason"]) for row in candidates}
        )
        result["arms"][arm["name"]] = {
            "stride": int(arm["stride"]),
            "stride_offset": int(arm["stride_offset"]),
            "attempts_per_step": int(arm["attempts_per_step"]),
            "non_degenerate": bool(record["non_degenerate"]),
            "candidate_count": int(record["candidate_count"]),
            "distinct_keys": len(
                {tuple(row["rollout_key"]) for row in candidates}
            ),
            "max_placed": max(placed, default=0),
            "total_placed": sum(placed),
            "any_future_placement": bool(max(placed, default=0) > 0),
            "attempts_used_total": sum(attempts),
            "terminal_reasons": terminal,
            "would_change_item": bool(record["would_change_item"]),
            "elapsed_ms": round(elapsed * 1000.0, 3),
        }
    return result


_WORKER_AGENT = None


def _worker_agent():
    """One agent module per process; loading it is not cheap."""
    global _WORKER_AGENT
    if _WORKER_AGENT is None:
        _WORKER_AGENT = load_agent_module()
    return _WORKER_AGENT


def _measure_one(work_item):
    snapshot, arms, depth, immediate_budget = work_item
    return measure_snapshot(
        _worker_agent(),
        pathlib.Path(snapshot),
        arms,
        depth=depth,
        immediate_budget=immediate_budget,
    )


def _progress(index: int, total: int, row: dict[str, Any]) -> None:
    print(
        f"[{index}/{total}] {row['case_id']} step {row['step']}",
        file=sys.stderr,
        flush=True,
    )


def _rate(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def summarize(
    rows: list[dict[str, Any]],
    arms: list[dict[str, Any]],
    late_step: int,
) -> dict[str, Any]:
    usable = [row for row in rows if row.get("arms")]
    bands = {
        "all": usable,
        f"early_step_lt_{late_step}": [
            row for row in usable if row["step"] < late_step
        ],
        f"late_step_ge_{late_step}": [
            row for row in usable if row["step"] >= late_step
        ],
    }
    summary: dict[str, Any] = {"snapshots": len(rows), "usable": len(usable)}
    for band_name, band_rows in bands.items():
        band: dict[str, Any] = {"snapshots": len(band_rows), "arms": {}}
        baseline_late = {
            row["snapshot"]
            for row in band_rows
            if not row["arms"]["baseline"]["non_degenerate"]
        }
        for arm in arms:
            name = arm["name"]
            values = [row["arms"][name] for row in band_rows]
            non_degenerate = sum(1 for v in values if v["non_degenerate"])
            with_future = sum(1 for v in values if v["any_future_placement"])
            recovered = sum(
                1
                for row in band_rows
                if row["snapshot"] in baseline_late
                and row["arms"][name]["non_degenerate"]
            )
            band["arms"][name] = {
                "stride": arm["stride"],
                "stride_offset": arm["stride_offset"],
                "attempts_per_step": arm["attempts_per_step"],
                "non_degenerate": non_degenerate,
                "non_degenerate_rate": _rate(non_degenerate, len(values)),
                "any_future_placement": with_future,
                "any_future_placement_rate": _rate(with_future, len(values)),
                "recovered_from_baseline_ties": recovered,
                "baseline_tied_snapshots": len(baseline_late),
                "mean_elapsed_ms": (
                    round(
                        statistics.fmean(v["elapsed_ms"] for v in values), 3
                    )
                    if values
                    else None
                ),
            }
        summary[band_name] = band
    return summary


def render_markdown(report: dict[str, Any]) -> str:
    settings = report["settings"]
    lines = [
        "# Stride x endgame rollout saturation",
        "",
        f"- snapshots: {report['summary']['snapshots']} "
        f"(usable {report['summary']['usable']})",
        f"- depth: {settings['depth']}",
        f"- late band: step >= {settings['late_step']}",
        f"- immediate Top-K budget: {settings['immediate_budget']} attempts",
        f"- Top-K: {settings['top_k']}",
        "",
        "`baseline` is the shipped shadow setting. `stride-S` holds the "
        "attempt budget fixed and widens the anchor scan; `budget-N` widens "
        "the budget at stride 1 and acts as the reach oracle.",
        "",
    ]
    for band in ("all", *[k for k in report["summary"] if k.startswith(
        ("early_step", "late_step")
    )]):
        if band not in report["summary"]:
            continue
        data = report["summary"][band]
        lines.extend(
            [
                f"## {band} ({data['snapshots']} snapshots)",
                "",
                "| arm | stride | attempts/step | non-degenerate | rate | "
                "any future placement | recovered baseline ties | "
                "mean ms |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for name, arm in data["arms"].items():
            lines.append(
                "| {name} | {stride} | {attempts_per_step} | "
                "{non_degenerate} | {rate} | {future} | "
                "{recovered}/{tied} | {ms} |".format(
                    name=name,
                    stride=arm["stride"],
                    attempts_per_step=arm["attempts_per_step"],
                    non_degenerate=arm["non_degenerate"],
                    rate=arm["non_degenerate_rate"],
                    future=arm["any_future_placement"],
                    recovered=arm["recovered_from_baseline_ties"],
                    tied=arm["baseline_tied_snapshots"],
                    ms=arm["mean_elapsed_ms"],
                )
            )
        lines.append("")
    lines.extend(
        [
            "## Interpretation boundary",
            "",
            "These are static-proxy rollouts on saved states, not PyBullet "
            "counterfactuals. Non-degeneracy is a property of the "
            "measurement, not a score: an arm that discriminates more is "
            "not thereby a better policy. The immediate Top-K is "
            "reconstructed under a fixed attempt budget and is not a replay "
            "of any specific deadline-limited live search, so these rates "
            "are comparable across arms but not directly equal to the live "
            "shadow rates from the enforce run.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot",
        type=pathlib.Path,
        action="append",
        default=[],
        help="explicit snapshot path; repeatable",
    )
    parser.add_argument(
        "--snapshot-glob",
        default="reports/replay-dataset/*/step-*-state.json",
        help="glob used when no explicit snapshot is given",
    )
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--base-attempts", type=int, default=64)
    parser.add_argument(
        "--stride", type=int, action="append", default=[]
    )
    parser.add_argument(
        "--stride-offset", type=int, action="append", default=[]
    )
    parser.add_argument(
        "--budget", type=int, action="append", default=[]
    )
    parser.add_argument("--late-step", type=int, default=DEFAULT_LATE_STEP)
    parser.add_argument(
        "--immediate-budget", type=int, default=DEFAULT_IMMEDIATE_BUDGET
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="measure this many snapshots in parallel processes",
    )
    args = parser.parse_args()

    snapshots = list(args.snapshot)
    if not snapshots:
        snapshots = sorted(ROOT.glob(args.snapshot_glob))
    if args.limit > 0:
        snapshots = snapshots[: args.limit]
    if not snapshots:
        raise SystemExit("no snapshots matched")

    agent_module = load_agent_module()
    arms = build_arms(
        args.stride or [2, 4, 8],
        args.budget or [256, 512],
        args.base_attempts,
        args.stride_offset,
    )
    jobs = max(1, int(args.jobs))
    work = [
        (
            pathlib.Path(path).as_posix(),
            arms,
            int(args.depth),
            int(args.immediate_budget),
        )
        for path in snapshots
    ]
    rows = []
    if jobs == 1:
        for index, item in enumerate(work, start=1):
            rows.append(_measure_one(item))
            _progress(index, len(work), rows[-1])
    else:
        # Every snapshot is measured independently from a file on disk, so
        # sharding across processes cannot change a result - only the wall
        # clock. Results are re-sorted below so the report does not depend
        # on completion order.
        with multiprocessing.get_context("spawn").Pool(jobs) as pool:
            for index, row in enumerate(
                pool.imap_unordered(_measure_one, work), start=1
            ):
                rows.append(row)
                _progress(index, len(work), row)
    rows.sort(key=lambda row: (str(row["case_id"]), int(row["step"])))
    report = {
        "schema_version": SCHEMA_VERSION,
        "settings": {
            "depth": int(args.depth),
            "base_attempts": int(args.base_attempts),
            "late_step": int(args.late_step),
            "immediate_budget": int(args.immediate_budget),
            "top_k": int(agent_module.VISIBLE_POOL_ROLLOUT_TOP_K),
            "generator_mode": str(agent_module.ANCHOR_GENERATOR_MODE),
            "arms": arms,
        },
        "summary": summarize(rows, arms, args.late_step),
        "rows": rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "report.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    print(json.dumps(report["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
