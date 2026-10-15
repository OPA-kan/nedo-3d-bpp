"""fidelity.py <record> <scene> <t> [<t> ...] -- probe the agent on the recorded board
after t placements and compare its pick with the record's placement t.
Writes $SCRATCH/probe/<record>/<scene>-t<t>.json (full instrumentation log)."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import branch as B  # noqa: E402
import sealkit as K  # noqa: E402

SCRATCH = os.environ.get("SCRATCH", "/home/user/inv-G-scratch")


def compare(ep, t, out):
    p = ep.placements[t] if t < len(ep.placements) else None
    rec = None
    if p is not None:
        s = p["step"]
        rec = dict(
            item=p["item"]["index"],
            arch=str(s.get("archetype")),
            ci=p["ci"],
            centre=[round(v, 3) for v in s["pos_local"]],
            size=p["dims"],
        )
    a = out.get("action")
    same = None
    if a and rec:
        same = (
            a["item"] == rec["item"]
            and a["ci"] == rec["ci"]
            and max(abs(u - v) for u, v in zip(a["centre"], rec["centre"])) < 0.03
            and sorted(a["size"]) == sorted(rec["size"])
        )
    return rec, same


def main():
    rec_name, scene = sys.argv[1], sys.argv[2]
    ts = [int(x) for x in sys.argv[3:]]
    rec = K.load_record(rec_name, scene)
    ep = K.Episode(rec)
    od = os.path.join(SCRATCH, "probe", rec_name)
    os.makedirs(od, exist_ok=True)
    for t in ts:
        st = B.state_at(ep, t, rec)
        out, _a, _d = B.probe_state(st)
        r, same = compare(ep, t, out)
        out["record"] = r
        out["same"] = same
        json.dump(
            out,
            open(os.path.join(od, f"{scene}-t{t}.json"), "w"),
            default=str,
            indent=1,
        )
        a = out.get("action") or {}
        print(
            f"{scene} t{t}: agent {a.get('item')} {a.get('arch')} c{a.get('ci')} {a.get('centre')} {a.get('size')} "
            f"| record {r and (r['item'], r['arch'], r['ci'], r['centre'], r['size'])} | same {same} ({out['seconds']} s)",
            flush=True,
        )


if __name__ == "__main__":
    main()
