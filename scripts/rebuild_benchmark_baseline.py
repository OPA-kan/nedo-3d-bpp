#!/usr/bin/env python3
"""Rebuild the Task B regression baseline from across-runner repeats.

The 2026-08-01 baseline was a single episode per config from a foreign
machine, which cannot support its own contract ("reject unexplained
drops"): an identical binary on one box returned 13/17/18 placed on
b000-k40. This builder harvests every same-protocol base episode from the
named collection runs — branch-label capture-free references and paired
ablation base arms, all on standard GitHub ubuntu-24.04 runners with the
shipped agent defaults — and replaces the point estimates with per-config
mean, spread and an explicit minimum resolvable effect.

Two resolvable-effect statements are recorded per config:

- versus a stored constant (one fresh episode against this file):
  a drop is attributable only beyond ~2 standard deviations;
- paired same-run A/B with three replicates per arm: the detectable mean
  difference at alpha=0.05 is roughly t(4) * sd * sqrt(2/3).

The A/B form is the procedure; the stored constants exist only for coarse
sanity, never for adjudication.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
from typing import Any

STREAM_TOTALS = {"000": 41, "001": 42}
T_975_DF4 = 2.776


def _case_total(case_id: str) -> int:
    for source, total in STREAM_TOTALS.items():
        if case_id.startswith(f"b{source}") or case_id.startswith(f"c{source}"):
            return total
    raise ValueError(f"unknown source for case {case_id}")


def harvest_reference(path: pathlib.Path, run_id: str) -> dict[str, Any] | None:
    data = json.loads((path / "branch-labels.json").read_text(encoding="utf-8"))
    reference = (
        (data.get("instrument_validity") or {}).get("capture_free_reference")
    )
    if not reference:
        return None
    case = data["task_id"]
    fraction = float(reference["num_placed_items"])
    return {
        "case": case,
        "source": f"{run_id}:capture_free_reference",
        "placed_count": round(fraction * _case_total(case)),
        "fill_score": float(reference["fill_score"]),
    }


def harvest_ablation_rows(path: pathlib.Path, run_id: str) -> list[dict[str, Any]]:
    samples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("arm") != "base":
            continue
        for case, case_data in row["cases"].items():
            if case_data.get("placed_count") is None:
                continue
            samples.append({
                "case": case,
                "source": f"{run_id}:base-r{row['repeat']}",
                "placed_count": int(case_data["placed_count"]),
                "fill_score": float(case_data["fill_score"]),
            })
    return samples


def build(samples: list[dict[str, Any]]) -> dict[str, Any]:
    cases: dict[str, Any] = {}
    for case in sorted({sample["case"] for sample in samples}):
        rows = [sample for sample in samples if sample["case"] == case]
        placed = [row["placed_count"] for row in rows]
        fills = [row["fill_score"] for row in rows]
        placed_sd = statistics.stdev(placed) if len(placed) > 1 else None
        fill_sd = statistics.stdev(fills) if len(fills) > 1 else None
        cases[case] = {
            "episodes": len(rows),
            "placed_mean": round(statistics.fmean(placed), 3),
            "placed_sd": round(placed_sd, 3) if placed_sd is not None else None,
            "placed_range": [min(placed), max(placed)],
            "fill_mean": round(statistics.fmean(fills), 3),
            "fill_sd": round(fill_sd, 3) if fill_sd is not None else None,
            "minimum_resolvable_placed": {
                "single_episode_vs_stored": (
                    round(2.0 * placed_sd, 2) if placed_sd else None
                ),
                "paired_3v3_same_run": (
                    round(T_975_DF4 * placed_sd * (2.0 / 3.0) ** 0.5, 2)
                    if placed_sd else None
                ),
            },
            "samples": rows,
        }
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reference-dir", action="append", nargs=2,
        metavar=("RUN_ID", "DIR"), default=[],
    )
    parser.add_argument(
        "--ablation-rows", action="append", nargs=2,
        metavar=("RUN_ID", "ROWS_JSONL"), default=[],
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    samples: list[dict[str, Any]] = []
    for run_id, directory in args.reference_dir:
        harvested = harvest_reference(pathlib.Path(directory), run_id)
        if harvested:
            samples.append(harvested)
    for run_id, rows_path in args.ablation_rows:
        samples.extend(harvest_ablation_rows(pathlib.Path(rows_path), run_id))
    baseline = {
        "schema_version": 2,
        "policy": "shipped defaults (risk-on rot lambda=1, slide lambda=0.5)",
        "environment": {
            "runner": "GitHub-hosted ubuntu-24.04, python 3.12",
            "protocol": "run_risk_ablation base arm / branch-label "
                        "capture-free reference, policy_timeout 8",
        },
        "contract": (
            "Adjudicate changes with a paired same-run A/B (both arms in one "
            "workflow, >=3 replicates per arm); the per-config "
            "minimum_resolvable_placed.paired_3v3_same_run is the smallest "
            "mean difference that test can attribute. The stored means are "
            "coarse sanity only: a single fresh episode is unremarkable "
            "anywhere inside ~2 sd. Never compare a local run on other "
            "hardware against these numbers."
        ),
        "cases": build(samples),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(baseline, indent=2) + "\n", encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
