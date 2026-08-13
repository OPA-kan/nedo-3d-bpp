"""Build a bounded 3--5 step physical counterfactual DAG.

Every branch is reconstructed in a fresh GroundHandlingEnv from the recorded
episode prefix.  This is intentionally slower than PyBullet save/restore: the
latter does not restore ItemStreamManager or container Python state.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import subprocess
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.counterfactual_graph import (  # noqa: E402
    BoundedGraphExecutor,
    BranchCandidate,
    CounterfactualGraph,
    GraphBudget,
    board_difference,
    board_fingerprint,
    canonical_action,
    replay_action_prefix,
    state_tensor_from_snapshot,
    stable_id,
    write_graph,
)
from scripts.measure_anchor_recall import (  # noqa: E402
    DEFAULT_CONFIG,
    SIMULATOR,
    json_safe,
    load_agent_module,
    policy_indexed_items,
    policy_observation,
    state_snapshot,
)


METRIC_KEYS = (
    "placed_count",
    "placed_volume",
    "fill_score_proxy",
    "fill_percent_proxy",
    "center_of_mass_z",
    "com_z",
    "com_z_above_floor",
    "com_height_ratio",
    "surface_height_std",
    "surface_total_variation",
    "flat_support_edge_ratio",
    "priority_items",
    "soft_items",
    "priority_covered_by_other",
    "priority_misrouted",
    "soft_covered_by_other",
)


def cumulative_metrics(env) -> dict[str, Any]:
    metrics = env.evaluator.settled_snapshot(
        env.container_manager.containers
    )
    metrics["placed_count"] = sum(
        len(container.packed_items)
        for container in env.container_manager.containers
    )
    # ``fill_score_proxy`` is the bundled fill percentage, not the official
    # weighted total score.
    metrics["fill_score_proxy"] = metrics.get("fill_percent_proxy")
    return {
        key: json_safe(metrics.get(key))
        for key in METRIC_KEYS
        if key in metrics or key == "fill_score_proxy"
    }


def transition_outcomes(
    env,
    info: dict[str, Any],
    parent: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    cumulative = cumulative_metrics(env)
    status = info.get("status", {}) if isinstance(info, dict) else {}
    immediate: dict[str, Any] = {
        "is_included": bool(status.get("is_included")),
        "is_valid": bool(status.get("is_valid")),
        "is_placed_safe": bool(status.get("is_placed_safe")),
    }
    for key, value in cumulative.items():
        immediate[f"{key}_after"] = value
        previous = parent.get(key)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and isinstance(previous, (int, float))
            and not isinstance(previous, bool)
        ):
            immediate[f"{key}_delta"] = float(value) - float(previous)
    if env.step_metrics:
        step = env.step_metrics[-1]
        for key in (
            "settle_angle_deg",
            "settle_displacement_norm",
            "settle_displacement_xyz",
            "settle_final_position",
            "settle_final_quaternion",
            "settle_aabb_dimensions",
        ):
            if key in step:
                immediate[key] = json_safe(step[key])
    return immediate, cumulative


def build_candidate_provider(
    agent_module, *, attempt_budget: int,
    include_release_fallbacks: bool = False,
):
    risk_lambda = (
        agent_module.RELEASE_RISK_RERANK_LAMBDA
        if agent_module.RELEASE_RISK_LIVE_RERANK
        else None
    )

    def provide(env, raw_observation, limit: int) -> list[BranchCandidate]:
        observation = policy_observation(env, raw_observation)
        indexed_items = policy_indexed_items(agent_module, observation)
        settled_by_item = {}
        release_by_item = {}

        def retain_item_best(
            pool_index,
            item,
            _container_index,
            _orientation,
            decision,
        ):
            stable_item_index = int(item.get("index", pool_index))
            target = (
                release_by_item
                if decision.candidate.name == "release_candidate"
                else settled_by_item
            )
            previous = target.get(stable_item_index)
            if previous is None or float(decision.score) > float(
                previous.score
            ):
                target[stable_item_index] = decision

        # Run an equal fixed-attempt scan PER ITEM. A single shared scan still
        # spent all 512 pilot attempts on one easy item and produced a graph
        # of width one. This is offline state-coverage sampling, so the extra
        # cost is intentional and recorded; live policy timing is untouched.
        for indexed_item in indexed_items:
            agent_module.PlacementCore.top_candidates(
                observation,
                [indexed_item],
                1,
                deadline=None,
                diagnostics=None,
                risk_lambda=risk_lambda,
                candidate_observer=retain_item_best,
                attempt_budget=int(attempt_budget),
            )
        settled = sorted(
            settled_by_item.items(),
            key=lambda pair: (-float(pair[1].score), int(pair[0])),
        )
        release = sorted(
            (
                pair
                for pair in release_by_item.items()
                if include_release_fallbacks or pair[0] not in settled_by_item
            ),
            key=lambda pair: (-float(pair[1].score), int(pair[0])),
        )
        # Settled-first is an ordering, not a population filter here. A live
        # action should prefer settled, but an offline training graph must not
        # collapse to width one merely because one item has a settled action.
        # Fill unused width with distinct-item release actions and let the
        # physical replay provide their failure labels.
        decisions = (settled + release)[: int(limit)]
        result = []
        for rank, (stable_item_index, decision) in enumerate(decisions):
            action = canonical_action(decision.action)
            candidate_kind = (
                "release_candidate"
                if decision.candidate.name == "release_candidate"
                else "settled_candidate"
            )
            result.append(
                BranchCandidate(
                    candidate_id=stable_id(
                        "candidate",
                        {
                            "action": action,
                            "kind": candidate_kind,
                            "stable_item_index": stable_item_index,
                        },
                    ),
                    command_action=action,
                    selection={
                        "provider": (
                            "placement_core_item_stratified_fixed_attempts"
                        ),
                        "rank": int(rank),
                        "pool_index": int(action["item_idx"]),
                        "stable_item_index": int(stable_item_index),
                        "score": float(decision.score),
                        "candidate_kind": candidate_kind,
                        "attempt_budget": int(attempt_budget),
                        "attempt_budget_scope": "per_item",
                        "risk_lambda": (
                            None
                            if risk_lambda is None
                            else float(risk_lambda)
                        ),
                        "release_fallbacks_included": bool(
                            include_release_fallbacks
                        ),
                    },
                )
            )
        return result

    return provide


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def scenario_axes(task_config: dict[str, Any]) -> dict[str, Any]:
    """Record the competition-condition axes represented by one root."""
    containers = task_config.get("containers", {}).get(
        "container_list", []
    )
    return {
        "container_count": len(containers),
        "shelf_count": sum(
            bool(container.get("require_shelf"))
            for container in containers
        ),
        "dedicated_container_count": sum(
            bool(container.get("is_prioritized"))
            for container in containers
        ),
        "preloaded_item_count": sum(
            len(container.get("packed_items", []))
            for container in containers
        ),
        "pool_width": int(
            task_config.get("item_stream", {}).get("look_ahead", 0)
        ),
        "stream_item_count": len(
            task_config.get("item_stream", {}).get("item_list", [])
        ),
        "stream_variant": task_config.get("item_stream", {}).get(
            "development_stream_variant", "original"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--case", required=True, help="config mapping key")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--horizon", type=int, choices=(3, 4, 5), default=3)
    parser.add_argument("--branch-factor", type=int, default=2)
    parser.add_argument("--attempt-budget", type=int, default=512)
    parser.add_argument("--max-nodes", type=int, default=128)
    parser.add_argument("--max-edges", type=int, default=256)
    parser.add_argument("--forced-candidate-spec", type=pathlib.Path)
    parser.add_argument("--forced-target-id")
    parser.add_argument(
        "--split",
        choices=("development", "validation"),
        required=True,
        help="final_holdout is deliberately unavailable in this builder",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.output.exists() and not args.overwrite:
        raise SystemExit(f"output already exists: {args.output}")
    if args.branch_factor < 1 or args.attempt_budget < 1:
        raise SystemExit("branch-factor and attempt-budget must be positive")

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    contract = snapshot.get("replay_contract")
    if not isinstance(contract, dict):
        raise SystemExit(
            "snapshot has no replay_contract; regenerate it with the current "
            "build_replay_dataset.py"
        )
    expected = snapshot.get("board_fingerprint") or board_fingerprint(snapshot)
    configs = json.loads(args.config.read_text(encoding="utf-8"))
    if args.case not in configs:
        raise SystemExit(f"unknown config case: {args.case}")
    task_config = configs[args.case]
    forced_candidates: dict[tuple[int, ...], list[int]] = {}
    forced_target = None
    if bool(args.forced_candidate_spec) != bool(args.forced_target_id):
        raise SystemExit(
            "--forced-candidate-spec and --forced-target-id are required together"
        )
    if args.forced_candidate_spec:
        forced_spec = json.loads(
            args.forced_candidate_spec.read_text(encoding="utf-8")
        )
        matches = [
            row for row in forced_spec.get("targets", [])
            if row.get("target_id") == args.forced_target_id
        ]
        if len(matches) != 1:
            raise SystemExit(
                f"forced target must match exactly once: {args.forced_target_id}"
            )
        forced_target = matches[0]
        parent_path = tuple(
            int(value) for value in forced_target.get(
                "parent_path_item_indices", []
            )
        )
        for offset, item_index in enumerate(parent_path):
            forced_candidates[parent_path[:offset]] = [int(item_index)]
        forced_candidates[parent_path] = [
            int(forced_target["lower_stable_item_index"]),
            int(forced_target["higher_stable_item_index"]),
        ]

    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    from src.ground_handling.env import GroundHandlingEnv

    agent_module = load_agent_module()

    def env_factory():
        return GroundHandlingEnv(
            config=copy.deepcopy(task_config),
            verbose=False,
            render_mode=None,
        )

    root_step = int(snapshot.get("step", 0))
    case_id = str(snapshot.get("case_id", args.case))

    def snapshot_factory(env, raw_observation):
        observation = policy_observation(env, raw_observation)
        return state_snapshot(
            env,
            observation,
            case_id=case_id,
            step=root_step,
        )

    root_env = env_factory()
    try:
        rebuilt = replay_action_prefix(
            root_env,
            contract,
            expected_fingerprint=expected,
            snapshot_factory=snapshot_factory,
            expected_snapshot=snapshot,
        )
        if not rebuilt.matched:
            difference = None
            if rebuilt.observation is not None:
                observed_snapshot = snapshot_factory(
                    root_env, rebuilt.observation
                )
                difference = board_difference(snapshot, observed_snapshot)
            raise SystemExit(
                "root reconstruction failed: "
                f"expected={expected} observed={rebuilt.observed_fingerprint} "
                f"error={rebuilt.error} difference="
                f"{json.dumps(difference, sort_keys=True)}"
            )
        root_metrics = cumulative_metrics(root_env)
    finally:
        root_env.close()

    budget = GraphBudget(
        horizon=args.horizon,
        branch_factor=args.branch_factor,
        max_nodes=args.max_nodes,
        max_edges=args.max_edges,
    )
    graph = CounterfactualGraph.create(
        root_snapshot_id=str(
            snapshot.get("snapshot_id", args.snapshot.stem)
        ),
        case_id=case_id,
        root_step=root_step,
        future_stream_id=str(contract["future_stream_id"]),
        budget=budget,
        provenance={
            "commit": git_commit(),
            "config": str(args.config),
            "config_case": str(args.case),
            "split": str(args.split),
            "candidate_provider": (
                "placement_core_item_stratified_fixed_attempts"
            ),
            "attempt_budget": int(args.attempt_budget),
            "attempt_budget_scope": "per_item",
            "root_action_prefix_id": contract.get("action_prefix_id"),
            "scenario_axes": scenario_axes(task_config),
            "forced_candidate_target_id": (
                None if forced_target is None else forced_target["target_id"]
            ),
            "forced_candidate_paths": [
                {"path": list(path), "required_item_indices": indices}
                for path, indices in forced_candidates.items()
            ],
        },
        board_fingerprint=expected,
        state_ref=str(args.snapshot),
        pool_item_indices=contract["visible_pool_item_indices"],
        cumulative_outcomes=root_metrics,
        state_tensor=state_tensor_from_snapshot(snapshot),
    )
    executor = BoundedGraphExecutor(
        env_factory=env_factory,
        snapshot_factory=snapshot_factory,
        candidate_provider=build_candidate_provider(
            agent_module,
            attempt_budget=args.attempt_budget,
        ),
        outcome_provider=transition_outcomes,
        state_tensor_factory=state_tensor_from_snapshot,
        forced_candidate_indices_by_path=forced_candidates,
    )
    executor.expand(graph, contract, root_snapshot=snapshot)
    write_graph(args.output, graph)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "graph_id": graph.graph_id,
                "nodes": len(graph.nodes),
                "edges": len(graph.edges),
                "max_depth": max(node.depth for node in graph.nodes.values()),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
