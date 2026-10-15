import json, sys
D = '/home/user/nedo-3d-bpp/reports/wedge/bridge-generator/'
names = sys.argv[1:] or ['an48_base', 'an48_slide', 'an48_slidex']
runs = [json.load(open(D + n + '.json')) for n in names]
scenes = sorted(runs[0]['per'])
for n, r in zip(names, runs):
    per = r['per']
    placed = sum(per[s]['placed'] for s in scenes)
    thr = sum(1 for s in scenes if per[s]['placed'] >= per[s]['total'] // 2 + 1)
    fill = sum(per[s]['metrics'].get('fill_volume', 0) for s in scenes) / len(scenes)
    soft = sum(per[s]['metrics'].get('soft_count', 0) for s in scenes)
    br = sum(per[s]['bridge'] for s in scenes)
    tmax = max(per[s]['max_s'] or 0 for s in scenes)
    tmean = sum(per[s]['metrics'].get('policy_time_mean', 0) for s in scenes) / len(scenes)
    wall = sum(per[s]['wall'] for s in scenes)
    c = r['counts']
    print(f"| {n} | {c.get('old_anchors',0)} | {c.get('slide_raw',0)} | {c.get('slide_clear',0)} | {c['legal']} | {c['into_vetoes']} | {c['survived']} | {br} | {placed} | {thr} | {fill:.3f} | {soft} | {tmean*1000:.0f} | {tmax:.2f} | {wall:.0f} |")
base = runs[0]['per']
for n, r in zip(names[1:], runs[1:]):
    diff = [(s, base[s]['placed'], r['per'][s]['placed'], r['per'][s]['bridge']) for s in scenes if base[s]['placed'] != r['per'][s]['placed'] or r['per'][s]['bridge']]
    print(n, diff)
