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

Two things it deliberately does NOT do. It does not report the row total as
the corpus size: rows inside one snapshot share a parent state and are not
independent examples. And it does not merge arms: a seeded run and its
`--observed-swap-rounds 0` ablation are different constructions of the
positive portfolio, so they are counted separately and labelled.

States are counted by **snapshot fingerprint, not by (case, step)**. The two
disagree, and assuming otherwise gets the answer wrong in both directions.
The policy is deadline-limited, so two runs of the same scenario reach
different boards by the same step index: `m-single-empty-noshelf` step 9 was
measured three times locally and produced three different placed-item
configurations. Counting `(case, step)` slots would therefore say a re-run
adds nothing when it actually adds ~12 fresh states. It can also collide the
other way -- two runs occasionally do land on the identical board -- and those
must not be counted twice. The fingerprint covers the placed items with their
settled positions and the remaining pool, which is what makes one state a
different learning example from another.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import sys
from typing import Any


# Measured over the first two retained runs: 50.4 MB of JSON gzips to 3.4 MB.
# git stores blobs zlib-compressed, so this is the right order of magnitude
# for what the repository actually grows by.
COMPRESSION_RATIO = 14.7
ROW_KINDS = {
    "candidates": "positive_transition",
    "negative-risk": "negative_physical_risk",
    "random-control": "paired_random_control",
}


def corpus_bytes(root: pathlib.Path) -> dict[str, int]:
    """Raw bytes held, and what git will actually store.

    These rows are JSON and compress about 15x, so the number that matters
    for the repository is not the one `du` prints. Both are reported because
    a budget stated in the wrong one is a budget nobody can reason about.
    """
    raw = sum(
        path.stat().st_size for path in root.rglob("*") if path.is_file()
    )
    return {
        "raw_bytes": raw,
        "estimated_stored_bytes": int(raw / COMPRESSION_RATIO),
    }


def count_lines(path: pathlib.Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def read_manifest(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def state_fingerprint(path: pathlib.Path) -> str | None:
    """Identify the board a snapshot actually holds.

    Two runs of one scenario do not share a state at the same step index, so
    the file name cannot identify it. The placed items with their settled
    positions and the remaining pool can.
    """
    snapshot = read_manifest(path)
    if not isinstance(snapshot, dict):
        return None
    physics = snapshot.get("physics") or {}
    observation = snapshot.get("observation") or {}
    placed = sorted(
        (
            int(item.get("container_index", -1)),
            int(item.get("item_index", -1)),
            tuple(
                round(float(value), 4)
                for value in (item.get("position") or [])
            ),
        )
        for item in (physics.get("packed_items") or [])
    )
    pool = sorted(
        int(item.get("index", -1))
        for item in (observation.get("pool_list") or [])
    )
    payload = repr(
        (str(snapshot.get("case_id")), int(snapshot.get("step", -1)),
         placed, pool)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


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
    fingerprints = {
        step: fingerprint
        for step in steps
        if (
            fingerprint := state_fingerprint(
                directory / f"step-{step:03d}-state.json"
            )
        )
        is not None
    }
    return {
        "state_fingerprints": fingerprints,
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
        incomplete = sorted(
            dataset["case_id"]
            for dataset in datasets
            if dataset["status"] != "complete"
        )
        runs.append(
            {
                "run_id": run_dir.name,
                "verdict": (summary.get("acceptance") or {}).get("verdict"),
                "completeness": summary.get("completeness"),
                # A cancelled or crashed scenario job still uploads whatever
                # it had written. Those rows are validly labelled and worth
                # keeping, but a corpus that absorbs them without saying so
                # reports partial coverage as if it were a finished run.
                "incomplete_datasets": incomplete,
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


def summarize(
    runs: list[dict[str, Any]], *, size: dict[str, int] | None = None
) -> dict[str, Any]:
    # Distinct states, not rows, is the number that bounds a learner -- and a
    # state is a board, not a (case, step) label. See the module docstring.
    boards: set[str] = set()
    slots: set[tuple[str, int]] = set()
    board_runs: dict[str, set[str]] = collections.defaultdict(set)
    per_arm: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    arm_boards: dict[str, set[str]] = collections.defaultdict(set)
    totals: collections.Counter = collections.Counter()
    for run in runs:
        arm = str(run["observed_swap_rounds"])
        for dataset in run["datasets"]:
            for step in dataset["steps"]:
                slots.add((dataset["case_id"], step))
            for fingerprint in dataset["state_fingerprints"].values():
                boards.add(fingerprint)
                arm_boards[arm].add(fingerprint)
                board_runs[fingerprint].add(run["run_id"])
        per_arm[arm].update(run["rows"])
        totals.update(run["rows"])
    incomplete_runs = [
        run["run_id"] for run in runs if run["incomplete_datasets"]
    ]
    shared = sorted(
        fingerprint
        for fingerprint, seen in board_runs.items()
        if len(seen) > 1
    )
    return {
        "schema_version": 2,
        "runs": len(runs),
        "distinct_states": len(boards),
        "case_step_slots": len(slots),
        "distinct_cases": len({case for case, _step in slots}),
        "states_shared_by_more_than_one_run": len(shared),
        "runs_with_incomplete_datasets": incomplete_runs,
        "size": size or {},
        "rows_all_runs": dict(totals),
        "by_arm": {
            arm: {
                "rows": dict(counts),
                "distinct_states": len(arm_boards[arm]),
            }
            for arm, counts in sorted(per_arm.items())
        },
        "slots": sorted(f"{case}:{step:03d}" for case, step in slots),
        "run_index": runs,
        "contract": (
            "A state is a board fingerprint, not a (case, step) label: the "
            "policy is deadline-limited, so two runs of one scenario reach "
            "different boards at the same step index. Re-running the matrix "
            "therefore adds states. Rows inside one state share a parent and "
            "are not independent examples. Arms are not merged."
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
            "- Size: "
            f"{summary['size'].get('raw_bytes', 0) / 1048576:.0f} MB raw, "
            "about "
            f"{summary['size'].get('estimated_stored_bytes', 0) / 1048576:.0f}"
            " MB stored"
            if summary.get("size")
            else "- Size: not measured"
        ),
        (
            "- Distinct states (board fingerprints): "
            f"**{summary['distinct_states']}** across "
            f"{summary['distinct_cases']} cases and "
            f"{summary['case_step_slots']} (case, step) slots"
        ),
        (
            "- States reached by more than one run: "
            f"{summary['states_shared_by_more_than_one_run']}"
        ),
        (
            "- **Runs holding an unfinished dataset: "
            f"{summary['runs_with_incomplete_datasets']}** — those rows are "
            "labelled correctly but their scenario did not run to the end."
            if summary["runs_with_incomplete_datasets"]
            else "- Runs holding an unfinished dataset: none"
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
                run=(
                    run["run_id"] + " (partial)"
                    if run["incomplete_datasets"]
                    else run["run_id"]
                ),
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
    parser.add_argument(
        "--budget-bytes",
        type=int,
        default=0,
        help=(
            "Raw-byte ceiling for the retained corpus. Over it, this exits "
            "non-zero so the caller can stop retaining rows loudly instead "
            "of growing the repository until someone notices. 0 disables."
        ),
    )
    args = parser.parse_args()

    size = corpus_bytes(args.root)
    summary = summarize(scan_runs(args.root), size=size)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(summary), encoding="utf-8")
    print(args.markdown_output)
    if args.budget_bytes and size["raw_bytes"] > args.budget_bytes:
        print(
            f"corpus is {size['raw_bytes'] / 1048576:.0f} MB raw "
            f"(about {size['estimated_stored_bytes'] / 1048576:.0f} MB "
            f"stored), over the {args.budget_bytes / 1048576:.0f} MB budget",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
