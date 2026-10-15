"""guard_xctr.py: the pocket guard compares poses in different containers by the
post-placement slots of each pose's own container (rule_alpha/pocket.py:212-214), not
by the slots the pose costs.  For every probed soft floor decision where the guard
chose a floor pose (or kept the ladder's) while a soft-top pose existed in its
ranking, compare the two by slots lost (container's slots now - after)."""
import glob, json, collections, sys
rows = []
for f in sorted(glob.glob('/home/user/inv-D-scratch/arch/*.jsonl')):
    if 'gate0det' in f:
        continue
    for line in open(f):
        l = json.loads(line)
        p = l.get('pocket') or {}
        fin = l.get('final') or {}
        if 'chosen_slots' not in p or fin.get('on') != 'floor':
            continue
        bs = p.get('best_soft')
        best = (p.get('best') or [None])[0]
        if not bs or not best or best.get('on') != 'floor':
            continue
        now = p.get('now_slots') or []
        loss_floor = now[best['ci']] - best['slots']
        loss_soft = now[bs['ci']] - bs['slots']
        rows.append(dict(f=f.split('/')[-1].split('.jsonl')[0], step=l['step'], floor_ci=best['ci'], soft_ci=bs['ci'],
                         floor_slots=best['slots'], soft_slots=bs['slots'], loss_floor=round(loss_floor, 3), loss_soft=round(loss_soft, 3)))
c = collections.Counter()
for r in rows:
    same = r['floor_ci'] == r['soft_ci']
    c[('same ctr' if same else 'other ctr', 'soft top costs fewer slots' if r['loss_soft'] < r['loss_floor'] - 1e-6 else 'floor costs fewer or equal')] += 1
for r in rows:
    print(r)
print(dict(c))
