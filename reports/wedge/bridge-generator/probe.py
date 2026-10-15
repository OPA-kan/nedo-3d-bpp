"""probe.py <out.json> <armspec-file> <extra-overrides> <scene>... :
bridge anchors offered / legal / surviving / chosen under the analytic arm."""
import collections, json, sys, time
sys.path.insert(0, '/home/user/nedo-3d-bpp')
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.analytic import run_analytic_episode
from rule_alpha import layer1, layer2 as l2, classify as cls

out_path, arm_file, extra = sys.argv[1], sys.argv[2], sys.argv[3]
spec = open(arm_file).read().strip()
if extra and extra != '-':
    spec = spec + ',' + extra
arm = make_arm(spec)
C = collections.Counter()
drops = collections.Counter()

_bsa = l2.bridge_slide_anchors
def bsa(*a, **k):
    out = _bsa(*a, **k); C['slide_raw'] += len(out); return out
l2.bridge_slide_anchors = bsa
_clr = l2.clear_of_obstacles
def clr(*a, **k):
    out = _clr(*a, **k); C['slide_clear'] += int(out.sum()); return out
l2.clear_of_obstacles = clr

_gen = layer1.generate_layer2_candidates
def gen(board, profile, ci, orientation, config):
    out = _gen(board, profile, ci, orientation, config)
    if config.layer2_enabled and profile.cargo_class == cls.NORMAL_HARD:
        C['calls'] += 1
        model = board.model(ci); container = board.container(ci)
        tops = l2.hard_tops(container, model, config)
        for level, members in l2.level_groups(tops, config.layer2_bridge_level_tolerance):
            if level + orientation.dz > model.z_ceiling:
                continue
            C['old_anchors'] += len(l2.bridge_anchors(members, orientation.dx, orientation.dy))
        C['legal'] += sum(1 for c in out if c.family == l2.FAMILY_BRIDGE)
    return out
layer1.generate_layer2_candidates = gen

_av = layer1.apply_vetoes
def av(cands, board, ci, config):
    nb_in = [c for c in cands if c.family == l2.FAMILY_BRIDGE]
    surv, counts = _av(cands, board, ci, config)
    C['into_vetoes'] += len(nb_in)
    for c in nb_in:
        for r in c.vetoes:
            drops[r] += 1
    sb = [c for c in surv if c.family == l2.FAMILY_BRIDGE]
    C['survived'] += len(sb)
    C['calls_with_survivor'] += 1 if sb else 0
    return surv, counts
layer1.apply_vetoes = av

per = {}
chosen_all = collections.Counter()
for name in sys.argv[4:]:
    task, layout, s = name.split('-'); seed = int(s[1:]); task = task.upper()
    t0 = time.time()
    rec = run_analytic_episode(make_scene(seed, layout, task), arm)
    wall = time.time() - t0
    ch = collections.Counter(str(st.get('archetype')) for st in rec['steps'] if st.get('event') == 'step')
    chosen_all.update(ch)
    secs = [st.get('policy_seconds', st.get('seconds')) for st in rec['steps'] if st.get('event') == 'step']
    secs = [x for x in secs if isinstance(x, (int, float))]
    m = rec['metrics']
    per[name] = dict(placed=m['placed_count'], total=m['total_items'], bridge=ch.get('plateau-merge', 0),
                     wall=round(wall, 1), max_s=round(max(secs), 3) if secs else None,
                     metrics={k: v for k, v in m.items() if isinstance(v, (int, float))})
    print(name, per[name]['placed'], '/', per[name]['total'], 'bridge', per[name]['bridge'], 'wall', per[name]['wall'], 'max_s', per[name]['max_s'], flush=True)
json.dump(dict(spec_extra=extra, counts=dict(C), drops=drops.most_common(), chosen=chosen_all.most_common(), per=per),
          open(out_path, 'w'), indent=1)
print(json.dumps(dict(counts=dict(C), drops=drops.most_common(), bridge_chosen=chosen_all.get('plateau-merge', 0))))
