"""
Is there anything in Phi to learn, before anyone builds a model on it?

Keystone slice 5. The dataset pipeline now clears its coverage guard, which
says the sampled afterstates are spread out. It says nothing about whether the
recorded features predict the physical outcome. This asks that directly, and
it is designed to be able to answer "no".

Three decisions make the answer trustworthy rather than flattering:

**The split is by case, not by row.** Rows inside one snapshot share a parent
state, so a random row split would put near-duplicates on both sides and
report memorisation as skill. Leave-one-case-out is the coarsest split the
corpus supports; the audit asserts that no state appears on both sides.

**The incumbent is in the comparison.** `Ranker.score` already orders these
candidates in the live agent. A model that beats a constant but not the
existing score has established nothing worth shipping, so `score_immediate`
is evaluated as a ranker alongside the fitted models.

**Ranking is measured inside a state.** Pooled AUC across states can be driven
entirely by between-state differences in difficulty -- exactly the step/
fullness confound this project has already been burned by -- so the headline
ranking number is the mean of per-state AUCs, and top-1 regret is computed
within each state against that state's own best available candidate.

Scope limits, stated rather than papered over:

* Only `release_candidate` rows carry `phi_modelling`; settled candidates have
  no feature vector at all, so they are counted and excluded.
* The safe/unsafe mixture is a sampling design, not a natural rate. Rank
  metrics (AUC, regret) are meaningful; absolute calibration is not, and no
  calibration number is reported.
* numpy is the only dependency available, so the model family is a linear
  model and a quantile-bin lookup table. GBDT and Deep Sets from the keystone
  plan are NOT run. A null result here bounds those weakly, and the report
  says so.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.index_replay_corpus import state_fingerprint  # noqa: E402


FEATURES = (
    "support_ratio",
    "com_margin",
    "overhang_ratio",
    "drop_normalized",
    "support_imbalance",
    "left_right_imbalance",
    "front_back_imbalance",
    "initial_orientation",
)
REGRESSION_TARGETS = ("delta_theta_deg", "d_norm")
BIN_COUNT = 4
RIDGE = 1e-3


def load_rows(root: pathlib.Path) -> tuple[list[dict[str, Any]], dict]:
    """Every retained row, deduplicated inside its own state."""
    seen: set[tuple[str, str, int, str]] = set()
    rows: list[dict[str, Any]] = []
    skipped: collections.Counter = collections.Counter()
    for path in sorted(root.glob("*/dataset/*/step-*-*.jsonl")):
        if path.name.endswith("-state.json"):
            continue
        run_id = path.parents[2].name
        step_label = path.name.split("-")[1]
        # A state is a board, identified the same way the corpus index
        # identifies it. Two runs usually reach different boards at one step
        # index, but they sometimes land on the identical one, and counting
        # that twice would weight it twice inside its own fold.
        board = state_fingerprint(
            path.parent / f"step-{step_label}-state.json"
        )
        with path.open("r", encoding="utf-8") as handle:
            lines = [line for line in handle if line.strip()]
        for line in lines:
            row = json.loads(line)
            state = board or (
                run_id,
                str(row.get("case_id")),
                int(row.get("step", -1)),
            )
            key = (*state, str(row.get("candidate_id")))
            if key in seen:
                # The positive arm and the paired control legitimately share
                # candidates; one physical replay must count once.
                skipped["duplicate_across_arms"] += 1
                continue
            seen.add(key)
            phi = row.get("phi_modelling") or {}
            if not phi:
                skipped[f"no_phi_{row.get('kind')}"] += 1
                continue
            values = [phi.get(name) for name in FEATURES]
            if any(value is None for value in values):
                skipped["incomplete_phi"] += 1
                continue
            physical = row.get("physical") or {}
            rows.append(
                {
                    "state": state,
                    "case_id": str(row.get("case_id")),
                    "x": [float(value) for value in values],
                    "safe": bool(physical.get("is_placed_safe")),
                    "score": float(row.get("score_immediate", 0.0)),
                    "targets": {
                        name: (
                            None
                            if physical.get(name) is None
                            else float(physical[name])
                        )
                        for name in REGRESSION_TARGETS
                    },
                }
            )
    return rows, dict(skipped)


def auc(scores: np.ndarray, labels: np.ndarray) -> float | None:
    """Rank AUC. None when one class is absent, never 0.5 by default."""
    positive = labels.astype(bool)
    if positive.all() or not positive.any():
        return None
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=float)
    ranks[order] = np.arange(1, len(scores) + 1, dtype=float)
    # Average ranks over ties so a constant predictor scores exactly 0.5.
    _values, inverse, counts = np.unique(
        scores, return_inverse=True, return_counts=True
    )
    sums = np.zeros(len(counts))
    np.add.at(sums, inverse, ranks)
    ranks = (sums / counts)[inverse]
    n_pos = int(positive.sum())
    n_neg = len(labels) - n_pos
    return float(
        (ranks[positive].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    )


def standardize(train: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    mean = train.mean(axis=0)
    spread = train.std(axis=0)
    spread[spread <= 0.0] = 1.0
    return (matrix - mean) / spread


def fit_linear(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    design = np.hstack([np.ones((len(x), 1)), x])
    gram = design.T @ design + RIDGE * np.eye(design.shape[1])
    return np.linalg.solve(gram, design.T @ y)


def apply_linear(weights: np.ndarray, x: np.ndarray) -> np.ndarray:
    return np.hstack([np.ones((len(x), 1)), x]) @ weights


def fit_logistic(
    x: np.ndarray, y: np.ndarray, *, steps: int = 400
) -> np.ndarray:
    design = np.hstack([np.ones((len(x), 1)), x])
    weights = np.zeros(design.shape[1])
    for _step in range(steps):
        probability = 1.0 / (1.0 + np.exp(-design @ weights))
        gradient = design.T @ (probability - y) + RIDGE * weights
        weight = probability * (1.0 - probability) + 1e-6
        hessian = design.T @ (design * weight[:, None]) + RIDGE * np.eye(
            design.shape[1]
        )
        step = np.linalg.solve(hessian, gradient)
        weights = weights - step
        if np.max(np.abs(step)) < 1e-9:
            break
    return weights


def bin_edges(x: np.ndarray) -> list[np.ndarray]:
    return [
        np.quantile(
            x[:, index], np.linspace(0.0, 1.0, BIN_COUNT + 1)[1:-1]
        )
        for index in range(x.shape[1])
    ]


def cell_keys(x: np.ndarray, edges: list[np.ndarray]) -> list[tuple[int, ...]]:
    columns = [
        np.digitize(x[:, index], edges[index]) for index in range(x.shape[1])
    ]
    return [
        tuple(int(column[row]) for column in columns)
        for row in range(len(x))
    ]


def lookup_predictor(x: np.ndarray, y: np.ndarray):
    """Quantile-cell mean with backoff. The simplest thing that could work."""
    edges = bin_edges(x)
    table: dict[tuple[int, ...], list[float]] = collections.defaultdict(list)
    for key, value in zip(cell_keys(x, edges), y):
        table[key].append(float(value))
    means = {key: sum(values) / len(values) for key, values in table.items()}
    fallback = float(y.mean())

    def predict(matrix: np.ndarray) -> np.ndarray:
        return np.array(
            [means.get(key, fallback) for key in cell_keys(matrix, edges)]
        )

    return predict


def state_ranking(
    rows: list[dict[str, Any]], predictions: np.ndarray
) -> dict[str, Any]:
    """Per-state AUC and top-1 regret on `is_placed_safe`.

    Pooled AUC can be produced entirely by between-state difficulty. Ranking
    is a within-state question, so it is answered within a state.
    """
    by_state: dict[Any, list[int]] = collections.defaultdict(list)
    for index, row in enumerate(rows):
        by_state[row["state"]].append(index)

    aucs: list[float] = []
    hits = 0
    usable = 0
    for indexes in by_state.values():
        labels = np.array([rows[i]["safe"] for i in indexes], dtype=float)
        if labels.all() or not labels.any():
            continue
        usable += 1
        value = auc(predictions[indexes], labels)
        if value is not None:
            aucs.append(value)
        # Ties must not be broken by row order. A constant predictor ties
        # everything, and argmax would hand it whichever candidate happens to
        # be first -- scoring 1.000 for a model that ranks nothing. Credit the
        # expected value over the tied set, so a constant scores the state's
        # own safe rate.
        values = predictions[indexes]
        tied = np.flatnonzero(values >= values.max() - 1e-12)
        hits += float(
            sum(rows[indexes[i]]["safe"] for i in tied) / len(tied)
        )
    return {
        "states_with_both_classes": usable,
        "mean_state_auc": (
            sum(aucs) / len(aucs) if aucs else None
        ),
        "top1_safe_rate": (hits / usable) if usable else None,
    }


def evaluate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cases = sorted({row["case_id"] for row in rows})
    folds: list[dict[str, Any]] = []
    predictions: dict[str, np.ndarray] = {
        name: np.zeros(len(rows))
        for name in ("constant", "incumbent", "lookup", "linear")
    }
    regression: dict[str, dict[str, np.ndarray]] = {
        target: {
            name: np.zeros(len(rows))
            for name in ("constant", "lookup", "linear")
        }
        for target in REGRESSION_TARGETS
    }

    for case in cases:
        test_index = [
            i for i, row in enumerate(rows) if row["case_id"] == case
        ]
        train_index = [
            i for i, row in enumerate(rows) if row["case_id"] != case
        ]
        if not test_index or not train_index:
            continue
        # Leakage audit: a state must never straddle the split.
        train_states = {rows[i]["state"] for i in train_index}
        test_states = {rows[i]["state"] for i in test_index}
        assert not (train_states & test_states), "state leaked across the fold"

        x_train_raw = np.array([rows[i]["x"] for i in train_index])
        x_test_raw = np.array([rows[i]["x"] for i in test_index])
        x_train = standardize(x_train_raw, x_train_raw)
        x_test = standardize(x_train_raw, x_test_raw)
        y_train = np.array(
            [float(rows[i]["safe"]) for i in train_index]
        )

        predictions["constant"][test_index] = y_train.mean()
        predictions["incumbent"][test_index] = [
            rows[i]["score"] for i in test_index
        ]
        if 0.0 < y_train.mean() < 1.0:
            predictions["linear"][test_index] = apply_linear(
                fit_logistic(x_train, y_train), x_test
            )
        else:
            predictions["linear"][test_index] = y_train.mean()
        predictions["lookup"][test_index] = lookup_predictor(
            x_train, y_train
        )(x_test)

        for target in REGRESSION_TARGETS:
            train_rows = [
                i
                for i in train_index
                if rows[i]["targets"][target] is not None
            ]
            if not train_rows:
                continue
            xt = standardize(
                x_train_raw, np.array([rows[i]["x"] for i in train_rows])
            )
            yt = np.array(
                [rows[i]["targets"][target] for i in train_rows]
            )
            regression[target]["constant"][test_index] = yt.mean()
            regression[target]["linear"][test_index] = apply_linear(
                fit_linear(xt, yt), x_test
            )
            regression[target]["lookup"][test_index] = lookup_predictor(
                xt, yt
            )(x_test)

        folds.append(
            {
                "held_out_case": case,
                "train_rows": len(train_index),
                "test_rows": len(test_index),
                "train_states": len(train_states),
                "test_states": len(test_states),
                "train_safe_rate": float(y_train.mean()),
            }
        )

    labels = np.array([float(row["safe"]) for row in rows])
    classification = {
        name: {
            "pooled_auc": auc(values, labels),
            **state_ranking(rows, values),
        }
        for name, values in predictions.items()
    }

    regression_report: dict[str, Any] = {}
    for target in REGRESSION_TARGETS:
        actual_index = [
            i
            for i, row in enumerate(rows)
            if row["targets"][target] is not None
        ]
        actual = np.array(
            [rows[i]["targets"][target] for i in actual_index]
        )
        baseline = regression[target]["constant"][actual_index]
        denominator = float(((actual - baseline) ** 2).sum())
        regression_report[target] = {
            "rows": len(actual_index),
            "r2_versus_constant": {
                name: (
                    None
                    if denominator <= 0.0
                    else 1.0
                    - float(
                        (
                            (actual - regression[target][name][actual_index])
                            ** 2
                        ).sum()
                    )
                    / denominator
                )
                for name in ("lookup", "linear")
            },
        }

    return {
        "folds": folds,
        "classification": classification,
        "regression": regression_report,
    }


def contributing_runs(root: pathlib.Path) -> list[dict[str, Any]]:
    """Which runs the rows came from, and under what verdict and arm.

    A corpus assembled entirely from runs that failed their coverage guard is
    still validly labelled -- the labels come from the official validator, not
    from the sampler -- but a reader has to be able to see that, so the audit
    reports the mix instead of flattening it.
    """
    runs: list[dict[str, Any]] = []
    for run_dir in sorted(root.glob("*")):
        if not (run_dir / "dataset").is_dir():
            continue
        try:
            summary = json.loads(
                (run_dir / "summary.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            summary = {}
        runs.append(
            {
                "run_id": run_dir.name,
                "verdict": (summary.get("acceptance") or {}).get("verdict"),
                "completeness": summary.get("completeness"),
                "observed_swap_rounds": (summary.get("arm") or {}).get(
                    "observed_swap_rounds"
                ),
            }
        )
    return runs


def learning_curve(
    rows: list[dict[str, Any]],
    *,
    sizes: list[int],
    repeats: int = 5,
) -> dict[str, Any]:
    """How the metrics move as the number of training STATES grows.

    "When can we train a bigger model?" is a question about the slope, not
    about today's number, and the slope is measurable: hold out a case, train
    on k sampled states from the rest, and sweep k. Sampling is by state
    rather than by row because rows inside a state are not independent, so a
    row-wise curve would flatten early and read as saturation that has not
    happened.

    Extrapolating this is still extrapolation. The curve says what the last
    doubling bought, not what the next one will.
    """
    cases = sorted({row["case_id"] for row in rows})
    states_by_case: dict[str, list[Any]] = collections.defaultdict(list)
    for row in rows:
        if row["state"] not in states_by_case[row["case_id"]]:
            states_by_case[row["case_id"]].append(row["state"])

    points: list[dict[str, Any]] = []
    for size in sizes:
        auc_values: list[float] = []
        r2_values: dict[str, list[float]] = collections.defaultdict(list)
        for repeat in range(repeats):
            rng = np.random.default_rng(1000 * repeat + size)
            for case in cases:
                pool = [
                    state
                    for other in cases
                    if other != case
                    for state in states_by_case[other]
                ]
                if len(pool) < size:
                    continue
                chosen = {
                    pool[index]
                    for index in rng.choice(
                        len(pool), size=size, replace=False
                    )
                }
                train = [r for r in rows if r["state"] in chosen]
                test = [r for r in rows if r["case_id"] == case]
                if len(train) < 2 * len(FEATURES) or not test:
                    continue
                x_train_raw = np.array([r["x"] for r in train])
                x_train = standardize(x_train_raw, x_train_raw)
                x_test = standardize(
                    x_train_raw, np.array([r["x"] for r in test])
                )
                y_train = np.array([float(r["safe"]) for r in train])
                if 0.0 < y_train.mean() < 1.0:
                    scores = apply_linear(
                        fit_logistic(x_train, y_train), x_test
                    )
                    ranked = state_ranking(test, scores)
                    if ranked["mean_state_auc"] is not None:
                        auc_values.append(ranked["mean_state_auc"])
                for target in REGRESSION_TARGETS:
                    train_rows = [
                        i
                        for i, r in enumerate(train)
                        if r["targets"][target] is not None
                    ]
                    test_rows = [
                        i
                        for i, r in enumerate(test)
                        if r["targets"][target] is not None
                    ]
                    if not train_rows or not test_rows:
                        continue
                    yt = np.array(
                        [train[i]["targets"][target] for i in train_rows]
                    )
                    actual = np.array(
                        [test[i]["targets"][target] for i in test_rows]
                    )
                    weights = fit_linear(x_train[train_rows], yt)
                    predicted = apply_linear(weights, x_test[test_rows])
                    denominator = float(((actual - yt.mean()) ** 2).sum())
                    if denominator <= 0.0:
                        continue
                    r2_values[target].append(
                        1.0
                        - float(((actual - predicted) ** 2).sum())
                        / denominator
                    )
        points.append(
            {
                "train_states": size,
                "folds_evaluated": len(auc_values),
                "mean_state_auc": (
                    sum(auc_values) / len(auc_values) if auc_values else None
                ),
                "r2": {
                    target: (
                        sum(values) / len(values) if values else None
                    )
                    for target, values in r2_values.items()
                },
            }
        )
    return {
        "repeats": repeats,
        "points": points,
        "contract": (
            "Sampling is by state, not by row: rows inside a state are not "
            "independent, so a row-wise curve saturates early and reads as a "
            "ceiling that is not there. The curve describes doublings "
            "already taken, not the next one."
        ),
    }


def audit(root: pathlib.Path) -> dict[str, Any]:
    rows, skipped = load_rows(root)
    states = {row["state"] for row in rows}
    cases = sorted({row["case_id"] for row in rows})
    safe = sum(row["safe"] for row in rows)
    report: dict[str, Any] = {
        "schema_version": 1,
        "corpus": {
            "modelable_rows": len(rows),
            "distinct_states": len(states),
            "cases": cases,
            "rows_per_state": sorted(
                collections.Counter(row["state"] for row in rows).values()
            ),
            "safe_rows": safe,
            "unsafe_rows": len(rows) - safe,
            "excluded": skipped,
            "contributing_runs": contributing_runs(root),
        },
        "design": {
            "split": "leave_one_case_out",
            "features": list(FEATURES),
            "models": ["constant", "incumbent_score", "lookup", "linear"],
            "not_run": ["gbdt", "deep_sets"],
        },
    }
    if len(cases) < 2 or len(rows) < 2 * len(FEATURES):
        report["verdict"] = "insufficient_corpus"
        report["interpretation"] = (
            "Too few cases or rows to hold out anything meaningful. This is a "
            "statement about the corpus, not about learnability."
        )
        return report

    report.update(evaluate(rows))
    total = len({row["state"] for row in rows})
    sizes = sorted(
        {
            size
            for size in (4, 8, 12, 16, 24, 32, 40, total - 4)
            if 4 <= size <= total - 4
        }
    )
    if sizes:
        report["learning_curve"] = learning_curve(rows, sizes=sizes)
    incumbent = report["classification"]["incumbent"]["mean_state_auc"]
    best_model = max(
        (
            report["classification"][name]["mean_state_auc"] or 0.0,
            name,
        )
        for name in ("lookup", "linear")
    )
    report["verdict"] = (
        "signal_beyond_incumbent"
        if incumbent is not None and best_model[0] > incumbent + 0.05
        else "no_established_signal"
    )
    report["interpretation"] = (
        "Mean within-state AUC is the headline. A model must beat the "
        "incumbent Ranker.score, not merely a constant, to be worth "
        "building on. With this few cases the fold spread is wide, so a "
        "small difference is not a result. GBDT and Deep Sets were not run "
        "-- only numpy is available -- so a null here bounds them weakly."
    )
    return report


def markdown(report: dict[str, Any]) -> str:
    corpus = report["corpus"]
    lines = [
        "# Learnability audit",
        "",
        f"- Verdict: **{report['verdict']}**",
        (
            f"- Modelable rows: {corpus['modelable_rows']} across "
            f"{corpus['distinct_states']} states and "
            f"{len(corpus['cases'])} cases"
        ),
        (
            f"- Safe / unsafe: {corpus['safe_rows']} / "
            f"{corpus['unsafe_rows']} (a sampling design, not a natural rate)"
        ),
        f"- Excluded: {corpus['excluded']}",
        (
            "- Contributing runs: "
            + ", ".join(
                f"`{run['run_id']}` (verdict {run['verdict']}, "
                f"swap rounds {run['observed_swap_rounds']})"
                for run in corpus["contributing_runs"]
            )
        ),
        f"- Split: `{report['design']['split']}`; "
        f"not run: {report['design']['not_run']}",
        "",
    ]
    if "classification" not in report:
        lines.extend([report["interpretation"], ""])
        return "\n".join(lines)

    lines.extend(
        [
            "## is_placed_safe (ranking only; prevalence is designed)",
            "",
            "| model | mean within-state AUC | pooled AUC | "
            "top-1 safe rate |",
            "|---|---:|---:|---:|",
        ]
    )
    for name, values in report["classification"].items():
        lines.append(
            "| {name} | {state_auc} | {pooled} | {top1} |".format(
                name=name,
                state_auc=_fmt(values["mean_state_auc"]),
                pooled=_fmt(values["pooled_auc"]),
                top1=_fmt(values["top1_safe_rate"]),
            )
        )
    lines.extend(
        [
            "",
            "## settle regression (R^2 against a held-out constant)",
            "",
            "| target | rows | lookup | linear |",
            "|---|---:|---:|---:|",
        ]
    )
    for target, values in report["regression"].items():
        lines.append(
            "| {target} | {rows} | {lookup} | {linear} |".format(
                target=target,
                rows=values["rows"],
                lookup=_fmt(values["r2_versus_constant"]["lookup"]),
                linear=_fmt(values["r2_versus_constant"]["linear"]),
            )
        )
    lines.extend(
        [
            "",
            "## folds",
            "",
            "| held out | train rows | test rows | train states | "
            "test states | train safe rate |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for fold in report["folds"]:
        lines.append(
            "| {held_out_case} | {train_rows} | {test_rows} | "
            "{train_states} | {test_states} | {rate} |".format(
                rate=_fmt(fold["train_safe_rate"]), **fold
            )
        )
    curve = report.get("learning_curve")
    if curve:
        lines.extend(
            [
                "",
                "## learning curve (training STATES, not rows)",
                "",
                "| train states | folds | mean within-state AUC | "
                "R^2 delta_theta_deg | R^2 d_norm |",
                "|---:|---:|---:|---:|---:|",
            ]
        )
        for point in curve["points"]:
            lines.append(
                "| {states} | {folds} | {auc} | {theta} | {dnorm} |".format(
                    states=point["train_states"],
                    folds=point["folds_evaluated"],
                    auc=_fmt(point["mean_state_auc"]),
                    theta=_fmt(point["r2"].get("delta_theta_deg")),
                    dnorm=_fmt(point["r2"].get("d_norm")),
                )
            )
        lines.extend(["", curve["contract"]])

    lines.extend(["", report["interpretation"], ""])
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        return f"{value:.3f}"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    report = audit(args.root)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=float) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
