"""arch_stats.py: the decision archaeology over every reference run (ref.py).

For every step of every H reference run: which stage placed the item (ladder
rung, shadow alternative, stack option, last resort relaxed / any container,
physics resort, count mode, grid rescue), whether the ladder's own best pose
was refused by the gate's shade veto (its shade > 0.15 m^2 in the trace) or
by the shadow, whether the strict ladder had any candidate at all, the pose
(floor lying / floor standing / raised), and the usable floor it covered and
killed (free floor lost = covered; usable lost - covered = killed).

Writes arch_stats.md: totals by stage, the floor-killing steps, and for every
episode the chain of the steps that took the usable floor down to zero."""

from __future__ import annotations

import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from arch_report import stage_of  # noqa: E402
from strips import cls_of  # noqa: E402

REF = "/home/user/inv-H-scratch/ref"
SHADE = 0.15


def stage(a):
    if a is None:
        return "DECLINE"
    s = stage_of(a)
    arch = a["arch"]
    if s.startswith("LR-relaxed"):
        return "last-resort relaxed: " + arch
    if s.startswith("LR-any"):
        return "last-resort any-container: " + arch
    if s.startswith("shadow-alt"):
        return "ladder, shadow alternative: " + arch
    if arch in (
        "physics-resort",
        "count-mode",
        "grid-rescue",
        "grid-rescue-cover",
        "stack-rl",
        "pocket-soft",
        "pocket-hard",
    ):
        return arch
    if a.get("shadow") == "fallback-after-veto":
        return "fallback-after-veto: " + arch
    return "ladder: " + arch


def coarse(st):
    if st.startswith("ladder: "):
        return "ladder"
    if st.startswith("ladder, shadow"):
        return "ladder (shadow alternative)"
    if st.startswith("last-resort"):
        return "last resort (relaxed margins)"
    return st.split(":")[0]


def pose(a):
    if a is None or a["pos_local"] is None:
        return "-"
    sz, c = a["size"], a["pos_local"]
    bottom = c[2] - sz[2] / 2.0
    if bottom > 0.04 + 0.10:
        return "raised"
    return (
        "floor-standing"
        if (sz[2] > min(sz[0], sz[1]) + 1e-6 and sz[2] > 0.3)
        else "floor-lying"
    )


def ladder_pick_refusal(x):
    """Why the strict ladder's own best pose was not played: 'no-ladder',
    'shade' (its shade > 0.15 in the trace or the dump), 'shadow-hard',
    'shadow-soft', or 'played'."""
    lad = x["ladder"]
    if lad.get("none"):
        return "no-ladder"
    best = None
    for r in lad.get("rung_detail") or []:
        if r["rung"] == lad.get("chosen_rung") and r["top"]:
            best = r["top"][0]
    a = x["agent"]
    if (
        a is not None
        and best is not None
        and a["pos_local"] is not None
        and stage(a).startswith("ladder: ")
    ):
        return "played"
    if best is None:
        return "unknown"
    if (best.get("shade") or 0.0) > SHADE:
        return "shade"
    v = best.get("verdict") or {}
    if v.get("hard"):
        return "shadow-hard"
    if v and not v.get("ok"):
        return "shadow-soft"
    return "other (passed shade and shadow)"


def main():
    files = sorted(glob.glob(f"{REF}/ref-*.json"))
    totals = collections.defaultdict(lambda: collections.Counter())
    killers = []
    chains = []
    refusals = collections.Counter()
    hset = {h["scene"] for h in json.load(open(f"{HERE}/hlist.json"))}
    gone_rows = collections.defaultdict(list)
    shade_kill = collections.defaultdict(lambda: [0, 0.0])
    for f in files:
        d = json.load(open(f))
        grp = "H" if d["scene"] in hset else "X"
        dumps = d["dumps"]
        uf = [sum(c["usable"] for c in x["floor_before"]) for x in dumps]
        fr = [sum(c["free"] for c in x["floor_before"]) for x in dumps]
        gone = next(
            (i for i in range(len(uf) - 1) if all(u < 0.26 for u in uf[i + 1 :])), None
        )
        chain = []
        for i, x in enumerate(dumps[:-1]):
            a = x["agent"]
            if a is None:
                continue
            covered = max(0.0, fr[i] - fr[i + 1])
            lost = max(0.0, uf[i] - uf[i + 1])
            killed = max(0.0, lost - covered)
            st = stage(a)
            cs = coarse(st)
            pz = pose(a)
            it = x["pool"][a["pool_index"]]
            ref = ladder_pick_refusal(x)
            totals[(grp, cs)]["n"] += 1
            totals[(grp, cs)]["killed"] += killed
            totals[(grp, cs)]["covered"] += covered
            totals[(grp, cs)][pz] += 1
            if pz.startswith("floor"):
                refusals[(grp, ref, cs)] += 1
                shade_kill[(grp, "shade-vetoed pick" if ref == "shade" else ("no ladder pose" if ref == "no-ladder" else "ladder pick played or other"))][0] += 1
                shade_kill[(grp, "shade-vetoed pick" if ref == "shade" else ("no ladder pose" if ref == "no-ladder" else "ladder pick played or other"))][1] += killed
            if gone is not None and i == gone:
                gone_rows[grp].append((d["scene"], d["margin"], d["end"], i, len(dumps) - 1, cls_of(it), st, pz, ref, round(lost, 2), round(killed, 2)))
            if grp == "X":
                continue
            if killed >= 0.1:
                killers.append(
                    (
                        d["scene"],
                        i,
                        st,
                        pz,
                        cls_of(it),
                        round(killed, 2),
                        round(covered, 2),
                        ref,
                    )
                )
            if gone is not None and i <= gone and lost > 0.05 and i >= gone - 6:
                chain.append(
                    f"{i}: {cls_of(it)} {st} [{pz}] lost {lost:.2f} (killed {killed:.2f}); ladder pick: {ref}"
                )
        if grp == "X":
            continue
        chains.append(
            (
                d["scene"],
                d["placed"],
                d["thr"],
                d["margin"],
                gone,
                len(dumps) - 1,
                chain,
            )
        )
    L = [
        "# Decision archaeology over the H reference runs",
        "",
        f"Generated by `arch_stats.py` from {len(files)} reference runs (`ref.py`: the v50 arm with deterministic budgets, "
        "C from `gate0det-hard2`'s arm, B from `gate0-hard2-b`'s).  \"lost\" = usable floor lost by the step; "
        '"covered" = free floor the box covers; "killed" = lost - covered (usable floor turned into strips).',
        "",
        "## 1. Placements by stage",
        "",
        "Group H = the 21 H scenes; X = the crossing scenes run for contrast (same arm).",
        "",
        "| group | stage | placements | floor lying / standing / raised | usable floor covered | usable floor killed | killed per placement | killed per floor placement |",
        "|---|---|---:|---|---:|---:|---:|---:|",
    ]
    for (grp, cs), c in sorted(totals.items(), key=lambda kv: (kv[0][0], -kv[1]["killed"])):
        L.append(
            f"| {grp} | {cs} | {c['n']} | {c['floor-lying']} / {c['floor-standing']} / {c['raised']} | {c['covered']:.2f} | {c['killed']:.2f} | {c['killed'] / max(1, c['n']):.3f} | {c['killed'] / max(1, c['floor-lying'] + c['floor-standing']):.3f} |"
        )
    L += [
        "",
        "## 2. Floor placements: what happened to the strict ladder's own best pose",
        "",
        "| group | ladder pick | placed by | floor placements |",
        "|---|---|---|---:|",
    ]
    for (grp, r, cs), n in sorted(refusals.items(), key=lambda kv: (kv[0][0], -kv[1])):
        L.append(f"| {grp} | {r} | {cs} | {n} |")
    L += ["", "## 2a. Floor placements by what happened to the ladder's pick: count, usable floor killed, per placement", "",
          "| group | path | floor placements | killed m^2 | killed per placement |", "|---|---|---:|---:|---:|"]
    for (grp, path), (nn, kk) in sorted(shade_kill.items()):
        L.append(f"| {grp} | {path} | {nn} | {kk:.2f} | {kk / max(1, nn):.3f} |")
    L += ["", "## 2b. The step that takes the last usable floor (\"floor gone\"), H against the crossings run for contrast", "",
          "| group | scene | ref margin | end | step / of | item | stage | pose | ladder pick | lost | killed |",
          "|---|---|---:|---|---|---|---|---|---|---:|---:|"]
    for grp in ("H", "X"):
        for r in gone_rows[grp]:
            L.append(f"| {grp} | {r[0]} | {r[1]:+d} | {r[2]} | {r[3]} / {r[4]} | {r[5]} | {r[6]} | {r[7]} | {r[8]} | {r[9]} | {r[10]} |")
        c = collections.Counter(coarse(r[6]) for r in gone_rows[grp])
        L.append(f"| {grp} | **by stage** | | | | | " + ", ".join(f"{k} {v}" for k, v in c.most_common()) + " | | | | |")
    L += [
        "",
        "## 3. Every step that killed >= 0.10 m^2 of usable floor",
        "",
        "| scene | step | stage | pose | item | killed | covered | ladder pick |",
        "|---|---:|---|---|---|---:|---:|---|",
    ]
    for k in sorted(killers, key=lambda t: -t[5]):
        L.append("| " + " | ".join(str(v) for v in k) + " |")
    L += [
        "",
        '## 4. The run-down of the usable floor, per episode (the steps that lost > 0.05 m^2 in the 6 placements up to "floor gone")',
        "",
    ]
    for sc, placed, thr, mg, gone, n, chain in chains:
        L.append(
            f"- **{sc}** placed {placed} (thr {thr}, {mg:+d}); floor gone at step {gone} of {n}:"
        )
        for c in chain:
            L.append(f"  - {c}")
    open(f"{HERE}/arch_stats.md", "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
