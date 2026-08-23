"""Compare fixed-support H2+V with H2+0 against a deep physical reference."""

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
from scripts.counterfactual_graph import replay_action_prefix  # noqa: E402
from scripts.evaluate_self_play_puct_convergence import policy_signature  # noqa: E402
from scripts.rerun_self_play_puct_roots import (  # noqa: E402
    discover_roots,
    load_task_config,
)
from scripts.run_self_play_packing import (  # noqa: E402
    build_exact_physical_legal_filter,
    build_physical_puct_search,
)
from scripts.self_play_packing_game import GameRules, GameState  # noqa: E402
from scripts.train_self_play_set_value import (  # noqa: E402
    BehaviorValueEnsemble,
    PlayerZeroLeafValue,
)


def _root_seed(root_id: str) -> int:
    return int(hashlib.sha256(root_id.encode("utf-8")).hexdigest()[:8], 16)


def trajectory_group_for_root(root: dict[str, Any]) -> str:
    manifest = pathlib.PurePosixPath(str(root["source_manifest"]))
    if len(manifest.parents) < 2:
        raise ValueError(f"cannot resolve pair ID from {manifest}")
    pair_id = manifest.parents[1].name
    return f"{pair_id}:{root['trajectory_id']}"


def summarize_leaf_calls(calls: list[dict[str, Any]]) -> dict[str, Any]:
    heads: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        for name, value in call["heads"].items():
            heads.setdefault(name, []).append(value)
    return {
        "calls": len(calls),
        "normalized_clipped_calls": sum(
            abs(float(call["normalized_player0_value"])) >= 1.0
            for call in calls
        ),
        "heads": {
            name: {
                "mean_prediction": sum(float(row["mean"]) for row in rows)
                / len(rows),
                "mean_epistemic_variance": sum(
                    float(row["variance"]) for row in rows
                ) / len(rows),
                "max_epistemic_variance": max(
                    float(row["variance"]) for row in rows
                ),
            }
            for name, rows in sorted(heads.items())
        },
    }


def compare_shadow_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    leaked = [
        row.get("root_id")
        for row in rows
        if row.get("excluded_training_group") is not None
        and row["excluded_training_group"] not in row.get(
            "model_excluded_groups", []
        )
    ]
    if leaked:
        raise ValueError(f"shadow rows used non-excluded trajectory models: {leaked}")

    def matches(row, arm, component):
        return (
            row[f"{arm}_signature"].get(component)
            == row["reference_signature"].get(component)
        )

    result = {
        "schema_version": 1,
        "experiment": "fixed_support_H2_behavior_value_shadow",
        "target_semantics": "V^pi_behavior_not_V_star",
        "evaluation_split": "root_trajectory_group_excluded_from_every_member",
        "candidate_support": (
            "frozen_top3_plus_exhaustion_K64_plus_stride4_provider_zero_rescue"
        ),
        "progressive_widening": False,
        "policy_head": False,
        "root_count": len(rows),
        "zero_q_top_matches_reference": sum(matches(row, "zero", "q_top") for row in rows),
        "value_q_top_matches_reference": sum(matches(row, "value", "q_top") for row in rows),
        "zero_visit_top_matches_reference": sum(matches(row, "zero", "visit_top") for row in rows),
        "value_visit_top_matches_reference": sum(matches(row, "value", "visit_top") for row in rows),
        "zero_full_signature_matches_reference": sum(
            row["zero_signature"] == row["reference_signature"] for row in rows
        ),
        "value_full_signature_matches_reference": sum(
            row["value_signature"] == row["reference_signature"] for row in rows
        ),
        "q_top_improved_roots": sum(
            matches(row, "value", "q_top") and not matches(row, "zero", "q_top")
            for row in rows
        ),
        "q_top_regressed_roots": sum(
            matches(row, "zero", "q_top") and not matches(row, "value", "q_top")
            for row in rows
        ),
        "visit_top_improved_roots": sum(
            matches(row, "value", "visit_top") and not matches(row, "zero", "visit_top")
            for row in rows
        ),
        "visit_top_regressed_roots": sum(
            matches(row, "zero", "visit_top") and not matches(row, "value", "visit_top")
            for row in rows
        ),
        "value_changed_q_top_roots": sum(
            row["zero_signature"].get("q_top")
            != row["value_signature"].get("q_top") for row in rows
        ),
        "value_changed_visit_top_roots": sum(
            row["zero_signature"].get("visit_top")
            != row["value_signature"].get("visit_top") for row in rows
        ),
        "leaf_value_calls": sum(row["leaf_value_summary"]["calls"] for row in rows),
        "leaf_value_clipped_calls": sum(
            row["leaf_value_summary"]["normalized_clipped_calls"] for row in rows
        ),
        "acceptance_gate": (
            "value_q_top_matches_reference > zero_q_top_matches_reference "
            "and q_top_improved_roots > q_top_regressed_roots"
        ),
        "rows": rows,
    }
    result["accepted"] = bool(
        result["value_q_top_matches_reference"]
        > result["zero_q_top_matches_reference"]
        and result["q_top_improved_roots"] > result["q_top_regressed_roots"]
    )
    return result


def render_markdown(result: dict[str, Any]) -> str:
    return "\n".join([
        "# Fixed-support H2 behavior-value shadow",
        "",
        f"- roots: {result['root_count']}",
        "- value semantics: `V^pi_behavior`, not `V*`",
        "- support: Top-3 + exhaustion K64 + stride-4 provider-zero rescue",
        "- progressive widening: disabled",
        f"- Q-top agreement: {result['zero_q_top_matches_reference']} -> {result['value_q_top_matches_reference']}",
        f"- visit-top agreement: {result['zero_visit_top_matches_reference']} -> {result['value_visit_top_matches_reference']}",
        f"- full-signature agreement: {result['zero_full_signature_matches_reference']} -> {result['value_full_signature_matches_reference']}",
        f"- Q-top paired improved/regressed: {result['q_top_improved_roots']}/{result['q_top_regressed_roots']}",
        f"- visit-top paired improved/regressed: {result['visit_top_improved_roots']}/{result['visit_top_regressed_roots']}",
        f"- leaf calls / clipped: {result['leaf_value_calls']} / {result['leaf_value_clipped_calls']}",
        f"- gate: **{'PASS' if result['accepted'] else 'FAIL'}**",
        "",
        "> This isolates leaf V under frozen candidate support. It is not an on-policy score claim.",
        "",
    ])


def _run_root(root, reference, agent_module, ensemble) -> dict[str, Any]:
    from src.ground_handling.env import GroundHandlingEnv

    task_config = load_task_config(root["config_path"], root["case_id"])
    manifest = root["manifest"]
    candidate_contract = manifest["candidate_contract"]
    rules = GameRules(**manifest["rules"])
    attempt_budget = int(candidate_contract["attempt_budget"])
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget, scan_all_visible_items=True,
    )
    provider_zero = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget, scan_all_visible_items=True,
        candidate_stride=4,
    )
    replay_contract = root["snapshot"]["replay_contract"]
    environment_seed = int(replay_contract["seed"])
    legal_filter = build_exact_physical_legal_filter(
        task_config, case_id=root["case_id"], environment_seed=environment_seed,
    )
    env = GroundHandlingEnv(
        config=copy.deepcopy(task_config), verbose=False, render_mode=None,
    )
    try:
        rebuilt = replay_action_prefix(
            env, replay_contract,
            expected_fingerprint=root["snapshot"]["board_fingerprint"],
            expected_snapshot=root["snapshot"],
            snapshot_factory=lambda current, raw: state_snapshot(
                current, policy_observation(current, raw),
                case_id=root["case_id"], step=root["step"],
            ),
        )
        if not rebuilt.matched:
            raise RuntimeError(
                f"target root reconstruction failed {root['root_id']}: {rebuilt.error}"
            )
        game = root["snapshot"]["self_play_game"]
        state = GameState(
            current_player=int(game["player_to_move"]),
            block_length=int(game["block_length"]),
            placements=len(replay_contract["action_prefix"]),
            handoff_count=int(game["handoff_count"]),
        )
        original = root["record"]["search"]
        seed = _root_seed(root["root_id"])
        conditions = {}
        leaf_adapter = PlayerZeroLeafValue(
            ensemble,
            value_scale=max(
                1.0, float(rules.terminal_reward), float(rules.attribute_penalty)
            ),
        )
        for label, leaf_fn in (("h2-s48-zero", None), ("h2-s48-value", leaf_adapter)):
            search = build_physical_puct_search(
                task_config, case_id=root["case_id"],
                environment_seed=environment_seed,
                candidate_provider=provider,
                provider_zero_rescue_fn=provider_zero,
                provider_zero_rescue_limit=64,
                provider_zero_rescue_safe_limit=1,
                legal_filter_fn=legal_filter, rules=rules,
                top_k=int(candidate_contract["top_k"]),
                candidate_audit_limit=64, candidate_rescue_limit=64,
                simulations=48, horizon=2,
                cpuct=float(original["cpuct"]),
                prior_mode=str(original["prior_mode"]),
                prior_temperature=float(original["prior_temperature"]),
                action_temperature=0.0,
                root_dirichlet_alpha=0.0, root_dirichlet_epsilon=0.0,
                search_seed=seed, leaf_value_fn=leaf_fn,
            )
            _chosen, search_result = search(
                env=env, observation=rebuilt.observation,
                candidates=list(root["record"]["candidate_set"]),
                actions=list(replay_contract["action_prefix"]), state=state,
                step=root["step"], policy_rng=random.Random(seed + 1),
            )
            conditions[label] = search_result
        return {
            "root_id": root["root_id"],
            "case_id": root["case_id"],
            "trajectory_id": root["trajectory_id"],
            "excluded_training_group": trajectory_group_for_root(root),
            "model_excluded_groups": list(ensemble.excluded_groups),
            "step": root["step"],
            "reference_signature": reference["reference_signature"],
            "zero_signature": policy_signature(
                conditions["h2-s48-zero"]["policy_target"]
            ),
            "value_signature": policy_signature(
                conditions["h2-s48-value"]["policy_target"]
            ),
            "zero_search": conditions["h2-s48-zero"],
            "value_search": conditions["h2-s48-value"],
            "leaf_value_summary": summarize_leaf_calls(leaf_adapter.calls),
        }
    finally:
        env.close()


def _write(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=pathlib.Path, required=True)
    parser.add_argument("--reference", type=pathlib.Path, required=True)
    parser.add_argument("--model-dir", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--expected-roots", type=int, default=58)
    args = parser.parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        raise SystemExit("invalid shard index/count")
    roots = discover_roots(args.source_root)
    if len(roots) != args.expected_roots:
        raise SystemExit(f"expected {args.expected_roots} roots, got {len(roots)}")
    references = {
        str(row["root_id"]): row
        for row in json.loads(args.reference.read_text(encoding="utf-8"))["roots"]
    }
    if {root["root_id"] for root in roots} != set(references):
        raise SystemExit("source and deep-reference root sets differ")
    assigned = [
        root for index, root in enumerate(roots)
        if index % args.shard_count == args.shard_index
    ]
    agent_module = load_agent_module()
    ensembles = {
        group: BehaviorValueEnsemble(args.model_dir, excluded_group=group)
        for group in sorted({trajectory_group_for_root(root) for root in assigned})
    }
    rows = [
        _run_root(
            root, references[root["root_id"]], agent_module,
            ensembles[trajectory_group_for_root(root)],
        )
        for root in assigned
    ]
    payload = {
        "schema_version": 1,
        "complete": True,
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "source_root_count": len(roots),
        "rows": rows,
    }
    _write(args.output, payload)
    if args.shard_count == 1 and args.markdown_output is not None:
        result = compare_shadow_rows(rows)
        _write(args.output, result)
        args.markdown_output.write_text(render_markdown(result), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
