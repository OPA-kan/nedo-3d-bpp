"""nonplan.py <record.json>...: the steps of an episode that were not replayed plan poses, and the record's soft /
priority / fill / centre-of-mass metrics."""
import json
import sys

for f in sys.argv[1:]:
    r = json.load(open(f))
    print(f)
    for s in r["steps"]:
        if s.get("event") == "step" and s.get("archetype") != "plan":
            print("  ", {k: s.get(k) for k in ("step", "item_index", "archetype", "role", "surface", "pos_local", "size",
                                               "considered", "survivors")})
    m = r["metrics"]
    print("  ", {k: m[k] for k in m if "soft" in k or "prior" in k or "fill" in k or "com_" in k or k == "end_reason"})
