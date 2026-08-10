"""
What labelled rows the repository actually holds, and under which arm.

The condition matrix used to commit only its verdict. The rows themselves
lived in Actions artifacts, which expire 90 days after the run, so a corpus
could never accumulate: by the time anyone wanted to train on a run it was
gone, and the trajectory is wall-clock dependent, so the same states could not
be regenerated either. The rows are now retained in git and this index is what
makes them findable.

The index is DERIVED. Re-run it after any run lands:

    python scripts/index_replay_corpus.py \
      --root reports/residual-diversity-scale/history \
      --json-output reports/residual-diversity-scale/corpus.json \
      --markdown-output reports/residual-diversity-scale/corpus.md

Two things it deliberately does NOT do. It does not pool rows across runs into
a single count and call that the corpus size: the matrix re-measures the same
(case, step) pairs every run, so rows add up while distinct states do not, and
reporting only the row total would overstate what a learner has by more than
an order of magnitude. And it does not merge arms: a seeded run and its
`--observed-swap-rounds 0` ablation are different constructions of the
positive portfolio, so they are counted separately and labelled.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
from typing import Any


ROW_KINDS = {
    "candidates": "positive_transition",
    "negative-risk": "negative_physical_risk",
    "random-control": "paired_random_control",
}


def count_lines(path: pathlib.Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def read_manifest(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def scan_dataset(directory: pathlib.Path) -> dict[str, Any] | None:
    """One scenario's dataset directory: its arm, its states and its rows."""
    manifest = read_manifest(directory / "manifest.json")
    if manifest is None:
        return None
    case = manifest.get("case") or {}
    steps = [
        int(step["step"])
        for step in (case.get("steps") or [])
        if step.get("step") is not None
    ]
    rows: dict[str, int] = collections.Counter()
    for suffix, name in ROW_KINDS.items():
        for path in sorted(directory.glob(f"step-*-{suffix}.jsonl")):
            rows[name] += count_lines(path)
    return {
        "case_id": str(case.get("case_id") or manifest.get("case_id") or ""),
        "dataset_id": manifest.get("dataset_id"),
        "status": manifest.get("status"),
        "schema_version": manifest.get("schema_version"),
        "sampling_mode": manifest.get("sampling_mode"),
        "overdraw_factor": manifest.get("overdraw_factor"),
        "observed_swap_rounds": manifest.get("observed_swap_rounds"),
        "split": manifest.get("split"),
        "steps": sorted(steps),
        "snapshots": len(sorted(directory.glob("step-*-state.json"))),
        "rows": dict(rows),
        "path": directory.as_posix(),
    }


def scan_runs(root: pathlib.Path) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for run_dir in sorted(root.glob("*")):
        dataset_root = run_dir / "dataset"
        if not dataset_root.is_dir():
            continue
        datasets = [
            scanned
            for scenario in sorted(dataset_root.glob("*"))
            if scenario.is_dir()
            and (scanned := scan_dataset(scenario)) is not None
        ]
        if not datasets:
            continue
        summary = read_manifest(run_dir / "summary.json") or {}
        arms = {row["observed_swap_rounds"] for row in datasets}
        rows: dict[str, int] = collections.Counter()
        for dataset in datasets:
            rows.update(dataset["rows"])
        runs.append(
            {
                "run_id": run_dir.name,
                "verdict": (summary.get("acceptance") or {}).get("verdict"),
                "observed_swap_rounds": (
                    next(iter(arms)) if len(arms) == 1 else None
                ),
                "uniform_arm": len(arms) == 1,
                "scenarios": len(datasets),
                "states": sum(len(row["steps"]) for row in datasets),
                "rows": dict(rows),
                "datasets": datasets,
            }
        )
    return runs


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    # Distinct states, not rows, is the number that bounds a learner. The
    # matrix re-measures the same (case, step) pairs on every run.
    distinct: set[tuple[str, int]] = set()
    per_arm: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    arm_states: dict[str, set[tuple[str, int]]] = collections.defaultdict(set)
    totals: collections.Counter = collections.Counter()
    for run in runs:
        arm = str(run["observed_swap_rounds"])
        for dataset in run["datasets"]:
            for step in dataset["steps"]:
                distinct.add((dataset["case_id"], step))
                arm_states[arm].add((dataset["case_id"], step))
        per_arm[arm].update(run["rows"])
        totals.update(run["rows"])
    return {
        "schema_version": 1,
        "runs": len(runs),
        "distinct_states": len(distinct),
        "distinct_cases": len({case for case, _step in distinct}),
        "rows_all_runs": dict(totals),
        "by_arm": {
            arm: {
                "rows": dict(counts),
                "distinct_states": len(arm_states[arm]),
            }
            for arm, counts in sorted(per_arm.items())
        },
        "states": sorted(f"{case}:{step:03d}" for case, step in distinct),
        "run_index": runs,
        "contract": (
            "Rows accumulate across runs but distinct states do not: the "
            "matrix re-measures the same (case, step) pairs. Rows inside one "
            "state share a parent state and are not independent examples. "
            "Arms are not merged."
        ),
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Retained replay corpus",
        "",
        "**This file is generated.** Rebuild it with "
        "`python scripts/index_replay_corpus.py`.",
        "",
        f"- Runs retained: {summary['runs']}",
        (
            "- Distinct states: "
            f"**{summary['distinct_states']}** across "
            f"{summary['distinct_cases']} cases"
        ),
        (
            "- Rows across all runs: "
            + ", ".join(
                f"{name} {count}"
                for name, count in sorted(summary["rows_all_runs"].items())
            )
        ),
        "",
        "| run | arm (swap rounds) | verdict | scenarios | states | "
        "positive | negative | control |",
        "|---|---:|---|---:|---:|---:|---:|---:|",
    ]
    for run in summary["run_index"]:
        rows = run["rows"]
        lines.append(
            "| `{run}` | {arm} | {verdict} | {scenarios} | {states} | "
            "{positive} | {negative} | {control} |".format(
                run=run["run_id"],
                arm=(
                    run["observed_swap_rounds"]
                    if run["uniform_arm"]
                    else "**mixed**"
                ),
                verdict=run["verdict"],
                scenarios=run["scenarios"],
                states=run["states"],
                positive=rows.get("positive_transition", 0),
                negative=rows.get("negative_physical_risk", 0),
                control=rows.get("paired_random_control", 0),
            )
        )
    lines.extend(["", summary["contract"], ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    summary = summarize(scan_runs(args.root))
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
