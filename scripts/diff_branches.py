"""
Dissect one improvement case: read two branches step by step, side by side.

This is not a labelling instrument and produces no statistics. It takes the
one surviving improvement case - b000-k20 step 4, where the lowest-Q sibling
reached about 25 placed across repeats while the highest-Q sibling reached 17
to 21 - and asks what actually differed.

## Pre-registered predictions

Written before the diff was read, so that whatever is found is a test rather
than a story fitted afterwards. The three quantities come from the account of
what strong Tetris players maintain: acceptance breadth, alternativity, and
repairability.

* **A - acceptance breadth.** The losing branch lost a remaining class that
  had nowhere left to go. **Predicted to FAIL.** Acceptance is already
  measured saturated here: release capacity was constant across all 24
  snapshots of the Stage A set, thousands of release anchors persist at
  placed-to-go zero, and settled-zero states still placed five more items.
  In Tetris the failure is "cannot place"; here you can nearly always drop
  something somewhere.
* **R - alternativity.** The losing branch concentrated the remaining
  capacity into one region, so distinct classes ended up competing for the
  same space. **Untested either way** - inter-class competition is the one
  quantity in this family that has never been measured.
* **H - repairability.** The losing branch produced a topple, and a toppled
  item is an irregular obstacle that cannot be removed, so the container
  never recovered. **Predicted to HOLD.** Episode endings are 45% the
  fixed-coordinate fallback and 36% topple, and a settled topple was
  observed with an AABB of 0.307 x 0.795 x 0.715 - nothing like the item's
  nominal box.

If H holds, the first candidate board functional is "avoid creating
irremovable debris, and keep a shape that can route around it once created",
which is a different axis from the four option-count quantities that failed
today. If nothing holds, the case is dropped rather than explained.

## What is compared

Per step, for both branches: the chosen item and pose, the action source,
the settle angle and displacement, the number and area of connected support
plane components, and how many remaining item classes still have at least
one accepted placement. The last two are the computable stand-ins for R and
A; the settle metrics are the stand-in for H.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
for path in (ROOT, SIMULATOR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

SCHEMA_VERSION = 1


def board_descriptors(agent, observation, item_list):
    """Computable stand-ins for acceptance breadth and alternativity."""
    container = observation["container_list"][0]
    packed = {
        int(entry["index"])
        for c in observation.get("container_list", [])
        for entry in c.get("packed_items", [])
    }
    surfaces = agent.support_surfaces(container)
    components = agent.order_support_plane_components(
        agent.support_plane_components(surfaces)
    )
    remaining = [i for i in item_list if int(i["index"]) not in packed]
    classes: dict[tuple, dict[str, Any]] = {}
    for item in remaining:
        key = (
            round(float(item["length"]), 4),
            round(float(item["width"]), 4),
            round(float(item["height"]), 4),
            bool(item.get("is_soft", False)),
            bool(item.get("is_prioritized", False)),
        )
        classes.setdefault(key, item)
    accepted_classes = 0
    for representative in classes.values():
        found = False
        for orientation in agent.unique_orientations(representative):
            for candidate in agent.CandidateGenerator.iter_cartesian_attempts(
                observation, representative, 0, orientation,
                limit=1, attempt_kind="settled", stride=16,
            ):
                if candidate is not None:
                    found = True
                    break
            if found:
                break
        accepted_classes += int(found)
    return {
        "packed_items": len(packed),
        "remaining_classes": len(classes),
        "classes_with_a_settled_option": accepted_classes,
        "support_components": len(components),
        "support_component_areas": [
            round(float(c.area), 5) for c in components
        ],
        "largest_support_area": (
            round(max(float(c.area) for c in components), 5)
            if components else 0.0
        ),
    }


def run_branch(agent, task, item_list, *, force_step, force_action, label):
    from src.ground_handling.env import GroundHandlingEnv
    from scripts.measure_anchor_recall import policy_observation

    env = GroundHandlingEnv(config=task, verbose=False, render_mode=None)
    solver = agent.Agent("")
    trail = []
    step = 0
    try:
        env.reset_settings()
        solver.get_init_states(env.get_init_states())
        env.reset_item_stream()
        raw_observation, _info = env.reset(seed=42)
        terminated = truncated = False
        while not terminated and not truncated:
            observation = policy_observation(env, raw_observation)
            before = board_descriptors(agent, observation, item_list)
            action = solver.policy(observation)
            forced = force_action is not None and step == force_step
            emitted = force_action if forced else action
            diagnostics = getattr(solver, "last_candidate_diagnostics", {})
            trail.append({
                "step": step,
                "forced": forced,
                "item_idx": int(emitted["item_idx"]),
                "orientation": int(emitted["orientation"]),
                "policy_item_idx": int(action["item_idx"]),
                "before": before,
                "search": {
                    "deadline_reached": bool(
                        (diagnostics.get("search") or {}).get(
                            "deadline_reached", False
                        )
                    ),
                    "units_started": int(
                        (diagnostics.get("search") or {}).get(
                            "units_started", 0
                        )
                    ),
                },
            })
            raw_observation, _r, terminated, truncated, _info = env.step(
                emitted
            )
            step += 1
        evaluation = env.evaluate()
    finally:
        env.close()
    metrics = evaluation.get("step_metrics") or []
    for index, entry in enumerate(trail):
        if index < len(metrics):
            m = metrics[index] or {}
            entry["settle"] = {
                "angle_deg": m.get("settle_angle_deg"),
                "displacement": m.get("settle_displacement_norm"),
            }
    return {
        "label": label,
        "steps": step,
        "evaluation": {
            k: v for k, v in evaluation.items() if k != "step_metrics"
        },
        "trail": trail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--step", type=int, required=True)
    parser.add_argument("--sibling-budget", type=int, default=4096)
    parser.add_argument("--siblings", type=int, default=3)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("NEDO_POLICY_TRACE_PATH", "")
    from scripts.build_branch_labels import (
        reconstruct_siblings, run_episode, action_signature,
    )
    from scripts.measure_anchor_recall import load_agent_module

    config = json.loads(args.config.read_text(encoding="utf-8"))
    task = config[next(iter(config))]
    item_list = task["item_stream"]["item_list"]
    agent = load_agent_module()

    reference = run_episode(agent, task, capture_steps={args.step})
    observation = reference["captured"][args.step]
    siblings = reconstruct_siblings(
        agent, observation, budget=args.sibling_budget, limit=args.siblings
    )
    ranked = sorted(siblings, key=lambda d: d.score)
    low, high = ranked[0], ranked[-1]

    branches = []
    for label, decision in (("low_q_winner", low), ("high_q_control", high)):
        forced = {
            "item_idx": int(decision.action["item_idx"]),
            "container_idx": int(decision.action["container_idx"]),
            "place_pos": np.asarray(
                decision.action["place_pos"], dtype=np.float32
            ),
            "orientation": int(decision.action["orientation"]),
        }
        print(f"running {label} (Q={decision.score:+.3f})",
              file=sys.stderr, flush=True)
        result = run_branch(
            agent, task, item_list,
            force_step=args.step, force_action=forced, label=label,
        )
        result["q"] = float(decision.score)
        result["action"] = action_signature(forced)
        branches.append(result)

    report = {
        "schema_version": SCHEMA_VERSION,
        "branch_step": args.step,
        "predictions": {
            "A_acceptance_breadth": "predicted to FAIL",
            "R_alternativity": "untested either way",
            "H_repairability": "predicted to HOLD",
            "registered": "before the diff was read",
        },
        "branches": branches,
    }
    (args.output_dir / "diff.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    for b in branches:
        print(f"{b['label']}: Q={b['q']:+.3f} steps={b['steps']} "
              f"{b['evaluation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
