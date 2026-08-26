"""How much load does a Layer 1 item take before it sinks out of the score?

The placement spec is release-and-drop: the robot lets go a little above the
resting surface.  ``check_inclusion`` enforces that on the *commanded* pose.
``Evaluator.calculate_fill_rate`` then re-tests the **settled** pose against the
same ``inclusion_margin``, and a settled box sits slightly *into* its support
because PyBullet resolves contact with a load-dependent penetration.

So the bottom layer has a penetration budget, and stacking spends it.  This
module measures the curve instead of assuming it: put one box on the floor,
stack mass on top of it, and watch its floor-plane term move.

    .venv312/bin/python -m rule_alpha.penetration

Needs the simulator extras and Python 3.12 (see docs/rule_alpha/README.md).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import pathlib

import numpy as np

from .config import DEFAULT_CONFIG
from .geometry import make_container_dict, ContainerModel
from .physics import _load_env_module
from .scenarios import ULD


def _config(items: list[dict], inclusion_margin: float) -> dict:
    container = make_container_dict(index=0, **ULD)
    spec = dict(container["_spec"])
    spec["packed_items"] = []
    return {
        "containers": {"spacing": 2.5, "container_list": [spec]},
        "item_stream": {
            "item_list": items, "look_ahead": 1, "max_space": 1, "visible_pool": [],
        },
        "camera": {
            "num_containers": 1, "target_pos": [0, 0, 0], "distance": 3.0,
            "yaw": 0, "pitch": 0, "roll": 0, "img_width": 64, "img_height": 64,
            "fov": 60, "near_val": 0.1, "far_val": 10.0,
        },
        "validator": {
            "inclusion_margin": inclusion_margin, "start_z": 0.08,
            "safety_margin": 0.015, "ceiling_margin": 0.018,
            "displacement_threshold": 0.3, "angle_displacement_threshold": 45,
            "settle_wait_step": 300,
        },
        "action": {
            "keys": {"item_idx": "int", "container_idx": "int",
                     "place_pos": "float", "orientation": "int"},
            "pos_lim": {"low": -100, "high": 100},
            "orientations": [0, 1, 2, 3, 4, 5],
        },
        "agent": {"optimize": False, "init_timeout": 10.0,
                  "optimization_timeout": 180.0, "policy_timeout": 8.0,
                  "allowed_methods": ["get_init_states", "optimize", "policy"],
                  "max_mem": 12},
        "visualizer": {"vis": False, "camera": {"yaw": 0, "pitch": -20}},
    }


def _floor_term(container, pos, dims) -> float:
    """The floor-plane term the evaluator computes for a settled box.

    Positive means the box has sunk into the floor plane; the evaluator keeps
    the box only while this stays at or below ``inclusion_margin``.
    """
    normals = np.asarray(container.n_vecs, dtype=np.float64)
    points = np.asarray(container.points, dtype=np.float64)
    floor = int(np.nonzero(normals[:, 2] < -0.99)[0][0])
    half = np.asarray(dims, dtype=np.float64) / 2.0
    return float(
        np.dot(normals[floor], np.asarray(pos) - points[floor])
        + np.dot(np.abs(normals[floor]), half)
    )


def run(stack_height: int = 5, unit_mass: float = 18.0,
        inclusion_margin: float = -0.005, soft_bottom: bool = False,
        verbose: bool = False) -> dict:
    """Stack ``stack_height`` boxes and track the bottom one's floor term.

    ``soft_bottom`` makes the bottom box soft.  Soft cargo is given a contact
    stiffness three orders of magnitude below the default, so this is where a
    load-dependent penetration actually shows up.
    """
    length, width, height = 0.60, 0.45, 0.25
    items = []
    for i in range(stack_height):
        item = {
            "index": i, "length": length, "width": width, "height": height,
            "mass": unit_mass, "is_soft": False, "is_prioritized": False,
        }
        if soft_bottom and i == 0:
            item.update({
                "is_soft": True, "contactStiffness": 5000,
                "contactDamping": 500, "linearDamping": 0.8,
            })
        items.append(item)

    GroundHandlingEnv = _load_env_module()
    sink = io.StringIO()
    stream = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(sink)

    rows = []
    with stream:
        env = GroundHandlingEnv(
            config=_config(items, inclusion_margin), verbose=False, render_mode=None
        )
        try:
            env.reset_settings()
            env.reset_item_stream()
            observation, _info = env.reset(seed=42)
            container = env.container_manager.get_container(0)
            model = ContainerModel(
                observation["container_list"][0], DEFAULT_CONFIG
            )

            x, y = 0.30, 0.20
            for level in range(stack_height):
                # commanded pose: release-and-drop, a little above the support
                bottom = model.z_floor + level * height
                lift = (
                    DEFAULT_CONFIG.floor_action_lift if level == 0
                    else DEFAULT_CONFIG.floor_action_lift
                )
                action = {
                    "item_idx": 0,
                    "container_idx": 0,
                    "place_pos": np.array(
                        [x, y, bottom + lift + height / 2.0], dtype=np.float32
                    ),
                    "orientation": 0,
                }
                observation, _r, terminated, truncated, info = env.step(action)
                status = (info or {}).get("status", {})
                if not status.get("is_placed_safe"):
                    rows.append({
                        "level": level + 1, "placed": False,
                        "status": {k: bool(v) for k, v in status.items()},
                    })
                    break

                packed = observation["container_list"][0]["packed_items"]
                bottom_item = next(p for p in packed if int(p["index"]) == 0)
                dims = (length, width, height)
                term = _floor_term(container, bottom_item["pos"], dims)
                borne = unit_mass * level  # mass resting on top of the bottom box
                rows.append({
                    "level": level + 1,
                    "placed": True,
                    "mass_on_bottom_box_kg": round(borne, 1),
                    "total_mass_kg": round(unit_mass * (level + 1), 1),
                    "bottom_box_bottom_z": round(float(bottom_item["pos"][2]) - height / 2.0, 6),
                    "penetration_mm": round(term * 1000.0, 4),
                    "floor_plane_term": round(term, 6),
                    "counted_by_evaluator": bool(term <= inclusion_margin),
                })
                if terminated or truncated:
                    break
        finally:
            with contextlib.suppress(Exception):
                env.close()

    return {
        "inclusion_margin": inclusion_margin,
        "soft_bottom": soft_bottom,
        "unit_mass_kg": unit_mass,
        "box": [length, width, height],
        "floor_plane_z": round(model.z_floor, 6),
        "rows": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--levels", type=int, default=5)
    parser.add_argument("--mass", type=float, default=18.0)
    parser.add_argument("--margin", type=float, default=-0.005)
    parser.add_argument("--soft-bottom", action="store_true")
    parser.add_argument("--out", type=pathlib.Path, default=None)
    args = parser.parse_args(argv)

    result = run(args.levels, args.mass, args.margin, args.soft_bottom)
    print(json.dumps(result, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
