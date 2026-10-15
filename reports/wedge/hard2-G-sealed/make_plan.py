"""make_plan.py <out.json> <record>:<scene> [...] -- the counterfactual plan for G episodes:
baseline repeats, a k=2 scan from the end back to the earliest sealing step, and at
every sealing step the ladder ranks 2-4, the next distinct poses 3-4, the first
non-sealing pose (one-shot and persistent), the patch filled, and on B the item
deferred."""

from __future__ import annotations

import json
import os
import sys

SCRATCH = os.environ.get("SCRATCH", "/home/user/inv-G-scratch")


def seal_steps(tr):
    out = []
    for n, p in enumerate(tr["patches"]):
        t = (
            p.get("seal_t")
            if p["kind"] == "sealed-after-open"
            else p.get("last_blocker_t")
        )
        if t is not None:
            out.append((n, int(t), p))
    return out


def plan_for(record, scene, scan=True):
    tr = json.load(open(os.path.join(SCRATCH, "trace", record, scene + ".json")))
    T = tr["T"]
    ss = seal_steps(tr)
    jobs = []
    base = dict(record=record, scene=scene)
    first = min([t for _n, t, _p in ss] + [max(0, T - 3)])
    for t in sorted({max(0, T - 3)} | {t for _n, t, _p in ss}):
        for rep in range(2):
            jobs.append(dict(base, t=t, mode="agent", rep=rep))
    if scan:
        for t in range(T - 1, max(-1, first - 2), -1):
            jobs.append(dict(base, t=t, mode="alt", k=2))
    for n, t, p in ss:
        for k in (2, 3, 4):
            jobs.append(dict(base, t=t, mode="kth", k=k))
        for k in (3, 4):
            jobs.append(dict(base, t=t, mode="alt", k=k))
        jobs.append(dict(base, t=t, mode="noseal", patch=n))
        jobs.append(dict(base, t=t, mode="noseal", patch=n, persistent=True))
        jobs.append(dict(base, t=t, mode="alt-noseal", k=6, patch=n))
        jobs.append(dict(base, t=t, mode="fill", patch=n))
        if (
            p["kind"] == "sealed-after-open"
            and p.get("open_from") is not None
            and p["open_from"] < t
        ):
            mid = (p["open_from"] + t) // 2
            jobs.append(dict(base, t=mid, mode="fill", patch=n))
            jobs.append(dict(base, t=mid, mode="noseal", patch=n, persistent=True))
        if tr["task"] == "B" and p.get("sealer"):
            jobs.append(dict(base, t=t, mode="defer", defer_item=p["sealer"]["item"]))
    return jobs


def main():
    out = sys.argv[1]
    jobs = []
    for arg in sys.argv[2:]:
        scan = not arg.endswith("!noscan")
        arg = arg.replace("!noscan", "")
        record, scene = arg.split(":")
        jobs += plan_for(record, scene, scan)
    json.dump(jobs, open(out, "w"), indent=0)
    print(len(jobs), "jobs")


if __name__ == "__main__":
    main()
