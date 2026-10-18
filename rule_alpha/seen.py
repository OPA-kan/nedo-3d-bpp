"""The classes the stream has shown: one tracker for the "seen" modes.

Tasks B and C run online -- a pool of ten in view on B, one item on C --
and several places in the shipped forms are pinned to the official
sample's SKU mix: the online rows' depth table (``online_row_depths``),
the pocket guard's class frequencies (``pocket_mix``) and the phase
switch's window (``phase_switch_window``).  Each of them has a ``"seen"``
value that reads this tracker instead, with the sample's table as the
fallback until enough hard boxes have been seen.

``SeenClasses.observe`` is called once a policy call from the
observation (``RuleAlphaAgent._policy_inner``): every item in the pool
and every packed item of every container, each counted once by its
index.  So on Task C a class is counted when its item comes into view,
on Task B when it enters the pool, and nothing is counted twice however
long it sits there.
"""

from __future__ import annotations


# the sample's tables, the fallbacks of every "seen" mode
SAMPLE_ROW_DEPTHS = (0.56, 0.45, 0.40)
SAMPLE_WINDOW = "0.40x0.55x0.24"


def class_key(item: dict) -> tuple:
    """A class is its dimensions as the stream gives them, to the millimetre."""
    return (round(float(item["length"]), 3), round(float(item["width"]), 3), round(float(item["height"]), 3))


class SeenClasses:
    def __init__(self):
        self.indices: set[int] = set()
        self.counts: dict[tuple, int] = {}
        self.soft: dict[tuple, bool] = {}
        self.mass: dict[tuple, float] = {}
        self.total = 0
        self.hard_total = 0

    def _add(self, item: dict) -> None:
        try:
            index = int(item["index"])
        except (KeyError, TypeError, ValueError):
            return
        if index in self.indices:
            return
        try:
            key = class_key(item)
        except (KeyError, TypeError, ValueError):
            return
        self.indices.add(index)
        soft = bool(item.get("is_soft", False))
        self.counts[key] = self.counts.get(key, 0) + 1
        self.soft[key] = soft
        self.mass[key] = float(item.get("mass", 0.0) or 0.0)
        self.total += 1
        if not soft:
            self.hard_total += 1

    def observe(self, pool: list, containers: list) -> None:
        """Every item in view (the pool) and every packed item, once each."""
        for item in pool or []:
            self._add(item)
        for container in containers or []:
            for item in container.get("packed_items") or []:
                self._add(item)

    # -- readings ---------------------------------------------------------------
    def hard_classes(self) -> list[tuple[tuple, int]]:
        """The hard classes seen, the most frequent first; among equals the
        smaller footprint first, then the key."""
        return sorted(((k, n) for k, n in self.counts.items() if not self.soft.get(k, False)),
                      key=lambda kn: (-kn[1], _footprint(kn[0]), kn[0]))

    def most_frequent_hard(self, lead: int = 0) -> tuple | None:
        """The most frequent hard class, when it leads the runner-up by at
        least ``lead`` items (0: always); None otherwise."""
        classes = self.hard_classes()
        if not classes:
            return None
        if len(classes) > 1 and classes[0][1] - classes[1][1] < int(lead):
            return None
        return classes[0][0]

    def smallest_hard(self) -> tuple | None:
        classes = self.hard_classes()
        if not classes:
            return None
        return min((k for k, _n in classes), key=lambda k: (_footprint(k), k))

    def row_depth_table(self, min_hard: int, prior=SAMPLE_ROW_DEPTHS) -> list[float]:
        """The row depths of the hard classes seen (each class's flat depth:
        its middle dimension, the box lying on its largest face) together
        with the prior's depths (the sample's three classes: a stream of
        the sample's kind gives exactly the shipped ``0.56,0.45,0.4``
        however few of its classes have shown yet), distinct, the deepest
        first; the prior alone while fewer than ``min_hard`` hard boxes
        have been seen."""
        depths = {round(float(d), 3) for d in prior}
        if self.hard_total >= int(min_hard):
            depths |= {round(sorted(k)[1], 3) for k, _n in self.hard_classes()}
        return sorted(depths, reverse=True)

    def window(self, min_hard: int, mode: str = "seen", fallback: str = SAMPLE_WINDOW, lead: int = 2) -> str:
        """The ``lxwxh`` window of one hard class: the most frequent
        (``mode`` "seen", when it leads the runner-up by ``lead`` items --
        on the sample's streams the A and B classes run neck and neck and
        a lead of 2 keeps the sample's window through their crossings) or
        the smallest by footprint ("seen-smallest"), the box lying flat
        (the smallest dimension the height); the fallback while fewer
        than ``min_hard`` hard boxes have been seen or no class leads."""
        if self.hard_total < int(min_hard):
            return fallback
        key = self.smallest_hard() if mode == "seen-smallest" else self.most_frequent_hard(lead)
        if key is None:
            return fallback
        h, a, b = sorted(key)
        return f"{a:.2f}x{b:.2f}x{h:.2f}"

    def mix(self, prior: dict, prior_weight: float, min_seen: int) -> dict:
        """The stream's mix for a sampler: ``{(l, w, h): (mass, soft,
        weight)}`` -- the prior's classes at ``prior_weight`` pseudo-items
        spread by their weights, plus every seen class by its count once
        ``min_seen`` items have been seen (the prior alone before that;
        ``rule_alpha.foresight`` reads the same way)."""
        prior_total = float(sum(v[2] for v in prior.values())) or 1.0
        mix = {k: (m, soft, float(prior_weight) * float(wt) / prior_total) for k, (m, soft, wt) in prior.items()}
        if self.total < int(min_seen):
            return mix
        for key, n in self.counts.items():
            old = mix.get(key, (self.mass.get(key, 0.0), self.soft.get(key, False), 0.0))
            mix[key] = (old[0], old[1], old[2] + float(n))
        return mix


def _footprint(key: tuple) -> float:
    dims = sorted(key)
    return float(dims[1] * dims[2])
