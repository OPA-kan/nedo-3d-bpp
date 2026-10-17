"""offplan.py <record.json>...: where each episode fell off its plan (the first non-plan archetype), the soft block's
poses as placed (standing soft boxes, their settled height and tilt), and the shake topples."""
import json, sys
for f in sys.argv[1:]:
    r = json.load(open(f)); m = r['metrics']
    cs = m.get('count_secure') or {}
    v = {x['side']: x for x in cs.get('variants', [])}
    print(f"== {f.split('/')[-1]} placed {m['placed_count']}/{m['total_items']} soft {m['soft_count']} prio {m['priority_count']} "
          f"topples {m.get('shake_topples')} end {m['end_reason']} src {r.get('plan_source')} chosen {cs.get('chosen')} "
          f"planned {v.get(cs.get('chosen'), {}).get('planned')} optimize {(m.get('optimize') or {}).get('seconds')}")
    steps = [s for s in r['steps'] if s['event'] == 'step']
    first_off = next((s['step'] for s in steps if s.get('archetype') != 'plan'), None)
    print(f"   first off-plan step: {first_off} of {len(steps)}; archetypes: " + " ".join(
        ('P' if s.get('archetype') == 'plan' else s.get('archetype', '?')[:6]) for s in steps))
    for s in steps:
        sz = s.get('size') or [0, 0, 0]
        sh = s.get('shadow', {}).get('chosen', {}) or {}
        standing = sz[2] >= max(sz) - 1e-9 and sz[2] >= 0.45
        if standing or s.get('archetype') != 'plan':
            print(f"   step {s['step']:2d} #{s['item_index']:3d} {s.get('archetype','?'):18s} pos {[round(x, 2) for x in s['pos_local']]} "
                  f"size {[round(x, 2) for x in sz]} drift_xy {sh.get('drift_xy', 0):.3f} angle {sh.get('angle_deg', 0):.1f} "
                  f"valid {s.get('is_valid')} safe {s.get('is_placed_safe')}")
    tp = m.get('shake_topple_items') or m.get('topple_items') or m.get('shake') or ''
    if tp:
        print("   topples:", str(tp)[:300])
