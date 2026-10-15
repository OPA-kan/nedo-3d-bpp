"""orient_stats.py: the orientation at the hard floor placements (orient.py
output), H against the crossings.  Per floor placement: was it standing, did
the ladder hold a standing floor survivor, what removed the standing poses,
and the usable floor left by the agent's pose, by the best standing survivor
and by the best legal standing pose (no vetoes)."""
import json, glob, os, collections, statistics as stx
HERE = os.path.dirname(os.path.abspath(__file__))
HSET = {h['scene'] for h in json.load(open(f'{HERE}/hlist.json'))}
rows = collections.defaultdict(list)
vetoes = collections.defaultdict(collections.Counter)
for f in sorted(glob.glob('/home/user/inv-H-scratch/orient/orient-*.json')):
    d = json.load(open(f)); g = 'H' if d['scene'] in HSET else 'X'
    for s in d['steps']:
        rows[g].append(s)
        for k, v in s['standing_vetoed_by'].items():
            vetoes[g][k] += v
L = ['# Orientation at the hard floor placements (orient.py)', '',
     'Every step of a reference run where the agent put a hard box on the floor.  "legal standing" = floor poses with the height '
     'not the smallest side and > 0.3 m that the ladder\'s generator and validator produce (no vetoes); "standing survivor" = one '
     'left after the ladder\'s orientation policy, shortlist and vetoes.  Floor = usable floor (0.58 x 0.43 window).', '',
     '| group | floor placements | agent stood the box | a legal standing pose existed | a standing survivor existed | lying chosen while a standing survivor existed | usable floor lost by the agent (mean) | by the best standing survivor (when one existed, the agent lying) | by the best legal standing pose (agent lying) |',
     '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
for g in ('H', 'X'):
    R = rows[g]
    if not R: continue
    stood = sum(1 for s in R if s['agent_standing'])
    leg = sum(1 for s in R if s['legal']['standing'] > 0)
    sv = sum(1 for s in R if s['survivors']['standing'] > 0)
    lying_sv = [s for s in R if not s['agent_standing'] and s.get('best_standing')]
    lost = [s['usable_floor_before'] - s['agent_floor_after'] for s in R]
    lost_lying = [s['usable_floor_before'] - s['agent_floor_after'] for s in lying_sv]
    lost_st = [s['usable_floor_before'] - s['best_standing']['floor_after'] for s in lying_sv]
    lying_leg = [s for s in R if not s['agent_standing'] and s.get('best_legal_standing_floor_after') is not None]
    lost_l = [s['usable_floor_before'] - s['agent_floor_after'] for s in lying_leg]
    lost_leg = [s['usable_floor_before'] - s['best_legal_standing_floor_after'] for s in lying_leg]
    m = lambda xs: f'{stx.mean(xs):.3f}' if xs else '-'
    L.append(f"| {g} | {len(R)} | {stood} | {leg} | {sv} | {len(lying_sv)} | {m(lost)} | agent {m(lost_lying)} vs standing {m(lost_st)} (n={len(lying_sv)}) | agent {m(lost_l)} vs standing {m(lost_leg)} (n={len(lying_leg)}) |")
L += ['', '## What removed the standing floor poses that were shortlisted (veto counts)', '', '| group | vetoes |', '|---|---|']
for g in ('H', 'X'):
    L.append(f"| {g} | " + ', '.join(f'{k} {v}' for k, v in vetoes[g].most_common(10)) + ' |')
L += ['', '## The best standing survivor when the agent laid the box: its rank in the chosen rung and whether it would stand (shadow)', '',
      '| group | n | rank 2-3 / 4-10 / >10 | shadow ok / soft veto / hard veto (tips or slides) | shade > 0.15 |', '|---|---:|---|---|---:|']
for g in ('H', 'X'):
    B = [s['best_standing'] for s in rows[g] if not s['agent_standing'] and s.get('best_standing')]
    if not B: continue
    rk = collections.Counter('2-3' if b['rank'] <= 3 else ('4-10' if b['rank'] <= 10 else '>10') for b in B)
    vv = collections.Counter(('ok' if b['verdict'].get('ok') else ('hard' if b['verdict'].get('hard') else 'soft')) if isinstance(b['verdict'], dict) else 'err' for b in B)
    sh = sum(1 for b in B if (b.get('shade') or 0) > 0.15)
    L.append(f"| {g} | {len(B)} | {rk['2-3']} / {rk['4-10']} / {rk['>10']} | {vv['ok']} / {vv['soft']} / {vv['hard']} | {sh} |")
open(f'{HERE}/orient_stats.md', 'w').write('\n'.join(L) + '\n')
print('\n'.join(L))
