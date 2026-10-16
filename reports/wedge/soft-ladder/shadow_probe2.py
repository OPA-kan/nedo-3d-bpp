"""shadow_probe2.py <record.json:step,step> ...: compact shadow-vs-official
table.  For each target step the record's action is replayed in the official
simulator; the shadow world is synced from the same observation and asked
about the same action as shipped, after a pre-settle of the synced world (60
and 300 steps), and with soft contacts warm-started (sync, then the packed
items' poses re-imposed after 60 steps).  One JSON line per case."""
import contextlib
import io
import json
import math
import os
import sys

import numpy as np

REPO = os.environ.get("REPO", "/home/user/nedo-3d-bpp")
sys.path.insert(0, REPO)
from bench.episode import load_env_class  # noqa: E402
from bench.scenes import make_scene  # noqa: E402
from rule_alpha import shadow as sh  # noqa: E402


def angle(q0, q1):
    d = min(1.0, abs(float(np.dot(q0, q1))))
    return math.degrees(2 * math.acos(d))


def shadow_variant(obs, ci, item, pos, orn_idx, pre=0, reimpose=False):
    sim = sh.ShadowSim()
    sim.sync(obs["container_list"])
    if pre:
        for _ in range(pre):
            sim.client.stepSimulation()
        if reimpose:
            for cj, c in enumerate(obs["container_list"]):
                for pk, body in zip(c["packed_items"], sim._containers[cj]["item_ids"]):
                    sim.client.resetBasePositionAndOrientation(body, tuple(float(v) for v in pk["pos"]),
                                                               sh._orientation_quaternion(pk))
                    sim.client.resetBaseVelocity(body, (0, 0, 0), (0, 0, 0))
    v = sim.check(ci, item, pos, orn_idx)
    return round(v["drift_xy"], 4), round(v["angle_deg"], 2), round(v["settled_local"][2] - pos[2], 4)


def main(path, steps):
    rec = json.load(open(path))
    sp = rec["scene_spec"]
    per = sp["item_count"] // (2 if sp["layout"].startswith("c2") else 1)
    scene = make_scene(sp["seed"], sp["layout"], sp["task"], **({} if sp["layout"] == "hard2" else {"items_per_container": per}))
    Env = load_env_class()
    sink = io.StringIO()
    acts = [s for s in rec["steps"] if s.get("event") == "step"]
    targets = sorted(int(s) for s in steps)
    with contextlib.redirect_stdout(sink):
        env = Env(config=scene.sim_config(policy_timeout=100.0), verbose=False, render_mode=None)
        env.reset_settings()
        env.reset_item_stream()
        obs, _ = env.reset(seed=42)
    for s in acts:
        k = int(s["step"])
        action = {"item_idx": int(s["pool_index"]), "container_idx": int(s["container_idx"]),
                  "place_pos": np.asarray(s["place_pos"], dtype=np.float32), "orientation": int(s["orientation"])}
        if k in targets:
            item = obs["pool_list"][action["item_idx"]]
            ci = action["container_idx"]
            offset_x = float(obs["container_list"][ci].get("center", (0, 0, 0))[0])
            pos = tuple(float(x) for x in action["place_pos"])
            row = {"scene": rec["scene"], "step": k, "soft": bool(item["is_soft"]), "arch": s.get("archetype")}
            row["shadow"] = shadow_variant(obs, ci, item, pos, action["orientation"])
            row["pre60"] = shadow_variant(obs, ci, item, pos, action["orientation"], pre=60)
            row["pre300"] = shadow_variant(obs, ci, item, pos, action["orientation"], pre=300)
            row["warm60"] = shadow_variant(obs, ci, item, pos, action["orientation"], pre=60, reimpose=True)
            with contextlib.redirect_stdout(sink):
                obs2, _r, term, trunc, info = env.step(action)
            st = (info or {}).get("status", {})
            got = None
            if obs2:
                for pk in obs2["container_list"][ci]["packed_items"]:
                    if int(pk["index"]) == int(item["index"]):
                        got = pk
            if got is not None:
                q_cmd = np.asarray(sh.p.getQuaternionFromEuler(sh.ORNS[action["orientation"]]))
                pw = np.asarray(got["pos"], float)
                row["official"] = (round(math.hypot(pw[0] - pos[0] - offset_x, pw[1] - pos[1]), 4),
                                   round(angle(q_cmd, np.asarray(got["orn"], float)), 2), round(pw[2] - pos[2], 4))
            else:
                row["official"] = None
            row["safe"] = st.get("is_placed_safe")
            print(json.dumps(row), flush=True)
            obs = obs2
        else:
            with contextlib.redirect_stdout(sink):
                obs, _r, term, trunc, info = env.step(action)
        if k >= targets[-1]:
            break
    with contextlib.suppress(Exception):
        env.close()


if __name__ == "__main__":
    args = []
    for arg in sys.argv[1:]:
        args.extend(open(arg[1:]).read().split() if arg.startswith("@") else [arg])
    for arg in args:
        f, _c, st = arg.partition(":")
        main(f, st.split(","))
