"""validate_sim.py <record> <scene> [...] -- the reach model against the official validator.

The record's actions are replayed in the official environment
(simulator/src/ground_handling, the bench's GroundHandlingEnv with the scene's
config).  Before the sealing placement of every patch (trace JSON) and at the end,
sampled spots of the patch are put to the official ``check_inclusion`` and
``check_transport_path`` (validator.py:85) with the visible item, commanded as the
agent commands a pose (floor +0.02, shelf +0.051, band escape).  Expected: open
spots pass before the sealer, fail after it, and fail at the end.  Also checks
that the replay reproduces the record's settled poses.
Writes $SCRATCH/vsim/<record>/<scene>.json.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sealkit as K  # noqa: E402
from bench.episode import load_env_class  # noqa: E402

SCRATCH = os.environ.get("SCRATCH", "/home/user/inv-G-scratch")


def orn_for(item, fx, fy, h):
    from ground_handling.utils import get_half_ext

    lwh = [item.length, item.width, item.height]
    for o in range(6):
        he = get_half_ext(lwh, o)
        if all(abs(2 * a - b) < 1e-4 for a, b in zip(he, (fx, fy, h))):
            return o
    return None


def commanded_centre(cont, cx, cy, z, h, on_floor, on_shelf):
    H = float(cont["height"])
    T = float(cont["thickness"])
    B = float(cont.get("buffer", 0.0))
    if on_floor:
        bottom = z + K.FLOOR_LIFT
    elif on_shelf:
        bottom = z + K.SHELF_LIFT
    else:
        bottom = z
        band = H / 2 + T + B
        if band - 0.003 <= bottom <= band + 0.053:
            bottom = band + 0.053
    return (cx, cy, bottom + h / 2)


def check(env, ci, item, spots, patch, cont):
    validator = env.validator
    container = env.container_manager.get_container(ci)
    out = []
    for cx, cy, tl, ts, it_idx, fx, fy, h in spots:
        o = orn_for(item, fx, fy, h)
        if o is None:
            out.append(dict(spot=[cx, cy], err="orientation"))
            continue
        local = commanded_centre(
            cont, cx, cy, patch["z"], h, patch["on_floor"], patch["on_shelf"]
        )
        g = container.local_to_global(tuple(float(v) for v in local))
        sink = io.StringIO()
        state = env.client.saveState()
        try:
            with contextlib.redirect_stdout(sink):
                inc = bool(validator.check_inclusion(container, item, g, o))
                val = (
                    bool(validator.check_transport_path(container, item, g, o))
                    if inc
                    else None
                )
        finally:
            if item.pybullet_id is not None:
                item.remove(env.client)
            env.client.restoreState(stateId=state)
            env.client.removeState(state)
        log = sink.getvalue()
        hit = [ln for ln in log.splitlines() if ln.startswith("collision")][:1]
        out.append(
            dict(
                spot=[cx, cy],
                tl=tl,
                ts=ts,
                inc=inc,
                valid=val,
                hit=hit[0][:120] if hit else "",
            )
        )
    return out


def main():
    rec_name = sys.argv[1]
    for scene in sys.argv[2:]:
        rec = K.load_record(rec_name, scene)
        ep = K.Episode(rec)
        tr = json.load(open(os.path.join(SCRATCH, "trace", rec_name, scene + ".json")))
        Env = load_env_class()
        sink = io.StringIO()
        res = dict(scene=scene, checks=[])
        with contextlib.redirect_stdout(sink):
            env = Env(
                config=ep.scene.sim_config(policy_timeout=8.0),
                verbose=False,
                render_mode=None,
            )
            env.reset_settings()
            env.get_init_states()
            env.reset_item_stream()
            obs, _ = env.reset(seed=42)
        # checkpoints: before each patch's sealer (prefix seal_t) and after it, and the end
        cps = {}
        for n, p in enumerate(tr["patches"]):
            t = p.get("seal_t") if p["kind"] == "sealed-after-open" else None
            if t is not None:
                cps.setdefault(t, []).append((n, "before"))
                cps.setdefault(t + 1, []).append((n, "after"))
        T = len(ep.placements)
        steps = [
            s
            for s in rec["steps"]
            if s.get("event") == "step" and s.get("is_placed_safe")
        ]
        for t in range(T + 1):
            for n, when in cps.get(t, []) + (
                [(n, "end") for n in range(len(tr["patches"]))] if t == T else []
            ):
                p = tr["patches"][n]
                vis = {v["idx"] for v in tr["visible"]}
                # the item: on C the next stream item (pool 0); on B the pool item of the spot
                spots = p["spots_xy"]
                take = spots[:: max(1, len(spots) // 12)][:12]
                for s in take:
                    pool = env.stream_manager.visible_pool
                    item = next((it for it in pool if it.index == s[4]), None) or next((it for it in env.stream_manager.all_items if it.index == s[4] and it.pybullet_id is None), None)
                    if item is None:
                        res["checks"].append(
                            dict(
                                patch=n, when=when, t=t, err=f"item {s[4]} not in pool"
                            )
                        )
                        continue
                    r = check(env, p["ci"], item, [s], p, ep.raw_containers[p["ci"]])[0]
                    res["checks"].append(dict(patch=n, when=when, t=t, **r))
            if t == T:
                break
            s = steps[t]
            act = {
                "item_idx": int(s["pool_index"]),
                "container_idx": int(s["container_idx"]),
                "orientation": int(s["orientation"]),
                "place_pos": np.asarray(s["place_pos"], dtype=np.float32),
            }
            with contextlib.redirect_stdout(sink):
                obs, _r, term, trunc, info = env.step(act)
            st = (info or {}).get("status", {})
            if not (
                st.get("is_included")
                and st.get("is_valid")
                and st.get("is_placed_safe")
            ):
                res["replay_failed_at"] = t
                break
        # replay fidelity: settled poses against the record's
        fin = {it["index"]: it["pos"] for it in rec["final_items"]}
        dev = []
        for c in (
            env.container_manager.containers
            if hasattr(env.container_manager, "containers")
            else []
        ):
            for it in c.packed_items:
                if it.pybullet_id is None or it.index not in fin:
                    continue
                pos, _o = it.get_pose(env.client)
                g = np.asarray(pos)
                dev.append(float(np.abs(g - np.asarray(fin[it.index])).max()))
        res["replay_max_dev"] = max(dev) if dev else None
        res["replay_n"] = len(dev)
        od = os.path.join(SCRATCH, "vsim", rec_name)
        os.makedirs(od, exist_ok=True)
        json.dump(
            res, open(os.path.join(od, scene + ".json"), "w"), indent=1, default=str
        )
        agg = {}
        for c in res["checks"]:
            k = c.get("when")
            a = agg.setdefault(k, [0, 0, 0])
            if c.get("valid") is True:
                a[0] += 1
            elif c.get("valid") is False:
                a[1] += 1
            else:
                a[2] += 1
        print(
            f"{scene}: replay dev {res['replay_max_dev']} n {res['replay_n']} failed_at {res.get('replay_failed_at')} | "
            + " ".join(
                f"{k}: valid {v[0]} refused {v[1]} other {v[2]}" for k, v in agg.items()
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
