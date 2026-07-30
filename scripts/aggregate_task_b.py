from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts.summarize_task_b import (  # noqa: E402
    SELECTED_CONFUSION_SCOPE,
)


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "count": 0,
            "mean": 0.0,
            "median": 0.0,
            "stddev": 0.0,
            "min": 0.0,
            "max": 0.0,
        }
    return {
        "count": len(values),
        "mean": float(statistics.mean(values)),
        "median": float(statistics.median(values)),
        "stddev": (
            float(statistics.stdev(values)) if len(values) > 1 else 0.0
        ),
        "min": min(values),
        "max": max(values),
    }


def aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = collections.defaultdict(
        list
    )
    for row in rows:
        key = (
            row.get("look_ahead"),
            row.get("selection_mode"),
            row.get("coverage_mode"),
            row.get("risk_gate_mode") or "unspecified",
        )
        groups[key].append(row)

    aggregates = []
    for key in sorted(
        groups,
        key=lambda value: (
            value[0],
            str(value[1]),
            str(value[2]),
            str(value[3]),
        ),
    ):
        group = groups[key]
        failures = collections.Counter(
            str(row.get("failure_mode", "unknown")) for row in group
        )

        def coverage_stats(scope: str, class_name: str | None = None):
            result = {}
            for metric in ("c1", "c2", "c3"):
                values = []
                for row in group:
                    coverage = row.get("coverage")
                    if not isinstance(coverage, dict):
                        continue
                    metrics = coverage.get(scope)
                    if scope == "by_class" and isinstance(metrics, dict):
                        metrics = metrics.get(class_name)
                    if not isinstance(metrics, dict):
                        continue
                    value = metrics.get(metric)
                    if isinstance(value, (int, float)):
                        values.append(float(value))
                result[metric] = _stats(values)
            return result

        def release_stats(metric: str):
            values = []
            for row in group:
                release = row.get("release")
                if not isinstance(release, dict):
                    continue
                value = release.get(metric)
                if isinstance(value, (int, float)):
                    values.append(float(value))
            return _stats(values)

        aggregates.append(
            {
                "look_ahead": key[0],
                "selection_mode": key[1],
                "coverage_mode": key[2],
                "risk_gate_mode": key[3],
                "runs": len(group),
                "placed": _stats(
                    [float(row.get("placed_count", 0)) for row in group]
                ),
                "fill": _stats(
                    [float(row.get("fill_score", 0.0)) for row in group]
                ),
                "coverage": {
                    "overall": coverage_stats("overall"),
                    "by_class": {
                        class_name: coverage_stats(
                            "by_class", class_name
                        )
                        for class_name in (
                            "normal",
                            "soft",
                            "priority",
                        )
                    },
                },
                "starvation_signal_count": sum(
                    bool(row.get("starvation_signal"))
                    for row in group
                ),
                "action_sequences_by_replicate": {
                    f"{row.get('replicate')}:{row.get('case')}": row["release"][
                        "action_sequence_sha256"
                    ]
                    for row in group
                    if isinstance(row.get("release"), dict)
                    and row["release"].get("action_sequence_sha256")
                },
                # The Markdown carries this warning, but analysis code that
                # reads only the JSON would otherwise see four bare cells.
                "selected_confusion_scope": SELECTED_CONFUSION_SCOPE,
                "release": {
                    metric: release_stats(metric)
                    for metric in (
                        "gate_evaluated",
                        "gate_would_reject",
                        "gate_enforced_rejections",
                        "release_static_count",
                        "release_gate_pass_count",
                        "release_gate_reject_count",
                        "release_all_rejected_count",
                        "release_static_step_count",
                        "protocol_fallback_count",
                        "gate_pass_ratio",
                        "release_all_rejected_ratio",
                        "protocol_fallback_ratio",
                        "selected_release_count",
                        "rotation_over_30_count",
                        "large_displacement_count",
                        "physical_failure_count",
                        "selected_gate_pass_count",
                        "selected_gate_pass_physical_failure_count",
                        "shadow_rejected_but_safe_count",
                        # 2x2 over selected release candidates only.
                        "selected_gate_reject_count",
                        "selected_gate_scored_count",
                        "selected_gate_pass_physical_safe_count",
                        "selected_gate_reject_physical_safe_count",
                        "selected_gate_reject_physical_failure_count",
                        "selected_gate_reject_physical_failure_rate",
                        # Separated physical labels.
                        "selected_labelled_count",
                        "selected_rotated_over_30_count",
                        "selected_displaced_over_half_footprint_count",
                        (
                            "selected_horizontal_displaced"
                            "_over_half_footprint_count"
                        ),
                        "selected_not_placed_safe_count",
                        "selected_not_valid_count",
                        "selected_not_included_count",
                        "selected_physically_dangerous_count",
                    )
                },
                "failure_modes": dict(sorted(failures.items())),
            }
        )
    return aggregates


def build_aggregate_markdown(aggregates: list[dict[str, Any]]) -> str:
    def percent_mean(stats: dict[str, Any]) -> str:
        if stats.get("count", 0) == 0:
            return "-"
        return f"{stats['mean']:.1%}"

    lines = [
        "## Task B screening aggregate",
        "",
        "| Pool | Selection | Coverage | Risk gate | Runs | Placed mean/median/std "
        "| Placed min-max | Fill mean/median/std | C1/C2/C3 mean "
        "| Failure modes | Starvation signals |",
        "| ---: | --- | --- | --- | ---: | --- | --- | --- | --- | --- | ---: |",
    ]
    for result in aggregates:
        placed = result["placed"]
        fill = result["fill"]
        failures = ", ".join(
            f"{name}={count}"
            for name, count in result["failure_modes"].items()
        )
        coverage = result["coverage"]["overall"]
        lines.append(
            f"| {result['look_ahead']} | {result['selection_mode']} | "
            f"{result['coverage_mode']} | {result['risk_gate_mode']} | "
            f"{result['runs']} | "
            f"{placed['mean']:.2f}/{placed['median']:.2f}/"
            f"{placed['stddev']:.2f} | "
            f"{placed['min']:.0f}-{placed['max']:.0f} | "
            f"{fill['mean']:.3f}/{fill['median']:.3f}/"
            f"{fill['stddev']:.3f} | "
            f"{percent_mean(coverage['c1'])}/"
            f"{percent_mean(coverage['c2'])}/"
            f"{percent_mean(coverage['c3'])} | {failures} | "
            f"{result['starvation_signal_count']} |"
        )
    lines.extend(
        [
            "",
            "### Class coverage means",
            "",
            "| Pool | Class | C1 | C2 | C3 |",
            "| ---: | --- | ---: | ---: | ---: |",
        ]
    )
    for result in aggregates:
        for class_name in ("normal", "soft", "priority"):
            coverage = result["coverage"]["by_class"][class_name]
            lines.append(
                f"| {result['look_ahead']} | {class_name} | "
                f"{percent_mean(coverage['c1'])} | "
                f"{percent_mean(coverage['c2'])} | "
                f"{percent_mean(coverage['c3'])} |"
            )
    lines.extend(
        [
            "",
            "### Release risk means",
            "",
            "| Pool | Risk gate | Static | Gate pass | Pass rate | "
            "Gate reject | All rejected | All-reject rate | "
            "Protocol fallback | Evaluated | Enforced | "
            "Selected | >30° | Large displacement | Physical failure | "
            "Gate-pass failures | Shadow reject but safe |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
            "---: |",
        ]
    )
    for result in aggregates:
        release = result["release"]
        lines.append(
            f"| {result['look_ahead']} | {result['risk_gate_mode']} | "
            f"{release['release_static_count']['mean']:.1f} | "
            f"{release['release_gate_pass_count']['mean']:.1f} | "
            f"{percent_mean(release['gate_pass_ratio'])} | "
            f"{release['release_gate_reject_count']['mean']:.1f} | "
            f"{release['release_all_rejected_count']['mean']:.1f} | "
            f"{percent_mean(release['release_all_rejected_ratio'])} | "
            f"{release['protocol_fallback_count']['mean']:.1f} | "
            f"{release['gate_evaluated']['mean']:.1f} | "
            f"{release['gate_enforced_rejections']['mean']:.1f} | "
            f"{release['selected_release_count']['mean']:.1f} | "
            f"{release['rotation_over_30_count']['mean']:.1f} | "
            f"{release['large_displacement_count']['mean']:.1f} | "
            f"{release['physical_failure_count']['mean']:.1f} | "
            f"{release['selected_gate_pass_physical_failure_count']['mean']:.1f} | "
            f"{release['shadow_rejected_but_safe_count']['mean']:.1f} |"
        )
    lines.extend(
        [
            "",
            "### Selected-release confusion matrix means",
            "",
            "Means over release candidates the ranking actually selected. "
            "They are conditioned on that selection and are **not** the "
            "gate's overall precision/recall: the selected set is the top of "
            "the ranking, not a sample of all candidates. In `enforce` the "
            "reject cells are empty by construction. Estimating gate-wide "
            "behaviour needs the stratified counterfactual replay dataset, "
            "not more runs of this benchmark.",
            "",
            "| Pool | Risk gate | Scored | TN pass/safe | FN pass/failed | "
            "FP reject/safe | TP reject/failed | Reject failure rate |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in aggregates:
        release = result["release"]
        lines.append(
            f"| {result['look_ahead']} | {result['risk_gate_mode']} | "
            f"{release['selected_gate_scored_count']['mean']:.1f} | "
            f"{release['selected_gate_pass_physical_safe_count']['mean']:.1f} | "
            f"{release['selected_gate_pass_physical_failure_count']['mean']:.1f} | "
            f"{release['selected_gate_reject_physical_safe_count']['mean']:.1f} | "
            f"{release['selected_gate_reject_physical_failure_count']['mean']:.1f} | "
            f"{percent_mean(release['selected_gate_reject_physical_failure_rate'])} |"
        )
    lines.extend(
        [
            "",
            "### Selected-release physical label means",
            "",
            "Independent outcomes. `Dangerous` is the historical OR of "
            "rotation, 3D displacement and not-placed-safe, kept only for "
            "continuity with earlier runs.",
            "",
            "| Pool | Risk gate | Labelled | Rotated >30° | Displaced 3D | "
            "Displaced XY | Not placed safe | Not valid | Not included | "
            "Dangerous |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: "
            "| ---: |",
        ]
    )
    for result in aggregates:
        release = result["release"]
        horizontal = release[
            "selected_horizontal_displaced_over_half_footprint_count"
        ]
        lines.append(
            f"| {result['look_ahead']} | {result['risk_gate_mode']} | "
            f"{release['selected_labelled_count']['mean']:.1f} | "
            f"{release['selected_rotated_over_30_count']['mean']:.1f} | "
            f"{release['selected_displaced_over_half_footprint_count']['mean']:.1f} | "
            f"{horizontal['mean']:.1f} | "
            f"{release['selected_not_placed_safe_count']['mean']:.1f} | "
            f"{release['selected_not_valid_count']['mean']:.1f} | "
            f"{release['selected_not_included_count']['mean']:.1f} | "
            f"{release['selected_physically_dangerous_count']['mean']:.1f} |"
        )
    lines.extend(
        [
            "",
            "### Off/shadow action-sequence invariant",
            "",
            "| Pool | Comparable replicates | Exact matches | Blocker |",
            "| ---: | ---: | ---: | --- |",
        ]
    )
    indexed = {
        (
            result["look_ahead"],
            result["selection_mode"],
            result["coverage_mode"],
            result["risk_gate_mode"],
        ): result
        for result in aggregates
    }
    base_keys = sorted(
        {
            (
                result["look_ahead"],
                result["selection_mode"],
                result["coverage_mode"],
            )
            for result in aggregates
        },
        key=lambda value: (value[0], str(value[1]), str(value[2])),
    )
    for look_ahead, selection_mode, coverage_mode in base_keys:
        off = indexed.get(
            (look_ahead, selection_mode, coverage_mode, "off")
        )
        shadow = indexed.get(
            (look_ahead, selection_mode, coverage_mode, "shadow")
        )
        if off is None or shadow is None:
            continue
        off_hashes = off["action_sequences_by_replicate"]
        shadow_hashes = shadow["action_sequences_by_replicate"]
        replicates = sorted(set(off_hashes) & set(shadow_hashes))
        matches = sum(
            off_hashes[replicate] == shadow_hashes[replicate]
            for replicate in replicates
        )
        lines.append(
            f"| {look_ahead} | {len(replicates)} | {matches} | "
            f"{'yes' if matches != len(replicates) else 'no'} |"
        )
    return "\n".join(lines) + "\n"


def load_result_rows(root: pathlib.Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("summary-*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows.extend(row for row in payload if isinstance(row, dict))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    aggregates = aggregate_rows(load_result_rows(args.root))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        build_aggregate_markdown(aggregates),
        encoding="utf-8",
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(aggregates, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    print(args.json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
