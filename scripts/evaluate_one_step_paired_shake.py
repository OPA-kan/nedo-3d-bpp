"""Shake baseline/rescue root actions after exactly one forced placement.

Both arms rebuild the same recorded root in independent PyBullet worlds.  The
only intervention is the root action selected by the two deep bounded-search
references.  No continuation policy is run, so the result measures immediate
afterstate stability rather than a mixture of action and suffix-policy effects.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import statistics
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
for path in (ROOT, SIMULATOR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.build_counterfactual_graph import post_shake_metrics  # noqa: E402
from scripts.build_replay_dataset import policy_observation, state_snapshot  # noqa: E402
from scripts.counterfactual_graph import canonical_action, replay_action_prefix  # noqa: E402
from scripts.evaluate_paired_matched_shake import normalized_shake  # noqa: E402
from scripts.rerun_self_play_puct_roots import (  # noqa: E402
    discover_roots,
    load_task_config,
)


DELTA_AXES = (
    "peak_kinetic_energy",
    "peak_kinetic_energy_per_item",
    "peak_kinetic_energy_per_mass",
    "items_lost",
    "shifted_fraction",
    "toppled_fraction",
    "max_shift",
    "mean_shift",
    "max_rotation_deg",
    "post_shake_soft_covered_by_other",
    "post_shake_priority_covered_by_other",
    "post_shake_priority_misrouted",
)


def _root_map(aggregate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = {
        str(row["root_id"]): row for row in aggregate.get("roots", [])
    }
    if len(rows) != len(aggregate.get("roots", [])):
        raise ValueError("aggregate root IDs are not unique")
    return rows


def build_changed_action_pairs(
    roots: list[dict[str, Any]],
    baseline: dict[str, Any],
    rescue: dict[str, Any],
) -> list[dict[str, Any]]:
    """Resolve changed deep Q-top IDs against the frozen root candidate set."""
    source = {str(root["root_id"]): root for root in roots}
    left = _root_map(baseline)
    right = _root_map(rescue)
    if set(source) != set(left) or set(source) != set(right):
        raise ValueError("source/baseline/rescue root sets differ")

    pairs = []
    for root_id in sorted(source):
        baseline_id = left[root_id]["reference_signature"].get("q_top")
        rescue_id = right[root_id]["reference_signature"].get("q_top")
        if baseline_id == rescue_id:
            continue
        root = source[root_id]
        candidates = {
            str(row["candidate_id"]): row
            for row in root["record"].get("candidate_set", [])
        }
        missing = [
            candidate_id for candidate_id in (baseline_id, rescue_id)
            if candidate_id not in candidates
        ]
        if missing:
            raise ValueError(
                f"changed Q-top candidate missing from frozen root support "
                f"for {root_id}: {missing}"
            )
        pairs.append({
            "root_id": root_id,
            "case_id": root.get("case_id"),
            "trajectory_id": root.get("trajectory_id"),
            "step": root.get("step"),
            "game_state_signature": root.get("game_state_signature"),
            "baseline_candidate_id": baseline_id,
            "rescue_candidate_id": rescue_id,
            "baseline_action": canonical_action(
                candidates[baseline_id]["command_action"]
            ),
            "rescue_action": canonical_action(
                candidates[rescue_id]["command_action"]
            ),
            "root": root,
        })
    return pairs


def compare_shake_arms(
    baseline: dict[str, Any], rescue: dict[str, Any],
) -> dict[str, float | None]:
    """Return rescue-minus-baseline deltas without scalarizing axes."""
    return {
        key: (
            float(rescue[key]) - float(baseline[key])
            if baseline.get(key) is not None and rescue.get(key) is not None
            else None
        )
        for key in DELTA_AXES
    }


def _run_arm(
    task_config: dict[str, Any], root: dict[str, Any],
    action: dict[str, Any], *, arm: str,
) -> dict[str, Any]:
    from src.ground_handling.env import GroundHandlingEnv

    snapshot = root["snapshot"]
    contract = snapshot["replay_contract"]
    env = GroundHandlingEnv(
        config=copy.deepcopy(task_config), verbose=False, render_mode=None
    )
    try:
        rebuilt = replay_action_prefix(
            env,
            contract,
            expected_fingerprint=snapshot["board_fingerprint"],
            expected_snapshot=snapshot,
            snapshot_factory=lambda current, raw: state_snapshot(
                current,
                policy_observation(current, raw),
                case_id=root["case_id"],
                step=root["step"],
            ),
        )
        if not rebuilt.matched:
            raise RuntimeError(
                f"{arm} root reconstruction failed for {root['root_id']}: "
                f"{rebuilt.error}; observed={rebuilt.observed_fingerprint}"
            )
        _observation, _reward, terminated, truncated, info = env.step(action)
        status = info.get("status", {})
        required = ("is_included", "is_valid", "is_placed_safe")
        if not all(status.get(key) is True for key in required):
            raise RuntimeError(
                f"{arm} forced action is not physically safe for "
                f"{root['root_id']}: {status}"
            )
        settled = env.evaluator.settled_snapshot(
            env.container_manager.containers
        )
        shake = post_shake_metrics(env)
        normalized = normalized_shake(settled, {
            "shake_peak_kinetic_energy": shake.get(
                "post_shake_peak_kinetic_energy", 0.0
            ),
            "shake_items_lost": shake.get("post_shake_items_lost", 0),
            "shake_items_shifted": shake.get("post_shake_items_shifted", 0),
            "shake_items_toppled": shake.get("post_shake_items_toppled", 0),
            "shake_max_shift": shake.get("post_shake_max_shift", 0.0),
            "shake_mean_shift": shake.get("post_shake_mean_shift", 0.0),
            "shake_max_rotation_deg": shake.get(
                "post_shake_max_rotation_deg", 0.0
            ),
        })
        normalized.update({
            key: shake[key]
            for key in (
                "post_shake_soft_covered_by_other",
                "post_shake_priority_covered_by_other",
                "post_shake_priority_misrouted",
                "post_shake_soft_clean_ratio",
                "post_shake_priority_clean_ratio",
            )
            if key in shake
        })
        normalized.update({
            "terminated_after_action": bool(terminated),
            "truncated_after_action": bool(truncated),
            "status": {key: bool(status.get(key)) for key in required},
        })
        return normalized
    finally:
        env.close()


def evaluate_pairs(
    pairs: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    for pair in pairs:
        root = pair["root"]
        task_config = load_task_config(root["config_path"], root["case_id"])
        baseline = _run_arm(
            task_config, root, pair["baseline_action"], arm="baseline"
        )
        rescue = _run_arm(
            task_config, root, pair["rescue_action"], arm="rescue"
        )
        if baseline["placed_count"] != rescue["placed_count"]:
            raise RuntimeError(
                f"one-step pair placed-count mismatch for {pair['root_id']}: "
                f"{baseline['placed_count']} != {rescue['placed_count']}"
            )
        rows.append({
            key: value for key, value in pair.items() if key != "root"
        } | {
            "contract": "same_reconstructed_root_one_forced_action_then_shake",
            "baseline": baseline,
            "rescue": rescue,
            "delta_rescue_minus_baseline": compare_shake_arms(
                baseline, rescue
            ),
        })

    axis_summary = {}
    for axis in DELTA_AXES:
        values = [
            row["delta_rescue_minus_baseline"][axis] for row in rows
            if row["delta_rescue_minus_baseline"].get(axis) is not None
        ]
        axis_summary[axis] = {
            "paired_rows": len(values),
            "mean_delta": statistics.fmean(values) if values else None,
            "rescue_better": sum(value < 0 for value in values),
            "tie": sum(value == 0 for value in values),
            "rescue_worse": sum(value > 0 for value in values),
        }
    return {
        "schema_version": 1,
        "experiment": "one_step_paired_shake_after_candidate_support_change",
        "pair_count": len(rows),
        "intervention": (
            "same history/root/count; force baseline or rescue deep-Q-top "
            "action once; shake immediately; no continuation policy"
        ),
        "kinetic_energy_definition": (
            "bundled Evaluator.shake_test maximum instantaneous aggregate "
            "kinetic energy over the four gravity phases; also divided by "
            "settled item count and settled mass as separate axes; no time "
            "integral is measured"
        ),
        "scalarized": False,
        "axes": axis_summary,
        "pairs": rows,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# One-step paired shake after candidate-support rescue",
        "",
        f"- pairs: {result['pair_count']}",
        f"- contract: {result['intervention']}",
        f"- KE: {result['kinetic_energy_definition']}",
        "- scalarized: false",
        "",
        "| axis | n | mean rescue-baseline | better/tie/worse |",
        "|---|---:|---:|---:|",
    ]
    for axis, summary in result["axes"].items():
        mean = summary["mean_delta"]
        lines.append(
            f"| {axis} | {summary['paired_rows']} | "
            f"{mean if mean is not None else 'n/a'} | "
            f"{summary['rescue_better']}/{summary['tie']}/"
            f"{summary['rescue_worse']} |"
        )
    lines.extend([
        "",
        "> Negative deltas are better for every reported delta axis. This "
        "is an immediate one-action stability test, not a continuation or "
        "on-policy score comparison.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=pathlib.Path, required=True)
    parser.add_argument("--baseline", type=pathlib.Path, required=True)
    parser.add_argument("--rescue", type=pathlib.Path, required=True)
    parser.add_argument("--expected-pairs", type=int)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    roots = discover_roots(args.source_root)
    pairs = build_changed_action_pairs(
        roots,
        json.loads(args.baseline.read_text(encoding="utf-8")),
        json.loads(args.rescue.read_text(encoding="utf-8")),
    )
    if args.expected_pairs is not None and len(pairs) != args.expected_pairs:
        raise ValueError(
            f"expected {args.expected_pairs} changed Q-top pairs, got {len(pairs)}"
        )
    result = evaluate_pairs(pairs)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    print(args.json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
