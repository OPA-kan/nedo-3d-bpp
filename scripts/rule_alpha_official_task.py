"""Run rule-alpha against a task from the official config, in the simulator.

    python3 -m scripts.rule_alpha_official_task --task 000

Reads ``simulator/configs/sample_config.json``, drives the real
``GroundHandlingEnv`` with the rule-alpha agent, and writes the settled board
plus pictures.  The scenarios in ``rule_alpha/scenarios.py`` are hand-built
stress cases; this is the thing that is actually scored.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.geometry import make_container_dict  # noqa: E402
from rule_alpha.physics import run_physics_episode  # noqa: E402
from rule_alpha.scenarios import Scenario  # noqa: E402

CONFIG = pathlib.Path("simulator/configs/sample_config.json")


def scenario_from_task(task_id: str, payload: dict) -> Scenario:
    containers = [
        make_container_dict(
            index=int(spec["index"]),
            length=float(spec["length"]), width=float(spec["width"]),
            height=float(spec["height"]),
            thickness=float(spec["thickness"]),
            cut_x=float(spec["cut_x"]), cut_y=float(spec["cut_y"]),
            buffer=float(spec.get("buffer", 0.0)),
            require_shelf=bool(spec.get("require_shelf", False)),
            is_prioritized=bool(spec.get("is_prioritized", False)),
        )
        for spec in payload["containers"]["container_list"]
    ]
    stream = payload["item_stream"]
    return Scenario(
        name=f"task{task_id}",
        description=(
            f"official task {task_id}: {len(stream['item_list'])} items, "
            f"look_ahead={stream['look_ahead']}, "
            f"{len(containers)} container(s)"
        ),
        containers=containers,
        items=[dict(item) for item in stream["item_list"]],
        look_ahead=int(stream["look_ahead"]),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="000")
    parser.add_argument("--config", type=pathlib.Path, default=CONFIG)
    parser.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path("reports/rule_alpha/official"))
    parser.add_argument("--no-images", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.config.read_text())
    if args.task not in payload:
        print(f"task {args.task} not in {args.config}: have {list(payload)}")
        return 2
    scenario = scenario_from_task(args.task, payload[args.task])
    print(scenario.description, flush=True)

    result = run_physics_episode(scenario, DEFAULT_CONFIG, verbose=False)
    steps = [s for s in result["steps"] if s.get("event") == "step"]
    safe = [s for s in steps if s.get("settle_ok")]
    print(f"\nattempted {len(steps)}, accepted {len(safe)}, "
          f"of {len(scenario.items)} in the stream "
          f"({result['runtime_seconds']}s)")
    for name, key in (("included", "is_included"),
                      ("transport ok", "transport_ok"),
                      ("settled ok", "settle_ok")):
        print(f"  {name:<14}{sum(1 for s in steps if s.get(key))}/{len(steps)}")
    print(f"\nofficial evaluation: "
          f"{json.dumps(result['evaluation'], ensure_ascii=False)}")

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / f"task{args.task}.json").write_text(
        json.dumps(
            {
                "scenario": result["scenario"],
                "runtime_seconds": result["runtime_seconds"],
                "evaluation": result["evaluation"],
                "steps": steps,
            },
            ensure_ascii=False, indent=1,
        ) + "\n"
    )
    if not args.no_images:
        from rule_alpha.terrain_view import render_stack, render_terrain

        for idx, model in enumerate(result["models"]):
            places = result["placements"][idx]
            base = args.out / f"task{args.task}"
            for written in render_stack(
                model, places, DEFAULT_CONFIG,
                f"official task {args.task} — container {idx} — settled in the "
                f"simulator", base / f"c{idx}_stack.png",
            ) + render_terrain(
                model, places, DEFAULT_CONFIG,
                f"official task {args.task} — container {idx} — terrain",
                base / f"c{idx}_terrain.png",
            ):
                print(f"wrote {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
