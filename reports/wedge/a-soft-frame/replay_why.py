"""replay_why.py <repo> <armfile> <overrides> <layout> <seed>: a physics episode with the replay's misses explained
(the planned pose, the validator's verdicts over the nudges, and the settled neighbours' AABBs)."""
import sys, json, dataclasses
repo = sys.argv[1]; sys.path.insert(0, repo)
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.episode import run_episode
from rule_alpha import planner, layer1
from rule_alpha.geometry import AABB
from rule_alpha._reuse import packed_aabbs_local

spec = open(sys.argv[2]).read().strip() + "," + sys.argv[3]
arm = make_arm(spec)
orig = planner._replay
MISSES = []


def patched(agent, board, pool_profiles, plan_by_index):
    hit = orig(agent, board, pool_profiles, plan_by_index)
    config = agent.config
    # explain the planned items in the pool that were not replayed
    hit_index = None if hit is None else int(hit[1].placement.profile.index)
    for _pi, profile in pool_profiles:
        entry = plan_by_index.get(int(profile.index))
        if entry is None or int(profile.index) == hit_index:
            continue
        if hit is not None and entry.get("step", 0) > plan_by_index[hit_index].get("step", 0):
            continue
        ci = int(entry["container_idx"]); model = board.model(ci); container = board.container(ci)
        clearance = min(config.settled_clearance, float(getattr(config, "plan_replay_clearance", 0.02)))
        rc = dataclasses.replace(config, settled_clearance=clearance, transport_clearance=config.settled_clearance)
        size = tuple(entry["size"]); c = entry["center"]
        whys = {}
        for dx in (0.0, 0.01, -0.01, 0.02, -0.02):
            for dy in (0.0, 0.01, -0.01, 0.02, -0.02):
                ok, why = layer1.validate(AABB((c[0] + dx, c[1] + dy, c[2]), size, "plan"), model, container, rc)
                whys[why if not ok else "ok"] = whys.get(why if not ok else "ok", 0) + 1
        box = AABB(tuple(c), size, "plan")
        near = []
        for b, s, p in packed_aabbs_local(container):
            if (b.maximum[0] > box.minimum[0] - 0.08 and b.minimum[0] < box.maximum[0] + 0.08
                    and b.maximum[1] > box.minimum[1] - 0.08 and b.minimum[1] < box.maximum[1] + 0.08):
                near.append(f"[{b.minimum[0]:+.3f},{b.maximum[0]:+.3f}]x[{b.minimum[1]:+.3f},{b.maximum[1]:+.3f}]x[{b.minimum[2]:.3f},{b.maximum[2]:.3f}]")
        rec = dict(step=entry.get("step"), index=int(profile.index), planned=[round(v, 3) for v in c], size=size,
                   box=f"[{box.minimum[0]:+.3f},{box.maximum[0]:+.3f}]x[{box.minimum[1]:+.3f},{box.maximum[1]:+.3f}]",
                   whys=whys, near=near, packed=len(container.get("packed_items", [])))
        if len(MISSES) < 12:
            MISSES.append(rec)
            print("MISS", json.dumps(rec), flush=True, file=sys.stderr)
            if len(MISSES) <= 2:
                scan = []
                for dy in (0.0, -0.01, -0.02, -0.03, -0.04, -0.05, -0.06):
                    for dx in (0.0, 0.02, 0.04):
                        ok, why = layer1.validate(AABB((c[0] + dx, c[1] + dy, c[2]), size, "plan"), model, container, rc)
                        scan.append(f"dx{dx:+.2f} dy{dy:+.2f}: {'ok' if ok else why}")
                print("SCAN clearance", rc.settled_clearance, rc.transport_clearance, "replay_clearance",
                      getattr(config, "plan_replay_clearance", None), "nudge", getattr(config, "plan_replay_nudge", None),
                      "|", "; ".join(scan), flush=True, file=sys.stderr)
    return hit


planner._replay = patched
scene = make_scene(int(sys.argv[5]), sys.argv[4], "A")
rec = run_episode(scene, arm, policy_budget=4.5, with_shake=True)
m = rec["metrics"]
print("placed", m["placed_count"], "of", m["total_items"], "soft", m["soft_count"], "prio", m["priority_count"],
      "topples", m.get("shake_topples"), "end", m["end_reason"], "src", rec.get("plan_source"))
