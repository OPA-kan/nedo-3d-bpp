"""pref_learn.py <pairs.jsonl>...: can the choice among the ladder's survivors be learned?

Reads the pairs of ``pref_pairs.py`` (an alternative to the ladder's
pick, labelled by the agent's own continuation) and answers, in order:

1. The room: how often some alternative beats the ladder's pick on the
   final count, by how much, and how often it loses a crossing the
   ladder kept -- the ceiling of a selector over the ladder's survivors,
   if it chose perfectly.
2. The proxy: does the pieces reading (the unusable volume a pose makes)
   agree with the outcome?  The sign agreement and the rank correlation
   between d_pieces and d_count.
3. The learnability: a logistic model on the feature differences (alt
   minus ladder: footprint, row waste, the neighbour step, the level
   match, the plateau gain, the open floor, the largest residual
   rectangle, the depth, the bottom, the surface, the pieces, the phase,
   the step) predicting "the alternative places more", fitted on some
   scenes and tested on the others (leave-scenes-out); the accuracy and
   the AUC against the base rate.  A model that beats the base rate
   out of sample on held-out scenes is the evidence that the preference
   is a function of the state the agent can see; one that does not says
   the outcome is decided by what comes after, not by the pose.
"""
import json
import pathlib
import sys

import numpy as np

FEATS = ["footprint", "row_waste", "neighbour_step", "level_match", "plateau_gain", "open_free_area",
         "largest_residual_rect", "y_back", "bottom", "top", "stability_margin"]


def load(paths):
    rows = []
    for p in paths:
        for line in open(p):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def vector(r):
    a, l = r["alt"], r["ladder"]
    x = [float(a.get(f, 0.0)) - float(l.get(f, 0.0)) for f in FEATS]
    x += [1.0 if a["surface"] == "item" else 0.0, 1.0 if l["surface"] == "item" else 0.0,
          float(r["d_pieces"]), float(r["phase"]), float(r["step"]) / 40.0,
          1.0 if a["archetype"] == l["archetype"] else 0.0]
    return np.asarray(x, dtype=float)


def logistic_fit(X, y, l2=1.0, iters=300, lr=0.1):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd
    Z = np.hstack([Z, np.ones((len(Z), 1))])
    w = np.zeros(Z.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-Z @ w))
        g = Z.T @ (p - y) / len(y) + l2 * np.r_[w[:-1], 0.0] / len(y)
        w -= lr * g
    return mu, sd, w


def logistic_predict(model, X):
    mu, sd, w = model
    Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))])
    return 1.0 / (1.0 + np.exp(-Z @ w))


def auc(y, s):
    order = np.argsort(s)
    ranks = np.empty(len(s)); ranks[order] = np.arange(1, len(s) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main():
    rows = load(sys.argv[1:])
    if not rows:
        print("no pairs"); return
    scenes = sorted({r["scene"] for r in rows})
    print(f"{len(rows)} pairs, {len(scenes)} scenes, {len({(r['scene'], r['step']) for r in rows})} decisions")
    # 1. the room
    by_dec = {}
    for r in rows:
        by_dec.setdefault((r["scene"], r["step"]), []).append(r)
    best = np.array([max(x["d_count"] for x in v) for v in by_dec.values()])
    worst = np.array([min(x["d_count"] for x in v) for v in by_dec.values()])
    lost = sum(1 for v in by_dec.values() for x in v if x["crossing_ladder"] and not x["crossing_alt"])
    gained = sum(1 for v in by_dec.values() for x in v if x["crossing_alt"] and not x["crossing_ladder"])
    print(f"the room: an alternative beats the ladder at {np.mean(best > 0):.2f} of the decisions (mean best gain {best[best > 0].mean() if (best > 0).any() else 0:.2f} items), "
          f"ties at {np.mean(best == 0):.2f}, every alternative worse at {np.mean(best < 0):.2f}; mean of the best alternative {best.mean():+.2f}, of the worst {worst.mean():+.2f}; "
          f"alternatives that lose a crossing the ladder kept {lost}, that gain one {gained}, of {len(rows)}")
    d = np.array([r["d_count"] for r in rows])
    print(f"d_count over all pairs: mean {d.mean():+.2f}, sd {d.std():.2f}, >0 {np.mean(d > 0):.2f}, =0 {np.mean(d == 0):.2f}, <0 {np.mean(d < 0):.2f}")
    # per-scene oracle: the best alternative at each decision, summed as if independent (an upper bound)
    per_scene = {}
    for (sc, _st), v in by_dec.items():
        per_scene.setdefault(sc, []).append(max(0, max(x["d_count"] for x in v)))
    print(f"oracle upper bound (sum of the best gains over the branched steps, a scene): mean {np.mean([sum(v) for v in per_scene.values()]):.1f} items")
    # 2. the proxy
    dp = np.array([r["d_pieces"] for r in rows])
    nz = (d != 0) & (np.abs(dp) > 1e-4)
    if nz.any():
        agree = np.mean(np.sign(-dp[nz]) == np.sign(d[nz]))
        from numpy import corrcoef
        rk = lambda a: np.argsort(np.argsort(a))
        rho = corrcoef(rk(-dp[nz]), rk(d[nz]))[0, 1]
        print(f"the proxy (fewer pieces -> more items?): sign agreement {agree:.2f} on {nz.sum()} pairs with both nonzero, rank correlation {rho:+.2f}")
    for name, sel in (("floor alternatives", [r["alt"]["surface"] == "floor" for r in rows]), ("raised alternatives", [r["alt"]["surface"] == "item" for r in rows])):
        sel = np.array(sel)
        if sel.any():
            print(f"  {name}: {sel.sum()} pairs, d_count mean {d[sel].mean():+.2f}, >0 {np.mean(d[sel] > 0):.2f}")
    # 3. learnability: leave-scenes-out
    X = np.stack([vector(r) for r in rows]); y = (d > 0).astype(float)
    base = y.mean()
    folds = 5
    sc_idx = {s: i % folds for i, s in enumerate(scenes)}
    fold = np.array([sc_idx[r["scene"]] for r in rows])
    accs, aucs, probs = [], [], np.zeros(len(rows))
    for f in range(folds):
        tr, te = fold != f, fold == f
        if te.sum() == 0 or tr.sum() == 0:
            continue
        m = logistic_fit(X[tr], y[tr])
        p = logistic_predict(m, X[te]); probs[te] = p
        accs.append(np.mean((p > 0.5) == (y[te] == 1))); aucs.append(auc(y[te], p))
    print(f"learnability (logistic on feature differences, leave-scenes-out {folds} folds): base rate of 'alternative better' {base:.2f}; "
          f"accuracy {np.mean(accs):.2f} (predicting the majority gives {max(base, 1 - base):.2f}), AUC {np.nanmean(aucs):.2f} (0.5 = chance)")
    # what a gated selector would have earned: take the alternative when p > tau
    for tau in (0.5, 0.6, 0.7, 0.8):
        take = probs > tau
        if take.any():
            print(f"  a selector taking the alternative when p > {tau}: {take.sum()} of {len(rows)} pairs taken, mean d_count {d[take].mean():+.2f}, crossings lost {sum(1 for r, t in zip(rows, take) if t and r['crossing_ladder'] and not r['crossing_alt'])}, gained {sum(1 for r, t in zip(rows, take) if t and r['crossing_alt'] and not r['crossing_ladder'])}")
    m = logistic_fit(X, y)
    names = [f"d_{f}" for f in FEATS] + ["alt_raised", "ladder_raised", "d_pieces", "phase", "step", "same_rung"]
    w = m[2][:-1]
    order = np.argsort(-np.abs(w))
    print("weights (standardised):", ", ".join(f"{names[i]} {w[i]:+.2f}" for i in order[:8]))


if __name__ == "__main__":
    main()
