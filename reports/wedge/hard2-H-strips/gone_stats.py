"""gone_stats.py: when the usable floor is gone, how far is the threshold,
and how many items does the stacking phase still place?  H against the
crossings, on the records (strips.py data, v50 C and B) and on the
reference runs (ref.py)."""
import json, os, sys, glob, statistics as stx, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from strip_stats import causes, group_of
DATA = '/home/user/inv-H-scratch/data'
cz = causes()
def q(xs):
    xs = sorted(xs)
    if not xs: return '-'
    return f"{stx.median(xs):.0f} [{xs[len(xs)//4]:.0f}-{xs[(3*len(xs))//4]:.0f}]"
print('## Records (v50 C `gate0-hard2`, B `gate0-hard2-b`): placements at and after "floor gone" (median [IQR])')
print()
print('| group | task | n | placed at floor-gone | short of thr at floor-gone | placed after floor-gone | margin |')
print('|---|---|---:|---|---|---|---|')
for task, rec in (('C', 'gate0-hard2'), ('B', 'gate0-hard2-b')):
    E = json.load(open(f'{DATA}/strips-{rec}.json'))
    for g in ('H', 'G', 'D', 'X'):
        at, short, after, mg = [], [], [], []
        for e in E:
            if group_of(e, cz) != g: continue
            st = e['steps']; uf = [s['usable_floor_m2'] for s in st]
            gone = next((i for i in range(len(st)) if all(u < 0.26 for u in uf[i:])), None)
            if gone is None: continue
            at.append(gone + 1); short.append(e['thr'] - (gone + 1)); after.append(len(st) - gone - 1); mg.append(e['margin'])
        if at:
            print(f"| {g} | {task} | {len(at)} | {q(at)} | {q(short)} | {q(after)} | {q(mg)} |")
print()
print('## Reference runs (ref.py): the same, H scenes against the crossings run for contrast')
print()
hset = {h['scene'] for h in json.load(open(f'{HERE}/hlist.json'))}
print('| group | n | placed at floor-gone | short of thr at floor-gone | placed after floor-gone | margin |')
print('|---|---:|---|---|---|---|')
rows = collections.defaultdict(lambda: ([], [], [], []))
for f in sorted(glob.glob('/home/user/inv-H-scratch/ref/ref-*.json')):
    d = json.load(open(f)); dumps = d['dumps']
    uf = [sum(c['usable'] for c in x['floor_before']) for x in dumps]
    gone = next((i for i in range(len(uf) - 1) if all(u < 0.26 for u in uf[i + 1:])), None)
    if gone is None: continue
    g = 'H' if d['scene'] in hset else 'X'
    r = rows[g]; r[0].append(gone + 1); r[1].append(d['thr'] - gone - 1); r[2].append(d['placed'] - gone - 1); r[3].append(d['margin'])
for g, r in rows.items():
    print(f"| {g} | {len(r[0])} | {q(r[0])} | {q(r[1])} | {q(r[2])} | {q(r[3])} |")

print()
print('## Records: the floor phase per m^2 of floor (median [IQR]); mean item volume of the first-threshold items (litres)')
print()
print('| group | task | n | items per m^2 floor at floor-gone | floor boxes per m^2 | stacked (raised) per m^2 at floor-gone | fill at floor-gone | mean item volume (l) | items per m^2 needed (thr / floor) |')
print('|---|---|---:|---|---|---|---|---|---|')
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '../../..')))
from bench.scenes import make_scene
def qf(xs, n=2):
    xs = sorted(xs)
    return f"{stx.median(xs):.{n}f} [{xs[len(xs)//4]:.{n}f}-{xs[(3*len(xs))//4]:.{n}f}]" if xs else '-'
for task, rec in (('C', 'gate0-hard2'), ('B', 'gate0-hard2-b')):
    E = json.load(open(f'{DATA}/strips-{rec}.json'))
    for g in ('H', 'X'):
        a, fb, rb, fl, iv, need = [], [], [], [], [], []
        for e in E:
            if group_of(e, cz) != g: continue
            st = e['steps']; uf = [s['usable_floor_m2'] for s in st]
            gone = next((i for i in range(len(st)) if all(u < 0.26 for u in uf[i:])), None)
            if gone is None: continue
            F = e['floor_m2']
            a.append((gone + 1) / F); fb.append(sum(1 for s in st[:gone + 1] if s['floor']) / F)
            rb.append(sum(1 for s in st[:gone + 1] if not s['floor']) / F); fl.append(st[gone]['fill'])
            sc = make_scene(int(e['scene'].split('s')[-1]), 'hard2', task)
            iv.append(1000 * stx.mean(i['length'] * i['width'] * i['height'] for i in sc.items[:e['thr']]))
            need.append(e['thr'] / F)
        print(f"| {g} | {task} | {len(a)} | {qf(a)} | {qf(fb)} | {qf(rb)} | {qf(fl)} | {qf(iv, 0)} | {qf(need)} |")

print()
print('## Records: crossing rate by the count the threshold asks per m^2 of floor (all episodes except the volume misses, cause A)')
print()
print('| task | thr / floor m^2 | episodes | cross | H | G | D | other misses |')
print('|---|---|---:|---:|---:|---:|---:|---:|')
for task, rec in (('C', 'gate0-hard2'), ('B', 'gate0-hard2-b')):
    E = json.load(open(f'{DATA}/strips-{rec}.json'))
    for lo, hi in ((0, 8), (8, 10), (10, 12), (12, 14), (14, 99)):
        c = collections.Counter()
        for e in E:
            cause = cz.get(e['scene'])
            if cause == 'A': continue
            r = e['thr'] / e['floor_m2']
            if not (lo <= r < hi): continue
            c['n'] += 1
            if e['margin'] >= 0: c['X'] += 1
            elif cause in ('H', 'G', 'D'): c[cause] += 1
            else: c['o'] += 1
        print(f"| {task} | {lo}-{hi} | {c['n']} | {c['X']} | {c['H']} | {c['G']} | {c['D']} | {c['o']} |")
