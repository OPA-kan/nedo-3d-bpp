#!/usr/bin/env python3
"""Is "deviate here" predictable from decision-time state features?

The fatal-case branch labels showed large single-deviation gains exist
(a different placement of the same item at c000-k1 step 8 was worth six
placements) but that harvesting them needs a selective trigger — wholesale
deviation collapses episodes. This script asks the prerequisite question:
across many pool-1 streams, can the states where a strictly better sibling
exists be recognised from features available at decision time?

Every feature is computable from the deterministic sibling reconstruction
before any branch outcome is known: the step index, the sibling q
statistics, the candidate kinds, and the support-surface ledger of the
sibling set. The label — a sibling beats the policy's own choice on final
placed — comes from the physically executed branches. Evaluation is
leave-one-stream-out ridge scoring with a rank AUC, so a stream's own
states never inform its trigger.
"""

from __future__ import annotations

import argparse
import itertools
import json
import pathlib
import statistics
from typing import Any

import numpy as np

try:
    from .analyze_commitment_point import load_config
except ImportError:
    from analyze_commitment_point import load_config

RIDGE_L2 = 1.0
FEATURE_NAMES = (
    "step",
    "branch_count",
    "q_max",
    "q_spread",
    "release_share",
    "item_is_soft",
    "item_is_prioritized",
    "mean_delta_usable_support",
    "min_delta_usable_support",
    "mean_base_z",
    "floor_share",
    "forbidden_share",
    "mean_footprint",
)


BOARD_FEATURE_NAMES = (
    "packed_count",
    "pool_volume",
    "pool_soft",
    "pool_priority",
    "grid_max",
    "grid_mean",
    "grid_std",
    "grid_occupied_share",
    "grid_container_imbalance",
    "grid_roughness",
)


def board_feature_vector(state: dict[str, Any]) -> list[float] | None:
    """Whole-board summary plus the raw height cells, decision-time only."""
    board = state.get("board")
    if not board:
        return None
    grids = board.get("height_grids") or []
    cells = [cell for grid in grids for cell in grid]
    if not cells:
        return None
    per_container_mean = [
        statistics.fmean(grid) if grid else 0.0 for grid in grids
    ]
    roughness = statistics.fmean(
        abs(a - b)
        for grid in grids
        for a, b in zip(grid, grid[1:])
    )
    summary = [
        float(board.get("packed_count", 0)),
        float(board.get("pool_volume", 0.0)),
        float(board.get("pool_soft", 0)),
        float(board.get("pool_priority", 0)),
        max(cells),
        statistics.fmean(cells),
        statistics.pstdev(cells),
        statistics.fmean(1.0 if cell > 0.0 else 0.0 for cell in cells),
        (
            max(per_container_mean) - min(per_container_mean)
            if len(per_container_mean) > 1 else 0.0
        ),
        roughness,
    ]
    return summary + [float(cell) for cell in cells]


def state_features(state: dict[str, Any]) -> list[float] | None:
    branches = state["branches"]
    ledgers = [b["support_ledger"] for b in branches if b.get("support_ledger")]
    if not ledgers:
        return None
    qs = [b["q"] for b in branches]
    control = next((b for b in branches if b["is_control"]), None)
    control_ledger = (control or branches[0]).get("support_ledger") or ledgers[0]
    forbidden = [
        (l["supporter_overlap"]["soft"] + l["supporter_overlap"]["priority"])
        / max(l["footprint_area"], 1e-9)
        for l in ledgers
    ]
    return [
        float(state["step"]),
        float(len(branches)),
        max(qs),
        max(qs) - min(qs),
        statistics.fmean(
            1.0 if "release" in str(b.get("kind", "")) else 0.0
            for b in branches
        ),
        1.0 if control_ledger["item_is_soft"] else 0.0,
        1.0 if control_ledger["item_is_prioritized"] else 0.0,
        statistics.fmean(l["delta_usable_support"] for l in ledgers),
        min(l["delta_usable_support"] for l in ledgers),
        statistics.fmean(l["base_z"] for l in ledgers),
        statistics.fmean(1.0 if l["on_floor"] else 0.0 for l in ledgers),
        statistics.fmean(forbidden),
        statistics.fmean(l["footprint_area"] for l in ledgers),
    ]


def state_label(state: dict[str, Any], outcome: str) -> tuple[bool, float] | None:
    control = next(
        (b for b in state["branches"] if b["is_control"]), None
    )
    if control is None:
        return None
    best = max(b[outcome] for b in state["branches"])
    return best > control[outcome], best - control[outcome]


def build_rows(
    dirs: list[pathlib.Path], outcome: str, *, feature_set: str = "sibling",
) -> list[dict[str, Any]]:
    rows = []
    for path in dirs:
        config = load_config(path)
        for state in config["states"]:
            if len(state["branches"]) < 2:
                continue
            sibling = state_features(state)
            board = board_feature_vector(state)
            if feature_set == "sibling":
                features = sibling
            elif feature_set == "board":
                features = board
            else:
                features = (
                    sibling + board
                    if sibling is not None and board is not None else None
                )
            labeled = state_label(state, outcome)
            if features is None or labeled is None:
                continue
            avoidable, gap = labeled
            rows.append({
                "stream": config["task_id"],
                "step": state["step"],
                "features": features,
                "avoidable": avoidable,
                "gap": gap,
            })
    return rows


def _fit_scores(
    train: list[dict[str, Any]], test: list[dict[str, Any]],
) -> list[float]:
    design = np.asarray([row["features"] for row in train], dtype=float)
    target = np.asarray(
        [1.0 if row["avoidable"] else -1.0 for row in train]
    )
    means = design.mean(axis=0)
    scales = design.std(axis=0)
    scales[scales < 1e-12] = 1.0
    standardized = (design - means) / scales
    weights = np.linalg.solve(
        standardized.T @ standardized + RIDGE_L2 * np.eye(standardized.shape[1]),
        standardized.T @ target,
    )
    probe = (np.asarray([row["features"] for row in test]) - means) / scales
    return (probe @ weights).tolist()


def rank_auc(scores: list[float], labels: list[bool]) -> float | None:
    positives = [s for s, y in zip(scores, labels) if y]
    negatives = [s for s, y in zip(scores, labels) if not y]
    if not positives or not negatives:
        return None
    wins = sum(
        1.0 if p > n else 0.5 if p == n else 0.0
        for p, n in itertools.product(positives, negatives)
    )
    return wins / (len(positives) * len(negatives))


def evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    streams = sorted({row["stream"] for row in rows})
    held_scores: list[float] = []
    held_labels: list[bool] = []
    held_gaps: list[float] = []
    for stream in streams:
        train = [row for row in rows if row["stream"] != stream]
        test = [row for row in rows if row["stream"] == stream]
        if not train or not test:
            continue
        if len({row["avoidable"] for row in train}) < 2:
            continue
        for row, score in zip(test, _fit_scores(train, test)):
            held_scores.append(score)
            held_labels.append(row["avoidable"])
            held_gaps.append(row["gap"])
    auc = rank_auc(held_scores, held_labels)
    order = sorted(
        range(len(held_scores)), key=lambda i: -held_scores[i]
    )
    quartile = max(1, len(order) // 4)
    top = order[:quartile]
    fired_positive = sum(1 for i in top if held_labels[i])
    result = {
        "streams": streams,
        "states": len(rows),
        "avoidable_states": sum(1 for row in rows if row["avoidable"]),
        "base_rate": (
            sum(1 for row in rows if row["avoidable"]) / len(rows)
            if rows else None
        ),
        "held_out_rank_auc": auc,
        "top_quartile_trigger": {
            "fired": len(top),
            "avoidable_among_fired": fired_positive,
            "precision": fired_positive / len(top) if top else None,
            "mean_gap_among_fired": (
                statistics.fmean(held_gaps[i] for i in top) if top else None
            ),
            "mean_gap_overall": (
                statistics.fmean(held_gaps) if held_gaps else None
            ),
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels-dir", action="append", type=pathlib.Path,
                        required=True)
    parser.add_argument(
        "--feature-set", default="sibling",
        choices=("sibling", "board", "both"),
    )
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path)
    args = parser.parse_args()
    result = {
        "schema_version": 1,
        "feature_set": args.feature_set,
        "feature_names": list(FEATURE_NAMES),
        "board_feature_names": list(BOARD_FEATURE_NAMES) + ["grid_cells..."],
        "per_outcome": {
            outcome: evaluate(build_rows(
                args.labels_dir, outcome, feature_set=args.feature_set
            ))
            for outcome in ("placed", "fill")
        },
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if args.markdown_output:
        lines = ["# Deviation-trigger detectability", ""]
        for outcome, block in result["per_outcome"].items():
            top = block["top_quartile_trigger"]
            lines += [
                f"## Outcome: final {outcome}",
                f"- streams {len(block['streams'])}, states {block['states']}, "
                f"avoidable {block['avoidable_states']} "
                f"(base rate {block['base_rate']:.2f})"
                if block["base_rate"] is not None else "- no states",
                f"- held-out rank AUC: {block['held_out_rank_auc']}",
                (
                    f"- top-quartile trigger: precision {top['precision']}, "
                    f"mean gap among fired {top['mean_gap_among_fired']} "
                    f"vs overall {top['mean_gap_overall']}"
                ),
                "",
            ]
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text("\n".join(lines), encoding="utf-8")
    print(args.json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
