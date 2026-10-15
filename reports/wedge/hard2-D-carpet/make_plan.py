"""make_plan.py <rec> <scene> [--light] > plan.json

Counterfactual plan for one episode, from the archaeology rows (data/arch_*.json):
  * every soft floor placement k: agent (the noise reference), soft:0 (on a soft top
    under the cap), softnocap:0 (the cap lifted for this box), ladder:0 (the ladder's
    pose before the pocket guard), floor:1 (the guard's second floor pose);
  * the last placements (N-1, N-2, N-3, N-5, N-8, N-10): agent, guard:0, guard:1,
    guard:2, ladder:1;
  * the first hard item of the hard run: agent, guard:0, ladder:1.
--light keeps only agent / soft:0 / softnocap:0 at the soft floor steps.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    rec, scene = sys.argv[1], sys.argv[2]
    light = "--light" in sys.argv
    rows = json.load(open(os.path.join(HERE, "data", f"arch_{scene}.{rec}.json")))
    placed = [r for r in rows if r.get("rec_rung")]
    n = len(placed)
    plan = []

    def add(k, spec, tag):
        if 0 <= k < n:
            plan.append({"rec": rec, "scene": scene, "k": k, "spec": spec, "tag": tag})

    for r in placed:
        if r["soft"] and r["agent_where"] == "floor":
            for s in (
                ["agent", "soft:0", "softnocap:0"]
                if light
                else ["agent", "soft:0", "softnocap:0", "ladder:0", "floor:1"]
            ):
                add(r["step"], s, "soft-floor")
    for back in (1, 2, 3, 5, 8, 10):
        for s in (
            ["agent", "guard:0"]
            if light
            else ["agent", "guard:0", "guard:1", "guard:2", "ladder:1"]
        ):
            add(n - back, s, f"end-{back}")
    first_hard = next(
        (
            r
            for r in placed
            if not r["soft"] and any(q["soft"] for q in placed[: r["step"]])
        ),
        None,
    )
    if first_hard:
        for s in ["agent", "guard:0", "ladder:1"]:
            add(first_hard["step"], s, "first-hard")
    seen, out = set(), []
    for e in plan:
        kk = (e["k"], e["spec"])
        if kk not in seen:
            seen.add(kk)
            out.append(e)
    json.dump(out, sys.stdout, indent=0)


if __name__ == "__main__":
    main()
