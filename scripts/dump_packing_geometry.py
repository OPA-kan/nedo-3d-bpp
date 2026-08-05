"""
Replay a case to termination and dump the geometry of what got packed.

The output is what the section drawings are built from, and it is
deliberately raw: the container's published half-spaces, the shelf AABBs the
agent derives from `cut_x` and the shelf flag, and every settled item AABB
as `packed_aabbs_local` reports it. Nothing is normalised or idealised --
the point of looking at these boards is that the envelope is not the box
`length x width x height` implies.

Two fields exist because reading them wrong cost a wrong conclusion:

  offset_x   `points`/`n_vecs` live in a frame offset in x, while items are
             local. Without it the second container's outline is drawn 2.5 m
             away from its contents.
  shelf      `container_requires_shelf` reads the `shelf` key first and only
             then `require_shelf`; asking for `require_shelf` directly
             reports False for a container that has a main shelf.

Usage:
    python scripts/dump_packing_geometry.py CONFIG CASE_ID OUTPUT.json
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "simulator"))

from scripts.measure_anchor_recall import (  # noqa: E402
    load_agent_module,
    policy_observation,
)
from src.ground_handling.env import GroundHandlingEnv  # noqa: E402


def dump(config_path, case_key, output_path):
    agent_module = load_agent_module()
    config = json.loads(pathlib.Path(config_path).read_text(encoding="utf-8"))
    case = config.get(case_key) or next(iter(config.values()))
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = agent_module.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)

    step = 0
    try:
        while True:
            observation = policy_observation(env, raw)
            action = solver.policy(observation)
            if solver.last_action_source == "unsafe_protocol_fallback":
                break
            raw, _reward, terminated, truncated, info = env.step(action)
            status = (info or {}).get("status", {})
            step += 1
            if not all(
                bool(status.get(flag))
                for flag in ("is_included", "is_valid", "is_placed_safe")
            ):
                break
            if terminated or truncated:
                break
    finally:
        observation = policy_observation(env, raw)
        containers = []
        for index, container in enumerate(observation["container_list"]):
            items = []
            for packed, is_soft, is_prioritized in agent_module.packed_aabbs_local(
                container
            ):
                items.append(
                    {
                        "c": [round(float(v), 4) for v in packed.center],
                        "s": [round(float(v), 4) for v in packed.size],
                        "soft": bool(is_soft),
                        "prio": bool(is_prioritized),
                    }
                )
            containers.append(
                {
                    "index": index,
                    "length": float(container["length"]),
                    "width": float(container["width"]),
                    "height": float(container["height"]),
                    "thickness": float(container["thickness"]),
                    "buffer": float(container.get("buffer") or 0.0),
                    "cut_x": float(container.get("cut_x") or 0.0),
                    "cut_y": float(container.get("cut_y") or 0.0),
                    "offset_x": float(agent_module.container_offset_x(container)),
                    "shelf": bool(agent_module.container_requires_shelf(container)),
                    "prio": bool(container.get("is_prioritized")),
                    "shelves": [
                        {
                            "min": [float(v) for v in plate.minimum],
                            "max": [float(v) for v in plate.maximum],
                            "name": plate.name,
                        }
                        for plate in agent_module.shelf_aabbs(container)
                    ],
                    "points": [
                        [float(v) for v in point]
                        for point in (container.get("points") or [])
                    ],
                    "n_vecs": [
                        [float(v) for v in normal]
                        for normal in (container.get("n_vecs") or [])
                    ],
                    "items": items,
                }
            )
        payload = {"case": case_key, "steps": step, "containers": containers}
        pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(output_path).write_text(
            json.dumps(payload), encoding="utf-8"
        )
        summary = ", ".join(
            f'c{c["index"]}={len(c["items"])} items' for c in containers
        )
        print(f"{case_key}: {step} steps, {summary} -> {output_path}")
        try:
            env.close()
        except Exception:
            pass


if __name__ == "__main__":
    dump(sys.argv[1], sys.argv[2], sys.argv[3])
