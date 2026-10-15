"""why.py <record> <scene> [t ...] -- decision archaeology at the sealing steps.

For every patch of the scene's trace (and any extra steps given), the agent is
probed on the recorded board before the sealing placement (branch.probe_state,
instrumented), and the log is reduced to:
  - the stage that produced the action and the item;
  - for every ladder decision of the call: the rungs tried in order with their
    top candidates (key, depth, top, the agent's sealed_added / stranded_added /
    terrain_behind), whether each candidate seals the patch (exact sweep), and
    the first candidate in the ladder's order that does not;
  - every emitted pose with the shadow verdict and the shade (shade_area);
  - whether the agent's pick matches the record.
Writes $SCRATCH/why/<record>/<scene>.json and prints a digest.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import branch as B  # noqa: E402
import sealkit as K  # noqa: E402
from rule_alpha._reuse import AABB  # noqa: E402

SCRATCH = os.environ.get("SCRATCH", "/home/user/inv-G-scratch")


def box_of(c):
    return AABB(tuple(c["centre"]), tuple(c["size"]), "c")


def digest(out, prots, ep, t):
    d = dict(
        t=t,
        seconds=out["seconds"],
        declined=out["declined"],
        action=out.get("action"),
        stages=[],
        ladders=[],
        emits=[],
    )
    for e in out["log"]:
        if e["ev"] == "stage-in":
            d["stages"].append(e["stage"])
        elif e["ev"] == "emit":
            b = box_of(e)
            d["emits"].append(
                dict(
                    arch=e["arch"],
                    centre=e["centre"],
                    size=e["size"],
                    ci=e["ci"],
                    accepted=e["accepted"],
                    outcome=(e.get("shadow") or {}).get("outcome"),
                    shade=((e.get("shadow") or {}).get("chosen") or {}).get("shade"),
                    seals={n: p.left_open(b, e["ci"], t) for n, p in prots.items()},
                )
            )
        elif e["ev"] == "ladder" and e["decision"]:
            dec = e["decision"]
            rungs = []
            first_ok = {}
            rank = 0
            for r in dec["rungs"]:
                tops = []
                for c in r["top"]:
                    rank += 1
                    s = {n: p.left_open(box_of(c), c["ci"], t) for n, p in prots.items()}
                    for n, v in s.items():
                        if (v[0] == 0 or v[1] > 0) and n not in first_ok:
                            first_ok[n] = dict(
                                rank=rank,
                                rung=r["name"],
                                centre=c["centre"],
                                size=c["size"],
                            )
                    tops.append(dict(c, seals=s))
                rungs.append(dict(name=r["name"], n=r["n"], top=tops))
            d["ladders"].append(
                dict(
                    item=e["item"],
                    archetype=dec["archetype"],
                    considered=dec["considered"],
                    n_survivors=dec["n_survivors"],
                    veto_counts=dec["veto_counts"],
                    ladder=dec["ladder"],
                    rungs=rungs,
                    first_nonsealing=first_ok,
                    chosen=dec.get("chosen"),
                )
            )
    return d


def main():
    rec_name, scene = sys.argv[1], sys.argv[2]
    extra = [int(x) for x in sys.argv[3:]]
    rec = K.load_record(rec_name, scene)
    ep = K.Episode(rec)
    tr = json.load(open(os.path.join(SCRATCH, "trace", rec_name, scene + ".json")))
    prots = {n: B.Protected(ep, p) for n, p in enumerate(tr["patches"])}
    steps = {}
    for n, p in enumerate(tr["patches"]):
        t = (
            p.get("seal_t")
            if p["kind"] == "sealed-after-open"
            else p.get("last_blocker_t")
        )
        if t is not None:
            steps.setdefault(int(t), []).append(n)
    for t in extra:
        steps.setdefault(t, [])
    res = []
    for t in sorted(steps):
        st = B.state_at(ep, t, rec)
        out, _a, _d = B.probe_state(st)
        dg = digest(out, prots, ep, t)
        dg["patches_sealed_here"] = steps[t]
        p = ep.placements[t] if t < len(ep.placements) else None
        if p is not None:
            dg["record"] = dict(
                item=p["item"]["index"],
                arch=str(p["step"].get("archetype")),
                ci=p["ci"],
                centre=[round(v, 3) for v in p["step"]["pos_local"]],
                size=p["dims"],
                shadow=p["step"].get("shadow"),
                policy_s=p["step"].get("policy_seconds"),
            )
            a = out.get("action") or {}
            dg["same"] = (
                bool(a)
                and a.get("item") == dg["record"]["item"]
                and a.get("ci") == p["ci"]
                and max(
                    abs(u - v)
                    for u, v in zip(a.get("centre", [9, 9, 9]), dg["record"]["centre"])
                )
                < 0.03
            )
        res.append(dg)
        a = dg.get("action") or {}
        lad = dg["ladders"][0] if dg["ladders"] else None
        print(
            f"{scene} t{t} patches {steps[t]}: agent {a.get('arch')} {a.get('centre')} {a.get('size')} same={dg.get('same')} "
            f"stages {dg['stages']} | ladder: "
            + (
                f"{lad['archetype']} surv {lad['n_survivors']} vetoes {lad['veto_counts']} first-nonsealing {lad['first_nonsealing']}"
                if lad
                else "-"
            ),
            flush=True,
        )
    od = os.path.join(SCRATCH, "why", rec_name)
    os.makedirs(od, exist_ok=True)
    json.dump(res, open(os.path.join(od, scene + ".json"), "w"), default=str, indent=1)


if __name__ == "__main__":
    main()
