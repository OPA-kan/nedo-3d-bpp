"""gate_learn.py <record_dir>...: can a gate be learned?  Per step of every baseline episode: the usable
surface ratio (0.40x0.55x0.24 window), the free floor share, the placed count, the step share; label =
the episode ends under the count threshold.  Logistic, leave-scenes-out; what a gate at tau opens on."""
import json, glob, sys, collections
import numpy as np
sys.path.insert(0, '.')
from bench.scenes import make_scene
from rule_alpha import layer1, classify as cls
from rule_alpha.surface import _Load
from rule_alpha._reuse import AABB
from rule_alpha.config import DEFAULT_CONFIG
rows = []
for d in sys.argv[1:]:
    for f in sorted(glob.glob(d + "/[bc]-*.json")):
        r = json.load(open(f)); m = r["metrics"]; sp = r["scene_spec"]
        sc = make_scene(sp["seed"], sp.get("layout") or "c1", sp["task"]); thr = m["total_items"] // 2 + 1
        label = 1 if m["placed_count"] < thr else 0
        steps = [s for s in r["steps"] if s.get("event") == "step" and "pos_local" in s]
        board = layer1.Board(sc.rule_alpha_containers(), DEFAULT_CONFIG)
        items = {int(i["index"]): i for i in sc.items}
        loads = {ci: _Load(board.model(ci), 0.04) for ci in range(len(sc.containers))}
        floor_cells = {ci: float(loads[ci].floor.sum()) for ci in loads}
        for k, s in enumerate(steps):
            ci = int(s["container_idx"]); box = AABB(tuple(s["pos_local"]), tuple(s["size"]), "p")
            loads[ci].add(box, bool(items[int(s["item_index"])]["is_soft"]))
            if k % 3 != 2:   # every third step
                continue
            usable = max(float(loads[c].usable((0.40, 0.55), 0.24, None, 1).sum()) / floor_cells[c] for c in loads)
            free = float(np.mean([1.0 - float(np.any([mk for mk, _b, _t, _s in loads[c].boxes], axis=0).sum()) / floor_cells[c] if loads[c].boxes else 1.0 for c in loads]))
            rows.append(dict(scene=r["scene"], suite=d.split("/")[-1], step=k + 1, placed=k + 1, n_ctr=len(sc.containers),
                             usable=usable, free=free, per_ctr=(k + 1) / len(sc.containers), label=label, margin=m["placed_count"] - thr, final=m["placed_count"]))
print(f"{len(rows)} states from {len({r['scene'] for r in rows})} episodes; under-threshold episodes {sum(1 for s in {r['scene']: r['label'] for r in rows}.values() if s)}")
X = np.array([[r["usable"], r["free"], r["per_ctr"] / 41.0, r["n_ctr"]] for r in rows]); y = np.array([r["label"] for r in rows], float)
scenes = sorted({r["scene"] for r in rows}); fold = np.array([scenes.index(r["scene"]) % 5 for r in rows])
def fit(X, y, l2=1.0, iters=400, lr=0.2):
    mu, sd = X.mean(0), X.std(0) + 1e-9; Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))]); w = np.zeros(Z.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Z @ w)); w -= lr * (Z.T @ (p - y) / len(y) + l2 * np.r_[w[:-1], 0] / len(y))
    return mu, sd, w
def predict(mdl, X):
    mu, sd, w = mdl; return 1 / (1 + np.exp(-np.hstack([(X - mu) / sd, np.ones((len(X), 1))]) @ w))
def auc(y, s):
    o = np.argsort(s); rk = np.empty(len(s)); rk[o] = np.arange(1, len(s) + 1); pos = y == 1
    return float((rk[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum()))
probs = np.zeros(len(rows))
for f in range(5):
    tr, te = fold != f, fold == f; probs[te] = predict(fit(X[tr], y[tr]), X[te])
print(f"leave-scenes-out AUC {auc(y, probs):.3f} (base rate {y.mean():.2f}); weights {fit(X, y)[2][:-1].round(2)} for usable, free, placed/41, containers")
# the gate at tau: the share of steps it opens, by suite and by the episode's fate; and when it first opens
for tau in (0.5, 0.6, 0.7):
    by = collections.defaultdict(lambda: [0, 0]); first = collections.defaultdict(list)
    for r, p in zip(rows, probs):
        key = (r["suite"], "under" if r["label"] else "crossed"); by[key][1] += 1; by[key][0] += int(p > tau)
    opened = collections.defaultdict(lambda: None)
    for r, p in zip(rows, probs):
        if p > tau and opened[r["scene"]] is None: opened[r["scene"]] = r["step"] / max(r["final"], 1)
    eps = collections.Counter(r["suite"] for r in {x["scene"]: x for x in rows}.values())
    print(f"tau {tau}: open share " + ", ".join(f"{k[0]}/{k[1]} {v[0]/v[1]:.2f}" for k, v in sorted(by.items())) + "; episodes ever open: " + ", ".join(f"{s} {sum(1 for sc, v in opened.items() if v is not None and sc.startswith(s[0]))}/{n}" for s, n in eps.items()) + f"; first open at {np.mean([v for v in opened.values() if v is not None]):.2f} of the episode")
# the hand gate for comparison: usable < 0.2
by = collections.defaultdict(lambda: [0, 0])
for r in rows:
    key = (r["suite"], "under" if r["label"] else "crossed"); by[key][1] += 1; by[key][0] += int(r["usable"] < 0.2)
print("hand gate (usable < 0.2) open share: " + ", ".join(f"{k[0]}/{k[1]} {v[0]/v[1]:.2f}" for k, v in sorted(by.items())))
