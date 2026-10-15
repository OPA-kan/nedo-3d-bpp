import json
import sys

for f in sys.argv[1:]:
    r = json.load(open(f))
    m = r["metrics"]
    print(f.split("/")[-1], "placed", m["placed_count"], "/", m["total_items"], m.get("end_reason"))
    for e in r["cf"]:
        print("  step", e["step"], "first", e["first_seconds"], "packed", e["packed"], "pool", e["pool"], "low", e["phase_low"])
        for t in e["retries"]:
            print("   %-6s %5.2fs placed=%s %s %s %s %s" % (t["variant"], t["seconds"], t["placed"], t["archetype"], t["stats"],
                                                       t["phase"], (t["box"] or {}).get("reason")))
