"""two_contacts.py <armfile> <record> <scene>: the scan's accepted two-contact
poses on one board, what each contact is, and the cover rule's verdict."""
import collections, json, sys
sys.path.insert(0, '/home/user/nedo-3d-bpp/reports/wedge/bridge-generator')
from recall import rebuild, WT, make_arm, layer1, l2, cls
from rule_alpha import stability
from rule_alpha._reuse import packed_aabbs_local, shelf_aabbs
cfg = make_arm(open(sys.argv[1]).read().strip()).config
rows = json.load(open(f'{WT}/reports/wedge/bridge-spots/bridge_scan.json'))
r = next(r for r in rows if r['record'] == sys.argv[2] and r['scene'] == sys.argv[3])
ep = rebuild(f"{WT}/reports/bench/{r['record']}/{r['scene']}.json")
board = layer1.Board(ep['containers'], cfg)
seen = collections.Counter()
for it in r['items']:
    for p in it.get('poses', []):
        ci = p['ci']; model = board.model(ci); container = board.container(ci)
        box = layer1.AABB((p['x'], p['y'], p['z'] + p['h'] / 2.0), (p['fx'], p['fy'], p['h']), 'c')
        if not layer1.validate(box, model, container, cfg)[0]:
            continue
        st = stability.evaluate(box, container, cfg)
        if st.contact_count < 2:
            continue
        kinds = []
        for b, soft, prio in packed_aabbs_local(container):
            if abs(float(b.maximum[2]) - p['z']) <= cfg.contact_tolerance:
                w = min(b.maximum[0], box.maximum[0]) - max(b.minimum[0], box.minimum[0])
                h = min(b.maximum[1], box.maximum[1]) - max(b.minimum[1], box.minimum[1])
                if w > 0 and h > 0:
                    kinds.append(('S' if soft else 'P' if prio else 'H') + f"{float(b.maximum[2]):.3f}")
        for s in shelf_aabbs(container):
            if abs(float(s.maximum[2]) - p['z']) <= cfg.contact_tolerance:
                kinds.append('shelf')
        cover = layer1._covers_other_attribute(box, container, it['soft'], False, shelves=model.shelves)
        seen[(tuple(sorted(kinds)), 'covers-other' if cover else 'cover-ok', 'soft' if it['soft'] else 'hard',
              (p['fx'], p['fy'], p['h']))] += 1
for k, v in seen.most_common():
    print(v, k)
