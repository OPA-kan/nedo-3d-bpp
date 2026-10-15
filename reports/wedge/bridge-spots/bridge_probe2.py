"""bridge_probe2.py <armfile> <scene>... : why the bridge anchors never become
candidates.  Re-derives the plateau-merge proposals at every Layer 2 call and
puts each through the same validate() as _build_layer2, counting the refusal
reasons; also counts how many bridge proposals sit past the per-orientation
candidate cap once the terrace proposals have filled it."""
import collections, json, sys
sys.path.insert(0, '/home/user/nedo-3d-bpp')
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.analytic import run_analytic_episode
from rule_alpha import layer1, layer2 as l2, classify as cls

spec = open(sys.argv[1]).read().strip()
arm = make_arm(spec)
C = collections.Counter(); why = collections.Counter(); whyw = collections.Counter()

_gen = layer1.generate_layer2_candidates
def gen(board, profile, ci, orientation, config):
    out = _gen(board, profile, ci, orientation, config)
    if config.layer2_enabled and profile.cargo_class == cls.NORMAL_HARD:
        model = board.model(ci); container = board.container(ci)
        dx, dy, dz = orientation.dx, orientation.dy, orientation.dz
        tops = l2.hard_tops(container, model, config)
        n_terrace = sum(1 for c in out if c.family == l2.FAMILY_TERRACE)
        cap = config.max_candidates_per_orientation
        C['calls'] += 1
        if n_terrace >= cap:
            C['calls_cap_filled_by_terraces'] += 1
        for level, members in l2.level_groups(tops, config.layer2_bridge_level_tolerance):
            if level + dz > model.z_ceiling:
                C['anchors_over_ceiling_groups'] += 1
                continue
            anchors = l2.bridge_anchors(members, dx, dy)
            C['anchors'] += len(anchors)
            if n_terrace >= cap:
                C['anchors_past_cap'] += len(anchors)
            for x, y in anchors:
                box = layer1.AABB((float(x), float(y), float(level) + dz / 2.0), (dx, dy, dz), 'candidate')
                box = layer1._lifted(box, container, config)
                ok, w = layer1.validate(box, model, container, config)
                if ok:
                    C['anchors_legal'] += 1
                    # the members' own heights: a true bridge (both within contact) or a span over a lower one
                    tol = config.contact_tolerance
                    on = [m for m in members if abs(m[1] - level) <= tol]
                    C['legal_true_bridge' if len(on) >= 2 else 'legal_cantilever_over_lower'] += 1
                else:
                    why[w.split(':')[0]] += 1
                    whyw[w[:60]] += 1
    return out
layer1.generate_layer2_candidates = gen

for name in sys.argv[2:]:
    task, layout, s = name.split('-'); seed = int(s[1:]); task = task.upper()
    rec = run_analytic_episode(make_scene(seed, layout, task), arm)
    print(name, 'placed', rec['metrics']['placed_count'], '/', rec['metrics']['total_items'], flush=True)
print(json.dumps(dict(counts=dict(C), why=why.most_common(10), why_detail=whyw.most_common(12)), indent=1))
