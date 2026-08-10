"""Compact report for the residual-diversity physical pilot."""
from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


def _delta(comparison: dict[str, Any], name: str) -> float | int | None:
    value = (comparison.get("diversity_minus_random") or {}).get(name)
    return value if isinstance(value, (int, float)) else None


def summarize_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") != "complete":
        raise ValueError(
            f"dataset status is not complete: {payload.get('status')!r}"
        )
    case = payload.get("case")
    steps = case.get("steps", []) if isinstance(case, dict) else []
    if not steps:
        raise ValueError("dataset has no measured steps")

    rows = []
    for step in steps:
        sampling = step.get("sampling") or {}
        proxy = sampling.get("coverage_comparison")
        physical = sampling.get("physical_coverage_comparison")
        if not isinstance(physical, dict):
            raise ValueError(
                f"step {step.get('step')} has no physical coverage comparison"
            )
        if not isinstance(proxy, dict):
            raise ValueError(
                f"step {step.get('step')} has no proxy coverage comparison"
            )
        outcome_split = sampling.get("outcome_split") or {}
        rows.append(
            {
                "step": int(step["step"]),
                "status": str(step.get("status", "unknown")),
                "population": int(
                    (step.get("population") or {}).get("total", 0)
                ),
                "unique_replayed": int(sampling.get("unique_replayed", 0)),
                "primary_overdraw": int(
                    outcome_split.get("primary_overdraw", 0)
                ),
                "primary_safe_pool": int(
                    outcome_split.get("primary_safe_pool", 0)
                ),
                "positive_transition": int(
                    outcome_split.get("positive_transition", 0)
                ),
                "negative_physical_risk": int(
                    outcome_split.get("negative_physical_risk", 0)
                ),
                "proxy_nn_distance_delta": _delta(
                    proxy, "mean_nearest_neighbor_distance"
                ),
                "proxy_spatial_cells_delta": _delta(
                    proxy, "spatial_cell_count"
                ),
                "physical_nn_distance_delta": _delta(
                    physical, "mean_nearest_neighbor_distance"
                ),
                "physical_spatial_cells_delta": _delta(
                    physical, "spatial_cell_count"
                ),
                "unique_items_delta": _delta(physical, "unique_items"),
                "unique_item_orientations_delta": _delta(
                    physical, "unique_item_orientations"
                ),
                "settled_delta": _delta(physical, "settled"),
                "placed_safe_delta": _delta(physical, "placed_safe"),
                "proxy": proxy,
                "physical": physical,
            }
        )

    physical_deltas = [
        float(row["physical_nn_distance_delta"])
        for row in rows
        if row["physical_nn_distance_delta"] is not None
    ]
    guards = {
        "physical_nn_distance": all(
            (row["physical_nn_distance_delta"] or 0.0) > 0.0
            for row in rows
        ),
        "unique_items": all(
            row["unique_items_delta"] is not None
            and row["unique_items_delta"] >= 0
            for row in rows
        ),
        "unique_item_orientations": all(
            row["unique_item_orientations_delta"] is not None
            and row["unique_item_orientations_delta"] >= 0
            for row in rows
        ),
        "placed_safe": all(
            row["placed_safe_delta"] is not None
            and row["placed_safe_delta"] >= 0
            for row in rows
        ),
    }
    return {
        "dataset_id": payload.get("dataset_id"),
        "sampling_mode": payload.get("sampling_mode"),
        "status": "complete",
        "steps_measured": len(rows),
        "steps_with_proxy_gain": sum(
            (row["proxy_nn_distance_delta"] or 0.0) > 0.0 for row in rows
        ),
        "steps_with_physical_gain": sum(
            (row["physical_nn_distance_delta"] or 0.0) > 0.0
            for row in rows
        ),
        "mean_physical_nn_distance_delta": (
            sum(physical_deltas) / len(physical_deltas)
            if physical_deltas
            else None
        ),
        "acceptance": {
            "verdict": "pass" if all(guards.values()) else "fail",
            "guards": guards,
            "failed_guards": [
                name for name, passed in guards.items() if not passed
            ],
            "contract": (
                "Every measured step must improve physical NN distance and "
                "must not reduce unique items, unique item-orientations, or "
                "placed-safe replay count versus the paired random control."
            ),
        },
        "steps": rows,
        "interpretation_contract": (
            "Positive physical distance delta means the sampled observed "
            "settle afterstates are more dispersed. It is a dataset-coverage "
            "result, not evidence of a better live policy or score."
        ),
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Residual-state diversity physical pilot",
        "",
        f"- Dataset: `{summary.get('dataset_id')}`",
        f"- Sampling mode: `{summary.get('sampling_mode')}`",
        f"- Steps measured: {summary['steps_measured']}",
        (
            "- Steps with positive proxy/physical NN-distance delta: "
            f"{summary['steps_with_proxy_gain']}/"
            f"{summary['steps_with_physical_gain']}"
        ),
        (
            "- Mean physical NN-distance delta: "
            f"{summary['mean_physical_nn_distance_delta']}"
        ),
        f"- Acceptance verdict: **{summary['acceptance']['verdict']}**",
        f"- Failed guards: {summary['acceptance']['failed_guards']}",
        "",
        "| step | population | replayed | proxy ΔNN | physical ΔNN | "
        "physical Δcells | Δitems | Δitem-pose | safe pool | positive | "
        "negative | Δsettled | Δsafe |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary["steps"]:
        lines.append(
            "| {step} | {population} | {unique_replayed} | "
            "{proxy_nn_distance_delta} | {physical_nn_distance_delta} | "
            "{physical_spatial_cells_delta} | {unique_items_delta} | "
            "{unique_item_orientations_delta} | {primary_safe_pool} | "
            "{positive_transition} | {negative_physical_risk} | "
            "{settled_delta} | "
            "{placed_safe_delta} |".format(**row)
        )
    lines.extend(["", summary["interpretation_contract"], ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    summary = summarize_manifest(payload)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(summary), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
