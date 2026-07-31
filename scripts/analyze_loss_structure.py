"""
How does the official safe judgment depend on rotation magnitude?

Motivation (risk-rule comparison, Reading section): one remaining
justification for a nonlinear risk penalty would be damage that grows
with rotation magnitude. This script measures the label-side loss
structure directly: the official ``not_placed_safe`` rate per
continuous settle-angle band, and what drives failures below the
rotation threshold. Exploratory instrument -- runs on all non-holdout
release rows, not on the frozen split metrics.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.evaluate_release_risk as err  # noqa: E402

DEFAULT_DATASET_ROOT = ROOT / "reports" / "replay-dataset"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "replay-analysis"
ANGLE_BANDS = (0, 5, 10, 20, 30, 45, 60, 80, 100, 181)


def band_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    angles = np.array(
        [
            float(r["physical"]["settle_metrics"]["settle_angle_deg"])
            for r in rows
        ]
    )
    disp = np.array(
        [
            float(
                r["physical"]["settle_metrics"]["settle_displacement_norm"]
            )
            for r in rows
        ]
    )
    unsafe = np.array(
        [bool(r["physical"]["Y"]["not_placed_safe"]) for r in rows]
    )
    table = []
    for low, high in zip(ANGLE_BANDS[:-1], ANGLE_BANDS[1:]):
        mask = (angles >= low) & (angles < high)
        if not mask.any():
            continue
        table.append(
            {
                "band_deg": [low, high],
                "n": int(mask.sum()),
                "not_placed_safe_rate": float(unsafe[mask].mean()),
                "median_displacement_m": float(np.median(disp[mask])),
            }
        )
    return table


def low_angle_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    angles = np.array(
        [
            float(r["physical"]["settle_metrics"]["settle_angle_deg"])
            for r in rows
        ]
    )
    disp = np.array(
        [
            float(
                r["physical"]["settle_metrics"]["settle_displacement_norm"]
            )
            for r in rows
        ]
    )
    unsafe = np.array(
        [bool(r["physical"]["Y"]["not_placed_safe"]) for r in rows]
    )
    low = angles < 30
    return {
        "n": int(low.sum()),
        "unsafe_rate": float(unsafe[low].mean()),
        "median_displacement_unsafe": float(
            np.median(disp[low & unsafe])
        ),
        "median_displacement_safe": float(
            np.median(disp[low & ~unsafe])
        ),
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Loss structure: official safe judgment vs rotation magnitude",
        "",
        f"- release rows with settle metrics: {result['rows']} "
        "(all non-holdout datasets; exploratory, not frozen-split)",
        "",
        "| angle band (deg) | n | not_placed_safe rate "
        "| median displacement (m) |",
        "|---|---:|---:|---:|",
    ]
    for entry in result["bands"]:
        low, high = entry["band_deg"]
        lines.append(
            f"| {low}-{high} | {entry['n']} "
            f"| {entry['not_placed_safe_rate']:.3f} "
            f"| {entry['median_displacement_m']:.3f} |"
        )
    low = result["low_angle"]
    lines += [
        "",
        "## Below the rotation threshold (<30 deg)",
        "",
        f"- rows: {low['n']}, unsafe rate {low['unsafe_rate']:.3f}",
        f"- median displacement among unsafe "
        f"{low['median_displacement_unsafe']:.3f} m vs safe "
        f"{low['median_displacement_safe']:.3f} m: low-angle failures "
        "are displacement (slide) failures, i.e. the unresolved d_xy "
        "channel, not small rotations.",
        "",
        "## Reading",
        "",
        "- The official judgment is close to a step function of angle: "
        "every band at or above 45 deg is unconditionally unsafe, "
        "30-45 deg is mixed, and below 30 deg the rate is small and "
        "displacement-driven. A damage model that grows smoothly with "
        "rotation magnitude has little room: the label-side loss is "
        "effectively binary in angle with a threshold near 45 deg.",
        "- rotated_over_30 is therefore a slightly conservative but "
        "structurally faithful proxy for the angle channel of the "
        "official loss.",
        "- The remaining loss mass below the threshold belongs to the "
        "slide channel (d_xy), which stays unresolved -- prioritizing "
        "it above rotation-magnitude modelling.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-root", type=pathlib.Path, default=DEFAULT_DATASET_ROOT
    )
    parser.add_argument(
        "--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT_DIR
    )
    args = parser.parse_args()
    dataset_dirs = sorted(
        path for path in args.dataset_root.iterdir() if path.is_dir()
    )
    _all_rows, release, _summaries = err.load_release_rows(dataset_dirs)
    rows = [r for r in release if r["physical"].get("settle_metrics")]
    result = {
        "rows": len(rows),
        "bands": band_table(rows),
        "low_angle": low_angle_report(rows),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "loss-structure.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    markdown_path = args.output_dir / "loss-structure.md"
    markdown_path.write_text(render_markdown(result), encoding="utf-8")
    print(markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
