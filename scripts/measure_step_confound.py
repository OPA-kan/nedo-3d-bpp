"""
How much of a board feature's apparent skill is just "how late is it"?

The afterstate corpus labels each row `1` when the episode ends within a
horizon of that step. Step index is therefore, by construction, an excellent
predictor -- and every fullness-flavoured feature rises monotonically with
step index too. A literal step counter (`placed`) scored AUC 0.798 on this
corpus, which bounds how much of `occupancy_mean`'s 0.844 is board quality
rather than clock.

This separates the two:

  raw        AUC of the feature on its own
  step       AUC of the step counter on its own, the confound's own skill
  residual   AUC of the feature after regressing out step index, within
             case -- what is left when "how late is it" is removed
  within     AUC restricted to pairs from the SAME step index, which is the
             only contrast that is free of the confound by construction

A feature whose residual and within-step AUCs collapse to 0.5 is a clock,
not a board descriptor. Nothing here is adopted; it reports which of the
candidate features survive the confound.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def auc(scores, labels):
    positive = scores[labels == 1.0]
    negative = scores[labels == 0.0]
    if positive.size == 0 or negative.size == 0:
        return float("nan"), 0
    wins = sum(
        float((positive > value).sum()) + 0.5 * float((positive == value).sum())
        for value in negative
    )
    return wins / (positive.size * negative.size), int(positive.size * negative.size)


def residualise(values, step, group):
    """
    Within each case, remove the linear trend in step index and the level.

    Centring as well as detrending matters: pooling detrended-but-uncentred
    residuals across cases lets a case that simply runs fuller than another
    contribute to the score, which is a between-case difference and not the
    thing being asked about. What is left is variation around the case's own
    trend line, which is the only part that could be board information.

    This removes a LINEAR trend only. A feature whose true dependence on
    step index is curved keeps some of the clock, so a surviving residual is
    an upper bound on the real signal, never a proof of it.
    """
    out = np.array(values, dtype=np.float64)
    for name in sorted(set(group.tolist())):
        mask = group == name
        if mask.sum() < 3:
            continue
        x = step[mask].astype(np.float64)
        y = out[mask]
        if x.std() < 1e-12:
            out[mask] = y - y.mean()
            continue
        slope = np.cov(x, y, bias=True)[0, 1] / np.var(x)
        out[mask] = y - y.mean() - slope * (x - x.mean())
    return out


def within_step_auc(values, labels, step, group):
    """
    Concordance over pairs that share a step index inside a case.

    This is the contrast the corpus was never built for -- most steps carry
    a single row -- so the pair count is reported alongside, and a small
    count means the number is not evidence.
    """
    concordant = 0.0
    total = 0
    buckets = collections.defaultdict(list)
    for index, (s, g) in enumerate(zip(step.tolist(), group.tolist())):
        buckets[(g, s)].append(index)
    for members in buckets.values():
        if len(members) < 2:
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if labels[a] == labels[b]:
                    continue
                high, low = (a, b) if labels[a] > labels[b] else (b, a)
                total += 1
                if values[high] > values[low]:
                    concordant += 1.0
                elif values[high] == values[low]:
                    concordant += 0.5
    return (concordant / total if total else float("nan")), total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.rows.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        print("no rows", file=sys.stderr)
        return 1

    labels = np.array([r["y"] for r in rows], dtype=np.float64)
    step = np.array([r["step"] for r in rows], dtype=np.float64)
    group = np.array([r["case"] for r in rows])
    names = sorted(rows[0]["f"].keys())

    step_auc, _ = auc(step, labels)
    print(f"{len(rows)} rows, {int(labels.sum())} positives, "
          f"{len(set(group.tolist()))} cases")
    print(f"step index on its own: AUC {step_auc:.3f}  <- the confound\n")
    print(f'{"feature":24s} {"raw":>7s} {"residual":>9s} {"within":>7s} {"pairs":>7s}')

    report = {"rows": len(rows), "step_auc": step_auc, "features": {}}
    scored = []
    for name in names:
        values = np.array([r["f"][name] for r in rows], dtype=np.float64)
        raw, _ = auc(values, labels)
        residual, _ = auc(residualise(values, step, group), labels)
        within, pairs = within_step_auc(values, labels, step, group)
        scored.append((abs(raw - 0.5), name, raw, residual, within, pairs))
        report["features"][name] = {
            "raw": raw,
            "residual": residual,
            "within_step": within,
            "within_step_pairs": pairs,
        }
    for _key, name, raw, residual, within, pairs in sorted(scored, reverse=True):
        within_text = "-" if within != within else f"{within:.3f}"
        print(
            f"{name:24s} {raw:7.3f} {residual:9.3f} {within_text:>7s} {pairs:7d}"
        )

    print(
        "\nresidual near 0.5 means the feature was reporting the clock. "
        "within-step is the confound-free contrast, and is only evidence "
        "where the pair count is large -- this corpus records one row per "
        "step, so it usually is not."
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
