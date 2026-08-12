"""Export multi-axis sibling teachers from a counterfactual signal audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

try:
    from scripts.summarize_counterfactual_graph_signal import METRIC_DIRECTIONS
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from summarize_counterfactual_graph_signal import METRIC_DIRECTIONS


def _best(metric: str, value_range: list[float | int]) -> float | int:
    return value_range[1] if METRIC_DIRECTIONS[metric] > 0 else value_range[0]


def teacher_row(graph: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    labels = {}
    for metric, comparison in pair["comparisons"].items():
        lower = _best(metric, comparison["lower_range"])
        higher = _best(metric, comparison["higher_range"])
        direction = METRIC_DIRECTIONS[metric]
        if lower == higher:
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
        "scenario_axes": graph.get("scenario_axes", {}),
        "lower_stable_item_index": pair["lower_stable_item_index"],
        "higher_stable_item_index": pair["higher_stable_item_index"],
        "immediate_score_gap": float(pair["score_gap"]),
        "equal_immediate_score": bool(pair["equal_immediate_score"]),
        "informative_on_recorded_axes": informative,
        "labels": labels,
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
    for split in ("discovery", "late_holdout"):
        for row in buckets[split]:
            for metric, label in row["labels"].items():
                relations[metric][label["relation"]] += 1
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
    manifest = {
        "schema_version": 1,
        "source_run_id": signal.get("run_id"),
        "source_commits": signal.get("commits", []),
        "label_contract": (
            "Per-axis optimistic bounded reachability. No axes are summed; "
            "a label compares each sibling subtree's best recorded leaf."
        ),
        "split_contract": "root_step < 15 discovery; root_step >= 15 late_holdout",
        "model_training_ready": bool(
            buckets["discovery"]
            and buckets["late_holdout"]
            and tensor_rows == len(informative)
            and tensor_contracts == [
                "observed_set_tensors_no_step_no_future_labels"
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
        "axis_relation_counts_on_training_rows": relations,
        "limitations": [
            "Synthetic condition matrix, not official-score calibration.",
            "Sibling rows from one graph share a root trajectory and are not independent.",
            "Best reachable leaf is existence under bounded search, not probability or expected value.",
            "Exact immediate-score controls have no recorded H3/H5 separation and are excluded from informative pairs.",
            "Variable-length set tensors require padding and masks in the batch loader; stored counts define the valid rows.",
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
    args = parser.parse_args()
    signal = json.loads(args.signal.read_text(encoding="utf-8"))
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
