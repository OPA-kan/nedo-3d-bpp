"""One episode of one arm on one scene, in the official environment.

The control flow is the one ``EvaluationApp.run`` uses, so that what the
bench measures is what the evaluation platform would see: ``optimize`` is
called only when the scene's task says so, the stream is reset after the
order is set, and the episode ends on the first failed placement.

Two departures, both recorded in the output rather than hidden:

* the policy timeout is measured, not enforced.  A step over budget is
  counted in ``over_budget_steps``; the run is not aborted, because a
  wall-clock abort would make the result depend on the machine.
* a policy that returns ``None`` ends the episode as ``declined``.  The
  official runner would substitute a random action, which fails.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import sys
import time

import numpy as np

from .metrics import terminal_metrics

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR_SRC = REPO_ROOT / "simulator" / "src"

END_REASONS = ("stream-exhausted", "declined", "inclusion", "transport",
               "settle", "format", "max-steps")


def load_env_class():
    if str(SIMULATOR_SRC) not in sys.path:
        sys.path.insert(0, str(SIMULATOR_SRC))
    from ground_handling.env import GroundHandlingEnv  # noqa: WPS433

    return GroundHandlingEnv


def _end_reason(status: dict, terminated: bool, truncated: bool, stream_empty: bool) -> str | None:
    if truncated:
        return "format"
    if not status.get("is_included", False):
        return "inclusion"
    if not status.get("is_valid", False):
        return "transport"
    if not status.get("is_placed_safe", False):
        return "settle"
    if terminated and stream_empty:
        return "stream-exhausted"
    return None


def _decision_digest(agent) -> dict:
    decision = getattr(agent, "last_decision", None)
    if decision is None:
        return {}
    placement = decision.placement
    return {
        "archetype": placement.archetype,
        "role": placement.role,
        "surface": placement.surface,
        "layer": int(placement.layer),
        "considered": int(decision.considered),
        "survivors": len(getattr(decision, "survivors", []) or []),
        "pos_local": [round(float(v), 4) for v in placement.box.center],
        "size": [round(float(v), 4) for v in placement.box.size],
    }


def run_episode(scene, arm, max_steps: int = 400, policy_budget: float = 8.0,
                probe=None, with_shake: bool = True, verbose: bool = False) -> dict:
    """Run ``arm`` on ``scene``; return a JSON-serialisable record.

    ``probe(env, agent, action, step_index)`` is called before every
    ``env.step`` and its return value stored under ``probes``; the agreement
    study uses it to ask the validator about alternative candidates.
    """
    GroundHandlingEnv = load_env_class()
    sim_config = scene.sim_config(policy_timeout=policy_budget)
    sink = io.StringIO()
    stream = contextlib.nullcontext() if verbose else contextlib.redirect_stdout(sink)

    started = time.perf_counter()
    steps: list[dict] = []
    probes: list = []
    end_reason = "max-steps"
    optimize_seconds = 0.0
    order = None

    with stream:
        env = GroundHandlingEnv(config=sim_config, verbose=False, render_mode=None)
        try:
            env.reset_settings()
            agent = arm(scene)
            agent.get_init_states(env.get_init_states())
            if scene.optimize:
                t0 = time.perf_counter()
                order = agent.optimize(env.get_info_for_optimization())
                optimize_seconds = time.perf_counter() - t0
                if not env.set_item_order(order):
                    raise RuntimeError("agent returned an invalid item order")
            env.reset_item_stream()
            observation, _info = env.reset(seed=42)

            for step_index in range(max_steps):
                t0 = time.perf_counter()
                action = agent.policy(observation)
                policy_seconds = time.perf_counter() - t0
                if action is None:
                    steps.append({"step": step_index, "event": "declined",
                                  "policy_seconds": round(policy_seconds, 4)})
                    end_reason = "declined"
                    break
                if probe is not None:
                    probes.append(probe(env, agent, action, step_index))
                item = env.stream_manager.get_item(int(action["item_idx"]))
                observation, _reward, terminated, truncated, info = env.step(action)
                status = (info or {}).get("status", {})
                record = {
                    "step": step_index,
                    "event": "step",
                    "item_index": None if item is None else int(item.index),
                    "pool_index": int(action["item_idx"]),
                    "container_idx": int(action["container_idx"]),
                    "orientation": int(action["orientation"]),
                    "place_pos": [round(float(v), 4) for v in np.asarray(action["place_pos"])],
                    "is_included": bool(status.get("is_included", False)),
                    "is_valid": bool(status.get("is_valid", False)),
                    "is_placed_safe": bool(status.get("is_placed_safe", False)),
                    "policy_seconds": round(policy_seconds, 4),
                    **_decision_digest(agent),
                }
                steps.append(record)
                reason = _end_reason(status, terminated, truncated, env.stream_manager.is_empty())
                if reason is not None:
                    end_reason = reason
                    break
                if terminated or truncated:
                    end_reason = "format"
                    break
            metrics = terminal_metrics(env, with_shake=with_shake)
            final_items = [
                {
                    "index": int(item.index), "container": int(container.index),
                    "pos": [round(float(v), 4) for v in item.get_pose(env.client)[0]],
                    "orn": [round(float(v), 5) for v in item.get_pose(env.client)[1]],
                }
                for container in env.container_manager.containers
                for item in container.packed_items
                if item.pybullet_id is not None
            ]
        finally:
            with contextlib.suppress(Exception):
                env.close()

    policy_times = [s["policy_seconds"] for s in steps if "policy_seconds" in s]
    metrics.update({
        "policy_time_max": max(policy_times) if policy_times else 0.0,
        "policy_time_mean": float(np.mean(policy_times)) if policy_times else 0.0,
        "over_budget_steps": sum(1 for t in policy_times if t > policy_budget),
        "optimize_seconds": round(optimize_seconds, 3),
        "end_reason": end_reason,
        "attempted": sum(1 for s in steps if s.get("event") == "step"),
    })
    record = {
        "scene": scene.name,
        "scene_spec": {k: v for k, v in scene.to_dict().items() if k not in ("items", "containers")},
        "arm": arm.describe() if hasattr(arm, "describe") else {"arm": str(arm)},
        "runtime_seconds": round(time.perf_counter() - started, 2),
        "order": order,
        "metrics": metrics,
        "steps": steps,
        "final_items": final_items,
        "log_tail": None if verbose else sink.getvalue()[-2000:],
    }
    if probes:
        record["probes"] = probes
    return record


def write_record(record: dict, out_dir: pathlib.Path) -> pathlib.Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{record['scene']}.json"
    path.write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    return path
