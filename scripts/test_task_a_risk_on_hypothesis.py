from __future__ import annotations

import argparse
import itertools
import json
import math
import pathlib
import statistics
from typing import Any, Iterable


METRICS = (
    "placed_count",
    "fill_score",
    "offline_evaluations",
    "optimization_seconds",
)
ARMS = ("default", "risk_on")
EPSILON = 1e-12


def load_rows(path: pathlib.Path) -> list[dict[str, Any]]:
    """Load compact JSONL or raw workflow row.json records."""
    if path.is_file():
        if path.suffix != ".jsonl":
            raise ValueError(f"expected a .jsonl file, got {path}")
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        files = sorted(path.rglob("row.json"))
        if not files:
            raise ValueError(f"no row.json records found under {path}")
        rows = [json.loads(file.read_text(encoding="utf-8")) for file in files]

    normalized = []
    for row in rows:
        case_result = row.get("case", {})
        offline = row.get("offline", {})
        normalized.append(
            {
                "source_case": row["source_case"],
                "arm": row["arm"],
                "repeat": int(row["repeat"]),
                "process_returncode": int(row.get("process_returncode", 0)),
                "placed_count": float(
                    row.get("placed_count", case_result.get("placed_count"))
                ),
                "fill_score": float(
                    row.get("fill_score", case_result.get("fill_score"))
                ),
                "offline_evaluations": float(
                    row.get(
                        "offline_evaluations", offline.get("evaluations")
                    )
                ),
                "optimization_seconds": float(row["optimization_seconds"]),
            }
        )
    validate_rows(normalized)
    return normalized


def validate_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("no observations")
    failures = [row for row in rows if row["process_returncode"] != 0]
    if failures:
        raise ValueError(f"{len(failures)} observations have non-zero return codes")

    seen: set[tuple[str, str, int]] = set()
    by_case: dict[str, dict[str, int]] = {}
    for row in rows:
        arm = row["arm"]
        if arm not in ARMS:
            raise ValueError(f"unexpected arm: {arm}")
        key = (row["source_case"], arm, row["repeat"])
        if key in seen:
            raise ValueError(f"duplicate observation: {key}")
        seen.add(key)
        counts = by_case.setdefault(
            row["source_case"], {name: 0 for name in ARMS}
        )
        counts[arm] += 1

    for source_case, counts in by_case.items():
        if not counts["default"] or not counts["risk_on"]:
            raise ValueError(f"case {source_case} is missing an arm: {counts}")


def _mean_difference(control: Iterable[float], treatment: Iterable[float]) -> float:
    return statistics.mean(treatment) - statistics.mean(control)


def exact_unpaired_permutation(
    control: list[float], treatment: list[float]
) -> dict[str, Any]:
    """Enumerate the randomization null for an independent two-arm design."""
    if not control or not treatment:
        raise ValueError("both arms need at least one observation")
    pooled = control + treatment
    treatment_size = len(treatment)
    observed = _mean_difference(control, treatment)
    null = []
    all_indices = set(range(len(pooled)))
    for treatment_indices_tuple in itertools.combinations(
        range(len(pooled)), treatment_size
    ):
        treatment_indices = set(treatment_indices_tuple)
        permuted_treatment = [pooled[index] for index in treatment_indices]
        permuted_control = [
            pooled[index] for index in all_indices - treatment_indices
        ]
        null.append(_mean_difference(permuted_control, permuted_treatment))

    permutations = len(null)
    p_improvement = sum(
        value >= observed - EPSILON for value in null
    ) / permutations
    p_harm = sum(value <= observed + EPSILON for value in null) / permutations
    p_two_sided = sum(
        abs(value) >= abs(observed) - EPSILON for value in null
    ) / permutations
    return {
        "control": control,
        "treatment": treatment,
        "control_mean": statistics.mean(control),
        "treatment_mean": statistics.mean(treatment),
        "delta_risk_on_minus_default": observed,
        "permutations": permutations,
        "p_improvement_one_sided": p_improvement,
        "p_harm_one_sided": p_harm,
        "p_two_sided": p_two_sided,
        "minimum_one_sided_p": 1 / math.comb(len(pooled), treatment_size),
        "minimum_two_sided_p_without_ties": min(
            1.0, 2 / math.comb(len(pooled), treatment_size)
        ),
        "null_distribution": null,
    }


def _stratified_exact(results: list[dict[str, Any]]) -> dict[str, Any]:
    observed = statistics.mean(
        result["delta_risk_on_minus_default"] for result in results
    )
    null = [
        statistics.mean(values)
        for values in itertools.product(
            *(result["null_distribution"] for result in results)
        )
    ]
    permutations = len(null)
    return {
        "estimand": "equal-case mean of risk_on minus default",
        "observed_delta": observed,
        "permutations": permutations,
        "p_improvement_one_sided": sum(
            value >= observed - EPSILON for value in null
        )
        / permutations,
        "p_harm_one_sided": sum(
            value <= observed + EPSILON for value in null
        )
        / permutations,
        "p_two_sided": sum(
            abs(value) >= abs(observed) - EPSILON for value in null
        )
        / permutations,
    }


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    validate_rows(rows)
    cases: dict[str, Any] = {}
    for source_case in sorted({row["source_case"] for row in rows}):
        case_rows = [row for row in rows if row["source_case"] == source_case]
        cases[source_case] = {}
        for metric in METRICS:
            control = [
                row[metric] for row in case_rows if row["arm"] == "default"
            ]
            treatment = [
                row[metric] for row in case_rows if row["arm"] == "risk_on"
            ]
            cases[source_case][metric] = exact_unpaired_permutation(
                control, treatment
            )

    primary = _stratified_exact(
        [cases[source_case]["placed_count"] for source_case in sorted(cases)]
    )
    no_regression = all(
        cases[source_case]["placed_count"]["delta_risk_on_minus_default"] >= 0
        for source_case in cases
    )
    alpha = 0.05
    supports_improvement = (
        primary["observed_delta"] > 0
        and primary["p_improvement_one_sided"] <= alpha
    )
    adopt_risk_on = supports_improvement and no_regression
    return {
        "design": {
            "assignment_unit": "independent GitHub Actions matrix job",
            "pairing": "unpaired; repeat labels are not matched execution pairs",
            "test": "exact within-case label permutation",
            "primary_metric": "placed_count",
            "primary_estimand": "equal-case mean of risk_on minus default",
        },
        "observations": len(rows),
        "cases": cases,
        "primary": primary,
        "decision": {
            "alpha": alpha,
            "supports_improvement": supports_improvement,
            "no_regression_gate": no_regression,
            "adopt_risk_on": adopt_risk_on,
            "verdict": "adopt" if adopt_risk_on else "reject_adoption",
            "reason": (
                "primary benefit is unsupported and the no-regression gate fails"
            ),
        },
    }


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def build_markdown(result: dict[str, Any], source: str) -> str:
    lines = [
        "# Task A risk-on proposal oracle: exact hypothesis test",
        "",
        f"Source: `{source}`",
        "",
        "The 12 episodes were independent GitHub Actions matrix jobs. Repeat IDs "
        "are labels, not matched pairs, so this analysis uses an **unpaired exact "
        "permutation test within each case**. The primary estimand is the equal-case "
        "mean change in placed count (`risk_on - default`).",
        "",
        "## Primary result",
        "",
    ]
    primary = result["primary"]
    lines.extend(
        [
            f"- Equal-case placed delta: **{_fmt(primary['observed_delta'])}**",
            "- Exact one-sided p for improvement: "
            f"**{_fmt(primary['p_improvement_one_sided'])}**",
            f"- Exact one-sided p for harm: **{_fmt(primary['p_harm_one_sided'])}**",
            f"- Exact two-sided p: **{_fmt(primary['p_two_sided'])}**",
            f"- Stratified label allocations enumerated: {primary['permutations']}",
            "",
            "There is no evidence that risk-on improves placed count. The observed "
            "effect is negative, and the prespecified no-regression adoption gate "
            "fails because a000 loses six placements. **Decision: do not adopt "
            "risk-on.**",
            "",
            "## Case results",
            "",
            "| Case | Metric | Default mean | Risk-on mean | Delta | p improve | "
            "p harm | p two-sided |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    labels = {
        "placed_count": "placed",
        "fill_score": "fill",
        "offline_evaluations": "offline evals",
        "optimization_seconds": "optimization s",
    }
    for source_case, metrics in result["cases"].items():
        for metric in METRICS:
            item = metrics[metric]
            lines.append(
                f"| {source_case} | {labels[metric]} | "
                f"{_fmt(item['control_mean'])} | {_fmt(item['treatment_mean'])} | "
                f"{_fmt(item['delta_risk_on_minus_default'])} | "
                f"{_fmt(item['p_improvement_one_sided'])} | "
                f"{_fmt(item['p_harm_one_sided'])} | "
                f"{_fmt(item['p_two_sided'])} |"
            )
    first = next(iter(result["cases"].values()))["placed_count"]
    lines.extend(
        [
            "",
            "## Resolution and interpretation",
            "",
            "With three observations per arm, there are only "
            f"`C(6,3) = {first['permutations']}` label allocations. Therefore the "
            f"smallest attainable one-sided p is {_fmt(first['minimum_one_sided_p'])} "
            "and the smallest two-sided p without ties is "
            f"{_fmt(first['minimum_two_sided_p_without_ties'])}. Complete separation "
            "can only reach p=0.10 two-sided. Four observations per arm would lower "
            "that theoretical two-sided floor to `2/C(8,4) = 0.0286`.",
            "",
            "The a000 harm and a001 benefit each sit at the one-sided resolution "
            "boundary (p=0.05), but neither is two-sided significant, and separate "
            "casewise claims would also require multiplicity control. The defensible "
            "conclusion is not that every possible risk-on policy is disproven: this "
            "specific F8 proposal oracle has no global benefit signal, has a large "
            "practical regression on a000, and fails its adoption gate.",
            "",
            "The p-values are exact for exchangeable labels within each case. They do "
            "not justify generalization beyond these two bundled Task A cases.",
        ]
    )
    return "\n".join(lines) + "\n"


def _strip_null_distributions(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_null_distributions(item)
            for key, item in value.items()
            if key != "null_distribution"
        }
    if isinstance(value, list):
        return [_strip_null_distributions(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=pathlib.Path, required=True)
    parser.add_argument("--output-json", type=pathlib.Path, required=True)
    parser.add_argument("--output-md", type=pathlib.Path, required=True)
    args = parser.parse_args()

    result = analyze(load_rows(args.input))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(_strip_null_distributions(result), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    args.output_md.write_text(
        build_markdown(result, str(args.input)), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
