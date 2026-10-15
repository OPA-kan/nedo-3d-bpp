"""count_bridges.py <record_dir>... : plateau-merge and bridge-slide placements
in bench records (steps[].archetype), with the episodes they occur in, the
items placed, and the slowest call."""
import collections, glob, json, os, sys

for d in sys.argv[1:]:
    c = collections.Counter(); eps = collections.Counter(); placed = 0; n = 0; tmax = 0.0
    for f in sorted(glob.glob(os.path.join(d, '[abc]-*.json'))):
        r = json.load(open(f)); n += 1
        placed += r['metrics']['placed_count']
        tmax = max(tmax, r['metrics'].get('policy_time_max', 0.0))
        for st in r['steps']:
            a = st.get('archetype')
            if a in ('plateau-merge', 'bridge-slide'):
                c[a] += 1; eps[r['scene']] += 1
    print(f"{os.path.basename(d.rstrip('/'))}: episodes {n}, placed {placed}, plateau-merge {c['plateau-merge']}, "
          f"bridge-slide {c['bridge-slide']}, in {len(eps)} episodes, policy time max {tmax:.2f} s")
