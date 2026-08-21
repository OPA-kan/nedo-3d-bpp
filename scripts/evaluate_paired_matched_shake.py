"""Replay paired game arms to the same placed count and shake both boards."""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
for path in (ROOT, SIMULATOR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.counterfactual_graph import canonical_action  # noqa: E402


def normalized_shake(
    settled: dict[str, Any], shake: dict[str, Any]
) -> dict[str, Any]:
    count = int(settled.get("placed_count", shake.get("shake_items", 0)))
    mass = float(settled.get("placed_mass", 0.0))
    energy = float(shake.get("shake_peak_kinetic_energy", 0.0))
    return {
        "placed_count": count,
        "placed_mass": mass,
        "peak_kinetic_energy": energy,
        "peak_kinetic_energy_per_item": energy / count if count else None,
        "peak_kinetic_energy_per_mass": energy / mass if mass else None,
        "items_lost": int(shake.get("shake_items_lost", 0)),
        "shifted_fraction": (
            float(shake.get("shake_items_shifted", 0)) / count
            if count else None
        ),
        "toppled_fraction": (
            float(shake.get("shake_items_toppled", 0)) / count
            if count else None
        ),
        "max_shift": float(shake.get("shake_max_shift", 0.0)),
        "mean_shift": float(shake.get("shake_mean_shift", 0.0)),
        "max_rotation_deg": float(shake.get("shake_max_rotation_deg", 0.0)),
    }


def _load_game(path: pathlib.Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    games = manifest.get("games", [])
    if len(games) != 1:
        raise ValueError(f"expected one game in {path}, got {len(games)}")
    return games[0]


def _final_placed(game: dict[str, Any]) -> int:
    terminal = (game.get("evaluation") or {}).get("terminal_step_metrics") or {}
    return int(terminal.get("placed_count", game.get("placements", 0)))


def replay_to_count(
    task_config: dict[str, Any], game: dict[str, Any], target_count: int,
) -> dict[str, Any]:
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(
        config=copy.deepcopy(task_config), verbose=False, render_mode=None
    )
    try:
        env.reset_settings()
        env.reset_item_stream()
        _observation, _info = env.reset(seed=int(game["environment_seed"]))
        initial_count = sum(
            len(container.packed_items)
            for container in env.container_manager.containers
        )
        prefix_length = target_count - initial_count
        actions = [row["action"] for row in game.get("records", [])]
        if prefix_length < 0 or prefix_length > len(actions):
            raise ValueError(
                f"cannot replay placed_count={target_count}; "
                f"initial={initial_count}, actions={len(actions)}"
            )
        for index, action in enumerate(actions[:prefix_length]):
            _observation, _reward, terminated, truncated, info = env.step(
                canonical_action(action)
            )
            status = info.get("status", {})
            if not all(status.get(key) is True for key in (
                "is_included", "is_valid", "is_placed_safe",
            )):
                raise RuntimeError(f"unsafe replay at prefix action {index}: {status}")
            if (terminated or truncated) and index + 1 < prefix_length:
                raise RuntimeError("paired replay ended before matched count")
        settled = env.evaluator.settled_snapshot(
            env.container_manager.containers
        )
        if int(settled.get("placed_count", -1)) != target_count:
            raise RuntimeError(
                f"matched-count replay drift: {settled.get('placed_count')} "
                f"!= {target_count}"
            )
        shake = env.evaluator.shake_test(env.container_manager.containers)
        return normalized_shake(settled, shake)
    finally:
        env.close()


def summarize_pair(
    task_config: dict[str, Any], rank0_game: dict[str, Any],
    mcts_game: dict[str, Any],
) -> dict[str, Any]:
    if rank0_game.get("environment_seed") != mcts_game.get("environment_seed"):
        raise ValueError("paired games use different environment seeds")
    matched_count = min(_final_placed(rank0_game), _final_placed(mcts_game))
    rank0 = replay_to_count(task_config, rank0_game, matched_count)
    mcts = replay_to_count(task_config, mcts_game, matched_count)
    numeric = (
        "peak_kinetic_energy", "peak_kinetic_energy_per_item",
        "peak_kinetic_energy_per_mass", "shifted_fraction",
        "toppled_fraction", "max_shift", "mean_shift", "max_rotation_deg",
    )
    delta = {
        key: (
            float(mcts[key]) - float(rank0[key])
            if mcts.get(key) is not None and rank0.get(key) is not None
            else None
        )
        for key in numeric
    }
    return {
        "schema_version": 1,
        "contract": "same_scenario_stream_seed_and_placed_count",
        "matched_placed_count": matched_count,
        "rank0": rank0,
        "mcts": mcts,
        "delta_mcts_minus_rank0": delta,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--rank0-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--mcts-manifest", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.case not in config:
        raise SystemExit(f"unknown case: {args.case}")
    result = summarize_pair(
        config[args.case], _load_game(args.rank0_manifest),
        _load_game(args.mcts_manifest),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
