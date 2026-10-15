import json
import sys

for f in sys.argv[1:]:
    r = json.load(open(f))
    for e in r["cf"]:
        print(f.split("/")[-1], "step", e["step"], "first", e["first_seconds"])
        for t in e["retries"]:
            print("  %-6s %5.2fs placed=%s %s" % (t["variant"], t["seconds"], t["placed"], (t["box"] or {}).get("reason")))
            for tr in t.get("trace", []):
                print("      ", tr)
