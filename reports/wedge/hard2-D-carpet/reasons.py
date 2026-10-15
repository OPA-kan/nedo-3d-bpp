"""reasons.py: why each floor-bound soft box went to the floor (counts).

Input: the archaeology probes (/home/user/inv-D-scratch/arch/*.jsonl, the record's
board at every step, the deterministic agent's answer and the pocket guard's full
ranking).  Unit: a soft item the RECORD put on the floor (bottom < 0.10 m).

Primary reason, first rule that fires:
  1 time-cut          the deterministic agent, on the same board, puts it on a soft top
                      (or the shelf): the record's clock cut a stage (the guard's 0.8 s)
  2 rescue-floor      the deterministic agent also floors it, through a rescue stage
                      (its guard / ladder poses were vetoed by the shadow world)
  3 guard-stood-down  the guard expected no hard class any more (41 items a container)
  4 no-soft-top       no soft-top pose with >= 0.6 support in the guard's set:
                       4a cap: poses exist once the 0.7 m cap is lifted
                       4b none: none even without the cap (no column yet / shelf / headroom)
  5 cross-container   a soft top existed, the guard took a floor pose in another
                      container (absolute per-container slots, pocket.py:212-214)
  6 tie-lower-pose    a soft top existed in the same container with equal slots; the
                      tie goes to the lower pose (the floor), pocket.py:214
  7 margin            a soft top scored better but within the 0.25 margin
  8 floor-better      the guard's scorer rated the floor pose higher
Flag (not exclusive): prio-ctr: the item is a plain soft box in a priority container,
barred from the strict ladder and the stack option (layer1.routing_order), placed by
the last resort's relaxed stage.
"""

import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import D_V50, load_record, scene_of  # noqa: E402


def classify(log, rec_row, prio_ctr):
    fin = log.get("final") or {}
    p = log.get("pocket") or {}
    on = fin.get("on") or ""
    if fin and on != "floor":
        return "1 time-cut (det: %s)" % ("soft top" if "soft" in on else on)
    rung = fin.get("rung") or ""
    if rung in ("physics-resort", "count-mode", "grid-rescue", "grid-rescue-cover"):
        return "2 rescue-floor"
    if not p:
        return "9 guard-not-asked"
    if p.get("stood_down"):
        return "3 guard-stood-down"
    cen = next(
        (c for c in (log.get("soft_tops") or []) if c["item"] == rec_row["item_index"]),
        {},
    )
    bs = p.get("best_soft")
    if not bs:
        unc = sum(
            v
            for k, v in (cen.get("uncapped") or {}).get("counts", {}).items()
            if k.startswith("soft/full")
        )
        cap = sum(
            v
            for k, v in (cen.get("capped") or {}).get("counts", {}).items()
            if k.startswith("soft/full")
        )
        if cap:
            return "4c no-soft-top in guard set (legal ones only off its anchors)"
        return "4a no-soft-top: cap" if unc else "4b no-soft-top: none"
    best = (p.get("best") or [{}])[0]
    if (
        p.get("real_override")
        and best.get("on") == "floor"
        and best.get("ci") != bs.get("ci")
    ):
        return "5 cross-container"
    if abs(bs["slots"] - best.get("slots", -1)) < 1e-6 or (
        not p.get("real_override") and abs(bs["slots"] - p["chosen_slots"]) < 1e-6
    ):
        return "6 tie-lower-pose"
    if bs["slots"] > p["chosen_slots"] and bs["slots"] <= p["chosen_slots"] + p.get(
        "margin", 0.25
    ):
        return "7 margin"
    return "8 floor-better"


def main():
    tot = collections.Counter()
    flags = collections.Counter()
    per = {}
    for rec, scenes in D_V50.items():
        for scene in scenes:
            path = f"/home/user/inv-D-scratch/arch/{scene}.{rec}.jsonl"
            if not os.path.exists(path):
                continue
            r = load_record(rec, scene)
            sc = scene_of(r["scene_spec"])
            pc = [bool(c.get("is_prioritized")) for c in sc.containers]
            items = {i["index"]: i for i in sc.items}
            c = collections.Counter()
            for line in open(path):
                log = json.loads(line)
                rr = log.get("record")
                if not rr or log.get("replay_failed") or log.get("substituted"):
                    continue
                it = items[rr["item_index"]]
                if not it["is_soft"]:
                    continue
                bottom = rr["pos_local"][2] - rr["size"][2] / 2.0
                if rr["surface"] != "floor" or bottom > 0.10 + 0.06:
                    continue
                why = classify(log, rr, pc[rr["container_idx"]])
                c[why] += 1
                tot[why] += 1
                if pc[rr["container_idx"]] and not it["is_prioritized"]:
                    flags["prio-ctr"] += 1
                    flags["prio-ctr & " + why.split(" ")[0]] += 1
            per[f"{scene}.{rec}"] = dict(c)
            print(scene, rec, dict(sorted(c.items())))
    print("ALL", dict(sorted(tot.items())), "n", sum(tot.values()))
    print("flags", dict(flags))
    json.dump(
        {"per_episode": per, "all": tot, "flags": flags},
        open(os.path.join(HERE, "data", "reasons.json"), "w"),
        indent=1,
    )


if __name__ == "__main__":
    main()
