"""Audit identical-item label symmetry against real PyBullet transitions.

For one recorded single-agent trajectory, transpose two stream items with
identical model-visible physical properties and replay the same pool-positional
action sequence.  Exact labels must differ (non-vacuous control), while every
status, terminal event, raw metric and item-symmetry child fingerprint must
remain equal.  This is an audit only; it never changes DAG merge semantics.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from scripts.build_counterfactual_graph import cumulative_metrics  # noqa: E402
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    policy_observation,
    state_snapshot,
)
from scripts.counterfactual_graph import (  # noqa: E402
    ITEM_TENSOR_FEATURES,
    board_fingerprint,
    canonical_action,
    item_symmetry_board_fingerprint,
)
from scripts.run_self_play_packing import _safe, _status  # noqa: E402
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402


def physical_item_signature(item: Any, *, digits: int = 9) -> tuple[float, ...]:
    values = []
    for name in ITEM_TENSOR_FEATURES:
        value = getattr(item, name, 0.0)
        if name in {"is_prioritized", "is_soft"}:
            value = float(bool(value))
        values.append(round(float(value or 0.0), digits))
    return tuple(values)


def _reset_env(task_config: dict[str, Any], *, seed: int, order=None):
    env = _fresh_env(task_config)
    env.reset_settings()
    if order is not None and not env.set_item_order(list(order)):
        env.close()
        raise RuntimeError("symmetry audit could not install item order")
    env.reset_item_stream()
    observation, _info = env.reset(seed=int(seed))
    return env, observation


def find_nonvacuous_transposition(
    task_config: dict[str, Any], actions: list[dict[str, Any]], *, seed: int,
) -> dict[str, Any]:
    """Find a selected item and a still-unselected identical partner."""
    env, observation = _reset_env(task_config, seed=seed)
    try:
        original_order = [int(item.index) for item in env.stream_manager.all_items]
        by_signature: dict[tuple[float, ...], list[int]] = {}
        for item in env.stream_manager.all_items:
            by_signature.setdefault(physical_item_signature(item), []).append(
                int(item.index)
            )
        consumed: set[int] = set()
        for step, action in enumerate(actions):
            pool_index = int(action["item_idx"])
            if not 0 <= pool_index < len(env.stream_manager.visible_pool):
                break
            selected = env.stream_manager.visible_pool[pool_index]
            selected_index = int(selected.index)
            partners = [
                index
                for index in by_signature[physical_item_signature(selected)]
                if index != selected_index and index not in consumed
            ]
            if partners:
                return {
                    "left_item_index": selected_index,
                    "right_item_index": int(partners[0]),
                    "witness_step": int(step),
                    "original_order": original_order,
                    "physical_signature": list(physical_item_signature(selected)),
                }
            observation, _reward, terminated, truncated, info = env.step(action)
            if not _safe(_status(info)) or terminated or truncated:
                break
            consumed.add(selected_index)
        raise ValueError("trajectory has no selected interchangeable item pair")
    finally:
        env.close()


def transposed_order(order: list[int], left: int, right: int) -> list[int]:
    result = list(order)
    left_position = result.index(int(left))
    right_position = result.index(int(right))
    result[left_position], result[right_position] = (
        result[right_position], result[left_position]
    )
    return result


def run_trace(
    task_config: dict[str, Any], actions: list[dict[str, Any]], *,
    case_id: str, seed: int, order: list[int],
) -> list[dict[str, Any]]:
    env, observation = _reset_env(task_config, seed=seed, order=order)
    trace = []
    try:
        for step, raw_action in enumerate(actions):
            action = canonical_action(raw_action)
            observed = policy_observation(env, observation)
            before = state_snapshot(env, observed, case_id=case_id, step=step)
            pool_index = int(action["item_idx"])
            selected_item_index = int(
                env.stream_manager.visible_pool[pool_index].index
            )
            observation, _reward, terminated, truncated, info = env.step(action)
            next_observed = policy_observation(env, observation)
            after = state_snapshot(
                env, next_observed, case_id=case_id, step=step + 1,
            )
            status = _status(info)
            trace.append({
                "step": int(step),
                "selected_item_index": selected_item_index,
                "status": status,
                "safe": _safe(status),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "before_exact": board_fingerprint(before),
                "before_symmetry": item_symmetry_board_fingerprint(before),
                "after_exact": board_fingerprint(after),
                "after_symmetry": item_symmetry_board_fingerprint(after),
                "metrics": cumulative_metrics(env),
            })
            if terminated or truncated or not _safe(status):
                break
        return trace
    finally:
        env.close()


def metric_mismatches(
    left: dict[str, Any], right: dict[str, Any], *, tolerance: float = 1e-6,
) -> dict[str, dict[str, Any]]:
    mismatches = {}
    for key in sorted(set(left) | set(right)):
        a, b = left.get(key), right.get(key)
        if a is None or b is None:
            equal = a is b
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
            equal = math.isclose(
                float(a), float(b), rel_tol=tolerance, abs_tol=tolerance,
            )
        else:
            equal = a == b
        if not equal:
            mismatches[key] = {"baseline": json_safe(a), "transposed": json_safe(b)}
    return mismatches


def compare_traces(
    baseline: list[dict[str, Any]], transposed: list[dict[str, Any]], *,
    witness_step: int,
) -> dict[str, Any]:
    if len(baseline) != len(transposed):
        return {
            "passed": False,
            "nonvacuous": False,
            "reason": "trace_length_mismatch",
            "baseline_steps": len(baseline),
            "transposed_steps": len(transposed),
            "steps": [],
            "equivariant_steps": 0,
            "false_merge_steps": 1,
        }
    rows = []
    for left, right in zip(baseline, transposed):
        metrics = metric_mismatches(left["metrics"], right["metrics"])
        row = {
            "step": left["step"],
            "parent_symmetry_match": (
                left["before_symmetry"] == right["before_symmetry"]
            ),
            "child_symmetry_match": (
                left["after_symmetry"] == right["after_symmetry"]
            ),
            "exact_label_state_differs": (
                left["before_exact"] != right["before_exact"]
                or left["after_exact"] != right["after_exact"]
            ),
            "selected_label_differs": (
                left["selected_item_index"] != right["selected_item_index"]
            ),
            "status_match": left["status"] == right["status"],
            "safe_match": left["safe"] == right["safe"],
            "terminal_match": (
                left["terminated"] == right["terminated"]
                and left["truncated"] == right["truncated"]
            ),
            "metric_mismatches": metrics,
        }
        row["transition_equivariant"] = bool(
            row["parent_symmetry_match"]
            and row["child_symmetry_match"]
            and row["status_match"]
            and row["safe_match"]
            and row["terminal_match"]
            and not metrics
        )
        rows.append(row)
    nonvacuous = bool(
        witness_step < len(rows)
        and rows[witness_step]["selected_label_differs"]
        and any(row["exact_label_state_differs"] for row in rows)
    )
    return {
        "passed": bool(nonvacuous and all(
            row["transition_equivariant"] for row in rows
        )),
        "nonvacuous": nonvacuous,
        "steps": rows,
        "equivariant_steps": sum(
            row["transition_equivariant"] for row in rows
        ),
        "false_merge_steps": sum(
            not row["transition_equivariant"] for row in rows
        ),
    }


def audit(
    task_config: dict[str, Any], manifest: dict[str, Any], *,
    case_id: str, seed: int, max_steps: int | None = None,
) -> dict[str, Any]:
    episodes = manifest.get("episodes") or []
    if not episodes:
        raise ValueError("manifest contains no episodes")
    actions = [
        canonical_action(action)
        for action in episodes[0].get("executed_actions") or []
    ]
    if max_steps is not None:
        actions = actions[:max_steps]
    if not actions:
        raise ValueError("manifest contains no executed actions")
    try:
        pair = find_nonvacuous_transposition(task_config, actions, seed=seed)
    except ValueError as exc:
        # Lack of support is a measured FAIL, not a crashed cell. Preserve it
        # for the matrix aggregate, which requires all six cells non-vacuous.
        return {
            "schema_version": 1,
            "contract": "identical_item_transposition_equivariance_v1",
            "case_id": case_id,
            "environment_seed": int(seed),
            "group_action": "transposition_in_product_of_identical_item_symmetric_groups",
            "action_count": len(actions),
            "passed": False,
            "nonvacuous": False,
            "reason": str(exc),
            "steps": [],
            "equivariant_steps": 0,
            "false_merge_steps": 0,
        }
    baseline_order = pair["original_order"]
    swapped_order = transposed_order(
        baseline_order, pair["left_item_index"], pair["right_item_index"],
    )
    baseline = run_trace(
        task_config, actions, case_id=case_id, seed=seed,
        order=baseline_order,
    )
    swapped = run_trace(
        task_config, actions, case_id=case_id, seed=seed,
        order=swapped_order,
    )
    comparison = compare_traces(
        baseline, swapped, witness_step=pair["witness_step"],
    )
    return {
        "schema_version": 1,
        "contract": "identical_item_transposition_equivariance_v1",
        "case_id": case_id,
        "environment_seed": int(seed),
        "group_action": "transposition_in_product_of_identical_item_symmetric_groups",
        "pair": pair,
        "action_count": len(actions),
        **comparison,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_config = config[args.case] if args.case in config else config
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = audit(
        task_config, manifest, case_id=args.case,
        seed=args.environment_seed, max_steps=args.max_steps,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "case_id": result["case_id"],
        "passed": result["passed"],
        "nonvacuous": result.get("nonvacuous"),
        "steps": len(result.get("steps", [])),
        "false_merge_steps": result.get("false_merge_steps"),
    }, ensure_ascii=False))
    # A counterexample is experimental evidence, not a cell-infrastructure
    # failure. Keep the matrix job alive so the aggregate can report every
    # cell and enforce the final zero-false-merge gate in one place.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
