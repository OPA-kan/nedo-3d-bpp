"""Learn searched residual-space affordances from raw H3 graph topology.

The target is deliberately multi-objective.  Each physical afterstate is
summarized by the safe searched paths and item classes reachable below it.
Only sibling pairs with Pareto dominance across the full affordance vector are
directional teachers.  Branch-factor-limited search breadth is a proxy for
true feasibility, never reported as the complete action set.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from collections import defaultdict
from typing import Any, Callable

try:
    from scripts.analyze_counterfactual_sensitivity_regimes import _state_observables
    from scripts.evaluate_counterfactual_afterstate_value import (
        _features,
        _predict_ridge,
        _state_delta,
        fit_ridge_model,
        predict_ridge_model,
    )
    from scripts.summarize_counterfactual_graph_signal import summarize_graph_signal
    from scripts.train_phase_conditioned_soft_policy import teacher_signature
except ModuleNotFoundError:
    from analyze_counterfactual_sensitivity_regimes import _state_observables
    from evaluate_counterfactual_afterstate_value import (
        _features,
        _predict_ridge,
        _state_delta,
        fit_ridge_model,
        predict_ridge_model,
    )
    from summarize_counterfactual_graph_signal import summarize_graph_signal
    from train_phase_conditioned_soft_policy import teacher_signature


LABEL_FAMILY = "residual_affordance_labels"
PARETO_METRIC = "searched_residual_affordance_pareto"
DIRECTIONAL = ("lower_afterstate_better", "higher_afterstate_better")
AFFORDANCE_NAMES = (
    "expected_safe_additional_placements",
    "searched_horizon_completion_probability",
    "next_safe_item_breadth",
    "future_safe_item_breadth",
    "future_safe_nonsoft_item_breadth",
    "future_safe_soft_item_breadth",
    "future_safe_priority_item_breadth",
    "maximum_future_safe_item_volume",
)


def _visible_items(state: dict[str, Any]) -> dict[int, dict[str, float]]:
    names = state.get("visible_item_features", [])
    return {
        int(index): {name: float(value) for name, value in zip(names, values)}
        for index, values in zip(
            state.get("visible_item_indices", []),
            state.get("visible_item_values", []),
        )
    }


def affordance_summary(
    samples: list[dict[str, Any]], afterstate: dict[str, Any],
) -> list[float]:
    """Return a weight-aware searched-affordance vector for one afterstate."""
    items = _visible_items(afterstate)
    total_weight = sum(float(sample["search_policy_weight"]) for sample in samples)
    if not samples or total_weight <= 0.0:
        return [0.0] * len(AFFORDANCE_NAMES)
    expected_safe = horizon_weight = 0.0
    safe_paths: list[list[int]] = []
    for sample in samples:
        weight = float(sample["search_policy_weight"]) / total_weight
        path = [int(value) for value in sample["path_stable_item_indices"]]
        reason = str(sample.get("terminal_reason", "open_leaf"))
        if reason == "physical_failure" and path:
            path = path[:-1]
        safe_paths.append(path)
        expected_safe += weight * len(path)
        horizon_weight += weight * int(reason == "horizon")
    next_items = {path[0] for path in safe_paths if path}
    future_items = {item for path in safe_paths for item in path}
    nonsoft = {
        index for index in future_items
        if index in items and not bool(items[index].get("is_soft", 0.0))
    }
    soft = {
        index for index in future_items
        if index in items and bool(items[index].get("is_soft", 0.0))
    }
    priority = {
        index for index in future_items
        if index in items and bool(items[index].get("is_prioritized", 0.0))
    }
    volumes = [
        items[index].get("length", 0.0)
        * items[index].get("width", 0.0)
        * items[index].get("height", 0.0)
        for index in future_items if index in items
    ]
    return [
        expected_safe,
        horizon_weight,
        float(len(next_items)),
        float(len(future_items)),
        float(len(nonsoft)),
        float(len(soft)),
        float(len(priority)),
        max(volumes, default=0.0),
    ]


def pareto_relation(lower: list[float], higher: list[float]) -> str:
    if len(lower) != len(higher):
        raise ValueError("affordance vector shape mismatch")
    tolerance = 1e-12
    lower_not_worse = all(left >= right - tolerance for left, right in zip(lower, higher))
    higher_not_worse = all(right >= left - tolerance for left, right in zip(lower, higher))
    lower_strict = any(left > right + tolerance for left, right in zip(lower, higher))
    higher_strict = any(right > left + tolerance for left, right in zip(lower, higher))
    if lower_not_worse and lower_strict:
        return "lower_afterstate_better"
    if higher_not_worse and higher_strict:
        return "higher_afterstate_better"
    if not lower_strict and not higher_strict:
        return "equal"
    return "tradeoff"


def _row_id(graph_id: str, pair: dict[str, Any]) -> str:
    payload = (
        f"{graph_id}:{pair['source_node_id']}:"
        f"{pair['lower_stable_item_index']}:{pair['higher_stable_item_index']}"
    )
    return "affordance-" + hashlib.sha256(payload.encode()).hexdigest()[:20]


def build_affordance_rows(graph_root: pathlib.Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = []
    graph_count = pair_count = 0
    relations: dict[str, int] = defaultdict(int)
    relations_by_root_step: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    relations_by_case: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    commits = set()
    for path in sorted(graph_root.rglob("graph.json")):
        graph = json.loads(path.read_text(encoding="utf-8"))
        summary = summarize_graph_signal(
            graph, source=str(path), include_afterstate_tensors=True
        )
        graph_count += 1
        commits.add(str(summary.get("commit", "")))
        for pair in summary["sibling_pairs"]:
            pair_count += 1
            lower = affordance_summary(
                pair["lower_continuation_samples"], pair["lower_afterstate_tensor"]
            )
            higher = affordance_summary(
                pair["higher_continuation_samples"], pair["higher_afterstate_tensor"]
            )
            relation = pareto_relation(lower, higher)
            relations[relation] += 1
            relations_by_root_step[str(summary["root_step"])][relation] += 1
            relations_by_case[str(summary["case_id"])][relation] += 1
            rows.append({
                "teacher_id": _row_id(summary["graph_id"], pair),
                "case_id": summary["case_id"],
                "graph_id": summary["graph_id"],
                "root_step": int(summary["root_step"]),
                "source_node_id": pair["source_node_id"],
                "source_depth": int(pair["source_depth"]),
                "source_state_tensor": pair["source_state_tensor"],
                "lower_action_tensor": pair["lower_action_tensor"],
                "higher_action_tensor": pair["higher_action_tensor"],
                "lower_afterstate_tensor": pair["lower_afterstate_tensor"],
                "higher_afterstate_tensor": pair["higher_afterstate_tensor"],
                "immediate_score_gap": float(pair["score_gap"]),
                "lower_stable_item_index": pair["lower_stable_item_index"],
                "higher_stable_item_index": pair["higher_stable_item_index"],
                "scenario_axes": summary["scenario_axes"],
                "lower_affordance": dict(zip(AFFORDANCE_NAMES, lower)),
                "higher_affordance": dict(zip(AFFORDANCE_NAMES, higher)),
                LABEL_FAMILY: {
                    PARETO_METRIC: {
                        "relation": relation,
                        "contract": "pareto_over_branch_capped_searched_future_actions_v1",
                    }
                },
            })
    return rows, {
        "graph_count": graph_count,
        "sibling_pairs": pair_count,
        "relations": dict(sorted(relations.items())),
        "relations_by_root_step": {
            key: dict(sorted(value.items()))
            for key, value in sorted(relations_by_root_step.items())
        },
        "relations_by_case": {
            key: dict(sorted(value.items()))
            for key, value in sorted(relations_by_case.items())
        },
        "source_commits": sorted(commits),
        "affordance_names": list(AFFORDANCE_NAMES),
        "proxy_limit": "branch-factor-capped searched actions, not complete feasibility",
    }


def _eligible(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row for row in rows
        if row[LABEL_FAMILY][PARETO_METRIC]["relation"] in DIRECTIONAL
    ]


def _correct(predictions: dict[str, str], rows: list[dict[str, Any]]) -> int:
    return sum(
        predictions.get(row["teacher_id"])
        == row[LABEL_FAMILY][PARETO_METRIC]["relation"]
        for row in rows
    )


def _feature_sets() -> dict[str, Callable[[dict[str, Any]], list[float]]]:
    def compact_afterstate(row: dict[str, Any]) -> list[float]:
        lower = _state_observables(row["lower_afterstate_tensor"])
        higher = _state_observables(row["higher_afterstate_tensor"])
        return [right - left for left, right in zip(lower, higher)]

    action = lambda row: _features(
        row, include_action=True, include_afterstate=False
    )
    return {
        "action_geometry": action,
        "compact_physical_afterstate": compact_afterstate,
        "pooled_afterstate": _state_delta,
        "action_plus_compact_afterstate": lambda row: (
            action(row) + compact_afterstate(row)
        ),
        "action_plus_afterstate": lambda row: _features(
            row, include_action=True, include_afterstate=True
        ),
    }


def train_policy(
    source_run_id: str, rows: list[dict[str, Any]], metadata: dict[str, Any],
) -> dict[str, Any]:
    eligible = _eligible(rows)
    groups = sorted({row["graph_id"] for row in eligible})
    if len(eligible) < 20 or len(groups) < 2:
        raise ValueError("residual affordance training requires 20 rows and two graphs")
    features = _feature_sets()
    predictions = {name: {} for name in features}
    graph_results = []
    for group in groups:
        train = [row for row in eligible if row["graph_id"] != group]
        test = [row for row in eligible if row["graph_id"] == group]
        for name, values in features.items():
            predictions[name].update(_predict_ridge(
                train, test, PARETO_METRIC, values, label_family=LABEL_FAMILY
            ))
        graph_results.append((group, test))
    immediate = {
        row["teacher_id"]: (
            "higher_afterstate_better"
            if row["immediate_score_gap"] >= 0.0 else "lower_afterstate_better"
        )
        for row in eligible
    }
    counts = {
        "immediate_score": _correct(immediate, eligible),
        **{name: _correct(value, eligible) for name, value in predictions.items()},
    }
    candidates = (
        "compact_physical_afterstate",
        "pooled_afterstate",
        "action_plus_compact_afterstate",
        "action_plus_afterstate",
    )
    selected = max(candidates, key=lambda name: (counts[name], -candidates.index(name)))
    wins = ties = losses = 0
    for _group, test in graph_results:
        selected_correct = _correct(predictions[selected], test)
        action_correct = _correct(predictions["action_geometry"], test)
        if selected_correct > action_correct:
            wins += 1
        elif selected_correct < action_correct:
            losses += 1
        else:
            ties += 1
    development_passed = (
        counts[selected] > counts["immediate_score"]
        and counts[selected] > counts["action_geometry"]
        and wins > losses
    )
    return {
        "schema_version": 1,
        "status": "prospective_evaluation_only",
        "target": PARETO_METRIC,
        "label_family": LABEL_FAMILY,
        "source_run_id": str(source_run_id),
        "source_commits": metadata["source_commits"],
        "teacher_contract": "pareto_over_branch_capped_searched_future_actions_v1",
        "proxy_limit": metadata["proxy_limit"],
        "training_graphs": len(groups),
        "training_directional_rows": len(eligible),
        "training_relations": metadata["relations"],
        "training_relations_by_root_step": metadata["relations_by_root_step"],
        "training_relations_by_case": metadata["relations_by_case"],
        "selected_model": selected,
        "development_cv": {
            "protocol": "leave_one_physical_graph_out",
            "models": {
                name: {"correct": value, "total": len(eligible)}
                for name, value in counts.items()
            },
            "selected_vs_action_by_graph": {
                "wins": wins, "ties": ties, "losses": losses,
            },
            "passed": development_passed,
        },
        "model": fit_ridge_model(
            eligible, PARETO_METRIC, features[selected], label_family=LABEL_FAMILY
        ),
        "action_model": fit_ridge_model(
            eligible, PARETO_METRIC, features["action_geometry"],
            label_family=LABEL_FAMILY,
        ),
        "training_teacher_signatures": sorted(teacher_signature(row) for row in eligible),
        "promotion_contract": (
            "development CV passed; different physical run; zero signature overlap; "
            "at least 20 Pareto-directional rows; selected strictly beats immediate "
            "score and action geometry"
        ),
    }


def evaluate_policy(
    policy: dict[str, Any], target_run_id: str, rows: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    if str(target_run_id) == str(policy["source_run_id"]):
        raise ValueError("prospective evaluation requires a different physical run")
    eligible = _eligible(rows)
    features = _feature_sets()
    selected_name = str(policy["selected_model"])
    selected_predictions = predict_ridge_model(
        policy["model"], eligible, features[selected_name]
    )
    action_predictions = predict_ridge_model(
        policy["action_model"], eligible, features["action_geometry"]
    )
    immediate = {
        row["teacher_id"]: (
            "higher_afterstate_better"
            if row["immediate_score_gap"] >= 0.0 else "lower_afterstate_better"
        )
        for row in eligible
    }
    overlap = (
        set(policy["training_teacher_signatures"])
        & {teacher_signature(row) for row in eligible}
    )
    counts = {
        "immediate_score": _correct(immediate, eligible),
        "action_geometry": _correct(action_predictions, eligible),
        selected_name: _correct(selected_predictions, eligible),
    }
    selected_correct = counts[selected_name]
    passed = (
        bool(policy["development_cv"]["passed"])
        and len(eligible) >= 20
        and not overlap
        and selected_correct > counts["immediate_score"]
        and selected_correct > counts["action_geometry"]
    )
    return {
        "schema_version": 1,
        "protocol": "frozen_residual_affordance_model_on_whole_future_physical_run",
        "training_run_id": str(policy["source_run_id"]),
        "target_run_id": str(target_run_id),
        "proxy_limit": metadata["proxy_limit"],
        "target_graphs": metadata["graph_count"],
        "target_sibling_pairs": metadata["sibling_pairs"],
        "target_relations": metadata["relations"],
        "target_relations_by_root_step": metadata["relations_by_root_step"],
        "target_relations_by_case": metadata["relations_by_case"],
        "directional_rows": len(eligible),
        "teacher_signature_overlap": len(overlap),
        "selected_model": selected_name,
        "development_cv": policy["development_cv"],
        "models": {
            name: {"correct": correct, "total": len(eligible)}
            for name, correct in counts.items()
        },
        "prospective_signal": {
            "non_immediate_model_beats_immediate": max(
                counts["action_geometry"], selected_correct
            ) > counts["immediate_score"],
            "best_gain_over_immediate": max(
                counts["action_geometry"], selected_correct
            ) - counts["immediate_score"],
            "interpretation": (
                "candidate_for_independent_replication_not_live_licensing"
            ),
        },
        "promotion_gate": {
            "passed": passed,
            "decision": "license_residual_affordance_shadow"
            if passed else "do_not_connect_residual_affordance_model",
        },
    }


def freeze_replication_candidate(
    policy: dict[str, Any], discovery_run_id: str,
    discovery_rows: list[dict[str, Any]], discovery_report: dict[str, Any],
) -> dict[str, Any]:
    """Nominate the frozen action model only after a prospective gain appears."""
    signal = discovery_report["prospective_signal"]
    action = discovery_report["models"]["action_geometry"]["correct"]
    immediate = discovery_report["models"]["immediate_score"]["correct"]
    if not signal["non_immediate_model_beats_immediate"] or action <= immediate:
        raise ValueError("replication candidate requires prospective action gain")
    discovery_eligible = _eligible(discovery_rows)
    excluded = set(policy["training_teacher_signatures"])
    excluded.update(teacher_signature(row) for row in discovery_eligible)
    return {
        "schema_version": 1,
        "status": "prospective_replication_only",
        "target": PARETO_METRIC,
        "label_family": LABEL_FAMILY,
        "candidate_model": "action_geometry",
        "model": policy["action_model"],
        "training_run_id": str(policy["source_run_id"]),
        "discovery_run_id": str(discovery_run_id),
        "discovery_evidence": {
            "directional_rows": discovery_report["directional_rows"],
            "immediate_correct": immediate,
            "candidate_correct": action,
            "gain": action - immediate,
        },
        "excluded_teacher_signatures": sorted(excluded),
        "replication_contract": (
            "one third physical run distinct from training and discovery; zero "
            "teacher-signature overlap; at least 20 Pareto-directional rows; frozen "
            "action geometry strictly beats immediate score"
        ),
    }


def evaluate_replication_candidate(
    candidate: dict[str, Any], target_run_id: str,
    rows: list[dict[str, Any]], metadata: dict[str, Any],
) -> dict[str, Any]:
    if candidate.get("status") != "prospective_replication_only":
        raise ValueError("artifact is not a prospective replication candidate")
    if str(target_run_id) in {
        str(candidate["training_run_id"]), str(candidate["discovery_run_id"])
    }:
        raise ValueError("replication requires a third physical run")
    eligible = _eligible(rows)
    predictions = predict_ridge_model(
        candidate["model"], eligible, _feature_sets()["action_geometry"]
    )
    immediate_predictions = {
        row["teacher_id"]: (
            "higher_afterstate_better"
            if row["immediate_score_gap"] >= 0.0 else "lower_afterstate_better"
        )
        for row in eligible
    }
    overlap = (
        set(candidate["excluded_teacher_signatures"])
        & {teacher_signature(row) for row in eligible}
    )
    immediate = _correct(immediate_predictions, eligible)
    learned = _correct(predictions, eligible)
    candidate_wins = candidate_losses = both_correct = both_wrong = 0
    by_root_step: dict[str, dict[str, int]] = defaultdict(
        lambda: {"candidate_correct": 0, "immediate_correct": 0, "rows": 0}
    )
    by_case: dict[str, dict[str, int]] = defaultdict(
        lambda: {"candidate_correct": 0, "immediate_correct": 0, "rows": 0}
    )
    graph_scores: dict[str, dict[str, int]] = defaultdict(
        lambda: {"candidate_correct": 0, "immediate_correct": 0, "rows": 0}
    )
    for row in eligible:
        actual = row[LABEL_FAMILY][PARETO_METRIC]["relation"]
        candidate_correct = predictions[row["teacher_id"]] == actual
        immediate_row_correct = immediate_predictions[row["teacher_id"]] == actual
        candidate_wins += int(candidate_correct and not immediate_row_correct)
        candidate_losses += int(immediate_row_correct and not candidate_correct)
        both_correct += int(candidate_correct and immediate_row_correct)
        both_wrong += int(not candidate_correct and not immediate_row_correct)
        for bucket, key in (
            (by_root_step, str(row["root_step"])),
            (by_case, str(row["case_id"])),
            (graph_scores, str(row["graph_id"])),
        ):
            bucket[key]["candidate_correct"] += int(candidate_correct)
            bucket[key]["immediate_correct"] += int(immediate_row_correct)
            bucket[key]["rows"] += 1
    graph_wins = sum(
        value["candidate_correct"] > value["immediate_correct"]
        for value in graph_scores.values()
    )
    graph_losses = sum(
        value["candidate_correct"] < value["immediate_correct"]
        for value in graph_scores.values()
    )
    graph_ties = len(graph_scores) - graph_wins - graph_losses
    passed = len(eligible) >= 20 and not overlap and learned > immediate
    return {
        "schema_version": 1,
        "protocol": "third_stream_replication_of_frozen_affordance_action_model",
        "training_run_id": str(candidate["training_run_id"]),
        "discovery_run_id": str(candidate["discovery_run_id"]),
        "target_run_id": str(target_run_id),
        "target_graphs": metadata["graph_count"],
        "target_sibling_pairs": metadata["sibling_pairs"],
        "target_relations": metadata["relations"],
        "target_relations_by_root_step": metadata["relations_by_root_step"],
        "target_relations_by_case": metadata["relations_by_case"],
        "directional_rows": len(eligible),
        "teacher_signature_overlap": len(overlap),
        "models": {
            "immediate_score": {"correct": immediate, "total": len(eligible)},
            "frozen_action_geometry": {"correct": learned, "total": len(eligible)},
        },
        "paired_vs_immediate": {
            "wins": candidate_wins,
            "ties_both_correct": both_correct,
            "ties_both_wrong": both_wrong,
            "losses": candidate_losses,
        },
        "by_graph_vs_immediate": {
            "wins": graph_wins, "ties": graph_ties, "losses": graph_losses,
        },
        "by_root_step": dict(sorted(by_root_step.items())),
        "by_case": dict(sorted(by_case.items())),
        "replication_gate": {
            "passed": passed,
            "gain_over_immediate": learned - immediate,
            "decision": "license_residual_affordance_shadow"
            if passed else "do_not_connect_residual_affordance_model",
        },
    }


def freeze_phase_hybrid_candidate(
    candidate: dict[str, Any], replication_run_id: str,
    replication_rows: list[dict[str, Any]], replication_report: dict[str, Any],
) -> dict[str, Any]:
    gate = replication_report["replication_gate"]
    if not gate["passed"]:
        raise ValueError("phase hybrid requires a passed replication candidate")
    eligible = _eligible(replication_rows)
    predictions = predict_ridge_model(
        candidate["model"], eligible, _feature_sets()["action_geometry"]
    )
    immediate_predictions = {
        row["teacher_id"]: (
            "higher_afterstate_better"
            if row["immediate_score_gap"] >= 0.0 else "lower_afterstate_better"
        )
        for row in eligible
    }
    hybrid_predictions = phase_hybrid_predictions(
        eligible, predictions, immediate_predictions, maximum_root_step=6
    )
    excluded = set(candidate["excluded_teacher_signatures"])
    excluded.update(teacher_signature(row) for row in eligible)
    return {
        "schema_version": 1,
        "status": "prospective_phase_hybrid_only",
        "target": PARETO_METRIC,
        "label_family": LABEL_FAMILY,
        "candidate_model": "action_geometry_at_root_step_le_6_else_immediate_score",
        "action_model": candidate["model"],
        "action_gate": {"observable": "root_step", "maximum_inclusive": 6},
        "training_run_id": str(candidate["training_run_id"]),
        "discovery_run_id": str(candidate["discovery_run_id"]),
        "replication_run_id": str(replication_run_id),
        "replication_evidence": {
            "directional_rows": len(eligible),
            "immediate_correct": _correct(immediate_predictions, eligible),
            "global_action_correct": _correct(predictions, eligible),
            "phase_hybrid_correct": _correct(hybrid_predictions, eligible),
        },
        "excluded_teacher_signatures": sorted(excluded),
        "promotion_contract": (
            "one fourth physical run distinct from training/discovery/replication; "
            "zero signature overlap; at least 20 Pareto-directional rows; frozen "
            "step-6 hybrid strictly beats immediate and does not underperform the "
            "globally applied frozen action model; graph wins exceed losses"
        ),
    }


def evaluate_phase_hybrid_candidate(
    candidate: dict[str, Any], target_run_id: str,
    rows: list[dict[str, Any]], metadata: dict[str, Any],
) -> dict[str, Any]:
    if candidate.get("status") != "prospective_phase_hybrid_only":
        raise ValueError("artifact is not a prospective phase hybrid")
    prior_runs = {
        str(candidate["training_run_id"]),
        str(candidate["discovery_run_id"]),
        str(candidate["replication_run_id"]),
    }
    if str(target_run_id) in prior_runs:
        raise ValueError("phase hybrid evaluation requires a fourth physical run")
    eligible = _eligible(rows)
    action_predictions = predict_ridge_model(
        candidate["action_model"], eligible, _feature_sets()["action_geometry"]
    )
    immediate_predictions = {
        row["teacher_id"]: (
            "higher_afterstate_better"
            if row["immediate_score_gap"] >= 0.0 else "lower_afterstate_better"
        )
        for row in eligible
    }
    maximum = int(candidate["action_gate"]["maximum_inclusive"])
    hybrid_predictions = phase_hybrid_predictions(
        eligible, action_predictions, immediate_predictions,
        maximum_root_step=maximum,
    )
    overlap = (
        set(candidate["excluded_teacher_signatures"])
        & {teacher_signature(row) for row in eligible}
    )
    immediate = _correct(immediate_predictions, eligible)
    action = _correct(action_predictions, eligible)
    hybrid = _correct(hybrid_predictions, eligible)
    graph_scores: dict[str, dict[str, int]] = defaultdict(
        lambda: {"hybrid": 0, "action": 0, "immediate": 0}
    )
    for row in eligible:
        actual = row[LABEL_FAMILY][PARETO_METRIC]["relation"]
        graph = graph_scores[str(row["graph_id"])]
        graph["hybrid"] += int(hybrid_predictions[row["teacher_id"]] == actual)
        graph["action"] += int(action_predictions[row["teacher_id"]] == actual)
        graph["immediate"] += int(
            immediate_predictions[row["teacher_id"]] == actual
        )
    graph_wins = sum(
        value["hybrid"] > value["immediate"] for value in graph_scores.values()
    )
    graph_losses = sum(
        value["hybrid"] < value["immediate"] for value in graph_scores.values()
    )
    graph_ties = len(graph_scores) - graph_wins - graph_losses
    action_graph_wins = sum(
        value["action"] > value["immediate"] for value in graph_scores.values()
    )
    action_graph_losses = sum(
        value["action"] < value["immediate"] for value in graph_scores.values()
    )
    action_graph_ties = len(graph_scores) - action_graph_wins - action_graph_losses
    passed = (
        len(eligible) >= 20 and not overlap
        and hybrid > immediate and hybrid >= action
        and graph_wins > graph_losses
    )
    by_root_step = {}
    for step in sorted({int(row["root_step"]) for row in eligible}):
        selected = [row for row in eligible if int(row["root_step"]) == step]
        by_root_step[str(step)] = {
            "rows": len(selected),
            "immediate_correct": _correct(immediate_predictions, selected),
            "global_action_correct": _correct(action_predictions, selected),
            "phase_hybrid_correct": _correct(hybrid_predictions, selected),
        }
    return {
        "schema_version": 1,
        "protocol": "fourth_stream_frozen_step6_residual_affordance_hybrid",
        "training_run_id": str(candidate["training_run_id"]),
        "discovery_run_id": str(candidate["discovery_run_id"]),
        "replication_run_id": str(candidate["replication_run_id"]),
        "target_run_id": str(target_run_id),
        "target_graphs": metadata["graph_count"],
        "target_sibling_pairs": metadata["sibling_pairs"],
        "directional_rows": len(eligible),
        "teacher_signature_overlap": len(overlap),
        "models": {
            "immediate_score": {"correct": immediate, "total": len(eligible)},
            "global_frozen_action": {"correct": action, "total": len(eligible)},
            "phase_hybrid": {"correct": hybrid, "total": len(eligible)},
        },
        "by_root_step": by_root_step,
        "by_graph_vs_immediate": {
            "wins": graph_wins, "ties": graph_ties, "losses": graph_losses,
        },
        "global_action_confirmation": {
            "gain_over_immediate": action - immediate,
            "graph_wins": action_graph_wins,
            "graph_ties": action_graph_ties,
            "graph_losses": action_graph_losses,
            "confirmed": (
                action > immediate and action_graph_wins > action_graph_losses
            ),
            "interpretation": "additional_confirmation_of_already_licensed_shadow",
        },
        "promotion_gate": {
            "passed": passed,
            "gain_over_immediate": hybrid - immediate,
            "gain_over_global_action": hybrid - action,
            "decision": "license_phase_hybrid_shadow"
            if passed else "do_not_connect_phase_hybrid",
        },
    }


def phase_hybrid_predictions(
    rows: list[dict[str, Any]], action_predictions: dict[str, str],
    immediate_predictions: dict[str, str], *, maximum_root_step: int,
) -> dict[str, str]:
    """Use the learned correction only in the predeclared early root regime."""
    return {
        row["teacher_id"]: (
            action_predictions[row["teacher_id"]]
            if int(row["root_step"]) <= maximum_root_step
            else immediate_predictions[row["teacher_id"]]
        )
        for row in rows
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Residual-space searched-affordance value", "",
        f"Training / target run: **{report['training_run_id']} / {report['target_run_id']}**",
        f"Target graphs / pairs / Pareto-directional rows: **{report['target_graphs']} / "
        f"{report['target_sibling_pairs']} / {report['directional_rows']}**",
        f"Teacher-signature overlap: **{report['teacher_signature_overlap']}**.",
        f"Proxy limit: {report['proxy_limit']}.", "",
        "| Model | Correct |", "|---|---:|",
    ]
    for name, result in report["models"].items():
        lines.append(f"| {name} | {result['correct']}/{result['total']} |")
    development = report["development_cv"]
    signal = report["prospective_signal"]
    gate = report["promotion_gate"]
    lines.extend([
        "",
        f"Development CV: **{'PASS' if development['passed'] else 'FAIL'}**; "
        f"selected `{report['selected_model']}`.",
        f"Prospective non-immediate gain: **{signal['best_gain_over_immediate']:+d}** "
        f"({signal['interpretation']}).",
        f"Prospective promotion: **{'PASS' if gate['passed'] else 'FAIL'}** "
        f"({gate['decision']}).", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-graphs", type=pathlib.Path, required=True)
    parser.add_argument("--training-run-id", required=True)
    parser.add_argument("--target-graphs", type=pathlib.Path, required=True)
    parser.add_argument("--target-run-id", required=True)
    parser.add_argument("--policy-output", type=pathlib.Path, required=True)
    parser.add_argument(
        "--replication-policy-output", type=pathlib.Path, required=True
    )
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    training_rows, training_metadata = build_affordance_rows(args.training_graphs)
    policy = train_policy(args.training_run_id, training_rows, training_metadata)
    target_rows, target_metadata = build_affordance_rows(args.target_graphs)
    report = evaluate_policy(policy, args.target_run_id, target_rows, target_metadata)
    replication = freeze_replication_candidate(
        policy, args.target_run_id, target_rows, report
    )
    for path in (
        args.policy_output, args.replication_policy_output,
        args.json_output, args.markdown_output,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.policy_output.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    args.replication_policy_output.write_text(
        json.dumps(replication, indent=2) + "\n", encoding="utf-8"
    )
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
