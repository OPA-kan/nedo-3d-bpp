"""Closed-loop metric: search-Pareto recall@K of ranked proposals.

For held-out vector-MCTS roots (whose candidate unions already include
beta proposals), rank each root's safe candidates three ways and ask
how much of the *search-discovered* Pareto frontier the top K capture:

- coverage order: provenance sequence order, no model;
- beta_0: feasibility score F(s, a);
- beta_1: F(s, a) * A(s, a) with A trained on search-Pareto labels
  from *other* cells — the first NN_t -> MCTS_t -> NN_{t+1} hand-off.
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

from scripts.counterfactual_graph import state_tensor_from_snapshot  # noqa: E402
from scripts.train_feasibility_head import FeasibilityEnsemble  # noqa: E402


def rank_root(
    root: dict[str, Any], state: dict[str, Any], *,
    feasibility: FeasibilityEnsemble, acceptance: FeasibilityEnsemble | None,
    k: int,
) -> dict[str, Any] | None:
    visible = list(state["visible_item_indices"])
    candidates = [
        candidate for candidate in root.get("root_candidates") or []
        if candidate.get("safe")
        and candidate.get("command_action") is not None
        and candidate.get("stable_item_index") in visible
    ]
    frontier = {
        candidate["root_candidate_id"] for candidate in candidates
        if candidate.get("in_search_pareto")
    }
    if len(candidates) <= k or not frontier:
        return None
    actions = [candidate["command_action"] for candidate in candidates]
    items = [
        [
            float(v)
            for v in state["visible_item_values"][
                visible.index(candidate["stable_item_index"])
            ]
        ]
        for candidate in candidates
    ]
    f_scores = feasibility.predict(state, actions, items)
    a_scores = (
        acceptance.predict(state, actions, items)
        if acceptance is not None else None
    )

    def recall(order) -> float:
        top = {
            candidates[index]["root_candidate_id"] for index in order[:k]
        }
        return len(top & frontier) / len(frontier)

    coverage_order = list(range(len(candidates)))  # provenance order
    beta0_order = sorted(
        range(len(candidates)), key=lambda i: -float(f_scores[i])
    )
    result = {
        "step": root["step"],
        "candidates": len(candidates),
        "frontier_size": len(frontier),
        "recall_at_k": {
            "coverage_order": recall(coverage_order),
            "beta0_feasibility": recall(beta0_order),
        },
    }
    if a_scores is not None:
        beta1_order = sorted(
            range(len(candidates)),
            key=lambda i: -(float(f_scores[i]) * float(a_scores[i])),
        )
        result["recall_at_k"]["beta1_search_pareto"] = recall(beta1_order)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="append", required=True,
        metavar="CELL=MCTS_JSON:EPISODE_DIR",
    )
    parser.add_argument("--feasibility-model-dir", type=pathlib.Path,
                        required=True)
    parser.add_argument("--acceptance-model-dir", type=pathlib.Path,
                        default=None)
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    feasibility = FeasibilityEnsemble(args.feasibility_model_dir)
    acceptance = (
        FeasibilityEnsemble(args.acceptance_model_dir)
        if args.acceptance_model_dir is not None else None
    )
    cells = {}
    for spec in args.run:
        cell, _, rest = spec.partition("=")
        mcts_path, _, episode_dir = rest.partition(":")
        payload = json.loads(pathlib.Path(mcts_path).read_text())
        rows = []
        for root in payload.get("roots") or []:
            snapshot_path = root.get("snapshot_path")
            if not snapshot_path:
                continue
            snapshot = json.loads(
                (pathlib.Path(episode_dir) / snapshot_path).read_text()
            )
            row = rank_root(
                root, state_tensor_from_snapshot(snapshot),
                feasibility=feasibility, acceptance=acceptance, k=args.k,
            )
            if row is not None:
                rows.append(row)
        cells[cell] = rows
    all_rows = [row for rows in cells.values() for row in rows]
    arms = sorted({
        arm for row in all_rows for arm in row["recall_at_k"]
    })
    summary = {
        "roots": len(all_rows),
        "k": args.k,
        "mean_recall_at_k": {
            arm: (
                sum(row["recall_at_k"][arm] for row in all_rows
                    if arm in row["recall_at_k"])
                / max(1, sum(arm in row["recall_at_k"] for row in all_rows))
            )
            for arm in arms
        },
    }
    report = {
        "schema_version": 1,
        "contract": "closed_loop_search_pareto_recall_v1",
        "feasibility_model": feasibility.model_id,
        "acceptance_model": (
            acceptance.model_id if acceptance is not None else None
        ),
        "cells": cells,
        "summary": summary,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
