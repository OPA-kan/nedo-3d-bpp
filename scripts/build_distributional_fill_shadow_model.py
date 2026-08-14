"""Freeze and apply the confirmed distributional fill shadow model."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any, Callable

try:
    from scripts.evaluate_counterfactual_afterstate_value import (
        _features,
        _read_jsonl,
        _state_block_delta,
        fit_ridge_model,
        load_run,
        predict_ridge_model,
    )
except ModuleNotFoundError:
    from evaluate_counterfactual_afterstate_value import (
        _features,
        _read_jsonl,
        _state_block_delta,
        fit_ridge_model,
        load_run,
        predict_ridge_model,
    )


LABEL_FAMILY = "distributional_continuation_labels"
METRIC = "fill_score_proxy"


def feature_builders() -> dict[str, Callable[[dict[str, Any]], list[float]]]:
    return {
        "packed": lambda row: _state_block_delta(row, "packed"),
        "packed_visible": lambda row: _state_block_delta(
            row, "packed_visible"
        ),
        "action_geometry": lambda row: _features(
            row, include_action=True, include_afterstate=False
        ),
    }


def build_model(training_runs: list[dict[str, Any]]) -> dict[str, Any]:
    run_ids = [str(run["run_id"]) for run in training_runs]
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("training run IDs must be unique")
    training = [
        row for run in training_runs for row in run["discovery"]
    ]
    models = {
        name: fit_ridge_model(
            training, METRIC, features, label_family=LABEL_FAMILY
        )
        for name, features in feature_builders().items()
    }
    return {
        "schema_version": 1,
        "status": "confirmed_offline_shadow_model",
        "label_family": LABEL_FAMILY,
        "axis": METRIC,
        "training_run_ids": run_ids,
        "decision": (
            "use packed/packed-visible consensus when they agree; otherwise "
            "use action geometry"
        ),
        "feature_contracts": {
            "packed": "packed_afterstate_summary_delta",
            "packed_visible": "packed_plus_visible_afterstate_summary_delta",
            "action_geometry": "action_geometry_delta_without_immediate_score",
        },
        "models": models,
        "claim_limit": (
            "Offline post-settle shadow use only; afterstates are unavailable "
            "to live ranking without a separate predictor or simulator."
        ),
    }


def shadow_predictions(
    model: dict[str, Any], rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    builders = feature_builders()
    predictions = {
        name: predict_ridge_model(model["models"][name], rows, features)
        for name, features in builders.items()
    }
    output = []
    for row in rows:
        teacher_id = row["teacher_id"]
        packed = predictions["packed"][teacher_id]
        packed_visible = predictions["packed_visible"][teacher_id]
        action = predictions["action_geometry"][teacher_id]
        used_afterstate = packed == packed_visible
        relation = packed if used_afterstate else action
        choose_higher = relation == "higher_afterstate_better"
        output.append({
            "teacher_id": teacher_id,
            "graph_id": row["graph_id"],
            "source_node_id": row["source_node_id"],
            "lower_stable_item_index": row["lower_stable_item_index"],
            "higher_stable_item_index": row["higher_stable_item_index"],
            "packed_prediction": packed,
            "packed_visible_prediction": packed_visible,
            "action_geometry_prediction": action,
            "used_afterstate": used_afterstate,
            "shadow_relation": relation,
            "shadow_stable_item_index": (
                row["higher_stable_item_index"]
                if choose_higher else row["lower_stable_item_index"]
            ),
            "action_geometry_stable_item_index": (
                row["higher_stable_item_index"]
                if action == "higher_afterstate_better"
                else row["lower_stable_item_index"]
            ),
            "changed_from_action_geometry": relation != action,
        })
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-dir", action="append", type=pathlib.Path)
    parser.add_argument("--model", type=pathlib.Path)
    parser.add_argument("--teacher-jsonl", type=pathlib.Path)
    parser.add_argument("--model-output", type=pathlib.Path)
    parser.add_argument("--shadow-output", type=pathlib.Path)
    args = parser.parse_args()
    if args.training_dir:
        if args.model or not args.model_output:
            parser.error("training requires --model-output and forbids --model")
        model = build_model([
            load_run(path, label_family=LABEL_FAMILY)
            for path in args.training_dir
        ])
        args.model_output.parent.mkdir(parents=True, exist_ok=True)
        args.model_output.write_text(
            json.dumps(model, indent=2) + "\n", encoding="utf-8"
        )
    elif args.model:
        model = json.loads(args.model.read_text(encoding="utf-8"))
    else:
        parser.error("provide --training-dir or --model")
    if args.teacher_jsonl:
        if not args.shadow_output:
            parser.error("--teacher-jsonl requires --shadow-output")
        predictions = shadow_predictions(model, _read_jsonl(args.teacher_jsonl))
        args.shadow_output.parent.mkdir(parents=True, exist_ok=True)
        args.shadow_output.write_text(
            "".join(json.dumps(row) + "\n" for row in predictions),
            encoding="utf-8",
        )
    print(args.model_output or args.shadow_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
