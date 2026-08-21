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
from scripts.postshake_capture import (  # noqa: E402
    ATTRIBUTE_KEYS,
    capture_shake_labels,
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

POST_SHAKE_STABILITY_KEYS = (
    "shake_items",
    "shake_items_lost",
    "shake_max_shift",
    "shake_mean_shift",
    "shake_max_rotation_deg",
    "shake_items_shifted",
    "shake_items_toppled",
    "shake_peak_kinetic_energy",
)

POST_SHAKE_EVENT_KEYS = (
    "post_shake_soft_clean_to_covered_events",
)


def post_shake_metrics(env) -> dict[str, Any]:
    """Measure stability and attribute coverage in the same live shake.

    The bundled shake saves/restores the world. ``capture_shake_labels``
    intercepts its exact post-shake state before that restore and delegates
    coverage arithmetic to ``Evaluator.settled_snapshot``.  Flattened names
    keep each physical/attribute axis separately consumable by graph tooling.
    """
    containers = env.container_manager.containers
    captured = capture_shake_labels(env.evaluator, containers)
    calls = int(captured.get("live_poses_calls", 0))
    pre = captured.get("pre_shake")
    post = captured.get("post_shake")
    response = captured.get("shake_response") or {}
    empty_shake = calls == 1 and int(response.get("shake_items", -1)) == 0
    if empty_shake and not isinstance(post, dict):
        # The bundled evaluator returns immediately after its pre-shake read
        # when the board is empty. The unchanged pre-state is therefore also
        # the exact post-state, not a missing measurement.
        post = captured.get("pre_shake")
    if (calls != 2 and not empty_shake) or not isinstance(post, dict):
        raise RuntimeError(
            "post-shake label capture requires two live-pose reads (one on "
            "an empty board) and a post-shake snapshot; "
            f"calls={calls} shake_items={response.get('shake_items')}"
        )

    metrics: dict[str, Any] = {
        "post_shake_measured": True,
        "post_shake_live_poses_calls": calls,
    }
    for key in POST_SHAKE_STABILITY_KEYS:
        if key in response:
            output_key = "post_shake_" + key.removeprefix("shake_")
            metrics[output_key] = json_safe(response[key])
    for key in ATTRIBUTE_KEYS:
        if key in post:
            metrics[f"post_shake_{key}"] = json_safe(post[key])
    if isinstance(pre, dict):
        before = pre.get("soft_covered_by_other")
        after = post.get("soft_covered_by_other")
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            metrics["post_shake_soft_covered_by_other_before"] = json_safe(
                before
            )
            metrics["post_shake_soft_clean_to_covered_events"] = int(
                before == 0 and after > 0
            )
    return metrics


def cumulative_metrics(
    env, *, include_post_shake: bool = False,
) -> dict[str, Any]:
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
    result = {
        key: json_safe(metrics.get(key))
        for key in METRIC_KEYS
        if key in metrics or key == "fill_score_proxy"
    }
    if include_post_shake:
        result.update(post_shake_metrics(env))
    return result


def transition_outcomes(
    env,
    info: dict[str, Any],
    parent: dict[str, Any],
    *,
    include_post_shake: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cumulative = cumulative_metrics(
        env, include_post_shake=include_post_shake
    )
    for key in POST_SHAKE_EVENT_KEYS:
        if key in cumulative:
            cumulative[key] = int(parent.get(key, 0)) + int(cumulative[key])
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
    scan_all_visible_items: bool = False,
):
    risk_lambda = (
        agent_module.RELEASE_RISK_RERANK_LAMBDA
        if agent_module.RELEASE_RISK_LIVE_RERANK
        else None
    )

    def provide(env, raw_observation, limit: int) -> list[BranchCandidate]:
        observation = policy_observation(env, raw_observation)
        indexed_items = (
            agent_module.online_item_order(observation.get("pool_list", []))
            if scan_all_visible_items
            else policy_indexed_items(agent_module, observation)
        )
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
                        "all_visible_items_scanned": bool(
                            scan_all_visible_items
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
    parser.add_argument(
        "--post-shake-labels",
        action="store_true",
        help=(
            "run the bundled shake at every reconstructed node and retain "
            "its exact post-shake stability and soft/priority measurements"
        ),
    )
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
        root_metrics = cumulative_metrics(
            root_env, include_post_shake=args.post_shake_labels
        )
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
            "behavior_policy": snapshot.get("behavior_policy"),
            "model_visible_state_signature": snapshot.get(
                "model_visible_state_signature"
            ),
            "scenario_axes": scenario_axes(task_config),
            "forced_candidate_target_id": (
                None if forced_target is None else forced_target["target_id"]
            ),
            "forced_candidate_paths": [
                {"path": list(path), "required_item_indices": indices}
                for path, indices in forced_candidates.items()
            ],
            "post_shake_labels": bool(args.post_shake_labels),
            "post_shake_label_contract": (
                "bundled_shake_live_state_direct_capture_v1"
                if args.post_shake_labels
                else None
            ),
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
        outcome_provider=lambda env, info, parent: transition_outcomes(
            env,
            info,
            parent,
            include_post_shake=args.post_shake_labels,
        ),
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
