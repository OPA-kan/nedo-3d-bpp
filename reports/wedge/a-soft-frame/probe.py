"""probe.py <repo> <armfile> <layout> <seed>: what soft-on-soft stacks the analytic model allows in a back region."""
import sys, time, contextlib, io, dataclasses
repo = sys.argv[1]
sys.path.insert(0, repo)
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.episode import load_env_class
from rule_alpha import layer1, classify as cls, stability
from rule_alpha.planner import _try_pose, _flat_poses, _standing_poses, plan_packing
import copy

spec = open(sys.argv[2]).read().strip() + ",offline_budget_seconds=30"
arm = make_arm(spec)
Env = load_env_class()
scene = make_scene(int(sys.argv[4]), sys.argv[3], "A")
with contextlib.redirect_stdout(io.StringIO()):
    env = Env(config=scene.sim_config(policy_timeout=8.0), verbose=False, render_mode=None)
    env.reset_settings()
    agent = arm(scene)
    agent.get_init_states(env.get_init_states())
    items = env.get_info_for_optimization()
config = agent.config
print("caps", stability.SOFT_STRUCTURE_MAX_TOP, stability.SOFT_STRUCTURE_FLOOR_SHARE, "soft_is_structure", config.soft_is_structure)
agent.plan_source = "planner"
agent.profiles = {int(i["index"]): cls.classify_item(int(i["index"]), i, config) for i in items}
containers = copy.deepcopy(agent.board.containers)
for c in containers:
    c.setdefault("packed_items", [])
board = layer1.Board(containers, config)
model = board.model(0)
rect = model.floor_rect
print("floor", rect.as_tuple(), "z", model.z_floor, model.z_ceiling, "area", round(rect.area, 3))
profiles = agent.profiles
soft = [p for p in profiles.values() if p.is_soft]
by_dims = {}
for p in soft:
    o = p.orientations[0]
    by_dims.setdefault(tuple(sorted((o.dx, o.dy, o.dz))), []).append(p)
for k, v in by_dims.items():
    print("soft class", k, len(v), [ (o.dx, o.dy, o.dz) for o in v[0].orientations])

gap = config.settled_clearance + config.anchor_slack
wall = config.inclusion_clearance + config.anchor_slack


def put(board, p, o, x, y, label):
    box, why = _try_pose(board, 0, p, o, x, y, config, None)
    if box is None:
        print(f"  {label}: REFUSED {why} at ({x:+.2f},{y:+.2f}) {o.dx}x{o.dy}x{o.dz}")
        return None
    from rule_alpha.planner import _Pose, _placement
    cand = _Pose(box, o, model.z_floor)
    pl = _placement(cand, 1, p, 0, model)
    pl.step = len(board.container(0)["packed_items"]) + 1
    board.apply(pl)
    print(f"  {label}: ok bot {box.minimum[2]:.2f} top {box.maximum[2]:.2f} at ({x:+.2f},{y:+.2f}) {o.dx}x{o.dy}x{o.dz}")
    return box


def fresh():
    cs = copy.deepcopy(agent.board.containers)
    for c in cs:
        c.setdefault("packed_items", [])
    return layer1.Board(cs, config)


big = [p for p in soft if abs(p.orientations[0].dx * p.orientations[0].dy * p.orientations[0].dz - 0.0523) < 1e-3]
print("\n== flat stacks of 0.65x0.35x0.23 at the back wall, 4 columns along x (floor share first)")
b = fresh()
x0 = rect.x_min + wall + 0.65 / 2
y0 = rect.y_max - config.anchor_slack - 0.35 / 2
cols = []
k = 0
for cx in (x0, x0 + 0.65 + gap, x0 + 2 * (0.65 + gap)):
    for cy in (y0, y0 - 0.35 - gap):
        o = next(oo for oo in _flat_poses(big[k]) if abs(oo.dx - 0.65) < 1e-9)
        if put(b, big[k], o, cx, cy, f"floor col {len(cols)}"):
            cols.append((cx, cy))
        k += 1
print("  floor share", round(stability.soft_floor_share(b.container(0)), 3))
for layer in (2, 3, 4):
    for n, (cx, cy) in enumerate(cols):
        if k >= len(big):
            break
        o = next(oo for oo in _flat_poses(big[k]) if abs(oo.dx - 0.65) < 1e-9)
        put(b, big[k], o, cx, cy, f"layer {layer} col {n}")
        k += 1

print("\n== standing 0.65x0.35x0.23 (0.65 tall) rows at the back wall, then a second standing layer, then flat on top")
b = fresh()
st = [o for o in _standing_poses(big[0]) if abs(o.dz - 0.65) < 1e-9]
print("  standing poses", [(o.dx, o.dy, o.dz) for o in st])
o = next(oo for oo in st if abs(oo.dx - 0.23) < 1e-9)   # 0.23 along x, 0.35 deep
k = 0
bases = []
y = rect.y_max - config.anchor_slack - o.dy / 2
x = rect.x_min + wall + o.dx / 2
while x + o.dx / 2 <= rect.x_max - config.anchor_slack and k < len(big):
    if put(b, big[k], o, x, y, f"stand row1 #{k}"):
        bases.append((x, y))
    k += 1
    x += o.dx + gap
print("  floor share", round(stability.soft_floor_share(b.container(0)), 3))
for n, (x, y) in enumerate(bases):
    if k >= len(big):
        break
    put(b, big[k], o, x, y, f"stand on stand #{n}")
    k += 1
# a flat one on the standing tops
of = next(oo for oo in _flat_poses(big[0]) if abs(oo.dx - 0.65) < 1e-9)
put(b, big[min(k, len(big) - 1)], of, bases[1][0], y, "flat on standing tops")

print("\n== standing rows: two rows then flat on top")
b = fresh()
k = 0
bases = []
for row in range(2):
    y = rect.y_max - config.anchor_slack - o.dy / 2 - row * (o.dy + gap)
    x = rect.x_min + wall + o.dx / 2
    while x + o.dx / 2 <= rect.x_max - config.anchor_slack and k < len(big):
        if put(b, big[k], o, x, y, f"stand row{row+1} #{k}"):
            bases.append((x, y))
        k += 1
        x += o.dx + gap
print("  floor share", round(stability.soft_floor_share(b.container(0)), 3))
put(b, big[min(k, len(big) - 1)], of, bases[1][0], bases[0][1], "flat on standing tops row1")
put(b, big[min(k, len(big) - 1)], of, bases[1][0] + 0.65 + gap, bases[0][1], "flat on standing tops row1 b")

print("\n== two flat layers then standing on top")
b = fresh()
k = 0
cols = []
for cx in (x0, x0 + 0.65 + gap):
    for cy in (y0, y0 - 0.35 - gap):
        if put(b, big[k], of, cx, cy, f"floor col {len(cols)}"):
            cols.append((cx, cy))
        k += 1
for n, (cx, cy) in enumerate(cols):
    put(b, big[k], of, cx, cy, f"layer 2 col {n}")
    k += 1
for n, (cx, cy) in enumerate(cols[:2]):
    put(b, big[k], o, cx - 0.65 / 2 + o.dx / 2, cy, f"standing on layer 2 col {n} a")
    k += 1
    put(b, big[k], o, cx - 0.65 / 2 + o.dx / 2 + o.dx + gap, cy, f"standing on layer 2 col {n} b")
    k += 1

print("\n== plan_packing with log")
lines = []
t0 = time.perf_counter()
order, plan = plan_packing(agent, items, time.perf_counter() + 30, log=lambda s: lines.append(s))
print("planned", len(plan), round(time.perf_counter() - t0, 1), "s", getattr(agent, "count_secure_log", None))
for s in lines:
    if "[typed]" in s and ("planned" in s or "refusals" in s or "row at" in s) or "[plan] variant" in s or "count-secure" in s:
        print(s)
