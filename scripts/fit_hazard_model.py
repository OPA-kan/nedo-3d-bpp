"""
Fit a multi-step termination hazard from the policy traces we already have.

Why this target and not the obvious one. Two attempts to learn "how many
more items fit" failed here (Stage A's placed-to-go descriptors, LOSO MAE
0.979 -> 1.456; the Monte-Carlo rollout value, Spearman -0.30 after the
common-random-numbers fix). Both targets are dominated by the arrival order,
which a Task C agent cannot observe and which our corpus samples about twice.
The one learned model that works here -- P_rot, the toppling probability
behind the death-band gate -- predicts something determined by the geometry
in front of it.

So the target here stays on the observable side: given the search
diagnostics and the chosen action AT DECISION TIME, will the episode hit an
irreversible end within k more steps? Every feature is read off the decision
the agent just made; none of them look forward.

Validation is leave-one-case-out, because rows inside one episode share a
board and a stream and would otherwise leak into each other.

No sklearn: the shipped agent may not add dependencies, so the model has to
be expressible in numpy and embeddable as coefficients.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]

FEATURES = [
    "immediate_score",
    "is_release",
    "top_candidate_count",
    "pool_size",
    "unit_coverage",
    "attempts_consumed_log",
    "attempts_to_first_log",
    "incumbent_updates_log",
    "deadline_reached",
    "settled_accept_rate",
    "release_accept_rate",
    "settled_share",
    "reject_support_frac",
    "reject_corridor_frac",
    "reject_static_frac",
    "release_all_rejected",
    "step_index",
]


def _safe_ratio(numerator, denominator):
    denominator = float(denominator or 0.0)
    if denominator <= 0.0:
        return 0.0
    return float(numerator or 0.0) / denominator


def row_features(row) -> dict[str, float] | None:
    if row.get("event") != "decision":
        return None
    diagnostics = row.get("candidate_diagnostics") or {}
    search = diagnostics.get("search") or {}
    by_kind = diagnostics.get("by_kind") or {}
    settled = by_kind.get("settled") or {}
    release = by_kind.get("release") or {}
    settled_rejects = settled.get("rejected") or {}
    release_rejects = release.get("rejected") or {}

    rejects = collections.Counter()
    for source in (settled_rejects, release_rejects):
        for reason, count in source.items():
            rejects[reason] += int(count or 0)
    total_rejects = sum(rejects.values())

    settled_attempted = float(settled.get("attempted") or 0.0)
    release_attempted = float(release.get("attempted") or 0.0)
    attempted = settled_attempted + release_attempted

    return {
        "immediate_score": float(row.get("immediate_score") or 0.0),
        "is_release": 1.0
        if row.get("candidate_kind") == "release_candidate"
        else 0.0,
        "top_candidate_count": float(row.get("top_candidate_count") or 0.0),
        "pool_size": float(row.get("pool_size") or 0.0),
        "unit_coverage": _safe_ratio(
            search.get("units_completed"), search.get("units_total")
        ),
        "attempts_consumed_log": math.log1p(
            float(search.get("attempts_consumed") or 0.0)
        ),
        "attempts_to_first_log": math.log1p(
            float(search.get("attempts_to_first_candidate") or 0.0)
        ),
        "incumbent_updates_log": math.log1p(
            float(search.get("incumbent_updates") or 0.0)
        ),
        "deadline_reached": 1.0
        if search.get("deadline_reached")
        else 0.0,
        "settled_accept_rate": _safe_ratio(
            settled.get("accepted"), settled_attempted
        ),
        "release_accept_rate": _safe_ratio(
            release.get("accepted"), release_attempted
        ),
        "settled_share": _safe_ratio(settled_attempted, attempted),
        "reject_support_frac": _safe_ratio(rejects.get("support"), total_rejects),
        "reject_corridor_frac": _safe_ratio(
            rejects.get("corridor"), total_rejects
        ),
        "reject_static_frac": _safe_ratio(
            rejects.get("static_geometry"), total_rejects
        ),
        "release_all_rejected": 1.0
        if diagnostics.get("release_all_rejected")
        else 0.0,
        "step_index": float(row.get("step") or 0.0),
    }


def load_dataset(roots, horizon):
    """
    One row per decision. Label: the episode ends irreversibly within
    ``horizon`` steps of this decision.

    An episode that consumed its whole stream did not end irreversibly, so
    every one of its rows is a negative -- otherwise the model would learn
    "episodes end" rather than "episodes fail".
    """
    features, labels, groups = [], [], []
    seen = 0
    for root in roots:
        for trace_path in sorted(
            glob.glob(f"{root}/**/policy-trace.jsonl", recursive=True)
        ):
            run_dir = pathlib.Path(trace_path).parent
            rows_path = run_dir.parent.parent / "rows.jsonl"
            if not rows_path.exists():
                continue
            try:
                summary = json.loads(rows_path.read_text().splitlines()[0])
            except (json.JSONDecodeError, IndexError):
                continue
            cases = summary.get("cases") or {}
            if not cases:
                continue
            case_id, case = next(iter(cases.items()))
            placed = case.get("placed_count")
            total = case.get("total_items")
            if placed is None or total is None:
                continue
            died = int(placed) < int(total)

            trace = []
            with open(trace_path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        trace.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            decisions = [r for r in trace if r.get("event") == "decision"]
            if not decisions:
                continue
            terminal_step = float(decisions[-1].get("step") or 0.0)
            seen += 1
            for row in decisions:
                vector = row_features(row)
                if vector is None:
                    continue
                to_go = terminal_step - float(row.get("step") or 0.0)
                label = 1.0 if (died and to_go <= horizon) else 0.0
                features.append([vector[name] for name in FEATURES])
                labels.append(label)
                groups.append(case_id)
    return (
        np.asarray(features, dtype=np.float64),
        np.asarray(labels, dtype=np.float64),
        np.asarray(groups),
        seen,
    )


def fit_logistic(x, y, l2=1.0, steps=4000, learning_rate=0.1):
    """Plain gradient descent. Small data, few features, no dependencies."""
    n, d = x.shape
    weights = np.zeros(d + 1, dtype=np.float64)
    design = np.hstack([np.ones((n, 1)), x])
    for _ in range(steps):
        prediction = 1.0 / (1.0 + np.exp(-design @ weights))
        gradient = design.T @ (prediction - y) / max(n, 1)
        gradient[1:] += l2 * weights[1:] / max(n, 1)
        weights -= learning_rate * gradient
    return weights


def predict(weights, x):
    design = np.hstack([np.ones((x.shape[0], 1)), x])
    return 1.0 / (1.0 + np.exp(-design @ weights))


def auc(y, p):
    positives = p[y == 1.0]
    negatives = p[y == 0.0]
    if positives.size == 0 or negatives.size == 0:
        return float("nan")
    order = np.argsort(np.concatenate([positives, negatives]))
    ranks = np.empty(order.size, dtype=np.float64)
    ranks[order] = np.arange(1, order.size + 1)
    rank_sum = ranks[: positives.size].sum()
    return float(
        (rank_sum - positives.size * (positives.size + 1) / 2.0)
        / (positives.size * negatives.size)
    )


def standardize(train, other):
    mean = train.mean(axis=0)
    scale = train.std(axis=0)
    scale[scale < 1e-9] = 1.0
    return (train - mean) / scale, (other - mean) / scale, mean, scale


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--roots",
        nargs="+",
        default=[str(ROOT / "reports")],
        help="directories to scan for policy-trace.jsonl",
    )
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--l2", type=float, default=1.0)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    x, y, groups, runs = load_dataset(args.roots, args.horizon)
    if x.size == 0:
        print("no rows found", file=sys.stderr)
        return 1
    base_rate = float(y.mean())
    print(
        f"runs {runs}, rows {len(y)}, cases {len(set(groups))}, "
        f"positives {int(y.sum())} ({base_rate:.3f})"
    )

    folds = []
    for case_id in sorted(set(groups)):
        held = groups == case_id
        if held.sum() == 0 or (~held).sum() == 0:
            continue
        if len(set(y[held])) < 2:
            folds.append((case_id, float("nan"), float("nan"), int(held.sum())))
            continue
        train_x, test_x, _, _ = standardize(x[~held], x[held])
        weights = fit_logistic(train_x, y[~held], l2=args.l2)
        p = predict(weights, test_x)
        fold_auc = auc(y[held], p)
        brier = float(np.mean((p - y[held]) ** 2))
        folds.append((case_id, fold_auc, brier, int(held.sum())))

    print(f"{'case':12s} {'AUC':>7s} {'Brier':>8s} {'rows':>6s}")
    scored = [f for f in folds if not math.isnan(f[1])]
    for case_id, fold_auc, brier, rows in folds:
        auc_text = "n/a" if math.isnan(fold_auc) else f"{fold_auc:.3f}"
        brier_text = "n/a" if math.isnan(brier) else f"{brier:.4f}"
        print(f"{case_id:12s} {auc_text:>7s} {brier_text:>8s} {rows:6d}")
    if scored:
        mean_auc = float(np.mean([f[1] for f in scored]))
        mean_brier = float(np.mean([f[2] for f in scored]))
        # The comparison that matters: a model that predicts the base rate
        # everywhere gets AUC 0.5 and this Brier score.
        baseline_brier = base_rate * (1 - base_rate)
        print(
            f"\nLOSO mean AUC {mean_auc:.3f} (chance 0.5), "
            f"Brier {mean_brier:.4f} vs base-rate {baseline_brier:.4f}"
        )

    train_x, _, mean, scale = standardize(x, x)
    weights = fit_logistic(train_x, y, l2=args.l2)
    model = {
        "horizon": args.horizon,
        "features": FEATURES,
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "weights": weights.tolist(),
        "base_rate": base_rate,
        "rows": int(len(y)),
        "loso": [
            {
                "case": case_id,
                "auc": None if math.isnan(a) else a,
                "brier": None if math.isnan(b) else b,
                "rows": r,
            }
            for case_id, a, b, r in folds
        ],
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(model, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
