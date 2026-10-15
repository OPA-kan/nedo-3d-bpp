"""recall.py <armfile> <record_dir>... : on every board that ends on a decline
in the records, rebuilt from the settled poses (as bridge_scan.rebuild), the
bridge-family candidates the Layer 2 generator yields for the visible items:
old anchors only, with bridge_slide=0.02, and with bridge_plateau_exempt as
well.  Counted over the orientations the agent tries (layer2 order, first
max_orientations_layer2) and over all six."""
import collections, dataclasses, json, statistics, sys
WT = '/home/user/nedo-3d-bpp'
sys.path.insert(0, WT)
from bench.arms import make_arm
from bench.scenes import make_scene
from rule_alpha import layer1, layer2 as l2, classify as cls


def rebuild(path):
    r = json.load(open(path)); sp = r['scene_spec']; m = r['metrics']
    sc = make_scene(sp['seed'], sp['layout'], sp['task'])
    items = sc.items; byidx = {i['index']: i for i in items}
    placed = m['placed_count']
    steps = [s for s in r['steps'] if s.get('event') == 'step']
    ok = [s for s in steps if s.get('is_placed_safe')]
    placed_idx = {s['item_index'] for s in ok}
    final = {it['index']: it for it in r['final_items']}
    off = collections.defaultdict(list)
    for s in ok:
        f = final.get(s['item_index'])
        if f is not None and 'pos_local' in s:
            off[s['container_idx']].append(f['pos'][0] - s['pos_local'][0])
    off = {k: statistics.median(v) for k, v in off.items()}
    containers = [dict(c, packed_items=[]) for c in sc.containers]
    for s in ok:
        f = final.get(s['item_index'])
        if f is None or 'size' not in s:
            continue
        ci = s['container_idx']; it = byidx[s['item_index']]
        pos = [f['pos'][0] - off.get(ci, 0.0), f['pos'][1], f['pos'][2]]
        containers[ci]['packed_items'].append(
            {'index': s['item_index'], 'pos': pos, 'dims': s['size'], 'is_soft': it['is_soft'],
             'is_prioritized': it['is_prioritized']})
    unplaced = [i for i in items if i['index'] not in placed_idx]
    if sp['task'] == 'C':
        visible = [i for i in items if i['index'] >= placed][:1]
    else:
        visible = unplaced[:int(sp.get('pool') or getattr(sc, 'look_ahead', 1) or 1)]
    return dict(scene=r['scene'], task=sp['task'], end=m['end_reason'], containers=containers,
                visible=visible, mg=placed - (m['total_items'] // 2 + 1))


def main():
  base = make_arm(open(sys.argv[1]).read().strip()).config
  cfgs = {
      'old': dataclasses.replace(base, bridge_slide=0.0),
      'slide': dataclasses.replace(base, bridge_slide=0.02),
      'slide+exempt': dataclasses.replace(base, bridge_slide=0.02, bridge_plateau_exempt=True),
  }
  import glob
  for rec in sys.argv[2:]:
      tab = collections.Counter(); boards = 0; examples = []
      for path in sorted(glob.glob(f'{WT}/reports/bench/{rec}/[bc]-*.json')):
          ep = rebuild(path)
          if ep['end'] != 'declined':
              continue
          boards += 1
          hit = collections.Counter()
          for name, cfg in cfgs.items():
              board = layer1.Board([dict(c) for c in ep['containers']], cfg)
              for item in ep['visible']:
                  profile = cls.classify_item(item['index'], item, cfg)
                  if profile.cargo_class != cls.NORMAL_HARD:
                      continue
                  tried = cls.layer2_orientation_order(profile, cfg)[: cfg.max_orientations_layer2]
                  tried_idx = {o.index for o in tried}
                  for ci in range(len(ep['containers'])):
                      for o in profile.orientations:
                          out = layer1.generate_layer2_candidates(board, profile, ci, o, cfg)
                          nb = [c for c in out if c.family == l2.FAMILY_BRIDGE]
                          if not nb:
                              continue
                          hit[name + ':all'] += len(nb)
                          if o.index in tried_idx:
                              hit[name + ':tried'] += len(nb)
                          if name == 'slide+exempt' and len(examples) < 12 and o.index in tried_idx:
                              c = nb[0]
                              examples.append((ep['scene'], ep['mg'], [round(float(v), 3) for v in c.box.center],
                                               [round(float(v), 3) for v in c.box.size]))
          for k, v in hit.items():
              tab[k + ':boards'] += 1
              tab[k + ':cands'] += v
          if hit:
              print('   ', ep['scene'], 'mg', ep['mg'], dict(hit), flush=True)
      print(rec, 'declining boards', boards)
      for name in cfgs:
          print(f"  {name:13s} boards with a bridge candidate: tried poses {tab[name + ':tried:boards']:3d} "
                f"(cands {tab[name + ':tried:cands']}), any pose {tab[name + ':all:boards']:3d} (cands {tab[name + ':all:cands']})")
      for e in examples:
          print('   ', e)
      sys.stdout.flush()

if __name__ == '__main__':
    main()