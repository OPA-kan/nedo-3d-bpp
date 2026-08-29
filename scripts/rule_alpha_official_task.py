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
from rule_alpha.layer1 import usable_shelf_rect  # noqa: E402
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


def diagnose_stop(scenario, config) -> dict:
    """Why did the run stop?  The first item that got no placement, and what
    the board looked like when it did.

    With the official ``max_space: 1`` a single unplaceable item ends the
    episode, so this is not a footnote -- it is the whole difference between
    the score and the score it could have had.
    """
    from rule_alpha import layer1, layer2 as l2

    grabbed: dict = {}
    original = layer1.choose_for_item

    def traced(board, profile, cfg, max_orientations=3):
        decision = original(board, profile, cfg, max_orientations)
        if decision is None and "profile" not in grabbed:
            grabbed["profile"] = profile
            grabbed["board"] = board
        return decision

    layer1.choose_for_item = traced
    try:
        result = run_physics_episode(scenario, config, verbose=False)
    finally:
        layer1.choose_for_item = original

    out: dict = {"result": result}
    if "profile" not in grabbed:
        out["stop"] = "stream exhausted"
        return out
    profile, board = grabbed["profile"], grabbed["board"]
    grid = board.grid(0)
    free = grid.free_mask()
    out["stop"] = "no placement for an item"
    out["item"] = {
        "index": profile.index,
        "size": [round(float(profile.item[k]), 3)
                 for k in ("length", "width", "height")],
        "class": profile.cargo_class,
    }
    out["board"] = {
        "coverage": round(grid.coverage(), 3),
        "free_floor_m2": round(float(free.sum()) * grid.cell_area, 3),
        "back_height": round(board.back_height(0), 3),
        "front_released": board.front_is_released(0),
        "free_rectangles": [
            [round(r.x_max - r.x_min, 3), round(r.y_max - r.y_min, 3),
             round(z, 3)]
            for r, z in l2.free_rectangles(grid, board.model(0), config)[:4]
        ],
    }
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="all",
                        help='task id, or "all" for every task in the config')
    parser.add_argument("--config", type=pathlib.Path, default=CONFIG)
    parser.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path("reports/rule_alpha/official"))
    parser.add_argument("--no-images", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.config.read_text())
    tasks = list(payload) if args.task == "all" else [args.task]
    missing = [t for t in tasks if t not in payload]
    if missing:
        print(f"task(s) {missing} not in {args.config}: have {list(payload)}")
        return 2
    status = 0
    for task in tasks:
        status |= run_one(task, payload[task], args)
    return status


def run_one(task: str, payload: dict, args) -> int:
    scenario = scenario_from_task(task, payload)
    print(f"\n{scenario.description}", flush=True)

    diagnosis = diagnose_stop(scenario, DEFAULT_CONFIG)
    result = diagnosis["result"]
    args.task = task
    steps = [s for s in result["steps"] if s.get("event") == "step"]
    safe = [s for s in steps if s.get("settle_ok")]
    print(f"\nattempted {len(steps)}, accepted {len(safe)}, "
          f"of {len(scenario.items)} in the stream "
          f"({result['runtime_seconds']}s)")
    for name, key in (("included", "is_included"),
                      ("transport ok", "transport_ok"),
                      ("settled ok", "settle_ok")):
        print(f"  {name:<14}{sum(1 for s in steps if s.get(key))}/{len(steps)}")
    print(f"  fill_score {result['evaluation']['fill_score']:.3f}, "
          f"num_placed_items {result['evaluation']['num_placed_items']:.3f}")
    print(f"\nwhy it stopped: {diagnosis['stop']}")
    if "item" in diagnosis:
        item, board = diagnosis["item"], diagnosis["board"]
        print(f"  item {item['index']} {item['size']} ({item['class']})")
        print(f"  board: coverage {board['coverage']}, "
              f"{board['free_floor_m2']} m2 bare floor, "
              f"back height {board['back_height']}, "
              f"front released {board['front_released']}")
        print(f"  largest empty rectangles (w, d, z): "
              f"{board['free_rectangles']}")

    for idx, model in enumerate(result["models"]):
        on_shelf = [p for p in result["placements"][idx] if p.surface == "shelf"]
        if not on_shelf:
            continue
        print(f"\nshelf placements, container {idx} "
              f"(offset from the shelf they rest on, m):")
        print(f"    {'shelf':>12}{'d_back':>8}{'d_left':>8}{'d_right':>8}"
              f"{'off-shelf':>10}")
        for place in on_shelf:
            best, best_overlap = None, 0.0
            for shelf in model.shelves:
                if abs(float(shelf.maximum[2])
                       - float(place.box.minimum[2])) > 0.02:
                    continue
                rect = usable_shelf_rect(shelf, model, DEFAULT_CONFIG)
                overlap = rect.overlap_area(place.rect)
                if overlap > best_overlap:
                    best, best_overlap = rect, overlap
            if best is None:
                continue
            print(f"    {model.shelves[0].name if False else '':>12}"
                  f"{best.y_max - place.rect.y_max:>8.3f}"
                  f"{place.rect.x_min - best.x_min:>8.3f}"
                  f"{best.x_max - place.rect.x_max:>8.3f}"
                  f"{1.0 - best_overlap / place.rect.area:>10.2f}")

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
