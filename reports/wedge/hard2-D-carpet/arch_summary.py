"""arch_summary.py: the "why" of every soft placement, from archaeology.py's probes.

For every probed step whose item is soft, the reason chain:
  * route: 'strict' (the ladder placed it under its own margins), 'last-resort' (the
    strict ladder had nothing -- on a priority container a soft item is barred
    until the last resort's relaxed stage), 'stack' (the stack option), 'rescue'
    (physics resort / grid rescue), 'shelf' when it went to a shelf;
  * where the agent's (deterministic) probe put it and where the record put it
    (they differ where the record's clock cut a stage, or where settle drift moved
    the board);
  * for a floor pose: did the pocket guard run; were there soft-top poses under the
    shipped cap (and without it); the guard's slots for the ladder's floor pose and
    for its best soft-top pose; whether the margin (0.25) is what kept the floor pose.
Output: data/arch_<scene>.<rec>.json (compact rows) and a summary on stdout.
"""

import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ARCH = "/home/user/inv-D-scratch/arch"


def where(fin):
    if not fin:
        return None
    on = fin.get("on") or ""
    if on == "floor":
        return "floor"
    if on == "shelf" or fin.get("surface") == "shelf":
        return "shelf"
    if on == "soft":
        return "soft"
    if "soft" in on:
        return "soft+" + on
    return on


def route(log):
    st = [s[0] for s in log["stages"]]
    ok = [s[0] for s in log["stages"] if s[2]]
    fin = log.get("final") or {}
    rung = fin.get("rung") or ""
    if rung in ("physics-resort", "count-mode", "grid-rescue", "grid-rescue-cover"):
        return "rescue"
    if "_last_resort" in ok:
        return "last-resort"
    if rung == "stack-rl":
        return "stack"
    if st and st[0] == "ladder" and log["stages"][0][2]:
        return "strict"
    return rung or "none"


def why_floor(log, it_census):
    p = log.get("pocket") or {}
    cen = it_census or {}
    capped = sum(
        v
        for k, v in (cen.get("capped") or {}).get("counts", {}).items()
        if k.startswith("soft")
    )
    uncapped = sum(
        v
        for k, v in (cen.get("uncapped") or {}).get("counts", {}).items()
        if k.startswith("soft")
    )
    capped_full = sum(
        v
        for k, v in (cen.get("capped") or {}).get("counts", {}).items()
        if k == "soft/full"
    )
    row = {
        "soft_tops_capped": capped,
        "soft_tops_capped_full": capped_full,
        "soft_tops_uncapped": uncapped,
    }
    if not p:
        row["reason"] = "guard-not-asked"
    elif p.get("stood_down"):
        row["reason"] = "guard-stood-down"
        row["guard_seen"] = p.get("seen")
        row["guard_remaining"] = p.get("remaining")
    elif "chosen_slots" in p:
        bs = p.get("best_soft")
        row.update(
            chosen_slots=p["chosen_slots"],
            best=(p.get("best") or [{}])[0].get("slots"),
            best_on=(p.get("best") or [{}])[0].get("on"),
            best_soft=None if not bs else bs["slots"],
            real_override=p.get("real_override"),
        )
        if p.get("real_override"):
            row["reason"] = (
                "guard-moved-it-on-the-floor"
                if (p.get("real_pick") or {}).get("on") == "floor"
                else "guard-override"
            )
        elif bs is None:
            row["reason"] = "no-soft-top(capped)" if uncapped else "no-soft-top(any)"
        elif bs["slots"] <= p["chosen_slots"] + p.get("margin", 0.25):
            row["reason"] = (
                "soft-top-within-margin"
                if bs["slots"] > p["chosen_slots"]
                else "soft-top-not-better"
            )
        else:
            row["reason"] = "other"
    else:
        row["reason"] = "guard-error"
    return row


def summarise(path):
    rows = []
    for line in open(path):
        log = json.loads(line)
        if log.get("replay_failed"):
            continue
        pool = log.get("pool") or []
        rec = log.get("record") or {}
        idx = rec.get("item_index")
        it = next((p for p in pool if p["index"] == idx), pool[0] if pool else None)
        if it is None:
            continue
        fin = log.get("final") or {}
        cen = next((c for c in (log.get("soft_tops") or []) if c["item"] == idx), None)
        row = {
            "step": log["step"],
            "item": idx,
            "soft": it["soft"],
            "prio": it["prio"],
            "dims": it["dims"],
            "rec_rung": rec.get("archetype"),
            "rec_surface": rec.get("surface"),
            "agent_rung": fin.get("rung"),
            "agent_where": where(fin),
            "agent_bottom": fin.get("bottom"),
            "agent_item": (log.get("action") or {}).get("item_idx"),
            "route": route(log),
            "sec": log.get("sec"),
            "rec_sec": rec.get("policy_seconds"),
            "stages": [s[0] + ("+" if s[2] else "-") for s in log["stages"]],
        }
        if it["soft"] and where(fin) == "floor":
            row.update(why_floor(log, cen))
            if row["route"] == "rescue":
                # the guard ran in an earlier stage; its pick (or the ladder's pose) did not survive
                row["reason"] = "rescue-floor (" + row["reason"] + ")"

        elif it["soft"] and cen:
            row["soft_tops_capped"] = sum(
                v for k, v in cen["capped"]["counts"].items() if k.startswith("soft")
            )
            row["soft_tops_uncapped"] = sum(
                v for k, v in cen["uncapped"]["counts"].items() if k.startswith("soft")
            )
        rows.append(row)
    return rows


def main():
    files = sorted(glob.glob(os.path.join(ARCH, "*.jsonl")))
    if len(sys.argv) > 1:
        files = [f for f in files if any(a in f for a in sys.argv[1:])]
    total = collections.Counter()
    for f in files:
        name = os.path.basename(f)[:-6]
        rows = summarise(f)
        json.dump(
            rows, open(os.path.join(HERE, "data", f"arch_{name}.json"), "w"), indent=0
        )
        soft = [r for r in rows if r["soft"] and r["agent_where"]]
        c = collections.Counter((r["route"], r["agent_where"]) for r in soft)
        reasons = collections.Counter(
            r.get("reason") for r in soft if r["agent_where"] == "floor"
        )
        agree = sum(1 for r in rows if r["agent_rung"] == r["rec_rung"])
        print(
            f"{name}: {len(rows)} probes, agent==record rung {agree}; soft by route/where {dict(c)}; floor reasons {dict(reasons)}"
        )
        for k, v in reasons.items():
            total[k] += v
    print("all floor reasons", dict(total))


if __name__ == "__main__":
    main()
