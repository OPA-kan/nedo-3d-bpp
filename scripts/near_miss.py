"""near_miss.py <dir> [lo hi]: the episodes whose margin to the count threshold lies in [lo, hi] (default -6..2), with the end state."""
import json, glob, sys, collections
d = sys.argv[1]; lo = int(sys.argv[2]) if len(sys.argv) > 2 else -6; hi = int(sys.argv[3]) if len(sys.argv) > 3 else 2
rows = []
for f in sorted(glob.glob(d + '/[abc]-*.json')):
    r = json.load(open(f)); m = r['metrics']; thr = m['total_items'] // 2 + 1; mg = m['placed_count'] - thr
    if not (lo <= mg <= hi):
        continue
    steps = [x for x in r['steps'] if x.get('event') == 'step']
    last = [str(x.get('archetype', '?')).split('/')[-1] for x in steps[-4:]]
    kinds = collections.Counter(str(x.get('archetype', '?')).split('/')[0] for x in steps)
    rescue = kinds.get('physics-resort', 0) + kinds.get('count-mode', 0)
    spec = r.get('scene_spec', {}) or {}
    items = r.get('final_items') or []
    rows.append((mg, r['scene'], m['total_items'], m['placed_count'], thr, m.get('end_reason'), round(m.get('fill_volume', 0), 1),
                 f"{m.get('soft_count')}/{spec.get('soft_total', '?')}", f"{m.get('priority_count')}/{spec.get('priority_total', '?')}",
                 m.get('per_container_count'), rescue, ' '.join(last), f"{spec.get('containers_n')}c {'x'.join(str(v) for v in (spec.get('dims') or [[]])[0])} {spec.get('mix')} {spec.get('order')} pool{spec.get('pool')} shelves{spec.get('shelves')}"))
rows.sort()
print(f"{'mg':>3} {'scene':14} {'tot':>3} {'plc':>3} {'thr':>3} {'end':12} {'fill':>5} {'soft':>7} {'prio':>6} {'per-ctr':10} {'resc':>4}  last four  | spec")
for row in rows:
    mg, sc, tot, plc, thr, end, fill, soft, prio, pc, resc, last, spec = row
    print(f"{mg:>3} {sc:14} {tot:>3} {plc:>3} {thr:>3} {str(end):12} {fill:>5} {soft:>7} {prio:>6} {str(pc):10} {resc:>4}  {last} | {spec}")
