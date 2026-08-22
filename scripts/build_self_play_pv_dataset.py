"""Build leakage-audited P/V rows from physical Self-Play manifests."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.counterfactual_graph import (  # noqa: E402
    canonical_action,
    state_tensor_from_snapshot,
)

FORBIDDEN_KEYS = {"score", "immediate_score", "rank", "prior", "selection"}


def _forbidden_key_hits(value: Any, prefix: str = "") -> list[str]:
    hits = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in FORBIDDEN_KEYS:
                hits.append(path)
            hits.extend(_forbidden_key_hits(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_forbidden_key_hits(child, f"{prefix}[{index}]"))
    return hits


def _candidate_rows(record: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {
        str(row["candidate_id"]): row
        for row in record.get("candidate_set", [])
    }
    result = []
    for policy in target.get("policy_target", []):
        identifier = str(policy["candidate_id"])
        candidate = by_id.get(identifier)
        if candidate is None:
            raise ValueError(f"policy candidate {identifier} missing from legal set")
        result.append({
            "candidate_id": identifier,
            "command_action": canonical_action(candidate["command_action"]),
            "visits": int(policy.get("visits", 0)),
            "probability": float(policy.get("probability", 0.0)),
            "search_q": (
                None if policy.get("q") is None else float(policy["q"])
            ),
        })
    return result


def build_rows(root: pathlib.Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    trajectory_ids = set()
    for manifest_path in sorted(root.rglob("mcts/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        pair_id = manifest_path.parents[1].name
        for game_index, game in enumerate(manifest.get("games", [])):
            trajectory_id = str(game.get("trajectory_id"))
            trajectory_group = f"{pair_id}:{trajectory_id}"
            trajectory_ids.add(trajectory_group)
            records = {
                int(row["step"]): row for row in game.get("records", [])
            }
            captures = {
                int(row["step"]): row for row in game.get("captures", [])
            }
            for target in game.get("learning_targets", []):
                step = int(target["step"])
                capture = captures.get(step)
                if capture is None:
                    raise ValueError(f"missing capture for {trajectory_id} step {step}")
                snapshot_path = (
                    manifest_path.parent / f"game-{game_index:03d}"
                    / str(capture["snapshot_path"])
                )
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                record = records.get(step)
                policy_candidates = []
                if target.get("policy_target_eligible"):
                    if record is None:
                        raise ValueError(
                            f"missing action record for policy target step {step}"
                        )
                    policy_candidates = _candidate_rows(record, target)
                game_state = snapshot.get("self_play_game") or {}
                row = {
                    "schema_version": 1,
                    "trajectory_group": trajectory_group,
                    "root_trajectory_id": trajectory_id,
                    "pair_id": pair_id,
                    "case_id": manifest.get("case_id"),
                    "policy_generation": manifest.get("policy_generation"),
                    "step": step,
                    "model_visible_state_signature": capture.get(
                        "model_visible_state_signature"
                    ),
                    "game_state_signature": capture.get("game_state_signature"),
                    "state": state_tensor_from_snapshot(snapshot),
                    "game_features": {
                        "player_to_move": int(target["player_to_move"]),
                        "block_length": int(game_state.get("block_length", 0)),
                        "handoff_count": int(game_state.get("handoff_count", 0)),
                    },
                    "policy_target_eligible": bool(
                        target.get("policy_target_eligible")
                    ),
                    "policy_target": policy_candidates,
                    "value_target_eligible": bool(
                        target.get("value_target_eligible")
                    ),
                    "return_to_go": float(target.get("return_to_go", 0.0)),
                }
                hits = _forbidden_key_hits(row)
                if hits:
                    raise ValueError(
                        "forbidden heuristic leakage keys in P/V row: "
                        + ", ".join(hits)
                    )
                rows.append(row)
    if not rows:
        raise ValueError(f"no MCTS Self-Play targets found below {root}")
    policy_rows = [row for row in rows if row["policy_target_eligible"]]
    value_rows = [row for row in rows if row["value_target_eligible"]]
    nonuniform = [
        row for row in policy_rows
        if len({item["visits"] for item in row["policy_target"]}) > 1
    ]
    q_discriminating = [
        row for row in policy_rows
        if len({
            round(float(item["search_q"]), 12)
            for item in row["policy_target"]
            if item["search_q"] is not None and item["visits"] > 0
        }) > 1
    ]
    summary = {
        "schema_version": 1,
        "contract": "physical_search_pi_and_terminal_suffix_return_no_ranker_score",
        "rows": len(rows),
        "trajectory_groups": len(trajectory_ids),
        "unique_game_states": len({
            row["game_state_signature"] for row in rows
            if row["game_state_signature"]
        }),
        "policy_rows": len(policy_rows),
        "nonuniform_policy_rows": len(nonuniform),
        "search_q_discriminating_rows": len(q_discriminating),
        "value_rows": len(value_rows),
        "forbidden_heuristic_key_hits": 0,
        "forbidden_keys": sorted(FORBIDDEN_KEYS),
    }
    return rows, summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--summary", type=pathlib.Path, required=True)
    args = parser.parse_args()
    rows, summary = build_rows(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
