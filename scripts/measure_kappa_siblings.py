"""
Stage B: does the *within-state* sign of delta kappa_safe track the outcome?

Stage A regressed an absolute state descriptor and lost to step and occupied
volume. Siblings of one state share step, occupancy, remaining pool and
episode difficulty, so a within-state difference drops those confounds. That
is the quantity the b000-k15 stride-4 result actually exercised, and it is
the one worth testing.

    sign[ kappa_safe(T(s,a)) - kappa_safe(T(s,a')) ]  versus
    sign[ outcome(s^a) - outcome(s^a') ]

Two successor states are built per candidate, and using the wrong one is a
trap this script is arranged to avoid:

* **commanded** - the settled proxy of the action as issued. This is the only
  legitimate predictor of the *immediate* settle outcome.
* **realised** - the item at `x_plus`, the pose the official validator
  actually observed after settling, with its measured settle AABB.

Scoring immediate survival with the realised successor would be circular: a
candidate that toppled leaves a wrecked state, so kappa would be reading the
failure back rather than predicting it. So immediate survival is scored
against the commanded successor only, and the realised successor is used for
horizons beyond the settle that already happened.

Outcome components are recorded **separately**, never pre-combined into a
lexicographic key:

* `physical_survival` - the official `is_placed_safe`. Real physics, from
  the committed candidate labels; no new simulator run.
* `placed`, `volume` - a bounded rollout from the successor. A static proxy,
  and labelled as one.

The rollout is instrumented at the coverage setting that was measured to
work (stride 4). At stride 1 the late-episode rollout is silent on 0/2
observations, so evaluating kappa differences through it would manufacture
the same all-equal degeneracy Stage A hit.
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import statistics
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measure_residual_capacity import (  # noqa: E402
    load_agent_module,
    rebuild_case_items,
)
from scripts.measure_safe_capacity import (  # noqa: E402
    WEIGHTINGS,
    snapshot_capacity,
)

SCHEMA_VERSION = 1
DEFAULT_Q_BAND = 0.15
DEFAULT_SIBLINGS = 4
DEFAULT_STRIDE = 4


def sibling_candidates(
    rows: list[dict[str, Any]],
    *,
    q_band: float,
    limit: int,
) -> list[dict[str, Any]]:
    """
    Q-band siblings of one state, diversified by item.

    The band is the existing enforce-band structure rather than a new
    constant. Diversifying by item stops one baggage instance with many
    near-identical anchors from filling the whole comparison set, which is
    the same failure the rollout Top-K already has to defend against.
    """
    labelled = [
        row for row in rows
        if (row.get("physical") or {}).get("is_placed_safe") is not None
    ]
    if not labelled:
        return []
    best = max(float(row["score_immediate"]) for row in labelled)
    in_band = [
        row for row in labelled
        if float(row["score_immediate"]) >= best - float(q_band)
    ]
    in_band.sort(
        key=lambda row: (-float(row["score_immediate"]), row["candidate_id"])
    )
    chosen: list[dict[str, Any]] = []
    seen_items: set[int] = set()
    for row in in_band:
        if int(row["item_index"]) in seen_items:
            continue
        seen_items.add(int(row["item_index"]))
        chosen.append(row)
        if len(chosen) >= limit:
            break
    for row in in_band:
        if len(chosen) >= limit:
            break
        if row not in chosen:
            chosen.append(row)
    return chosen


def commanded_successor(agent, observation, row):
    """Successor under the settled proxy of the action as issued."""
    successor = copy.deepcopy(observation)
    containers = successor["container_list"]
    item = successor["pool_list"][int(row["pool_index"])]
    candidate = agent.AABB(
        tuple(float(v) for v in row["center"]),
        tuple(float(v) for v in row["size"]),
        str(row["kind"]),
    )
    decision = agent.PlacementDecision(
        action={
            "item_idx": int(row["pool_index"]),
            "container_idx": int(row["container_index"]),
            "place_pos": np.asarray(
                row.get("action_center", row["center"]), dtype=np.float32
            ),
            "orientation": int(row["orientation"]),
        },
        candidate=candidate,
        score=float(row["score_immediate"]),
    )
    agent.apply_placement_decision(item, decision, containers)
    return successor


def realised_successor(observation, row):
    """
    Successor at the pose the official validator actually observed.

    `packed_items` are world-frame with an observed quaternion, which is
    exactly what `x_plus` holds, so this appends a real post-settle state
    rather than a proxy of one.
    """
    physical = row.get("physical") or {}
    x_plus = physical.get("x_plus") or {}
    if not x_plus.get("position") or not x_plus.get("quaternion"):
        return None
    successor = copy.deepcopy(observation)
    container = successor["container_list"][int(row["container_index"])]
    item = copy.deepcopy(successor["pool_list"][int(row["pool_index"])])
    item["pos"] = [float(v) for v in x_plus["position"]]
    item["orn"] = [float(v) for v in x_plus["quaternion"]]
    item["belongs_to"] = int(row["container_index"])
    container.setdefault("packed_items", []).append(item)
    return successor


def rollout_outcome(agent, observation, row, *, depth, attempts, stride):
    """Bounded static rollout from a successor state; proxy, not physics."""
    indexed = [
        (index, item)
        for index, item in agent.capped_online_items(
            observation.get("pool_list", []),
            agent.MAX_POOL_ITEMS_EVALUATED,
            mode=agent.ITEM_COVERAGE_MODE,
        )
        if int(index) != int(row["pool_index"])
    ]
    placed = 0
    volume = 0.0
    containers = copy.deepcopy(observation.get("container_list", []))
    pool = observation.get("pool_list", [])
    remaining = list(indexed)
    for _ in range(max(0, int(depth))):
        if not remaining:
            break
        decision, _attempts, _accepted = agent.bounded_rollout_decision(
            {"pool_list": pool, "container_list": containers},
            remaining,
            attempts,
            stride=stride,
        )
        if decision is None or decision.candidate.name == "release_candidate":
            break
        index = int(decision.action["item_idx"])
        item = pool[index]
        agent.apply_placement_decision(item, decision, containers)
        placed += 1
        volume += float(item["length"] * item["width"] * item["height"])
        remaining = [
            (i, it) for i, it in remaining if int(i) != index
        ]
    return {"placed": placed, "volume": round(volume, 6)}


def sign(value: float, tolerance: float = 1e-9) -> int:
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=pathlib.Path,
        default=ROOT / "reports" / "replay-dataset",
    )
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--q-band", type=float, default=DEFAULT_Q_BAND)
    parser.add_argument("--siblings", type=int, default=DEFAULT_SIBLINGS)
    parser.add_argument("--capacity-stride", type=int, default=16)
    parser.add_argument("--accept-cap", type=int, default=64)
    parser.add_argument("--rollout-stride", type=int, default=DEFAULT_STRIDE)
    parser.add_argument("--rollout-depth", type=int, default=2)
    parser.add_argument("--rollout-attempts", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--include-final-holdout",
        action="store_true",
        help="RELEASE_RISK_PROTOCOL 3.1: off unless deliberately opened",
    )
    args = parser.parse_args()

    agent = load_agent_module()
    states = []
    skipped_holdout: list[str] = []
    for manifest_path in sorted(args.dataset_root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("split") == "final_holdout"
            and not args.include_final_holdout
        ):
            skipped_holdout.append(manifest_path.parent.name)
            continue
        case = manifest.get("case") or {}
        for step in case.get("steps", []):
            if step.get("status") != "ok":
                continue
            state_path = manifest_path.parent / (step.get("snapshot_path") or "")
            rows_path = manifest_path.parent / (step.get("dataset_path") or "")
            if not state_path.exists() or not rows_path.exists():
                continue
            states.append(
                {
                    "case_id": case.get("case_id"),
                    "step": int(step["step"]),
                    "state_path": state_path,
                    "rows_path": rows_path,
                }
            )
    if args.limit > 0:
        states = states[: args.limit]
    if not states:
        raise SystemExit("no labelled states found")

    results = []
    for index, state in enumerate(states, start=1):
        snapshot = json.loads(state["state_path"].read_text(encoding="utf-8"))
        observation = snapshot["observation"]
        rows = [
            json.loads(line)
            for line in state["rows_path"].read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]
        siblings = sibling_candidates(
            rows, q_band=args.q_band, limit=args.siblings
        )
        if len(siblings) < 2:
            continue
        item_list, _count = rebuild_case_items(state["case_id"])
        evaluated = []
        for row in siblings:
            commanded = commanded_successor(agent, observation, row)
            realised = realised_successor(observation, row)
            entry = {
                "candidate_id": row["candidate_id"],
                "item_index": int(row["item_index"]),
                "kind": row["kind"],
                "q": float(row["score_immediate"]),
                "selected": bool(row.get("selected")),
                "physical_survival": int(
                    bool(row["physical"]["is_placed_safe"])
                ),
                "settle_angle_deg": (
                    row["physical"].get("settle_metrics") or {}
                ).get("settle_angle_deg"),
                "kappa_commanded": snapshot_capacity(
                    agent,
                    commanded,
                    item_list,
                    stride=args.capacity_stride,
                    phase=0,
                    accept_cap=args.accept_cap,
                )["totals"],
            }
            if realised is not None:
                entry["kappa_realised"] = snapshot_capacity(
                    agent,
                    realised,
                    item_list,
                    stride=args.capacity_stride,
                    phase=0,
                    accept_cap=args.accept_cap,
                )["totals"]
                entry["rollout"] = rollout_outcome(
                    agent,
                    realised,
                    row,
                    depth=args.rollout_depth,
                    attempts=args.rollout_attempts,
                    stride=args.rollout_stride,
                )
            evaluated.append(entry)
        results.append(
            {
                "case_id": state["case_id"],
                "step": state["step"],
                "siblings": evaluated,
            }
        )
        print(
            f"[{index}/{len(states)}] {state['case_id']} step {state['step']} "
            f"siblings={len(evaluated)}",
            file=sys.stderr,
            flush=True,
        )

    # Pairwise sign agreement, per weighting and per outcome component.
    pairs: dict[str, dict[str, list[int]]] = {}
    for state in results:
        siblings = state["siblings"]
        for i in range(len(siblings)):
            for j in range(i + 1, len(siblings)):
                a, b = siblings[i], siblings[j]
                outcomes = {
                    "physical_survival": (
                        a["physical_survival"] - b["physical_survival"],
                        "kappa_commanded",
                    ),
                }
                if "rollout" in a and "rollout" in b:
                    outcomes["rollout_placed"] = (
                        a["rollout"]["placed"] - b["rollout"]["placed"],
                        "kappa_realised",
                    )
                    outcomes["rollout_volume"] = (
                        a["rollout"]["volume"] - b["rollout"]["volume"],
                        "kappa_realised",
                    )
                for outcome, (delta, kappa_key) in outcomes.items():
                    if kappa_key not in a or kappa_key not in b:
                        continue
                    outcome_sign = sign(float(delta))
                    if outcome_sign == 0:
                        continue
                    for rule in WEIGHTINGS:
                        kappa_delta = sign(
                            float(a[kappa_key][rule]) - float(b[kappa_key][rule])
                        )
                        if kappa_delta == 0:
                            slot = "tied"
                        elif kappa_delta == outcome_sign:
                            slot = "agree"
                        else:
                            slot = "disagree"
                        bucket = pairs.setdefault(
                            outcome, {}
                        ).setdefault(rule, [0, 0, 0])
                        bucket[
                            {"agree": 0, "disagree": 1, "tied": 2}[slot]
                        ] += 1

    agreement = {}
    for outcome, per_rule in pairs.items():
        agreement[outcome] = {}
        for rule, (agree, disagree, tied) in per_rule.items():
            decided = agree + disagree
            agreement[outcome][rule] = {
                "agree": agree,
                "disagree": disagree,
                "tied": tied,
                "decided": decided,
                "agreement_rate": (
                    round(agree / decided, 4) if decided else None
                ),
                "tie_rate": (
                    round(tied / (decided + tied), 4)
                    if (decided + tied)
                    else None
                ),
            }

    report = {
        "schema_version": SCHEMA_VERSION,
        "settings": {
            "q_band": args.q_band,
            "siblings": args.siblings,
            "capacity_stride": args.capacity_stride,
            "accept_cap": args.accept_cap,
            "rollout_stride": args.rollout_stride,
            "rollout_depth": args.rollout_depth,
            "rollout_attempts": args.rollout_attempts,
        },
        "contract": {
            "physical_survival": (
                "official is_placed_safe from the committed candidate "
                "labels; scored against the COMMANDED successor only, "
                "because the realised successor already contains the "
                "outcome and scoring it would be circular"
            ),
            "rollout_placed_volume": (
                "bounded static rollout from the REALISED successor at "
                "stride 4; a proxy, not physics, and the settle it follows "
                "has already happened"
            ),
            "components": "recorded separately, never lexicographically merged",
        },
        "skipped_final_holdout_datasets": skipped_holdout,
        "states": len(results),
        "agreement": agreement,
        "rows": results,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        {"states": len(results), "agreement": agreement}, indent=2
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
