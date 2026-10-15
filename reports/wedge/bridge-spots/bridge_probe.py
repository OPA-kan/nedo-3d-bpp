"""bridge_probe.py <armfile> <scene> ... : where the plateau-merge (bridge)
candidates die.  Runs the analytic episode with layer1's generator and veto
pass wrapped: bridge-family candidates generated, entering the veto pass
(after the shortlist), dropped by reason, surviving, surviving with the
plateau-merge tag; and the archetype actually chosen at those calls."""
import collections, json, sys
sys.path.insert(0, '/home/user/nedo-3d-bpp')
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.analytic import run_analytic_episode
from rule_alpha import layer1, layer2 as l2

spec = open(sys.argv[1]).read().strip()
arm = make_arm(spec)
C = collections.Counter()
calls = collections.Counter()
drops = collections.Counter()

_gen = layer1.generate_layer2_candidates
def gen(board, profile, ci, orientation, config):
    out = _gen(board, profile, ci, orientation, config)
    nb = sum(1 for c in out if c.family == l2.FAMILY_BRIDGE)
    C['generated'] += nb
    C['generated_wedge_bridge'] += sum(1 for c in out if c.family == l2.FAMILY_WEDGE_BRIDGE)
    C['generated_terrace'] += sum(1 for c in out if c.family == l2.FAMILY_TERRACE)
    # the raw anchors, before validation: how many pairs the grouping offers
    model = board.model(ci); container = board.container(ci)
    tops = l2.hard_tops(container, model, config)
    groups = l2.level_groups(tops, config.layer2_bridge_level_tolerance)
    C['tops'] += len(tops); C['groups'] += len(groups)
    C['groups_with_pair'] += sum(1 for _lv, m in groups if len(m) >= 2)
    for _lv, m in groups:
        if len(m) >= 2:
            C['bridge_anchors'] += len(l2.bridge_anchors(m, orientation.dx, orientation.dy))
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
    C['survived_tagged'] += sum(1 for c in sb if layer1.A_BRIDGE in c.archetypes)
    if sb:
        calls['calls_with_bridge_survivor'] += 1
    calls['calls'] += 1
    return surv, counts
layer1.apply_vetoes = av

chosen = collections.Counter()
for name in sys.argv[2:]:
    task, layout, s = name.split('-'); seed = int(s[1:]); task = task.upper()
    scene = make_scene(seed, layout, task)
    rec = run_analytic_episode(scene, arm)
    for st in rec['steps']:
        if st.get('event') == 'step':
            chosen[str(st.get('archetype'))] += 1
    print(name, 'placed', rec['metrics']['placed_count'], '/', rec['metrics']['total_items'], flush=True)
print(json.dumps(dict(counts=dict(C), calls=dict(calls), drop_reasons=drops.most_common(), chosen=chosen.most_common(12)), indent=1))
