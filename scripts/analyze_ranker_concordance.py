#!/usr/bin/env python3
"""Score the live Ranker ordering against long-horizon branch labels.

Consumes schema-2 ``branch-labels.json`` files (one per config). Within each
usable branch state, every sibling pair whose final outcome differs is a
decided pair; the live ordering is concordant on it when the higher-q sibling
reaches the better final outcome. Pairs inside one state share history, so
alongside pooled pair counts the script reports a per-state top-pick check
and per-config splits, and it fits a leave-one-config-out logistic
reweighting on the recorded q components to ask whether any linear form of
the same terms orders these labels better than the shipped one.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import pathlib
from typing import Any

import numpy as np

COMPONENT_NAMES = (
    "volume", "support", "depth", "lateral", "lift", "routing", "zone",
    "risk_penalty",
)
RIDGE_L2 = 1.0
OUTCOMES = ("placed", "fill")


def _exact_two_sided_binomial_p(successes: int, trials: int) -> float:
    if not trials:
        return 1.0
    tail = sum(
        math.comb(trials, value)
        for value in range(min(successes, trials - successes) + 1)
    ) / (2 ** trials)
    return min(1.0, 2.0 * tail)


def load_states(path: pathlib.Path) -> list[dict[str, Any]]:
    data = json.loads((path / "branch-labels.json").read_text(encoding="utf-8"))
    if int(data.get("schema_version", 0)) < 2:
        raise ValueError(f"branch labels require schema 2: {path}")
    states = []
    for state in data["states"]:
        usable = []
        for branch in state["branches"]:
            reproducibility = branch["reproducibility"]
            if not reproducibility["prefix_reproduced_all"]:
                continue
            if not reproducibility["parent_state_matches_all"]:
                continue
            runs = branch["runs"]
            usable.append({
                "q": float(branch["q"]),
                "components": branch.get("q_components") or {},
                "is_control": bool(branch["is_control"]),
                "placed": float(runs[0]["evaluation"].get("num_placed_items", 0.0)),
                "fill": float(runs[0]["evaluation"].get("fill_score", 0.0)),
            })
        if len(usable) >= 2:
            states.append({
                "task_id": data["task_id"],
                "step": int(state["step"]),
                "branches": usable,
            })
    return states


def decided_pairs(states: list[dict[str, Any]], outcome: str) -> list[dict[str, Any]]:
    pairs = []
    for state in states:
        for left, right in itertools.combinations(state["branches"], 2):
            if left[outcome] == right[outcome] or left["q"] == right["q"]:
                continue
            better, worse = (
                (left, right) if left[outcome] > right[outcome] else (right, left)
            )
            pairs.append({
                "task_id": state["task_id"],
                "step": state["step"],
                "q_concordant": better["q"] > worse["q"],
                "outcome_gap": better[outcome] - worse[outcome],
                "better": better,
                "worse": worse,
            })
    return pairs


def _pair_matrix(pairs: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    rows, labels = [], []
    for pair in pairs:
        better, worse = pair["better"]["components"], pair["worse"]["components"]
        if not better or not worse:
            continue
        delta = [
            float(better.get(name, 0.0)) - float(worse.get(name, 0.0))
            for name in COMPONENT_NAMES
        ]
        # Antisymmetric training: both orientations, no intercept.
        rows.append(delta)
        labels.append(1.0)
        rows.append([-value for value in delta])
        labels.append(-1.0)
    return np.asarray(rows, dtype=float), np.asarray(labels, dtype=float)


def _fit_reweighting(pairs: list[dict[str, Any]]) -> dict[str, Any] | None:
    design, target = _pair_matrix(pairs)
    if not len(design):
        return None
    scales = design.std(axis=0)
    scales[scales < 1e-12] = 1.0
    standardized = design / scales
    weights = np.linalg.solve(
        standardized.T @ standardized + RIDGE_L2 * np.eye(standardized.shape[1]),
        standardized.T @ target,
    )
    return {
        "component_names": list(COMPONENT_NAMES),
        "scales": scales.tolist(),
        "weights": weights.tolist(),
    }


def _reweighted_concordant(model: dict[str, Any], pair: dict[str, Any]) -> bool | None:
    better, worse = pair["better"]["components"], pair["worse"]["components"]
    if not better or not worse:
        return None
    delta = np.asarray([
        float(better.get(name, 0.0)) - float(worse.get(name, 0.0))
        for name in COMPONENT_NAMES
    ])
    score = float(
        (delta / np.asarray(model["scales"])) @ np.asarray(model["weights"])
    )
    if score == 0.0:
        return None
    return score > 0.0


def _summary(flags: list[bool]) -> dict[str, Any]:
    concordant = sum(flags)
    return {
        "decided_pairs": len(flags),
        "concordant": concordant,
        "concordance": concordant / len(flags) if flags else None,
        "exact_two_sided_p_vs_chance": _exact_two_sided_binomial_p(
            concordant, len(flags)
        ),
    }


def analyze(dirs: list[pathlib.Path]) -> dict[str, Any]:
    states = [state for path in dirs for state in load_states(path)]
    configs = sorted({state["task_id"] for state in states})
    result: dict[str, Any] = {
        "schema_version": 1,
        "configs": configs,
        "states": len(states),
        "per_outcome": {},
    }
    for outcome in OUTCOMES:
        pairs = decided_pairs(states, outcome)
        live = _summary([pair["q_concordant"] for pair in pairs])
        per_config = {
            config: _summary([
                pair["q_concordant"] for pair in pairs
                if pair["task_id"] == config
            ])
            for config in configs
        }
        top_pick = []
        for state in states:
            values = [branch[outcome] for branch in state["branches"]]
            if len(set(values)) < 2:
                continue
            best = max(state["branches"], key=lambda branch: branch["q"])
            top_pick.append(best[outcome] == max(values))
        held_out_flags: list[bool] = []
        per_component = {name: [] for name in COMPONENT_NAMES}
        for config in configs:
            train = [pair for pair in pairs if pair["task_id"] != config]
            test = [pair for pair in pairs if pair["task_id"] == config]
            model = _fit_reweighting(train)
            if model is None:
                continue
            for pair in test:
                flag = _reweighted_concordant(model, pair)
                if flag is not None:
                    held_out_flags.append(flag)
        for pair in pairs:
            better, worse = pair["better"]["components"], pair["worse"]["components"]
            if not better or not worse:
                continue
            for name in COMPONENT_NAMES:
                gap = float(better.get(name, 0.0)) - float(worse.get(name, 0.0))
                if gap != 0.0:
                    per_component[name].append(gap > 0.0)
        result["per_outcome"][outcome] = {
            "live_q": live,
            "per_config_live_q": per_config,
            "top_pick": {
                "states": len(top_pick),
                "top_q_reaches_best_outcome": sum(top_pick),
                "fraction": (
                    sum(top_pick) / len(top_pick) if top_pick else None
                ),
            },
            "held_out_reweighting": _summary(held_out_flags),
            "single_component_concordance": {
                name: _summary(flags)
                for name, flags in per_component.items() if flags
            },
            "full_data_reweighting_weights": _fit_reweighting(pairs),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels-dir", action="append", type=pathlib.Path,
                        required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path)
    args = parser.parse_args()
    result = analyze(args.labels_dir)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if args.markdown_output:
        lines = [
            "# Ranker ordering versus long-horizon branch labels", "",
            f"- configs: {', '.join(result['configs'])}",
            f"- usable branch states: {result['states']}", "",
        ]
        for outcome, block in result["per_outcome"].items():
            live = block["live_q"]
            held = block["held_out_reweighting"]
            top = block["top_pick"]
            lines += [
                f"## Outcome: final {outcome}", "",
                (
                    f"- live q concordance: {live['concordant']}/"
                    f"{live['decided_pairs']}"
                    f" (p={live['exact_two_sided_p_vs_chance']:.4g})"
                ),
                (
                    f"- top-q sibling reaches best outcome in "
                    f"{top['top_q_reaches_best_outcome']}/{top['states']} states"
                ),
                (
                    f"- held-out reweighting concordance: {held['concordant']}/"
                    f"{held['decided_pairs']}"
                    f" (p={held['exact_two_sided_p_vs_chance']:.4g})"
                ),
                "",
            ]
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(
            "\n".join(lines), encoding="utf-8"
        )
    print(args.json_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
