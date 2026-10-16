"""probe2.py: two-high standing soft with the floor share met (non-priority boxes only), and the ledge."""
import sys, contextlib, io, copy
repo = sys.argv[1]; sys.path.insert(0, repo)
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.episode import load_env_class
from rule_alpha import layer1, classify as cls, stability
from rule_alpha.planner import _try_pose, _flat_poses, _standing_poses, _Pose, _placement
spec = open(sys.argv[2]).read().strip() + ",offline_budget_seconds=30"
arm = make_arm(spec); Env = load_env_class()
scene = make_scene(int(sys.argv[4]), sys.argv[3], "A")
with contextlib.redirect_stdout(io.StringIO()):
    env = Env(config=scene.sim_config(policy_timeout=8.0), verbose=False, render_mode=None)
    env.reset_settings(); agent = arm(scene); agent.get_init_states(env.get_init_states())
    items = env.get_info_for_optimization()
config = agent.config; agent.plan_source = "planner"
agent.profiles = {int(i["index"]): cls.classify_item(int(i["index"]), i, config) for i in items}
cs = copy.deepcopy(agent.board.containers)
for c in cs: c.setdefault("packed_items", [])
board = layer1.Board(cs, config); model = board.model(0); rect = model.floor_rect
gap = config.settled_clearance + config.anchor_slack; wall = config.inclusion_clearance + config.anchor_slack
def put(p, o, x, y, label, bottom=None):
    box, why = _try_pose(board, 0, p, o, x, y, config, None, bottom=bottom)
    if box is None:
        print(f"  {label}: REFUSED {why} at ({x:+.2f},{y:+.2f}) {o.dx}x{o.dy}x{o.dz}"); return None
    pl = _placement(_Pose(box, o, model.z_floor), 1, p, 0, model); pl.step = len(board.container(0)["packed_items"]) + 1
    board.apply(pl); print(f"  {label}: ok bot {box.minimum[2]:.2f} top {box.maximum[2]:.2f} at ({x:+.2f},{y:+.2f}) {o.dx}x{o.dy}x{o.dz}"); return box
soft = [p for p in agent.profiles.values() if p.is_soft and not p.is_prioritized]
big = [p for p in soft if abs(p.orientations[0].dx - 0.65) < 1e-9]
mid = [p for p in soft if abs(p.orientations[0].dx - 0.60) < 1e-9]
sml = [p for p in soft if abs(p.orientations[0].dx - 0.45) < 1e-9]
print(len(big), len(mid), len(sml))
o = next(oo for oo in _standing_poses(big[0]) if abs(oo.dx - 0.23) < 1e-9 and abs(oo.dz - 0.65) < 1e-9)
om = next(oo for oo in _standing_poses(mid[0]) if abs(oo.dx - 0.25) < 1e-9 and abs(oo.dz - 0.60) < 1e-9)
k = 0; bases = []
for row in range(2):
    y = rect.y_max - config.anchor_slack - o.dy / 2 - row * (o.dy + gap)
    x = rect.x_min + wall + o.dx / 2
    while x + o.dx / 2 <= rect.x_max - config.anchor_slack and k < len(big):
        if put(big[k], o, x, y, f"stand row{row+1} #{k}"): bases.append((x, y, big[k]))
        k += 1; x += o.dx + gap
print("  floor share", round(stability.soft_floor_share(board.container(0)), 3))
for n, (x, y, p0) in enumerate(bases[1:4]):
    pass
    put(mid[n], om, x, y, f"stand on stand #{n}")
# the ledge: standing boxes over the small shelf
for n, y in enumerate((rect.y_max - config.anchor_slack - o.dy / 2 - r * (o.dy + gap) for r in range(3))):
    p = mid[n]
    put(p, om, model.x_wall_min + wall + om.dx / 2, y, f"ledge #{n}", bottom=float(model.small_shelf.maximum[2]))
# a third row of mid boxes standing
k2 = 3
y = rect.y_max - config.anchor_slack - 2 * (o.dy + gap) - om.dy / 2
x = rect.x_min + wall + om.dx / 2
while x + om.dx / 2 <= rect.x_max - config.anchor_slack and k2 < len(mid):
    put(mid[k2], om, x, y, f"stand row3 mid #{k2}")
    k2 += 1; x += om.dx + gap
