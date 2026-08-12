"""Export multi-axis sibling teachers from a counterfactual signal audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import collections
from typing import Any

try:
    from scripts.summarize_counterfactual_graph_signal import METRIC_DIRECTIONS
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from summarize_counterfactual_graph_signal import METRIC_DIRECTIONS


def _best(metric: str, value_range: list[float | int]) -> float | int:
    return value_range[1] if METRIC_DIRECTIONS[metric] > 0 else value_range[0]


def _outcome_equal(metric: str, left: float | int, right: float | int) -> bool:
    if metric in ("placed_count", "priority_misrouted", "soft_covered_by_other"):
        return left == right
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)


def _weakly_dominates(
    left: dict[str, float | int], right: dict[str, float | int],
) -> bool:
    return all(
        METRIC_DIRECTIONS[metric] * (left[metric] - right[metric]) >= 0
        for metric in METRIC_DIRECTIONS
    )


def _strictly_dominates(
    left: dict[str, float | int], right: dict[str, float | int],
) -> bool:
    return _weakly_dominates(left, right) and any(
        METRIC_DIRECTIONS[metric] * (left[metric] - right[metric]) > 0
        for metric in METRIC_DIRECTIONS
    )


def _pareto_frontier(
    vectors: list[dict[str, float | int]],
) -> list[dict[str, float | int]]:
    return [
        vector for index, vector in enumerate(vectors)
        if not any(
            _strictly_dominates(other, vector)
            for other_index, other in enumerate(vectors)
            if other_index != index
        )
    ]


def joint_pareto_label(pair: dict[str, Any]) -> dict[str, Any]:
    """Compare jointly attainable leaf vectors without an axis-weighted sum."""
    lower = _pareto_frontier(pair.get("lower_reachable_outcome_vectors", []))
    higher = _pareto_frontier(pair.get("higher_reachable_outcome_vectors", []))
    lower_covers = bool(lower and higher) and all(
        any(_weakly_dominates(candidate, target) for candidate in lower)
        for target in higher
    )
    higher_covers = bool(lower and higher) and all(
        any(_weakly_dominates(candidate, target) for candidate in higher)
        for target in lower
    )
    if lower_covers and not higher_covers:
        relation = "lower_reachable_set_dominates"
    elif higher_covers and not lower_covers:
        relation = "higher_reachable_set_dominates"
    elif lower_covers and higher_covers:
        relation = "equivalent_reachable_sets"
    else:
        relation = "incomparable_reachable_sets"
    return {
        "relation": relation,
        "lower_pareto_frontier": lower,
        "higher_pareto_frontier": higher,
        "lower_frontier_covers_higher": lower_covers,
        "higher_frontier_covers_lower": higher_covers,
    }


def continuation_labels(pair: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Compare future gains from physical child states, excluding action H0."""
    lower_vectors = pair.get("lower_continuation_outcome_vectors", [])
    higher_vectors = pair.get("higher_continuation_outcome_vectors", [])
    labels = {}
    for metric, direction in METRIC_DIRECTIONS.items():
        lower_values = [vector[metric] for vector in lower_vectors]
        higher_values = [vector[metric] for vector in higher_vectors]
        if not lower_values or not higher_values:
            continue
        lower_best = max(lower_values) if direction > 0 else min(lower_values)
        higher_best = max(higher_values) if direction > 0 else min(higher_values)
        if _outcome_equal(metric, lower_best, higher_best):
            relation = "equal"
        elif direction * (lower_best - higher_best) > 0:
            relation = "lower_afterstate_better"
        else:
            relation = "higher_afterstate_better"
        labels[metric] = {
            "relation": relation,
            "lower_best_continuation": lower_best,
            "higher_best_continuation": higher_best,
            "lower_continuation_values": lower_values,
            "higher_continuation_values": higher_values,
        }
    return labels


def join_afterstate_tensors(
    signal: dict[str, Any], graph_paths: list[pathlib.Path],
) -> None:
    """Join child tensors from raw graphs without duplicating them in signal."""
    raw_graphs = {}
    for path in graph_paths:
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph_id = graph["graph_id"]
        if graph_id in raw_graphs:
            raise ValueError(f"duplicate raw graph ID: {graph_id}")
        raw_graphs[graph_id] = graph
    for graph in signal["graphs"]:
        raw = raw_graphs.get(graph["graph_id"])
        if raw is None:
            raise ValueError(f"missing raw graph: {graph['graph_id']}")
        nodes = {node["node_id"]: node for node in raw["nodes"]}
        outgoing: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for edge in raw["edges"]:
            outgoing[edge["source"]].append(edge)
        for pair in graph["sibling_pairs"]:
            edges = outgoing[pair["source_node_id"]]
            if len(edges) != 2:
                raise ValueError(
                    f"expected two raw sibling edges: {pair['source_node_id']}"
                )
            lower, higher = sorted(
                edges, key=lambda edge: float(edge["selection"]["score"])
            )
            pair["lower_afterstate_tensor"] = nodes[lower["target"]].get(
                "state_tensor"
            )
            pair["higher_afterstate_tensor"] = nodes[higher["target"]].get(
                "state_tensor"
            )


def teacher_row(graph: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    labels = {}
    for metric, comparison in pair["comparisons"].items():
        lower = _best(metric, comparison["lower_range"])
        higher = _best(metric, comparison["higher_range"])
        direction = METRIC_DIRECTIONS[metric]
        if _outcome_equal(metric, lower, higher):
            relation = "equal"
        elif (lower > higher and direction > 0) or (
            lower < higher and direction < 0
        ):
            relation = "lower_immediate_score_better"
        else:
            relation = "higher_immediate_score_better"
        labels[metric] = {
            "relation": relation,
            "lower_best_reachable": lower,
            "higher_best_reachable": higher,
            "lower_reachable_range": comparison["lower_range"],
            "higher_reachable_range": comparison["higher_range"],
        }
    informative = any(
        label["relation"] != "equal" for label in labels.values()
    )
    identity = {
        "graph_id": graph["graph_id"],
        "source_node_id": pair["source_node_id"],
    }
    teacher_id = "teacher-" + hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return {
        "teacher_id": teacher_id,
        "split": (
            "discovery" if int(graph["root_step"]) < 15 else "late_holdout"
        ),
        "case_id": graph["case_id"],
        "graph_id": graph["graph_id"],
        "root_step": int(graph["root_step"]),
        "source_node_id": pair["source_node_id"],
        "source_depth": int(pair["source_depth"]),
        "source_state_tensor": pair.get("source_state_tensor"),
        "lower_action_tensor": pair.get("lower_action_tensor"),
        "higher_action_tensor": pair.get("higher_action_tensor"),
        "lower_afterstate_tensor": pair.get("lower_afterstate_tensor"),
        "higher_afterstate_tensor": pair.get("higher_afterstate_tensor"),
        "scenario_axes": graph.get("scenario_axes", {}),
        "lower_stable_item_index": pair["lower_stable_item_index"],
        "higher_stable_item_index": pair["higher_stable_item_index"],
        "immediate_score_gap": float(pair["score_gap"]),
        "equal_immediate_score": bool(pair["equal_immediate_score"]),
        "informative_on_recorded_axes": informative,
        "labels": labels,
        "continuation_labels": continuation_labels(pair),
        "joint_pareto": joint_pareto_label(pair),
    }


def build_teacher_corpus(signal: dict[str, Any]) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    buckets = {"discovery": [], "late_holdout": [], "controls": []}
    for graph in signal["graphs"]:
        for pair in graph["sibling_pairs"]:
            row = teacher_row(graph, pair)
            if row["equal_immediate_score"] or not row[
                "informative_on_recorded_axes"
            ]:
                buckets["controls"].append(row)
            else:
                buckets[row["split"]].append(row)
    relations = {
        metric: {relation: 0 for relation in (
            "lower_immediate_score_better",
            "higher_immediate_score_better",
            "equal",
        )}
        for metric in METRIC_DIRECTIONS
    }
    joint_relations = {
        relation: 0 for relation in (
            "lower_reachable_set_dominates",
            "higher_reachable_set_dominates",
            "equivalent_reachable_sets",
            "incomparable_reachable_sets",
        )
    }
    for split in ("discovery", "late_holdout"):
        for row in buckets[split]:
            for metric, label in row["labels"].items():
                relations[metric][label["relation"]] += 1
            joint_relations[row["joint_pareto"]["relation"]] += 1
    informative = buckets["discovery"] + buckets["late_holdout"]
    tensor_rows = sum(
        isinstance(row.get("source_state_tensor"), dict)
        for row in informative
    )
    tensor_contracts = sorted({
        row["source_state_tensor"].get("contract")
        for row in informative
        if isinstance(row.get("source_state_tensor"), dict)
    })
    action_tensor_rows = sum(
        isinstance(row.get("lower_action_tensor"), dict)
        and isinstance(row.get("higher_action_tensor"), dict)
        for row in informative
    )
    action_tensor_contracts = sorted({
        action.get("contract")
        for row in informative
        for action in (
            row.get("lower_action_tensor"), row.get("higher_action_tensor")
        )
        if isinstance(action, dict)
    })
    afterstate_tensor_rows = sum(
        isinstance(row.get("lower_afterstate_tensor"), dict)
        and isinstance(row.get("higher_afterstate_tensor"), dict)
        for row in informative
    )
    continuation_directional_counts = {
        metric: sum(
            row.get("continuation_labels", {}).get(metric, {}).get("relation")
            in ("lower_afterstate_better", "higher_afterstate_better")
            for row in informative
        )
        for metric in METRIC_DIRECTIONS
    }
    manifest = {
        "schema_version": 4,
        "source_run_id": signal.get("run_id"),
        "source_commits": signal.get("commits", []),
        "label_contract": (
            "Per-axis optimistic bounded reachability. No axes are summed; "
            "a label compares each sibling subtree's best recorded leaf. "
            "Joint Pareto labels separately compare attainable leaf vectors. "
            "Continuation labels compare future gains from physical child "
            "states after subtracting each first action's H0 outcome. "
            "Continuous outcomes within absolute tolerance 1e-12 are equal; "
            "discrete outcomes require exact equality."
        ),
        "split_contract": "root_step < 15 discovery; root_step >= 15 late_holdout",
        "model_training_ready": bool(
            buckets["discovery"]
            and buckets["late_holdout"]
            and tensor_rows == len(informative)
            and action_tensor_rows == len(informative)
            and afterstate_tensor_rows == len(informative)
            and tensor_contracts == [
                "observed_set_tensors_no_step_no_future_labels"
            ]
            and action_tensor_contracts == [
                "observed_candidate_action_no_future_labels"
            ]
        ),
        "informative_pair_rows": (
            len(buckets["discovery"]) + len(buckets["late_holdout"])
        ),
        "discovery_rows": len(buckets["discovery"]),
        "late_holdout_rows": len(buckets["late_holdout"]),
        "uninformative_control_rows": len(buckets["controls"]),
        "rows_with_source_state_tensor": tensor_rows,
        "source_state_tensor_contracts": tensor_contracts,
        "rows_with_paired_action_tensors": action_tensor_rows,
        "action_tensor_contracts": action_tensor_contracts,
        "rows_with_paired_afterstate_tensors": afterstate_tensor_rows,
        "continuation_directional_counts": continuation_directional_counts,
        "axis_relation_counts_on_training_rows": relations,
        "joint_pareto_relation_counts_on_training_rows": joint_relations,
        "limitations": [
            "Synthetic condition matrix, not official-score calibration.",
            "Sibling rows from one graph share a root trajectory and are not independent.",
            "Best reachable leaf is existence under bounded search, not probability or expected value.",
            "Exact immediate-score controls have no recorded H3/H5 separation and are excluded from informative pairs.",
            "Variable-length set tensors require padding and masks in the batch loader; stored counts define the valid rows.",
            "Action tensors retain the official command coordinate frame and join only item fields visible at the source node.",
            "Joint Pareto labels preserve attainable multi-axis leaf vectors and do not combine axes with weights.",
            "Continuation labels subtract each physical child state's H0 outcomes from its leaves, so they supervise future value rather than the immediate action effect.",
        ],
    }
    return manifest, buckets


def _write_jsonl(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signal", type=pathlib.Path, required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--graph-root", type=pathlib.Path)
    args = parser.parse_args()
    signal = json.loads(args.signal.read_text(encoding="utf-8"))
    if args.graph_root is not None:
        paths = list(args.graph_root.rglob("graph.json"))
        if not paths:
            raise SystemExit(f"no graph.json files below {args.graph_root}")
        join_afterstate_tensors(signal, paths)
    manifest, buckets = build_teacher_corpus(signal)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, rows in buckets.items():
        _write_jsonl(args.output_dir / f"{name}.jsonl", rows)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output_dir / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
