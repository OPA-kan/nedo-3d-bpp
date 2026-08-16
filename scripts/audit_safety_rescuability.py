#!/usr/bin/env python3
"""Offline rescuability audit: why was the Gate 2 rerank arm inert?

Replays the preregistered swap rule over the committed state-model
corpus (every candidate row carries its immediate score, its physical
settle outcome, and the model's input features) and asks, board by
board: when the highest-Q candidate — the stand-in for the live
policy's choice — sits below the trigger logit, does the rule find an
eligible alternative, and was that alternative actually safe?

The audit that motivated the Gate 2b amendment found the answer was
"the alternatives exist and are safe, but the relative Q-conservation
bound blocks them": danger states have incumbent scores near zero, so
15% of |score| is a vanishing budget exactly where an absolute unit of
score buys survival. The sweep over absolute bounds is reproduced here
so the chosen constant stays auditable.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TRIGGER_LOGIT = 2.0
MARGIN_LOGIT = 2.0
RELATIVE_FRAC = 0.15
ABSOLUTE_BOUNDS = (0.5, 0.75, 1.0, 1.5, 2.0, None)


def trigger_boards(
    rows: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """(incumbent, escape-eligible alternatives) per triggered board."""
    states: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        states.setdefault(row["state"], []).append(row)
    boards = []
    for cands in states.values():
        if len(cands) < 2:
            continue
        incumbent = max(cands, key=lambda r: r["score"])
        if incumbent["logit"] >= TRIGGER_LOGIT:
            continue
        bar = max(TRIGGER_LOGIT, incumbent["logit"] + MARGIN_LOGIT)
        boards.append(
            (
                incumbent,
                [
                    c
                    for c in cands
                    if c is not incumbent and c["logit"] >= bar
                ],
            )
        )
    return boards


def apply_bound(
    boards, *, absolute: float | None = None, relative: float | None = None
) -> dict[str, Any]:
    rescued = unsafe_pick = needless = 0
    unsafe_incumbents = sum(
        1 for incumbent, _alts in boards if incumbent["safe"] < 0.5
    )
    needless_cost = []
    for incumbent, alts in boards:
        floor = None
        if absolute is not None:
            floor = incumbent["score"] - absolute
        elif relative is not None:
            floor = incumbent["score"] - relative * abs(incumbent["score"])
        eligible = [
            c for c in alts if floor is None or c["score"] >= floor
        ]
        if not eligible:
            continue
        best = max(eligible, key=lambda r: (r["logit"], r["score"]))
        incumbent_unsafe = incumbent["safe"] < 0.5
        pick_safe = best["safe"] > 0.5
        if incumbent_unsafe and pick_safe:
            rescued += 1
        if not pick_safe:
            unsafe_pick += 1
        if not incumbent_unsafe:
            needless += 1
            needless_cost.append(incumbent["score"] - best["score"])
    return {
        "unsafe_incumbent_boards": unsafe_incumbents,
        "rescued_safely": rescued,
        "swaps_to_unsafe_pick": unsafe_pick,
        "needless_swaps": needless,
        "needless_swap_mean_cost": (
            round(sum(needless_cost) / len(needless_cost), 3)
            if needless_cost
            else 0.0
        ),
    }


def audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    boards = trigger_boards(rows)
    result = {
        "corpus_rows": len(rows),
        "states": len({row["state"] for row in rows}),
        "trigger_boards": len(boards),
        "trigger_boards_with_escape_alternative": sum(
            1 for _incumbent, alts in boards if alts
        ),
        "shipped_relative_rule": apply_bound(
            boards, relative=RELATIVE_FRAC
        ),
        "absolute_bound_sweep": {
            str(bound): apply_bound(boards, absolute=bound)
            for bound in ABSOLUTE_BOUNDS
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=pathlib.Path, required=True)
    parser.add_argument("--artifact", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    from scripts.export_state_model import numpy_forward
    from scripts.train_state_model import load_examples

    rows = load_examples(args.corpus_root)
    if not rows:
        raise SystemExit("no corpus rows loaded")
    artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    logits = numpy_forward(
        artifact,
        [row["phi"] for row in rows],
        [row["candidate"] for row in rows],
    )
    for row, logit in zip(rows, logits):
        row["logit"] = float(logit)
    result = audit(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
