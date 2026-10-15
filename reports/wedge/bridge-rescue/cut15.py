"""cut15.py <dir> [<dir> ...]: episodes a 1.5x slower machine would cut.

A placing call over 5.3 s (C, 8 s limit) or 6.7 s (B, 10 s limit) on the
bench would time out at 1.5x; the platform answers with a random action
that fails and ends the episode, so the items placed from that call on
are lost.  Prints the episodes cut, the items lost a scene and the
crossings left."""
import glob
import json
import os
import sys

for d in sys.argv[1:]:
    eps = lost = cross = n = 0
    for f in glob.glob(os.path.join(d, "[bc]-*.json")):
        r = json.load(open(f))
        m = r["metrics"]
        line = 5.3 if r["scene_spec"]["task"] == "C" else 6.7
        thr = m["total_items"] // 2 + 1
        n += 1
        cut = [i for i, s in enumerate(r["steps"]) if s["event"] == "step" and (s.get("policy_seconds") or 0) > line]
        kept = cut[0] if cut else m["placed_count"]
        if cut:
            eps += 1
            lost += m["placed_count"] - kept
        cross += kept >= thr
    print("%-18s episodes cut at 1.5x %2d, items lost a scene %.2f, crossings left %d/%d" % (
        os.path.basename(d.rstrip("/")), eps, lost / n, cross, n))
