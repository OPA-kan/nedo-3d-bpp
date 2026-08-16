#!/usr/bin/env python3
"""Develop the v5 pre-action student with a powered prospective confirmation gate."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
from typing import Any

try:
    from .develop_distributional_fill_preaction_v2 import (
        deduplicate_rows,
    )
    from .develop_distributional_fill_preaction_v3 import (
        LABEL_FAMILY,
        METRIC,
        confirmation_gate,
    )
    from .develop_distributional_fill_preaction_v4 import (
        _all_rows,
        _score_predictions,
        fit_knn,
        predict_knn,
        select_policy,
    )
    from .evaluate_counterfactual_afterstate_value import (
        _eligible,
        load_run,
    )
except ImportError:
    from develop_distributional_fill_preaction_v2 import (
        deduplicate_rows,
    )
    from develop_distributional_fill_preaction_v3 import (
        LABEL_FAMILY,
        METRIC,
        confirmation_gate,
    )
    from develop_distributional_fill_preaction_v4 import (
        _all_rows,
        _score_predictions,
        fit_knn,
        predict_knn,
        select_policy,
    )
    from evaluate_counterfactual_afterstate_value import (
        _eligible,
        load_run,
    )


ALPHA = 0.05
TARGET_POWER = 0.5
# Below six discordant pairs the two-sided exact sign test cannot reach 0.05
# even on a perfect sweep, so any smaller confirmation is theater.
DISCORDANT_FLOOR = 6
POWER_SEARCH_CEILING = 400


def _exact_sign_p(wins: int, losses: int) -> float:
    discordant = wins + losses
    if not discordant:
        return 1.0
    tail = sum(
        math.comb(discordant, value)
        for value in range(min(wins, losses) + 1)
    ) / (2 ** discordant)
    return min(1.0, 2.0 * tail)


def minimum_powered_discordant(
    win_fraction: float, *,
    alpha: float = ALPHA, target_power: float = TARGET_POWER,
) -> int:
    """Smallest discordant count that can detect the development effect.

    Returns the smallest n such that, drawing wins from Binomial(n,
    win_fraction), the probability of a passing result (wins > losses and
    exact two-sided sign p <= alpha) is at least target_power.
    """
    if not 0.5 < win_fraction <= 1.0:
        raise ValueError("win fraction must exceed 0.5 for a powered gate")
    for n in range(DISCORDANT_FLOOR, POWER_SEARCH_CEILING + 1):
        achieved = sum(
            math.comb(n, wins)
            * win_fraction ** wins
            * (1.0 - win_fraction) ** (n - wins)
            for wins in range(n + 1)
            if wins > n - wins and _exact_sign_p(wins, n - wins) <= alpha
        )
        if achieved >= target_power:
            return n
    raise ValueError(
        f"no discordant count up to {POWER_SEARCH_CEILING} reaches "
        f"power {target_power} at win fraction {win_fraction}"
    )


def prediction_disagreements(candidate: list[str], action: list[str]) -> int:
    """Count rows where the two systems predict different directions.

    On rows whose true relation is directional, exactly one of two differing
    directional predictions is correct, so this count equals the sign test's
    future discordant-pair count without opening which direction is true.
    """
    return sum(left != right for left, right in zip(candidate, action))


def confirmation_gate_v5(
    evaluation: dict[str, Any], minimum_discordant: int, *,
    contract: str = "predeclared in distributional-fill-preaction-v5.md",
) -> dict[str, Any]:
    base = confirmation_gate(evaluation, contract=contract)
    paired = evaluation["paired_candidate_vs_action"]
    discordant = int(paired["wins"]) + int(paired["losses"])
    checks = dict(base["checks"])
    checks["discordant_pairs_at_least_frozen_minimum"] = (
        discordant >= minimum_discordant
    )
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "discordant_pairs": discordant,
        "minimum_discordant_pairs": minimum_discordant,
        "underpowered": discordant < minimum_discordant,
        "contract": contract,
    }


def build_v5(
    runs: list[dict[str, Any]], shadow: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    support = deduplicate_rows(_all_rows(runs))
    rows = support.pop("rows")
    selection = select_policy(rows, shadow)
    selected = selection["selected_result"]
    wins, losses = int(selected["wins"]), int(selected["losses"])
    win_fraction = wins / (wins + losses) if wins + losses else 0.0
    power = {
        "development_wins": wins,
        "development_losses": losses,
        "development_win_fraction": win_fraction,
        "alpha": ALPHA,
        "target_power": TARGET_POWER,
        "minimum_discordant_pairs": minimum_powered_discordant(win_fraction),
        "discordant_floor": DISCORDANT_FLOOR,
    }
    model = {
        "schema_version": 1,
        "status": "frozen_pending_powered_new_stream_confirmation",
        "label_family": LABEL_FAMILY,
        "axis": METRIC,
        "training_run_ids": [run["run_id"] for run in runs],
        "training_support": support,
        "model_selection": selection,
        "confirmation_power": power,
        "input_contract": (
            "source tensor plus candidate command/item geometry; immediate "
            "score, step, post-settle state, and future labels excluded"
        ),
        "knn_value_predictor": fit_knn(rows, selection),
    }
    development = {
        "schema_version": 1,
        "evaluation_kind": "group_complement_crossfit_unique_signatures",
        "training_run_ids": model["training_run_ids"],
        "support": support,
        "selected_result": selection["selected_result"],
        "confirmation_power": power,
        "claim": (
            "Development evidence only; a powered new-stream confirmation "
            "is required."
        ),
    }
    return model, development


def _late_unique_rows(runs: list[dict[str, Any]]) -> dict[str, Any]:
    raw = [
        row for run in runs
        for row in _eligible(run["late"], METRIC, label_family=LABEL_FAMILY)
    ]
    return deduplicate_rows(raw)


def power_audit(
    model: dict[str, Any], shadow: dict[str, Any], runs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Label-blind check that the admitted cohort can power the sign test.

    Eligibility opens only whether a row's relation is directional, never
    which direction. Predictions depend on tensors alone, so the audit can
    run before any confirmation label is opened.
    """
    support = _late_unique_rows(runs)
    rows = support.pop("rows")
    candidate, action, _ = predict_knn(model["knn_value_predictor"], shadow, rows)
    disagreements = prediction_disagreements(candidate, action)
    minimum = int(model["confirmation_power"]["minimum_discordant_pairs"])
    return {
        "schema_version": 1,
        "evaluation_kind": "label_blind_power_audit",
        "target_run_ids": [run["run_id"] for run in runs],
        "support": support,
        "prediction_disagreements": disagreements,
        "minimum_discordant_pairs": minimum,
        "powered": disagreements >= minimum,
        "claim": (
            "Directional eligibility was opened; direction labels were not. "
            "Expand the admitted cohort until this audit is powered, then "
            "evaluate the frozen artifact exactly once."
            if disagreements < minimum else
            "The admitted cohort powers the predeclared sign test; the "
            "frozen artifact may now be evaluated exactly once."
        ),
    }


def evaluate_v5(
    model: dict[str, Any], shadow: dict[str, Any], runs: list[dict[str, Any]],
    *, prospective: bool,
) -> dict[str, Any]:
    support = _late_unique_rows(runs)
    rows = support.pop("rows")
    candidate, action, distances = predict_knn(
        model["knn_value_predictor"], shadow, rows
    )
    scored = _score_predictions(rows, candidate, action)
    result = {
        "schema_version": 1,
        "evaluation_kind": (
            "prospective_confirmation_unique_signatures"
            if prospective else "inspected_development_unique_signatures"
        ),
        "target_run_ids": [run["run_id"] for run in runs],
        "support": support,
        "distance_support": {
            "supported_rows": sum(
                distance <= model["knn_value_predictor"]["support_distance_threshold"]
                for distance in distances
            ),
            "support_distance_threshold": model["knn_value_predictor"][
                "support_distance_threshold"
            ],
        },
        "correct": {
            "candidate": scored["candidate_correct"],
            "action_geometry": scored["action_geometry_correct"],
        },
        "paired_candidate_vs_action": {
            key: scored[key] for key in (
                "wins", "ties", "losses", "exact_two_sided_sign_p"
            )
        },
        "per_stream": scored["per_stream"],
    }
    if prospective:
        gate = confirmation_gate_v5(
            result,
            int(model["confirmation_power"]["minimum_discordant_pairs"]),
        )
        result["predeclared_confirmation_gate"] = gate
        if gate["underpowered"]:
            result["claim"] = (
                "Confirmation is underpowered; the frozen candidate is "
                "neither confirmed nor rejected. Expand the admitted cohort "
                "before the single evaluation. These labels are now opened "
                "development data."
            )
        elif gate["passed"]:
            result["claim"] = (
                "Prospective confirmation passed; offline branch-direction "
                "candidate only."
            )
        else:
            result["claim"] = (
                "Prospective confirmation failed; the frozen candidate is "
                "rejected."
            )
    else:
        result["claim"] = "Development evidence only; target labels are inspected."
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-dir", action="append", type=pathlib.Path)
    parser.add_argument("--target-dir", action="append", type=pathlib.Path)
    parser.add_argument("--model", type=pathlib.Path)
    parser.add_argument("--shadow-model", type=pathlib.Path, required=True)
    parser.add_argument("--model-output", type=pathlib.Path)
    parser.add_argument("--development-output", type=pathlib.Path)
    parser.add_argument("--evaluation-output", type=pathlib.Path)
    parser.add_argument("--power-audit-output", type=pathlib.Path)
    parser.add_argument("--prospective", action="store_true")
    args = parser.parse_args()
    shadow = json.loads(args.shadow_model.read_text(encoding="utf-8"))
    if args.model:
        if args.training_dir or args.model_output or args.development_output:
            parser.error("--model forbids training outputs")
        if not args.target_dir:
            parser.error("--model requires --target-dir")
        if not args.evaluation_output and not args.power_audit_output:
            parser.error(
                "--model requires --evaluation-output or --power-audit-output"
            )
        model = json.loads(args.model.read_text(encoding="utf-8"))
    elif args.training_dir and args.model_output and args.development_output:
        runs = [load_run(path, label_family=LABEL_FAMILY) for path in args.training_dir]
        model, development = build_v5(runs, shadow)
        args.model_output.parent.mkdir(parents=True, exist_ok=True)
        args.development_output.parent.mkdir(parents=True, exist_ok=True)
        args.model_output.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
        args.development_output.write_text(
            json.dumps(development, indent=2) + "\n", encoding="utf-8"
        )
    else:
        parser.error("provide --model or complete training inputs and outputs")
    if args.target_dir:
        target_runs = [
            load_run(path, label_family=LABEL_FAMILY) for path in args.target_dir
        ]
        if args.power_audit_output:
            audit = power_audit(model, shadow, target_runs)
            args.power_audit_output.parent.mkdir(parents=True, exist_ok=True)
            args.power_audit_output.write_text(
                json.dumps(audit, indent=2) + "\n", encoding="utf-8"
            )
        if args.evaluation_output:
            evaluation = evaluate_v5(
                model, shadow, target_runs, prospective=args.prospective
            )
            args.evaluation_output.parent.mkdir(parents=True, exist_ok=True)
            args.evaluation_output.write_text(
                json.dumps(evaluation, indent=2) + "\n", encoding="utf-8"
            )
    print(
        args.evaluation_output or args.power_audit_output or args.model_output
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
