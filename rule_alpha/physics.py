"""Drive rule-alpha inside the real PyBullet simulator.

The analytic driver in ``episode.py`` answers "what board do these rules
build?".  This one answers "does the official validator agree?" — real
``check_inclusion``, real transport sweep, real settle — and reports the
settled poses rather than the intended ones.

Requires the simulator extras (``requirements-simulator.txt``).
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import time

from . import layer1
from .agent import RuleAlphaAgent
from ._reuse import AABB, packed_dimensions
from .geometry import ContainerModel


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR_SRC = REPO_ROOT / "simulator" / "src"


def _load_env_module():
    if str(SIMULATOR_SRC) not in sys.path:
        sys.path.insert(0, str(SIMULATOR_SRC))
    from ground_handling.env import GroundHandlingEnv  # noqa: WPS433

    return GroundHandlingEnv


def scenario_to_config(scenario, look_ahead: int | None = None) -> dict:
    """Turn a rule-alpha scenario into an official simulator config dict."""
    container_list = []
    for container in scenario.containers:
        spec = dict(container["_spec"])
        spec["packed_items"] = []
        container_list.append(spec)

    lookahead = int(look_ahead or scenario.look_ahead)
    return {
        "containers": {"spacing": 2.5, "container_list": container_list},
        "item_stream": {
            "item_list": [dict(item) for item in scenario.items],
            "look_ahead": lookahead,
            "max_space": lookahead,
            "visible_pool": [],
        },
        "camera": {
            "num_containers": len(container_list),
            "target_pos": [0, 0, 0],
            "distance": 3.0,
            "yaw": 0, "pitch": 0, "roll": 0,
            "img_width": 64, "img_height": 64,
            "fov": 60, "near_val": 0.1, "far_val": 10.0,
        },
        "validator": {
            "inclusion_margin": -0.005,
            "start_z": 0.08,
            "safety_margin": 0.015,
            "ceiling_margin": 0.018,
            "displacement_threshold": 0.3,
            "angle_displacement_threshold": 45,
            "settle_wait_step": 300,
        },
        "action": {
            "keys": {
                "item_idx": "int", "container_idx": "int",
                "place_pos": "float", "orientation": "int",
            },
            "pos_lim": {"low": -100, "high": 100},
            "orientations": [0, 1, 2, 3, 4, 5],
        },
        "agent": {
            "optimize": True,
            "init_timeout": 10.0,
            "optimization_timeout": 180.0,
            "policy_timeout": 8.0,
            "allowed_methods": ["get_init_states", "optimize", "policy"],
            "max_mem": 12,
        },
        "visualizer": {"vis": False, "camera": {"yaw": 0, "pitch": -20}},
    }


def _settled_placements(observation, board_models, intent, config):
    """Rebuild Placement records from the simulator's settled poses."""
    per_container: list[list[layer1.Placement]] = [[] for _ in board_models]
    for position, container in enumerate(observation["container_list"]):
        offset_x = float(container.get("center", (0.0, 0.0, 0.0))[0])
        for packed in container.get("packed_items", []):
            index = int(packed["index"])
            record = intent.get(index)
            if record is None:
                continue
            profile, orientation, role, archetype, surface, surface_name = record
            pos = packed.get("pos")
            if pos is None:
                continue
            dims = packed_dimensions(packed)
            box = AABB(
                center=(float(pos[0]) - offset_x, float(pos[1]), float(pos[2])),
                size=tuple(float(v) for v in dims),
                name="settled",
            )
            per_container[position].append(
                layer1.Placement(
                    profile=profile,
                    orientation=orientation,
                    container_idx=position,
                    box=box,
                    surface=surface,
                    surface_name=surface_name,
                    role=role,
                    archetype=archetype,
                    reason="settled pose reported by the simulator",
                    settle_note="pybullet",
                )
            )
    return per_container


def run_physics_episode(scenario, config, max_steps: int = 400,
                        verbose: bool = False) -> dict:
    """Run one scenario through the official environment.

    Returns a dict with per-step validator results and the final settled
    placements per container.
    """
    GroundHandlingEnv = _load_env_module()
    sim_config = scenario_to_config(scenario)

    sink = io.StringIO()
    stream = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(sink)

    started = time.perf_counter()
    steps: list[dict] = []
    intent: dict[int, tuple] = {}
    final_placements: list[list[layer1.Placement]] = []
    models = []

    with stream:
        env = GroundHandlingEnv(config=sim_config, verbose=False, render_mode=None)
        try:
            # Exactly the order EvaluationApp.run uses.  reset_item_stream()
            # must come *after* set_item_order(): it fills the visible pool
            # from all_items, so reordering afterwards leaves a stale pool
            # entry that the stream then hands out a second time.
            env.reset_settings()
            agent = RuleAlphaAgent(config=config)
            agent.get_init_states(env.get_init_states())
            order = agent.optimize(env.get_info_for_optimization())
            env.set_item_order(order)
            env.reset_item_stream()
            observation, _info = env.reset(seed=42)

            for _ in range(max_steps):
                action = agent.policy(observation)
                if action is None:
                    steps.append({"event": "declined", "reason": "layer-1 complete"})
                    break
                decision = agent.last_decision
                placement = decision.placement
                intent[placement.profile.index] = (
                    placement.profile,
                    placement.orientation,
                    placement.role,
                    placement.archetype,
                    placement.surface,
                    placement.surface_name,
                )
                observation, _reward, terminated, truncated, info = env.step(action)
                status = (info or {}).get("status", {})
                steps.append(
                    {
                        "event": "step",
                        **placement.as_dict(config),
                        "action_pos": [float(v) for v in action["place_pos"]],
                        "is_included": bool(status.get("is_included", False)),
                        "transport_ok": bool(status.get("is_valid", False)),
                        "settle_ok": bool(status.get("is_placed_safe", False)),
                        "terminated": bool(terminated),
                        "truncated": bool(truncated),
                    }
                )
                if terminated or truncated:
                    break

            models = [
                ContainerModel(container, config)
                for container in observation["container_list"]
            ]
            # redraw with the strip widths the planner actually enforced
            for idx, scale in (agent.zone_scales or {}).items():
                if idx < len(models):
                    models[idx].set_zone_scales(
                        scale["soft_zone_scale"], scale["priority_zone_scale"]
                    )
            final_placements = _settled_placements(
                observation, models, intent, config
            )
            evaluation = env.evaluate()
        finally:
            with contextlib.suppress(Exception):
                env.close()

    return {
        "scenario": scenario.name,
        "runtime_seconds": round(time.perf_counter() - started, 2),
        "steps": steps,
        "evaluation": evaluation,
        "models": models,
        "placements": final_placements,
        "zone_scales": agent.zone_scales,
        "log": None if verbose else sink.getvalue()[-4000:],
    }
