"""Genetic programming of a priority function for a region.

A policy here is one expression over a candidate's features and a few
state summaries.  Every legal pose gets the expression's value, the best
one is taken, and the item is passed when the best value is below zero.
This is the hyper-heuristic form that has a long record on bin packing and
scheduling: the search space is expressions, the fitness is the region's
own gain on a fixed set of training streams, and the result is a formula
that runs in microseconds and can be read.

Expressions are trees of numpy-vectorised operations evaluated over all
candidates of a step at once.  Terminals are the twelve candidate features
of ``Candidate.features`` (per candidate), five state summaries (broadcast
over candidates) and constants.
"""

from __future__ import annotations

import json
import math
import random
import time

import numpy as np

from .env import FEATURE_SIZE, PASS

CAND_NAMES = ["x", "y", "z", "dx", "dy", "dz", "gain", "support", "margin", "on_base", "top", "reach"]
STATE_NAMES = ["remaining", "h_mean", "h_max", "h_free", "item_vol"]
TERMINALS = CAND_NAMES + STATE_NAMES
BINARY = ["add", "sub", "mul", "div", "min", "max"]
UNARY = ["neg", "sqrt", "sq", "gt0"]


def state_summary(env) -> np.ndarray:
    obs = env.observation()
    h = np.asarray(obs["heightmap"], dtype=np.float32)
    item = np.asarray(obs["item"], dtype=np.float32)
    return np.asarray([obs["remaining"], float(h.mean()), float(h.max()), float((h <= 1e-6).mean()),
                       float(item[0] * item[1] * item[2] / 0.12)], dtype=np.float32)


# --- expression trees --------------------------------------------------------
class Node:
    __slots__ = ("op", "kids", "value")

    def __init__(self, op: str, kids=(), value: float = 0.0):
        self.op = op
        self.kids = list(kids)
        self.value = value

    def __str__(self) -> str:
        if self.op == "const":
            return f"{self.value:.3g}"
        if self.op in TERMINALS:
            return self.op
        if self.op in UNARY:
            return f"{self.op}({self.kids[0]})"
        return f"{self.op}({self.kids[0]}, {self.kids[1]})"

    def size(self) -> int:
        return 1 + sum(k.size() for k in self.kids)

    def depth(self) -> int:
        return 1 + max((k.depth() for k in self.kids), default=0)

    def copy(self) -> "Node":
        return Node(self.op, [k.copy() for k in self.kids], self.value)

    def to_json(self):
        return {"op": self.op, "value": self.value, "kids": [k.to_json() for k in self.kids]}

    @staticmethod
    def from_json(d) -> "Node":
        return Node(d["op"], [Node.from_json(k) for k in d["kids"]], d.get("value", 0.0))


def evaluate(node: Node, feats: np.ndarray, state: np.ndarray) -> np.ndarray:
    """Value of the expression for every candidate row of ``feats``."""
    op = node.op
    if op == "const":
        return np.full(feats.shape[0], node.value, dtype=np.float64)
    if op in CAND_NAMES:
        return feats[:, CAND_NAMES.index(op)].astype(np.float64)
    if op in STATE_NAMES:
        return np.full(feats.shape[0], float(state[STATE_NAMES.index(op)]), dtype=np.float64)
    a = evaluate(node.kids[0], feats, state)
    if op == "neg":
        return -a
    if op == "sqrt":
        return np.sqrt(np.abs(a))
    if op == "sq":
        return np.clip(a * a, -1e6, 1e6)
    if op == "gt0":
        return (a > 0).astype(np.float64)
    b = evaluate(node.kids[1], feats, state)
    if op == "add":
        return a + b
    if op == "sub":
        return a - b
    if op == "mul":
        return np.clip(a * b, -1e6, 1e6)
    if op == "div":
        return np.where(np.abs(b) > 1e-6, a / np.where(np.abs(b) > 1e-6, b, 1.0), 1.0)
    if op == "min":
        return np.minimum(a, b)
    if op == "max":
        return np.maximum(a, b)
    raise KeyError(op)


def random_tree(rng: random.Random, depth: int, full: bool = False) -> Node:
    if depth <= 1 or (not full and rng.random() < 0.3):
        if rng.random() < 0.2:
            return Node("const", value=round(rng.uniform(-2.0, 2.0), 3))
        return Node(rng.choice(TERMINALS))
    if rng.random() < 0.25:
        return Node(rng.choice(UNARY), [random_tree(rng, depth - 1, full)])
    return Node(rng.choice(BINARY), [random_tree(rng, depth - 1, full), random_tree(rng, depth - 1, full)])


def _nodes(node: Node, out=None):
    out = [] if out is None else out
    out.append(node)
    for k in node.kids:
        _nodes(k, out)
    return out


def _replace(root: Node, target: Node, new: Node) -> Node:
    if root is target:
        return new
    return Node(root.op, [_replace(k, target, new) for k in root.kids], root.value)


def crossover(rng: random.Random, a: Node, b: Node, max_depth: int) -> Node:
    ta = rng.choice(_nodes(a))
    tb = rng.choice(_nodes(b))
    child = _replace(a.copy(), ta, tb.copy()) if ta is not a else tb.copy()
    return child if child.depth() <= max_depth else a.copy()


def mutate(rng: random.Random, a: Node, max_depth: int) -> Node:
    target = rng.choice(_nodes(a))
    r = rng.random()
    if target.op == "const" and r < 0.5:
        new = Node("const", value=round(target.value + rng.gauss(0, 0.5), 3))
    elif r < 0.7:
        new = random_tree(rng, rng.randint(1, 3))
    else:
        new = Node(rng.choice(TERMINALS)) if rng.random() < 0.8 else Node("const", value=round(rng.uniform(-2, 2), 3))
    child = _replace(a.copy(), target, new) if target is not a else new
    return child if child.depth() <= max_depth else a.copy()


# --- policies and fitness ----------------------------------------------------
def act(node: Node, env) -> int:
    cands = env.candidates()
    if not cands:
        return PASS
    feats = np.stack([c.features(env) for c in cands])
    scores = evaluate(node, feats, state_summary(env))
    best = int(np.argmax(scores))
    return PASS if scores[best] < 0.0 else best


def policy_of(node: Node):
    return lambda env, _rng=None: act(node, env)


def fitness(node: Node, env, seeds, parsimony: float = 0.0) -> float:
    total = 0.0
    for seed in seeds:
        env.reset(seed)
        while not env.done:
            _o, r, _d, _i = env.step(act(node, env))
            total += r
    return total / len(seeds) - parsimony * node.size()


# --- evolution ---------------------------------------------------------------
_WORKER: dict = {}


def _init(env_factory, seeds):
    _WORKER["env"] = env_factory()
    _WORKER["seeds"] = list(seeds)


def _fit(payload):
    node = Node.from_json(payload["tree"])
    return payload["i"], fitness(node, _WORKER["env"], _WORKER["seeds"], payload["parsimony"])


def evolve(env_factory, train_seeds, generations: int = 40, population: int = 120, seed: int = 0,
           max_depth: int = 6, parsimony: float = 1e-4, workers: int = 1, log=print,
           checkpoint=None, elite: int = 4, tournament: int = 5, crossover_rate: float = 0.7,
           max_minutes: float | None = None) -> dict:
    rng = random.Random(seed)
    started = time.perf_counter()
    pop = [random_tree(rng, rng.randint(2, max_depth), full=rng.random() < 0.5) for _ in range(population)]
    # hand seeds: gain alone (greedy) and gain plus a small on-base bias
    pop[0] = Node("gain")
    pop[1] = Node("add", [Node("gain"), Node("mul", [Node("const", value=0.01), Node("on_base")])])
    pool = None
    if workers > 1:
        import multiprocessing as mp

        pool = mp.get_context("spawn").Pool(workers, initializer=_init, initargs=(env_factory, train_seeds))
    env = env_factory() if pool is None else None
    history = []
    best = (-math.inf, None)
    try:
        for gen in range(generations):
            if max_minutes is not None and (time.perf_counter() - started) / 60.0 > max_minutes:
                if log:
                    log({"stopped": "time budget", "gen": gen})
                break
            t0 = time.perf_counter()
            payloads =[{"i": i, "tree": p.to_json(), "parsimony": parsimony} for i, p in enumerate(pop)]
            if pool is None:
                fits = [fitness(p, env, train_seeds, parsimony) for p in pop]
            else:
                fits = [0.0] * len(pop)
                for i, f in pool.imap_unordered(_fit, payloads):
                    fits[i] = f
            order = sorted(range(len(pop)), key=lambda i: -fits[i])
            if fits[order[0]] > best[0]:
                best = (fits[order[0]], pop[order[0]].copy())
            row = {"gen": gen, "best": fits[order[0]], "mean": float(np.mean(fits)),
                   "size": pop[order[0]].size(), "seconds": round(time.perf_counter() - t0, 1),
                   "expr": str(pop[order[0]])}
            history.append(row)
            if log:
                log(row)
            if checkpoint is not None:
                checkpoint(best[1], history)
            # next generation: elites, then tournament-selected offspring
            nxt = [pop[i].copy() for i in order[:elite]]
            while len(nxt) < population:
                def pick():
                    contenders = [rng.randrange(len(pop)) for _ in range(tournament)]
                    return pop[max(contenders, key=lambda i: fits[i])]
                if rng.random() < crossover_rate:
                    child = crossover(rng, pick(), pick(), max_depth)
                else:
                    child = mutate(rng, pick(), max_depth)
                nxt.append(child)
            pop = nxt
    finally:
        if pool is not None:
            pool.close()
            pool.join()
    return {"best_fitness": best[0], "best": best[1], "history": history}


def save(node: Node, path, extra=None) -> None:
    import pathlib

    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(path).write_text(json.dumps({"expr": str(node), "tree": node.to_json(),
                                              **(extra or {})}, indent=1), encoding="utf-8")


def load(path) -> Node:
    import pathlib

    return Node.from_json(json.loads(pathlib.Path(path).read_text(encoding="utf-8"))["tree"])
