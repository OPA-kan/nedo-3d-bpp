"""course.py: the course of the misses by cause -- covers, rescue share, the rung of the largest
usable-surface drop, special cargo on the floor -- against the crossings of the same record."""
import collections, statistics as st
import classify as C

def m(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else float('nan')

for s in ['gate0-hard2', 'gate0-hard2-b']:
    print(f'\n#### `{s}`: the course by cause (means; drop rung counts)\n')
    print('| group | n | soft placed / covered | prio placed / covered | soft floor | prio floor | rescue share | low_steps | shade vetoes | vetoes / kept / replaced | over-budget steps | largest-drop rung (top 3) | drop at the door side / standing |')
    print('|---|---:|---|---|---:|---:|---:|---:|---:|---|---:|---|---|')
    groups = collections.defaultdict(list)
    for r in C.D[s]:
        if r['mg'] < 0:
            groups[C.cause(r)].append(r)
        elif r['stratum'] in ('sample', 'stretch'):
            groups['~ crossings (sample+stretch)'].append(r)
    for g in sorted(groups):
        rs = groups[g]
        dr = collections.Counter(r.get('drop_arch') for r in rs).most_common(3)
        print(f'| {g} | {len(rs)} | {m([r["soft_count"] for r in rs]):.1f} / {m([r["soft_covered"] for r in rs]):.1f} | {m([r["prio_count"] for r in rs]):.1f} / {m([r["prio_covered"] for r in rs]):.1f} | '
              f'{m([r["soft_floor_share"] for r in rs]):.2f} | {m([r["prio_floor_share"] for r in rs]):.2f} | {m([r["rescue_share"] for r in rs]):.2f} | {m([r["phase"].get("low_steps") for r in rs]):.1f} | '
              f'{m([r["shadow"].get("shade_vetoes", 0) for r in rs]):.1f} | {m([r["shadow"].get("vetoes", 0) for r in rs]):.1f} / {m([r["shadow"].get("kept", 0) for r in rs]):.1f} / {m([r["shadow"].get("replaced", 0) for r in rs]):.1f} | '
              f'{m([r["over_budget"] for r in rs]):.1f} | {", ".join(f"{k} {v}" for k, v in dr)} | {sum(bool(r.get("drop_door")) for r in rs)} / {sum(bool(r.get("drop_standing")) for r in rs)} |')
