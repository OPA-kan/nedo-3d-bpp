"""bridge_check.py <armfile> : the agent's own verdict on the bridge poses the
scan found (bridge_scan.json): layer1.validate (the analytic mirror of the
official validator, with the convex-hull stability), stability.is_stable's
margin, and the grid rescue's contact share (the share of the footprint
window resting at the bottom within CONTACT_TOLERANCE), which the rescue
compares with 0.5 (0.25 under the count threshold)."""
import collections
import glob
import json
import os
import statistics
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, '/home/user/nedo-3d-bpp')
from extract import make_scene  # noqa: E402
from bench.arms import make_arm  # noqa: E402
from rule_alpha import layer1, stability, fastgeom  # noqa: E402
from bridge_scan import rebuild  # noqa: E402
from wedge_rl.stack import skyline  # noqa: E402

cfg = make_arm(open(sys.argv[1]).read().strip()).config
rows = json.load(open(HERE + '/bridge_scan.json'))
records = {r['record']: None for r in rows}
reasons = collections.Counter()
per = []
for r in rows:
    if r['any_full'] > 0 or r['any_bridge'] == 0:
        continue
    task = r['task']
    path = f"/home/user/nedo-3d-bpp/reports/bench/{r['record']}/{r['scene']}.json"
    ep = rebuild(path)
    board = layer1.Board(ep['board'].containers, cfg)
    verdicts = []
    for it in r['items']:
        for p in it.get('poses', []):
            ci = p['ci']; model = board.model(ci); container = board.container(ci)
            dx, dy, dz = p['fx'], p['fy'], p['h']
            box = layer1.AABB((p['x'], p['y'], p['z'] + dz / 2.0), (dx, dy, dz), 'candidate')
            ok, why = layer1.validate(box, model, container, cfg)
            st, margin = stability.is_stable(box, container, cfg)
            # the grid rescue's contact share on its own skyline
            xs, ys, tops = skyline(container, model, step=0.05)
            i0 = int(np.searchsorted(xs, p['x'] - dx / 2.0)); j0 = int(np.searchsorted(ys, p['y'] - dy / 2.0))
            wx, wy = max(1, int(round(dx / 0.05))), max(1, int(round(dy / 0.05)))
            win = tops[max(0, i0):i0 + wx, max(0, j0):j0 + wy]
            share = float(np.mean(np.abs(win - p['z']) <= fastgeom.CONTACT_TOLERANCE)) if win.size else 0.0
            rest = float(win.max()) if win.size else p['z']
            verdicts.append(dict(ok=ok, why=why, stable=st, margin=round(margin, 3), share=round(share, 2),
                                 rest_above=round(rest - p['z'], 3), soft=it['soft'], z=p['z'], sup=p['support_share']))
            if not ok:
                reasons[why.split(':')[0]] += 1
    n = len(verdicts)
    n_ok = sum(1 for v in verdicts if v['ok'])
    n_ok_half = sum(1 for v in verdicts if v['ok'] and v['share'] >= 0.5)
    n_ok_q = sum(1 for v in verdicts if v['ok'] and v['share'] >= 0.25)
    per.append(dict(record=r['record'], scene=r['scene'], mg=r['mg'], poses=n, legal=n_ok, legal_share50=n_ok_half,
                    legal_share25=n_ok_q, margins=[v['margin'] for v in verdicts if v['ok']][:5],
                    shares=[v['share'] for v in verdicts if v['ok']][:8],
                    whys=collections.Counter(v['why'].split(':')[0] for v in verdicts if not v['ok']).most_common(3)))
    print(f"{r['record']} {r['scene']} mg {r['mg']:+d}: poses {n} legal {n_ok} (share>=.5 {n_ok_half}, >=.25 {n_ok_q}) "
          f"margins {per[-1]['margins']} shares {per[-1]['shares']} refusals {per[-1]['whys']}", flush=True)
print()
print('| record | bridge-only episodes | with a pose the validator accepts | ...and contact share >= 0.5 (grid rescue) | ...>= 0.25 (count) |')
print('|---|---:|---:|---:|---:|')
for name in sorted({p['record'] for p in per}):
    ps = [p for p in per if p['record'] == name]
    print(f"| {name} | {len(ps)} | {sum(1 for p in ps if p['legal'] > 0)} | {sum(1 for p in ps if p['legal_share50'] > 0)} | {sum(1 for p in ps if p['legal_share25'] > 0)} |")
print('refusal reasons over all poses:', reasons.most_common(8))
json.dump(per, open(HERE + '/bridge_check.json', 'w'))
