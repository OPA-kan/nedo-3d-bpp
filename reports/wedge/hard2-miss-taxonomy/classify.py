"""classify.py: the miss taxonomy over data/<set>.json (written by extract.py).

Every hard2 episode under its threshold gets one primary cause by the first
rule that fires (order below) plus secondary tags; tables to stdout (markdown).
"""
import json, collections, statistics as st, sys, os

sys.path.insert(0, '/home/user/nedo-3d-bpp')
from bench.scenes import make_scene

HERE = os.path.dirname(os.path.abspath(__file__))
SETS = ['gate0-hard2', 'gate0-hard2-b', 'gate0-hard2-b-r2', 'gate0det-hard2', 'bandntdet-hard2', 'bandnt-hard2', 'bandnt-hard2-b']
D = {s: json.load(open(f'{HERE}/data/{s}.json')) for s in SETS}
STRATA = ['sample', 'stretch', 'edge', 'fill-only']

def need(r):  # the fill the first-threshold items take (fill basis: the simulator's container volume)
    return r['first_vol'] / r['cvol']

# R1's line: the largest need any crossing in any record met
REACH = max(need(r) for s in SETS for r in D[s] if r['mg'] >= 0)
STRETCH = 0.44   # crossing rate under 0.44: 64-86 %; 0.44-0.51: 20-35 %
SOFT_CARPET = 0.40
TIME_CUT = {'C': 5.0, 'B': 7.0}  # the declining call ran into the resort's extra window (budget 4.5 s + 1.0 C / + 3.0 B)

_prio = {}
def prio_flags(r):
    k = (r['seed'], r['task'])
    if k not in _prio:
        sc = make_scene(r['seed'], 'hard2', r['task'])
        _prio[k] = [bool(c.get('is_prioritized')) for c in sc.containers]
    return _prio[k]


def min_side(r):
    v = r['visible'][0]['dims'] if r['visible'] else [0.3, 0.3, 0.3]
    return sorted(v)[0]


def underused(r):
    """A container left with usable surface while another is fuller (multi-container)."""
    if r['n'] < 2:
        return None
    fills = [c['fill'] for c in r['per_ci']]
    for ci, c in enumerate(r['per_ci']):
        if c['usable'] >= 0.25 and c['fill'] <= 0.6 * max(fills):
            return ci
    return None


def tags(r):
    t = []
    fat = r['fill_at_thr']
    if STRETCH < fat <= REACH + 1e-9:
        t.append('vol-stretched')
    if r['end'] != 'declined':
        t.append('sim-' + r['end'])
    if r['soft_floor_share'] >= SOFT_CARPET:
        t.append('soft-carpet')
    if underused(r) is not None:
        t.append('ctr-underused' + ('(prio)' if prio_flags(r)[underused(r)] else ''))
    if (r['last_call_s'] or 0) >= TIME_CUT[r['task']]:
        t.append('time-cut')
    if r['any_reach'] > 0:
        t.append('patch-reachable')
    elif r['any_fit_soft'] > 0:
        t.append('patch-sealed')
    if r['order'] in ('soft-first', 'small-first'):
        t.append('soft-early')
    if r['order'] == 'big-first':
        t.append('big-first')
    if r.get('drop', 0) >= 0.2 and r.get('drop_lead', 0) >= 10:
        t.append('early-collapse')
    return t


def cause(r):
    fat = r['fill_at_thr']
    if fat > REACH + 1e-9:
        return 'A volume out of reach'
    if r['end'] != 'declined':
        return 'B ended by the simulator'
    if underused(r) is not None:
        return 'C container left under-used'
    if r['soft_floor_share'] >= SOFT_CARPET:
        return 'D soft carpet'
    if r['any_reach'] > 0:
        if (r['last_call_s'] or 0) >= TIME_CUT[r['task']]:
            return 'E reachable patch left, the call ran out of time'
        return 'F reachable patch left, not taken'
    if r['any_fit_soft'] > 0:
        return 'G patch left, sealed from the door'
    return 'H no level patch: floor in strips, tops closed'


def recoverable(r):
    return r['mg'] >= -3 and r['any_reach'] > 0


def misses(s):
    return [r for r in D[s] if r['mg'] < 0]


def fmt(x, n=2):
    return '-' if x is None else (f'{x:.{n}f}' if isinstance(x, float) else str(x))


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return st.mean(xs) if xs else None


def cause_table(s, title):
    ms = misses(s)
    by = collections.defaultdict(list)
    for r in ms:
        by[cause(r)].append(r)
    print(f'\n#### {title} (`{s}`): {len(ms)} misses, {sum(-r["mg"] for r in ms)} items under the thresholds\n')
    print('| cause | episodes | share | mean margin | median margin | items short | sample / stretch / edge / fill-only | need (mean) | orders rnd/bf/sf/sm/sl | within 3 | recoverable (within 3, reachable patch) |')
    print('|---|---:|---:|---:|---:|---:|---|---:|---|---:|---:|')
    for c in sorted(by):
        g = by[c]
        om = '/'.join(str(sum(r['order'] == o for r in g)) for o in ('random', 'big-first', 'soft-first', 'small-first', 'soft-last'))
        mix = ' / '.join(str(sum(1 for r in g if r['stratum'] == x)) for x in STRATA)
        print(f'| {c} | {len(g)} | {100 * len(g) / len(ms):.0f} % | {st.mean(r["mg"] for r in g):+.1f} | {st.median(r["mg"] for r in g):+.0f} | '
              f'{sum(-r["mg"] for r in g)} | {mix} | {st.mean(need(r) for r in g):.2f} | {om} | {sum(r["mg"] >= -3 for r in g)} | {sum(recoverable(r) for r in g)} |')
    return by


def dims_table(s, title):
    ms = misses(s)
    by = collections.defaultdict(list)
    for r in ms:
        by[cause(r)].append(r)
    print(f'\n#### {title}: the end and the course by cause (medians unless marked)\n')
    print('| cause | n | fill / fill at thr | free floor | largest empty rect (short side, m) | free floor in strips < 0.3 m (m2) | free pieces | usable tops | soft on floor | prio on floor | level patch / reachable patch for a visible item (episodes) | largest drop / its lead | low-phase lead | rescue share | low_steps | shadow vetoes / replaced / skipped | last call (s) | policy max (s) | over-budget steps (mean) |')
    print('|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|---:|---:|---:|')
    for c in sorted(by):
        g = by[c]
        print(f'| {c} | {len(g)} | {med([r["fill"] for r in g]):.2f} / {med([r["fill_at_thr"] for r in g]):.2f} | {med([r["free_floor_share"] for r in g]):.2f} | '
              f'{med([min(r["ler"]) for r in g]):.2f} | {med([r["strip_free"] for r in g]):.2f} | {med([r["pieces"] for r in g])} | {med([r["usable_end"] for r in g]):.2f} | '
              f'{med([r["soft_floor_share"] for r in g]):.2f} | {med([r["prio_floor_share"] for r in g]):.2f} | {sum(r["any_fit_soft"] > 0 for r in g)} / {sum(r["any_reach"] > 0 for r in g)} | '
              f'{fmt(med([r.get("drop") for r in g]))} / {fmt(med([r.get("drop_lead") for r in g]))} | {fmt(med([r["low_lead"] for r in g]))} | {med([r["rescue_share"] for r in g]):.2f} | '
              f'{fmt(med([r["phase"].get("low_steps") for r in g]))} | {fmt(med([r["shadow"].get("vetoes", 0) for r in g]))} / {fmt(med([r["shadow"].get("replaced", 0) for r in g]))} / {fmt(med([r["shadow"].get("skipped", 0) for r in g]))} | '
              f'{fmt(med([r["last_call_s"] for r in g]), 1)} | {fmt(med([r["ptmax"] for r in g]), 1)} | {mean([r["over_budget"] for r in g]):.1f} |')


def episode_table(s, title):
    ms = sorted(misses(s), key=lambda r: (cause(r), r['mg']))
    print(f'\n#### {title}: every miss\n')
    print('| scene | stratum | need | placed / thr | margin | end | next item | cause | tags | free floor / LER (m) | soft floor | patch m2 / reachable origins | last arch | drop (lead, rung) |')
    print('|---|---|---:|---|---:|---|---|---|---|---|---:|---:|---|---|')
    for r in ms:
        v = r['visible'][0] if r['visible'] else None
        item = ('soft ' if v and v['soft'] else '') + ('prio ' if v and v['prio'] else '') + ('x'.join(f'{x:g}' for x in v['dims']) if v else '-')
        if r.get('failed_item'):
            fi = r['failed_item']
            item = 'fell: ' + ('soft ' if fi['soft'] else '') + 'x'.join(f'{x:g}' for x in fi['dims'])
        print(f'| {r["scene"]} | {r["stratum"]} | {need(r):.2f} | {r["placed"]}/{r["thr"]} | {r["mg"]} | {r["end"]} | {item} | {cause(r)[0]} | {", ".join(tags(r))} | '
              f'{r["free_floor_share"]:.2f} / {r["ler"][0]:g}x{r["ler"][1]:g} | {r["soft_floor_share"]:.2f} | {r["any_fit_soft"]:.2f} / {r["any_reach"]} | {r["last_arch"][-1] if r["last_arch"] else "-"} | '
              f'{fmt(r.get("drop"))} ({r.get("drop_lead")}, {r.get("drop_arch")}) |')


def tag_table(sets):
    print('\n| tag | ' + ' | '.join(f'`{s}`' for s in sets) + ' |')
    print('|---|' + '---:|' * len(sets))
    allt = ['vol-stretched', 'soft-carpet', 'soft-early', 'big-first', 'patch-reachable', 'patch-sealed', 'time-cut', 'early-collapse', 'ctr-underused', 'ctr-underused(prio)', 'sim-settle', 'sim-transport']
    for t in allt:
        row = []
        for s in sets:
            ms = misses(s)
            row.append(f'{sum(t in tags(r) for r in ms)} / {len(ms)}')
        print(f'| {t} | ' + ' | '.join(row) + ' |')


def pair(sa, sb, la, lb):
    A = {r['seed']: r for r in D[sa]}; B = {r['seed']: r for r in D[sb]}
    print(f'\n| stratum | both cross | {la} only miss | {lb} only miss | both miss | placed {lb} - {la} (mean, all) | (both-miss episodes) |')
    print('|---|---:|---:|---:|---:|---:|---:|')
    for x in STRATA + ['all']:
        seeds = [k for k in A if x == 'all' or A[k]['stratum'] == x]
        bc = sum(A[k]['mg'] >= 0 and B[k]['mg'] >= 0 for k in seeds)
        ao = [k for k in seeds if A[k]['mg'] < 0 <= B[k]['mg']]
        bo = [k for k in seeds if B[k]['mg'] < 0 <= A[k]['mg']]
        bm = [k for k in seeds if A[k]['mg'] < 0 and B[k]['mg'] < 0]
        dpl = st.mean(B[k]['placed'] - A[k]['placed'] for k in seeds)
        dbm = st.mean(B[k]['placed'] - A[k]['placed'] for k in bm) if bm else 0
        print(f'| {x} | {bc} | {len(ao)} | {len(bo)} | {len(bm)} | {dpl:+.2f} | {dbm:+.2f} |')
    return A, B


def extras():
    print('\n#### Margin histogram of the misses (episodes; items short in brackets)\n')
    bins = [(-1, -1), (-3, -2), (-6, -4), (-15, -7), (-999, -16)]
    print('| record | ' + ' | '.join(f'{hi if lo == hi else f"{lo}..{hi}" if lo > -999 else f"<= {hi}"}' for lo, hi in bins) + ' |')
    print('|---|' + '---:|' * len(bins))
    for s in ['gate0-hard2', 'gate0-hard2-b', 'gate0det-hard2', 'bandntdet-hard2']:
        ms = misses(s)
        print(f'| `{s}` | ' + ' | '.join(f'{sum(lo <= r["mg"] <= hi for r in ms)} ({sum(-r["mg"] for r in ms if lo <= r["mg"] <= hi)})' for lo, hi in bins) + ' |')
    print('\n#### Crossing rate by order family, in reach (need <= 0.44) and stretched (0.44-0.506)\n')
    print('| record | ' + ' | '.join(['random', 'big-first', 'soft-first', 'small-first', 'soft-last']) + ' |')
    print('|---|---:|---:|---:|---:|---:|')
    for s in ['gate0-hard2', 'gate0-hard2-b', 'gate0det-hard2', 'bandntdet-hard2']:
        cells = []
        for o in ['random', 'big-first', 'soft-first', 'small-first', 'soft-last']:
            a = [r for r in D[s] if r['order'] == o and need(r) <= STRETCH]
            b = [r for r in D[s] if r['order'] == o and STRETCH < need(r) <= REACH]
            cells.append(f'{sum(r["mg"] >= 0 for r in a)}/{len(a)} ; {sum(r["mg"] >= 0 for r in b)}/{len(b)}')
        print(f'| `{s}` | ' + ' | '.join(cells) + ' |')
    print('\n#### Crossing rate by the soft cargo\'s share of the floor (at the end), episodes in reach (need <= 0.506)\n')
    sb = [(0, 0.1), (0.1, 0.25), (0.25, 0.4), (0.4, 0.55), (0.55, 1.01)]
    print('| record | ' + ' | '.join(f'{a:.2f}-{b:.2f}' for a, b in sb) + ' |')
    print('|---|' + '---:|' * len(sb))
    for s in ['gate0-hard2', 'gate0-hard2-b', 'gate0det-hard2', 'bandntdet-hard2']:
        g = [r for r in D[s] if need(r) <= REACH]
        print(f'| `{s}` | ' + ' | '.join(f'{sum(r["mg"] >= 0 for r in g if a <= r["soft_floor_share"] < b)}/{sum(1 for r in g if a <= r["soft_floor_share"] < b)}' for a, b in sb) + ' |')
    print('\n#### Level / reachable patch for a visible item at the final decline: misses against crossings\n')
    print('| record | misses ending declined: level patch / reachable | crossings ending declined: level patch / reachable |')
    print('|---|---|---|')
    for s in ['gate0-hard2', 'gate0-hard2-b', 'gate0det-hard2']:
        m = [r for r in D[s] if r['mg'] < 0 and r['end'] == 'declined']; c = [r for r in D[s] if r['mg'] >= 0 and r['end'] == 'declined']
        print(f'| `{s}` | {sum(r["any_fit_soft"] > 0 for r in m)} / {sum(r["any_reach"] > 0 for r in m)} of {len(m)} | {sum(r["any_fit_soft"] > 0 for r in c)} / {sum(r["any_reach"] > 0 for r in c)} of {len(c)} |')
    print('\n#### The near misses (margin -3..-1), v50 C and B\n')
    print('| scene | margin | stratum | need | order | cause | next item | free floor / LER | soft floor | last call (s) | crosses in |')
    print('|---|---:|---|---:|---|---|---|---|---:|---:|---|')
    other = {'C': ['gate0det-hard2', 'gate0-hard2-b', 'bandntdet-hard2'], 'B': ['gate0-hard2-b-r2', 'gate0-hard2']}
    for s in ['gate0-hard2', 'gate0-hard2-b']:
        for r in sorted(misses(s), key=lambda r: (-r['mg'], r['scene'])):
            if r['mg'] < -3:
                continue
            v = r['visible'][0] if r['visible'] else None
            item = ('soft ' if v and v['soft'] else '') + ('prio ' if v and v['prio'] else '') + ('x'.join(f'{x:g}' for x in v['dims']) if v else '-')
            xs = [o for o in other[r['task']] if next(q for q in D[o] if q['seed'] == r['seed'])['mg'] >= 0]
            print(f'| {r["scene"]} | {r["mg"]} | {r["stratum"]} | {need(r):.2f} | {r["order"]} | {cause(r)[0]} | {item} | {r["free_floor_share"]:.2f} / {r["ler"][0]:g}x{r["ler"][1]:g} | {r["soft_floor_share"]:.2f} | {fmt(r["last_call_s"], 1)} | {", ".join(xs) or "-"} |')


def main():
    print(f'REACH (largest need any crossing met, all records) = {REACH:.3f}')
    for s, t in [('gate0-hard2', 'v50 C'), ('gate0-hard2-b', 'v50 B'), ('gate0-hard2-b-r2', 'v50 B replicate'), ('gate0det-hard2', 'v50 C deterministic'),
                 ('bandntdet-hard2', 'v49 C deterministic'), ('bandnt-hard2', 'v49 C'), ('bandnt-hard2-b', 'v49 B')]:
        cause_table(s, t)
    for s, t in [('gate0-hard2', 'v50 C'), ('gate0-hard2-b', 'v50 B')]:
        dims_table(s, t)
    print('\n#### Secondary tags (misses carrying the tag)')
    tag_table(['gate0-hard2', 'gate0-hard2-b', 'gate0-hard2-b-r2', 'gate0det-hard2', 'bandntdet-hard2'])

    print('\n#### C against B on the same seeds (v50, `gate0-hard2` vs `gate0-hard2-b`)')
    A, B = pair('gate0-hard2', 'gate0-hard2-b', 'C', 'B')
    print('\nC-only misses (B crosses): ' + '; '.join(f'{A[k]["scene"][2:]} {A[k]["mg"]:+d} -> B {B[k]["mg"]:+d} [{cause(A[k])[0]}; {A[k]["order"]}]' for k in sorted(A) if A[k]['mg'] < 0 <= B[k]['mg']))
    print('\nB-only misses (C crosses): ' + '; '.join(f'{B[k]["scene"][2:]} {B[k]["mg"]:+d} (C {A[k]["mg"]:+d}) [{cause(B[k])[0]}; {B[k]["order"]}]' for k in sorted(A) if B[k]['mg'] < 0 <= A[k]['mg']))
    print('\nCause transitions on the both-miss seeds (C cause -> B cause):')
    tr = collections.Counter((cause(A[k])[0], cause(B[k])[0]) for k in A if A[k]['mg'] < 0 and B[k]['mg'] < 0)
    print(', '.join(f'{a}->{b}: {n}' for (a, b), n in sorted(tr.items())))
    print('\nC-only misses by C cause: ' + str(collections.Counter(cause(A[k]) for k in A if A[k]['mg'] < 0 <= B[k]['mg'])))
    print('\nB replicate (`gate0-hard2-b` vs `-r2`):')
    pair('gate0-hard2-b', 'gate0-hard2-b-r2', 'B r1', 'B r2')
    print('\nC time-faithful vs deterministic (v50, `gate0-hard2` vs `gate0det-hard2`):')
    A2, B2 = pair('gate0-hard2', 'gate0det-hard2', 'C tf', 'C det')
    print('tf-only misses: ' + '; '.join(f'{A2[k]["scene"][2:]} {A2[k]["mg"]:+d} -> {B2[k]["mg"]:+d} [{cause(A2[k])[0]}]' for k in sorted(A2) if A2[k]['mg'] < 0 <= B2[k]['mg']))
    print('det-only misses: ' + '; '.join(f'{B2[k]["scene"][2:]} {B2[k]["mg"]:+d} (tf {A2[k]["mg"]:+d}) [{cause(B2[k])[0]}]' for k in sorted(A2) if B2[k]['mg'] < 0 <= A2[k]['mg']))
    print('\nThe gate attributed (v49 det `bandntdet-hard2` vs v50 det `gate0det-hard2`):')
    A3, B3 = pair('bandntdet-hard2', 'gate0det-hard2', 'v49', 'v50')
    print('v49-only misses (gained by v50): ' + '; '.join(f'{A3[k]["scene"][2:]} {A3[k]["mg"]:+d} -> {B3[k]["mg"]:+d} [{cause(A3[k])[0]}, soft floor {A3[k]["soft_floor_share"]:.2f} -> {B3[k]["soft_floor_share"]:.2f}]' for k in sorted(A3) if A3[k]['mg'] < 0 <= B3[k]['mg']))
    print('v50-only misses (lost by v50): ' + '; '.join(f'{B3[k]["scene"][2:]} {B3[k]["mg"]:+d} (v49 {A3[k]["mg"]:+d}) [{cause(B3[k])[0]}, soft floor {A3[k]["soft_floor_share"]:.2f} -> {B3[k]["soft_floor_share"]:.2f}]' for k in sorted(A3) if B3[k]['mg'] < 0 <= A3[k]['mg']))
    sc = [k for k in A3 if A3[k]['mg'] < 0 and B3[k]['mg'] < 0]
    print(f'both-miss: soft floor share median {med([A3[k]["soft_floor_share"] for k in sc]):.2f} -> {med([B3[k]["soft_floor_share"] for k in sc]):.2f}; soft-carpet episodes {sum(A3[k]["soft_floor_share"] >= SOFT_CARPET for k in A3 if A3[k]["mg"] < 0)} -> {sum(B3[k]["soft_floor_share"] >= SOFT_CARPET for k in B3 if B3[k]["mg"] < 0)} (all misses)')

    extras()
    for s, t in [('gate0-hard2', 'v50 C'), ('gate0-hard2-b', 'v50 B')]:
        episode_table(s, t)


if __name__ == '__main__':
    main()
