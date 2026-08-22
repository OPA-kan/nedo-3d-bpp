"""Re-search only physics-Q-discriminating Self-Play roots."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import random
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
for path in (ROOT, SIMULATOR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.build_counterfactual_graph import build_candidate_provider  # noqa: E402
from scripts.build_replay_dataset import (  # noqa: E402
    load_agent_module,
    policy_observation,
    state_snapshot,
)
from scripts.counterfactual_graph import replay_action_prefix, stable_id  # noqa: E402
from scripts.evaluate_self_play_puct_convergence import policy_signature  # noqa: E402
from scripts.run_self_play_packing import (  # noqa: E402
    build_exact_physical_legal_filter,
    build_physical_puct_search,
)
from scripts.self_play_packing_game import GameRules, GameState  # noqa: E402


BASE_SCHEDULE = (
    ("h2-s12-a", 2, 12),
    ("h2-s12-b", 2, 12),
    ("h2-s24", 2, 24),
    ("h2-s48", 2, 48),
    ("h3-s48", 3, 48),
    ("h5-s48", 5, 48),
)
PROMOTED_SCHEDULE = (
    ("h2-s96", 2, 96),
    ("h3-s96", 3, 96),
    ("h5-s96", 5, 96),
)


def _is_q_discriminating(record: dict[str, Any]) -> bool:
    values = {
        round(float(row["q"]), 12)
        for row in (record.get("search") or {}).get("policy_target", [])
        if row.get("q") is not None and int(row.get("visits", 0)) > 0
    }
    return len(values) > 1


def discover_roots(source_root: pathlib.Path) -> list[dict[str, Any]]:
    """Locate raw root instances, preserving duplicates across trajectories."""
    roots = []
    for manifest_path in sorted(source_root.rglob("mcts/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        case_id = str(manifest["case_id"])
        scenario = case_id.removeprefix("m-")
        config_path = manifest_path.parent.parent / "configs" / f"{scenario}.json"
        if not config_path.exists():
            raise FileNotFoundError(f"missing task config for {manifest_path}: {config_path}")
        for game_index, game in enumerate(manifest.get("games", [])):
            captures = {
                int(row["step"]): row
                for row in game.get("captures", [])
                if row.get("step") is not None
            }
            for record in game.get("records", []):
                if not _is_q_discriminating(record):
                    continue
                step = int(record["step"])
                capture = captures.get(step)
                if capture is None or not capture.get("snapshot_path"):
                    raise ValueError(f"Q-discriminating root lacks capture: {manifest_path} step={step}")
                snapshot_path = (
                    manifest_path.parent / f"game-{game_index:03d}"
                    / str(capture["snapshot_path"])
                )
                snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
                source_manifest = manifest_path.relative_to(source_root).as_posix()
                root_id = stable_id("puct-convergence-root", {
                    "source_manifest": source_manifest,
                    "trajectory_id": game.get("trajectory_id"),
                    "step": step,
                    "game_state_signature": snapshot.get("game_state_signature"),
                })
                roots.append({
                    "root_id": root_id,
                    "manifest_path": manifest_path,
                    "config_path": config_path,
                    "snapshot_path": snapshot_path,
                    "manifest": manifest,
                    "game": game,
                    "record": record,
                    "snapshot": snapshot,
                    "case_id": case_id,
                    "trajectory_id": game.get("trajectory_id"),
                    "step": step,
                    "model_visible_state_signature": snapshot.get(
                        "model_visible_state_signature"
                    ),
                    "game_state_signature": snapshot.get("game_state_signature"),
                    "source_manifest": source_manifest,
                })
    identifiers = [root["root_id"] for root in roots]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Q-discriminating root IDs are not unique")
    return roots


def needs_promotion(conditions: dict[str, dict[str, Any]]) -> bool:
    labels = ("h2-s24", "h2-s48", "h3-s48", "h5-s48")
    signatures = {
        label: policy_signature(conditions[label]["policy_target"])
        for label in labels
    }
    return not (
        signatures["h2-s24"] == signatures["h2-s48"]
        and signatures["h2-s48"] == signatures["h3-s48"]
        and signatures["h3-s48"] == signatures["h5-s48"]
    )


def _root_seed(root_id: str) -> int:
    return int(hashlib.sha256(root_id.encode("utf-8")).hexdigest()[:8], 16)


def load_task_config(path: pathlib.Path, case_id: str) -> dict[str, Any]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if case_id not in cases:
        raise KeyError(f"missing case {case_id} in {path}")
    return cases[case_id]


def _run_root(root: dict[str, Any], agent_module) -> dict[str, Any]:
    from src.ground_handling.env import GroundHandlingEnv

    task_config = load_task_config(root["config_path"], root["case_id"])
    manifest = root["manifest"]
    contract = root["snapshot"]["replay_contract"]
    environment_seed = int(contract["seed"])
    candidate_contract = manifest["candidate_contract"]
    rules = GameRules(**manifest["rules"])
    provider = build_candidate_provider(
        agent_module,
        attempt_budget=int(candidate_contract["attempt_budget"]),
        scan_all_visible_items=True,
    )
    legal_filter = build_exact_physical_legal_filter(
        task_config, case_id=root["case_id"], environment_seed=environment_seed,
    )
    env = GroundHandlingEnv(
        config=copy.deepcopy(task_config), verbose=False, render_mode=None
    )
    try:
        rebuilt = replay_action_prefix(
            env, contract,
            expected_fingerprint=root["snapshot"]["board_fingerprint"],
            expected_snapshot=root["snapshot"],
            snapshot_factory=lambda current, raw: state_snapshot(
                current, policy_observation(current, raw),
                case_id=root["case_id"], step=root["step"],
            ),
        )
        if not rebuilt.matched:
            raise RuntimeError(
                f"target root reconstruction failed {root['root_id']}: {rebuilt.error}; "
                f"observed={rebuilt.observed_fingerprint}"
            )
        game = root["snapshot"]["self_play_game"]
        state = GameState(
            current_player=int(game["player_to_move"]),
            block_length=int(game["block_length"]),
            placements=len(contract["action_prefix"]),
            handoff_count=int(game["handoff_count"]),
        )
        original = root["record"]["search"]
        candidates = list(root["record"]["candidate_set"])
        actions = list(contract["action_prefix"])
        seed = _root_seed(root["root_id"])
        conditions = {}

        def run_condition(label: str, horizon: int, simulations: int) -> None:
            search = build_physical_puct_search(
                task_config,
                case_id=root["case_id"],
                environment_seed=environment_seed,
                candidate_provider=provider,
                legal_filter_fn=legal_filter,
                rules=rules,
                top_k=int(candidate_contract["top_k"]),
                simulations=simulations,
                horizon=horizon,
                cpuct=float(original["cpuct"]),
                prior_mode=str(original["prior_mode"]),
                prior_temperature=float(original["prior_temperature"]),
                action_temperature=0.0,
                root_dirichlet_alpha=0.0,
                root_dirichlet_epsilon=0.0,
                search_seed=seed,
            )
            _chosen, result = search(
                env=env,
                observation=rebuilt.observation,
                candidates=candidates,
                actions=actions,
                state=state,
                step=root["step"],
                policy_rng=random.Random(seed + 1),
            )
            conditions[label] = result

        for condition in BASE_SCHEDULE:
            run_condition(*condition)
        promoted = needs_promotion(conditions)
        if promoted:
            for condition in PROMOTED_SCHEDULE:
                run_condition(*condition)
        return {
            "root_id": root["root_id"],
            "case_id": root["case_id"],
            "trajectory_id": root["trajectory_id"],
            "step": root["step"],
            "model_visible_state_signature": root["model_visible_state_signature"],
            "game_state_signature": root["game_state_signature"],
            "source_manifest": root["source_manifest"],
            "candidate_ids": [row["candidate_id"] for row in candidates],
            "original_search": {
                "simulations": original["simulations"],
                "horizon": original["horizon"],
                "root_dirichlet_alpha": original["root_dirichlet_alpha"],
                "root_dirichlet_epsilon": original["root_dirichlet_epsilon"],
                "policy_target": original["policy_target"],
            },
            "measurement_root_noise": False,
            "search_seed": seed,
            "promoted": promoted,
            "conditions": conditions,
        }
    finally:
        env.close()


def _write_payload(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--expected-roots", type=int)
    args = parser.parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("invalid shard index/count")
    roots = discover_roots(args.source_root)
    if args.expected_roots is not None and len(roots) != args.expected_roots:
        raise SystemExit(f"expected {args.expected_roots} roots, got {len(roots)}")
    assigned = [
        root for index, root in enumerate(roots)
        if index % args.shard_count == args.shard_index
    ]
    payload = {
        "schema_version": 1,
        "experiment": "targeted_physical_puct_convergence",
        "source_root_count": len(roots),
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "base_schedule": [
            {"label": label, "horizon": horizon, "simulations": simulations}
            for label, horizon, simulations in BASE_SCHEDULE
        ],
        "promoted_schedule": [
            {"label": label, "horizon": horizon, "simulations": simulations}
            for label, horizon, simulations in PROMOTED_SCHEDULE
        ],
        "assigned_root_count": len(assigned),
        "complete": False,
        "roots": [],
    }
    _write_payload(args.output, payload)
    agent_module = load_agent_module()
    for root in assigned:
        payload["roots"].append(_run_root(root, agent_module))
        _write_payload(args.output, payload)
    payload["complete"] = True
    _write_payload(args.output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
