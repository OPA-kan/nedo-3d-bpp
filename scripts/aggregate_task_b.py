from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
from typing import Any


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
        )
        groups[key].append(row)

    aggregates = []
    for key in sorted(groups, key=lambda value: (value[0], value[1], value[2])):
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

        aggregates.append(
            {
                "look_ahead": key[0],
                "selection_mode": key[1],
                "coverage_mode": key[2],
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
        "| Pool | Selection | Coverage | Runs | Placed mean/median/std "
        "| Placed min-max | Fill mean/median/std | C1/C2/C3 mean "
        "| Failure modes | Starvation signals |",
        "| ---: | --- | --- | ---: | --- | --- | --- | --- | --- | ---: |",
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
            f"{result['coverage_mode']} | {result['runs']} | "
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
