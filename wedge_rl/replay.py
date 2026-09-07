"""Replay a wedge arrangement in the official simulator.

The environment scores placements with rule-alpha's analytic validator.  The
question that decides whether a learned staircase is worth anything is
whether PyBullet accepts the same boxes: inclusion, transport sweep, settle
without toppling, and how far each box slides once released.  This builds a
scene whose stream is exactly the boxes the policy placed, in order, and
drives ``bench.episode.run_episode`` with a scripted agent that commands the
planned poses.  Items the policy passed on are left out: in the real episode
they go elsewhere in the container, which this study is not about.
"""

from __future__ import annotations

import json
import pathlib
import random

import numpy as np

from bench.scenes import SKUS, Scene, make_scene
from rule_alpha import layer1

from .env import PASS, WedgeEnv

SKU_BY_NAME = {s[0]: s for s in SKUS}


def arrangement(env: WedgeEnv, policy, seed: int, rng=None) -> list[tuple[dict, object]]:
    """Run ``policy`` on one stream; the (item, candidate) pairs it placed."""
    env.reset(seed)
    rng = rng or random.Random(seed)
    placed = []
    while not env.done:
        item = env.item
        a = policy(env, rng)
        cands = env.candidates()
        if a != PASS and cands:
            placed.append((item, cands[a]))
        env.step(a)
    return placed


def scene_for(placed, layout: str, seed: int) -> Scene:
    """A Task C scene whose stream is the placed boxes, renumbered from zero."""
    base = make_scene(seed, layout, "C")
    items = []
    for new_index, (item, _cand) in enumerate(placed):
        _n, length, width, height, mass, soft, physics, _w = SKU_BY_NAME[item["sku"]]
        items.append({"index": new_index, "length": length, "width": width, "height": height,
                      "mass": mass, "is_prioritized": False, "is_soft": soft, **physics})
    return Scene(name=f"wedge-{layout}-s{seed:05d}", seed=seed, layout=layout, task="C",
                 look_ahead=1, items=items, containers=base.containers)


class ScriptedAgent:
    """Commands the planned pose for each item; declines anything unplanned."""

    def __init__(self, plan: dict, config):
        self.plan = plan
        self.config = config
        self.last_decision = None

    def get_init_states(self, init_states: dict):
        return True

    def optimize(self, item_list):
        return [int(i["index"]) for i in item_list]

    def policy(self, observation: dict):
        containers = observation.get("container_list", [])
        board = layer1.Board(containers, self.config)
        for pool_index, item in enumerate(observation.get("pool_list", [])):
            cand = self.plan.get(int(item["index"]))
            if cand is None:
                continue
            centre = layer1.action_center(cand.box, board.model(0), board.container(0), self.config)
            return {"item_idx": pool_index, "container_idx": 0,
                    "place_pos": np.asarray(centre, dtype=np.float32),
                    "orientation": int(cand.orientation)}
        return None


class ScriptedArm:
    def __init__(self, plan: dict, config, label: str):
        self.plan, self.config, self.label = plan, config, label

    def __call__(self, scene):
        return ScriptedAgent(self.plan, self.config)

    def describe(self) -> dict:
        return {"arm": f"scripted:{self.label}", "family": "scripted"}


def replay_episode(env: WedgeEnv, policy, seed: int, label: str, with_shake: bool = True) -> dict:
    """One stream: plan with ``policy``, replay in PyBullet, compare poses."""
    from bench.episode import run_episode

    placed = arrangement(env, policy, seed)
    planned_strip = float(sum(c.gain for _i, c in placed))
    row = {"seed": seed, "label": label, "planned": len(placed), "planned_strip": planned_strip,
           "planned_volume": float(sum(np.prod(c.dims) for _i, c in placed))}
    if not placed:
        row.update({"accepted": 0, "end_reason": "nothing-planned", "realized_strip": 0.0,
                    "xy_shift_max": 0.0, "z_anomaly_max": 0.0, "steps": []})
        return row
    plan = {i: c for i, (_item, c) in enumerate(placed)}
    scene = scene_for(placed, env.layout, seed)
    record = run_episode(scene, ScriptedArm(plan, env.config, label), max_steps=len(placed) + 1,
                         with_shake=with_shake)
    settled = {f["index"]: f for f in record["final_items"]}
    steps = []
    realized = 0.0
    for s in record["steps"]:
        if s.get("event") != "step":
            continue
        idx = int(s["item_index"])
        cand = plan[idx]
        ok = bool(s["is_included"] and s["is_valid"] and s["is_placed_safe"])
        entry = {"item": idx, "ok": ok, "strip_gain": cand.gain, "on_floor": cand.on_floor,
                 "bottom": cand.bottom, "reach": float(env.reach_of(cand.box))}
        fin = settled.get(idx)
        if fin is not None:
            place = np.asarray(s["place_pos"], dtype=np.float64)
            pos = np.asarray(fin["pos"], dtype=np.float64)
            # local and world frames share z (agent.agent.local_to_world only
            # shifts x), so the release lift is the commanded z minus the plan
            lift = float(place[2]) - float(cand.box.center[2])
            entry["xy_shift"] = float(np.hypot(*(pos[:2] - place[:2])))
            # how much further (or less) the box dropped than the release lift
            entry["z_anomaly"] = float(abs((place[2] - pos[2]) - lift))
            if ok:
                if env.region == "wedge":
                    # strip volume the settled pose still recovers: the same
                    # box shifted by what the simulator moved it in x
                    # (orientation changes are folded into the anomaly figures)
                    shifted = cand.box.minimum[0] + (pos[0] - place[0])
                    left = min(float(cand.box.maximum[0]) + (pos[0] - place[0]), env.model.x_floor_min) - shifted
                    realized += max(0.0, left) * float(cand.dims[1]) * float(cand.dims[2])
                else:
                    realized += cand.gain
        steps.append(entry)
    row.update({
        "accepted": sum(1 for e in steps if e["ok"]),
        "end_reason": record["metrics"]["end_reason"],
        "realized_strip": realized,
        "xy_shift_max": max((e.get("xy_shift", 0.0) for e in steps), default=0.0),
        "z_anomaly_max": max((e.get("z_anomaly", 0.0) for e in steps), default=0.0),
        "shake_proxy": record["metrics"].get("shake_proxy"),
        "steps": steps,
    })
    return row


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    planned = sum(r["planned"] for r in rows)
    accepted = sum(r["accepted"] for r in rows)
    steps = [e for r in rows for e in r["steps"]]
    overhang = [e for e in steps if not e["on_floor"] and e["strip_gain"] > 0]
    return {
        "episodes": n,
        "planned_per_episode": planned / max(n, 1),
        "accepted_per_episode": accepted / max(n, 1),
        "acceptance": accepted / max(planned, 1),
        "clean_episodes": sum(1 for r in rows if r["accepted"] == r["planned"]) / max(n, 1),
        "planned_strip": float(np.mean([r["planned_strip"] for r in rows])) if rows else 0.0,
        "realized_strip": float(np.mean([r["realized_strip"] for r in rows])) if rows else 0.0,
        "overhang_steps": len(overhang),
        "overhang_acceptance": (sum(1 for e in overhang if e["ok"]) / len(overhang)) if overhang else None,
        "end_reasons": {k: sum(1 for r in rows if r["end_reason"] == k)
                        for k in sorted({r["end_reason"] for r in rows})},
        "xy_shift_max": max((r["xy_shift_max"] for r in rows), default=0.0),
        "xy_shift_mean": float(np.mean([e["xy_shift"] for e in steps if "xy_shift" in e])) if steps else 0.0,
        "z_anomaly_max": max((r["z_anomaly_max"] for r in rows), default=0.0),
    }


def replay_many(env: WedgeEnv, policies: dict, seeds, out: pathlib.Path | None, with_shake: bool = True,
                log=print) -> dict:
    """Every policy on every seed; per-episode rows appended to ``out`` as they
    finish so an interrupted run can be resumed."""
    done = set()
    rows = []
    if out is not None and out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows.append(r)
                done.add((r["label"], r["seed"]))
    for label, policy in policies.items():
        for seed in seeds:
            if (label, seed) in done:
                continue
            row = replay_episode(env, policy, seed, label, with_shake=with_shake)
            rows.append(row)
            if out is not None:
                out.parent.mkdir(parents=True, exist_ok=True)
                with out.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row) + "\n")
            if log:
                log(f"[{label} s{seed}] planned {row['planned']} accepted {row['accepted']} "
                    f"strip {row['planned_strip']:.4f}->{row['realized_strip']:.4f} "
                    f"end {row['end_reason']} xy {row['xy_shift_max']:.3f}")
    return {label: summarize([r for r in rows if r["label"] == label]) for label in policies}
