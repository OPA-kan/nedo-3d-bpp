"""Build the joint outcome scorer dataset from paired physical manifests.

Each JointOutcomeSample v2 collected under ``paired_round_robin`` becomes
one training row: the searched root's state set tensors plus the commanded
root action are the inputs, and the raw joint outcome vector with its
per-head eligibility mask is the target. Provider rank/score/prior and
proposal provenance are carried for audit and splitting only and are
placed outside the feature payload, per
``reports/self-play-packing/joint-outcome-scorer-contract.md``.
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

try:
    from scripts.audit_paired_physical_contract import (
        PARETO_OBJECTIVES,
        UNMEASURED_BRANCH_HEADS,
    )
    from scripts.self_play_packing_search import MULTI_HEAD_SPECS
except ModuleNotFoundError:
    from audit_paired_physical_contract import (
        PARETO_OBJECTIVES,
        UNMEASURED_BRANCH_HEADS,
    )
    from self_play_packing_search import MULTI_HEAD_SPECS


TARGET_HEADS = tuple(
    name for name in MULTI_HEAD_SPECS if name not in UNMEASURED_BRANCH_HEADS
)

ACTION_FEATURES = (
    "container_index",
    "orientation_index",
    "place_x",
    "place_y",
    "place_z",
)


def _action_features(command: dict[str, Any]) -> list[float]:
    position = command["place_pos"]
    return [
        float(command["container_idx"]),
        float(command["orientation"]),
        float(position[0]),
        float(position[1]),
        float(position[2]),
    ]


def _acting_item_features(
    state: dict[str, Any], stable_item_index: int,
) -> list[float]:
    # command_action.item_idx is positional in the environment's current
    # pool and shifts as items are placed; the snapshot's visible set is
    # keyed by stable item index, so the join must use
    # selection.stable_item_index (identity only, never rank or score).
    indices = list(state["visible_item_indices"])
    if stable_item_index not in indices:
        raise ValueError(
            f"acting item {stable_item_index} is not in the visible set {indices}"
        )
    return [
        float(v)
        for v in state["visible_item_values"][indices.index(stable_item_index)]
    ]


def _root_state(
    run_dir: pathlib.Path, game_index: int, record: dict[str, Any],
) -> dict[str, Any]:
    snapshot_path = record.get("state_snapshot_path")
    if not snapshot_path:
        raise ValueError("record has no state snapshot to recover the root state")
    snapshot = json.loads(
        (run_dir / f"game-{game_index:03d}" / snapshot_path).read_text(
            encoding="utf-8"
        )
    )
    try:
        from scripts.counterfactual_graph import state_tensor_from_snapshot
    except ModuleNotFoundError:
        from counterfactual_graph import state_tensor_from_snapshot
    return state_tensor_from_snapshot(snapshot)


def build_rows(
    run_dir: pathlib.Path, *, cell_id: str,
    state_loader: Any = None,
) -> list[dict[str, Any]]:
    if state_loader is None:
        state_loader = _root_state
    manifest = json.loads(
        (run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    mcts = (manifest.get("selection") or {}).get("mcts") or {}
    if mcts.get("root_allocation_mode") != "paired_round_robin":
        raise ValueError(
            f"{run_dir} was not collected under paired_round_robin"
        )
    rows: list[dict[str, Any]] = []
    for game_index, game in enumerate(manifest.get("games") or []):
        for record in game.get("records") or []:
            search = record.get("search")
            if not search:
                continue
            root_state = state_loader(run_dir, game_index, record)
            commands = {
                entry["candidate_id"]: entry["command_action"]
                for entry in record.get("candidate_set") or []
            }
            stable_items = {
                entry["candidate_id"]: entry.get("selection", {}).get(
                    "stable_item_index"
                )
                for entry in record.get("candidate_set") or []
            }
            for sample in search.get("multi_head_branch_samples") or []:
                candidate = str(sample["root_candidate_id"])
                command = commands.get(candidate)
                if command is None:
                    raise ValueError(
                        f"sample candidate {candidate} missing from candidate_set"
                    )
                vector = sample.get("raw_outcome_vector") or {}
                eligibility = sample.get("head_eligibility") or {}
                rows.append({
                    "schema_version": 1,
                    "contract": "joint_outcome_scorer_row_v1",
                    "cell_id": cell_id,
                    "root_id": sample["root_id"],
                    "outcome_sample_id": sample["outcome_sample_id"],
                    "candidate_set_id": sample["candidate_set_id"],
                    "root_candidate_id": candidate,
                    "exogenous_world_id": sample["exogenous_world_id"],
                    "exogenous_world_sample_index": int(
                        sample["exogenous_world_sample_index"]
                    ),
                    "step": int(record["step"]),
                    "features": {
                        "state": root_state,
                        "action": _action_features(command),
                        "acting_item": _acting_item_features(
                            root_state, int(stable_items[candidate])
                        ),
                    },
                    "targets": {
                        head: (
                            float(vector[head])
                            if eligibility.get(head) is True
                            and vector.get(head) is not None
                            else None
                        )
                        for head in TARGET_HEADS
                    },
                    "target_mask": {
                        head: bool(eligibility.get(head) is True)
                        for head in TARGET_HEADS
                    },
                    "termination": sample.get("termination"),
                    "continuation_censored": bool(
                        sample.get("continuation_censored")
                    ),
                    # audit/split only, never features
                    "audit_only": {
                        "provenance": sample.get("root_candidate_provenance"),
                        "selection_rank": (
                            record.get("candidate_set") and next(
                                (
                                    entry.get("selection", {}).get("rank")
                                    for entry in record["candidate_set"]
                                    if entry["candidate_id"] == candidate
                                ),
                                None,
                            )
                        ),
                    },
                })
    if not rows:
        raise ValueError(f"{run_dir} produced no joint outcome rows")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="append", required=True,
        metavar="CELL_ID=RUN_DIR",
        help="paired run directory labelled with its collection cell id",
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    for spec in args.run:
        cell_id, _, run_dir = spec.partition("=")
        if not run_dir:
            raise SystemExit(f"expected CELL_ID=RUN_DIR, got: {spec}")
        rows.extend(build_rows(pathlib.Path(run_dir), cell_id=cell_id))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    cells = sorted({row["cell_id"] for row in rows})
    roots = len({row["root_id"] for row in rows})
    eligible = sum(
        1 for row in rows if all(row["target_mask"].values())
    )
    print(
        f"rows={len(rows)} roots={roots} cells={len(cells)} "
        f"fully_eligible={eligible} heads={len(TARGET_HEADS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
