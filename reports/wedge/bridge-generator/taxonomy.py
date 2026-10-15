"""taxonomy.py <armfile-C> <armfile-B> : the scan's bridge-only declining boards
(bridge_scan.json), split by what the validator-accepted poses rest on (one
contact: an overhang off one top; two or more: a true bridge), whether the
visible item is hard, and whether the Layer 2 generator offers a bridge-family
candidate on the board: old anchors, slide (all poses), slide + plateau exemption."""
import collections, dataclasses, json, sys
sys.path.insert(0, '/home/user/nedo-3d-bpp/reports/wedge/bridge-generator')
from recall import rebuild, WT, make_arm, layer1, l2, cls
from rule_alpha import stability

cfg_c = make_arm(open(sys.argv[1]).read().strip()).config
cfg_b = make_arm(open(sys.argv[2]).read().strip()).config
rows = json.load(open(f'{WT}/reports/wedge/bridge-spots/bridge_scan.json'))
tab = collections.defaultdict(collections.Counter)
for r in rows:
    if r['any_full'] > 0 or r['any_bridge'] == 0:
        continue
    rec = r['record']
    base = cfg_b if r['task'] == 'B' else cfg_c
    ep = rebuild(f"{WT}/reports/bench/{rec}/{r['scene']}.json")
    board = layer1.Board(ep['containers'], base)
    legal, two, hard_two = 0, 0, 0
    for it in r['items']:
        for p in it.get('poses', []):
            ci = p['ci']; model = board.model(ci); container = board.container(ci)
            box = layer1.AABB((p['x'], p['y'], p['z'] + p['h'] / 2.0), (p['fx'], p['fy'], p['h']), 'c')
            ok, _ = layer1.validate(box, model, container, base)
            if not ok:
                continue
            legal += 1
            n = stability.evaluate(box, container, base).contact_count
            if n >= 2:
                two += 1
                if not it['soft']:
                    hard_two += 1
    t = tab[rec]
    t['bridge-only boards'] += 1
    t['accepted pose'] += legal > 0
    t['accepted, two contacts'] += two > 0
    t['accepted, two contacts, hard item'] += hard_two > 0
    # the generator on this board, every pose of every visible hard item
    gen = collections.Counter()
    for name, cfg in (('old', dataclasses.replace(base, bridge_slide=0.0)),
                      ('slide', dataclasses.replace(base, bridge_slide=0.02)),
                      ('slide+exempt', dataclasses.replace(base, bridge_slide=0.02, bridge_plateau_exempt=True))):
        b2 = layer1.Board([dict(c) for c in ep['containers']], cfg)
        for item in ep['visible']:
            profile = cls.classify_item(item['index'], item, cfg)
            if profile.cargo_class != cls.NORMAL_HARD:
                continue
            for ci in range(len(ep['containers'])):
                for o in profile.orientations:
                    out = layer1.generate_layer2_candidates(b2, profile, ci, o, cfg)
                    gen[name] += sum(1 for c in out if c.family == l2.FAMILY_BRIDGE)
    for name in ('old', 'slide', 'slide+exempt'):
        t['generator offers a bridge: ' + name] += gen[name] > 0
    print(rec, r['scene'], 'mg', r['mg'], 'legal', legal, 'two', two, 'hard_two', hard_two, dict(gen), flush=True)
print()
keys = ['bridge-only boards', 'accepted pose', 'accepted, two contacts', 'accepted, two contacts, hard item',
        'generator offers a bridge: old', 'generator offers a bridge: slide', 'generator offers a bridge: slide+exempt']
print('| record | ' + ' | '.join(keys) + ' |')
print('|---|' + '---:|' * len(keys))
for rec in sorted(tab):
    print(f'| {rec} | ' + ' | '.join(str(tab[rec][k]) for k in keys) + ' |')
