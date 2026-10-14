"""cf_summary.py <dir>: one line per declining call of the cf_probe records."""
import glob
import json
import os
import sys

for f in sorted(glob.glob(os.path.join(sys.argv[1], "b-*.json"))):
    if f.endswith("-anchors.json"):
        continue
    r = json.load(open(f)); m = r["metrics"]; thr = m["total_items"] // 2 + 1
    print(f"{r['scene']}: placed {m['placed_count']}/{m['total_items']} margin {m['placed_count'] - thr:+d} end {m['end_reason']}")
    for e in r.get("cf", []):
        parts = []
        for x in e["retries"]:
            tag = f"{x['budget']:g}{'d' if x['deterministic'] else ''}"
            st = x["stats"]
            tries = st.get("count_mode_tried", 0) + st.get("resort_tried", 0) + st.get("grid_rescue_tried", 0)
            parts.append(f"{tag}: {'PLACED ' + str(x['archetype']) if x['placed'] else 'decline'} {x['seconds']:.1f}s checks {st.get('checks', 0)} (failed rescue tries {tries})")
        room = sum(int(s.rsplit(':', 1)[1]) for s in e.get('room', []) if s.rsplit(':', 1)[1].isdigit())
        print(f"   step {e['step']} first {e['first_seconds']:.1f}s, packed {e['packed']}, room {room} legal grid poses | " + " | ".join(parts))
