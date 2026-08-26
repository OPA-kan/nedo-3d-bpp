"""Build read-only spectator data for one league match.

Combines both arms' episode manifests (actions, switch decisions,
cumulative metrics), the frozen scenario geometry, and the league
report into a single JSON the spectator UI can replay: side-by-side
placement sequences, the first turn where the policies diverge, switch
confidence, and auto-extracted highlights.

Spectating is read-only by contract: nothing here feeds training, and
league results must never drive manual training-matrix tuning (the
frozen eval set would leak through the human).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_scenario_matrix import (  # noqa: E402
    DEFAULT_SOURCE,
    SCENARIOS,
    build_scenario,
)

ROTATED_DIMENSIONS = (
    (0, 1, 2), (0, 2, 1), (2, 1, 0), (1, 0, 2), (1, 2, 0), (2, 0, 1),
)
VIOLATION_HEADS = (
    "soft_covered_by_other", "priority_covered_by_other",
    "priority_misrouted",
)


def rotated(dims: tuple[float, float, float], orientation: int):
    order = ROTATED_DIMENSIONS[int(orientation)]
    return [float(dims[axis]) for axis in order]


def load_config_items(
    configs: pathlib.Path, stream: str, scenario: str,
) -> dict[int, tuple[float, float, float]]:
    path = configs / stream / f"{scenario}.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        # League artifacts intentionally contain episodes, not a second copy
        # of the deterministic scenario matrix.  Rebuild the exact declared
        # stream from the checked-in source when rendering a remote match.
        source = json.loads(DEFAULT_SOURCE.read_text(encoding="utf-8"))
        specs = dict(SCENARIOS)
        if scenario not in specs:
            raise ValueError(f"unknown league scenario {scenario!r}")
        payload = build_scenario(
            source, scenario, specs[scenario], look_ahead=10,
            policy_timeout=8.0, stream_variant=stream
        )
    case = payload[f"m-{scenario}"]
    return {
        int(item["index"]): (
            float(item["length"]), float(item["width"]),
            float(item["height"]),
        )
        for item in case["item_stream"]["item_list"]
    }


def episode_payload(cell_dir: pathlib.Path) -> dict[str, Any]:
    manifest = json.loads(
        (cell_dir / "rollout" / "manifest.json").read_text(encoding="utf-8")
    )
    episode = manifest["episodes"][0]
    snapshots = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(
            (cell_dir / "rollout" / "episode-000").glob("step-*-state.json")
        )
    ]
    containers = [
        {
            "index": int(row.get("index", 0)),
            "center": [float(v) for v in row.get("center", [0, 0, 0])],
            "length": float(row.get("length", 0) or 0),
            "width": float(row.get("width", 0) or 0),
            "height": float(row.get("height", 0) or 0),
            "thickness": float(row.get("thickness", 0) or 0),
            # front wedge cut (0.5*cut_x*cut_y*width removed) + a small
            # shelf plate over it; main shelf covers the +y half at
            # shelf_z = height/2 + thickness/2 + buffer (container-local)
            "cut_x": float(row.get("cut_x", 0) or 0),
            "cut_y": float(row.get("cut_y", 0) or 0),
            "shelf": bool(row.get("shelf")),
            "prioritized": bool(row.get("is_prioritized")),
        }
        for row in snapshots[0]["observation"]["container_list"]
    ]
    return {"episode": episode, "containers": containers,
            "snapshots": snapshots}


# board row flags: 1=soft item, 2=priority item, 4=covered by another
# box (approximate stacking check for the viewer; the numeric violation
# counters shown next to it come from the official metrics), 8=priority
# item routed into a non-dedicated container
FLAG_SOFT, FLAG_PRIORITY, FLAG_COVERED, FLAG_MISROUTED = 1, 2, 4, 8


def annotate_board(
    board: list[list[float]], containers: list[dict[str, Any]],
) -> None:
    dedicated = {
        c["index"] for c in containers if c.get("prioritized")
    }
    for row in board:
        flags = int(row[8])
        if flags & (FLAG_SOFT | FLAG_PRIORITY):
            x0, x1 = row[2] - row[5] / 2, row[2] + row[5] / 2
            y0, y1 = row[3] - row[6] / 2, row[3] + row[6] / 2
            top = row[4] + row[7] / 2
            area = max(1e-9, row[5] * row[6])
            for other in board:
                if other is row or other[0] != row[0]:
                    continue
                overlap_x = min(x1, other[2] + other[5] / 2) - max(
                    x0, other[2] - other[5] / 2
                )
                overlap_y = min(y1, other[3] + other[6] / 2) - max(
                    y0, other[3] - other[6] / 2
                )
                if overlap_x <= 0 or overlap_y <= 0:
                    continue
                bottom = other[4] - other[7] / 2
                if (
                    overlap_x * overlap_y >= 0.25 * area
                    and bottom >= top - 0.03
                ):
                    flags |= FLAG_COVERED
                    break
        if flags & FLAG_PRIORITY and dedicated and row[0] not in dedicated:
            flags |= FLAG_MISROUTED
        row[8] = flags


def settled_board(
    snapshot: dict[str, Any], containers: list[dict[str, Any]],
) -> list[list[float]]:
    """[container, item, world x/y/z, placed l/w/h, flags] rows.

    Observation packed poses are the settled physics poses in world
    coordinates — the truth after gravity, not the commanded target.
    """
    board = []
    for container in snapshot["observation"]["container_list"]:
        for item in container.get("packed_items") or []:
            board.append([
                int(container.get("index", 0)), int(item["index"]),
                *[round(float(v), 3) for v in item["pos"]],
                round(float(item["length"]), 3),
                round(float(item["width"]), 3),
                round(float(item["height"]), 3),
                (FLAG_SOFT if item.get("is_soft") else 0)
                | (FLAG_PRIORITY if item.get("is_prioritized") else 0),
            ])
    annotate_board(board, containers)
    return board


def selected_stable_index(record: dict[str, Any]) -> int | None:
    selected = (record.get("selection") or {}).get("selected_candidate_id")
    for row in (record.get("search") or {}).get("root_candidates") or []:
        if str(row.get("root_candidate_id")) == str(selected):
            value = row.get("stable_item_index")
            return int(value) if value is not None else None
    return None


def arm_steps(
    payload: dict[str, Any],
    items: dict[int, tuple[float, float, float]],
) -> list[dict[str, Any]]:
    episode = payload["episode"]
    snapshots = payload["snapshots"]
    containers = {c["index"]: c for c in payload["containers"]}
    records = episode.get("records") or []
    steps = []
    for position, record in enumerate(records):
        action = record["action"]
        selection = record.get("selection") or {}
        before = record.get("metrics_before") or {}
        if position + 1 < len(records):
            after = records[position + 1].get("metrics_before") or {}
        else:
            after = episode.get("final_metrics") or {}
        scores = selection.get("learned_scores") or {}
        selected_score = scores.get(selection.get("selected_candidate_id"))
        stable = selected_stable_index(record)
        if position + 1 < len(snapshots):
            board = settled_board(snapshots[position + 1],
                                  payload["containers"])
        else:
            # the final placement has no follow-up snapshot: append the
            # commanded box (container-local xy) to the last settled board
            board = settled_board(snapshots[-1], payload["containers"]) \
                if snapshots else []
            container = containers.get(int(action["container_idx"]), {})
            center = container.get("center", [0, 0, 0])
            dims = rotated(
                items.get(stable, (0.3, 0.3, 0.3)), action["orientation"]
            ) if stable is not None else [0.3, 0.3, 0.3]
            board = board + [[
                int(action["container_idx"]), int(stable or -1),
                round(center[0] + float(action["place_pos"][0]), 3),
                round(center[1] + float(action["place_pos"][1]), 3),
                round(float(action["place_pos"][2]), 3),
                *[round(v, 3) for v in dims],
                0,
            ]]
            annotate_board(board, payload["containers"])
        steps.append({
            "t": int(record.get("step", position)),
            "item": stable,
            "cont": int(action["container_idx"]),
            "switched": bool(selection.get("switched")),
            "reason": selection.get("reason"),
            "conf": (
                round(float(selected_score), 4)
                if isinstance(selected_score, (int, float)) else None
            ),
            "placed": int(after.get("placed_count", 0)),
            "fill": round(float(after.get("fill_score_proxy", 0.0)), 4),
            # official metric counters, in VIOLATION_HEADS order — the
            # box markers are approximate, these numbers are the truth
            "viol": [
                int(float(after.get(head, 0) or 0))
                for head in VIOLATION_HEADS
            ],
            # Event semantics are transition-aligned: the board is the
            # settled state after this action, and each delta compares this
            # record's metrics_before with the next/final metrics.
            "viol_delta": violation_delta(before, after),
            "board": board,
        })
    return steps


def violations(final: dict[str, Any]) -> float:
    return float(sum(float(final.get(head, 0) or 0)
                     for head in VIOLATION_HEADS))


def violation_delta(
    before: dict[str, Any], after: dict[str, Any]
) -> list[int]:
    """Newly created published-rule counters, kept head-separate."""
    return [
        max(0, int(float(after.get(head, 0) or 0))
            - int(float(before.get(head, 0) or 0)))
        for head in VIOLATION_HEADS
    ]


def build_cell(
    cell: str, arms: dict[str, pathlib.Path], configs: pathlib.Path,
) -> dict[str, Any]:
    scenario, stream = cell.rsplit("-permute-", 1)
    stream = f"permute-{stream}"
    items = load_config_items(configs, stream, scenario)
    payloads = {name: episode_payload(path) for name, path in arms.items()}
    arm_data = {}
    for name, payload in payloads.items():
        episode = payload["episode"]
        steps = arm_steps(payload, items)
        final = episode.get("final_metrics") or {}
        arm_data[name] = {
            "termination": episode.get("termination"),
            "steps": steps,
            "final": {
                "placed": int(final.get("placed_count", 0)),
                "fill": round(float(final.get("fill_score_proxy", 0.0)), 3),
                "violations": violations(final),
            },
        }
    names = list(arm_data)

    def placement_key(step):
        row = next(
            (r for r in step["board"]
             if r[1] == step["item"] and r[0] == step["cont"]), None
        )
        return (step["item"], step["cont"],
                tuple(round(v, 2) for v in row[2:5]) if row else None)

    divergence = None
    if len(names) == 2:
        first, second = (arm_data[name]["steps"] for name in names)
        for a, b in zip(first, second):
            if placement_key(a) != placement_key(b):
                divergence = a["t"]
                break
        else:
            if len(first) != len(second):
                divergence = min(len(first), len(second))
    return {
        "scenario": scenario,
        "stream": stream,
        "containers": payloads[names[0]]["containers"],
        "initial_board": settled_board(
            payloads[names[0]]["snapshots"][0],
            payloads[names[0]]["containers"],
        ),
        "divergence_turn": divergence,
        "arms": arm_data,
    }


def build_highlights(
    cells: dict[str, Any], relations: dict[str, str],
    challenger: str, opponent: str,
) -> list[dict[str, Any]]:
    highlights = []
    for cell, data in cells.items():
        relation = relations.get(cell)
        tags = []
        ch, op = data["arms"][challenger], data["arms"][opponent]
        switches = [s for s in ch["steps"] if s["switched"]]
        if relation == "challenger_wins":
            tags.append("challenger_win")
        if relation == "member_wins":
            tags.append("champion_win")
        if relation == "incomparable":
            tags.append("trade_off")
        if switches and relation == "challenger_wins":
            tags.append("switch_decided_it")
        if abs(ch["final"]["fill"] - op["final"]["fill"]) >= 0.1:
            tags.append("fill_gap")
        if ch["final"]["placed"] != op["final"]["placed"]:
            tags.append("placed_gap")
        if tags:
            highlights.append({
                "cell": cell,
                "tags": tags,
                "relation": relation,
                "divergence_turn": data["divergence_turn"],
                "switch_turns": [s["t"] for s in switches],
                "fill_delta": round(
                    ch["final"]["fill"] - op["final"]["fill"], 3
                ),
                "placed_delta": ch["final"]["placed"] - op["final"]["placed"],
            })
    order = {"switch_decided_it": 0, "challenger_win": 1,
             "champion_win": 2, "placed_gap": 3, "fill_gap": 4,
             "trade_off": 5}
    highlights.sort(key=lambda h: min(order[t] for t in h["tags"]))
    return highlights


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--challenger-name", required=True)
    parser.add_argument("--challenger-root", type=pathlib.Path, required=True)
    parser.add_argument("--opponent-name", required=True)
    parser.add_argument("--opponent-root", type=pathlib.Path, required=True)
    parser.add_argument("--configs", type=pathlib.Path, required=True)
    parser.add_argument("--report", type=pathlib.Path, required=True,
                        help="league promotion decision report.json")
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    relations = {
        cell.replace("league-cell-", ""): relation
        for cell, relation in report["matches"][args.opponent_name][
            "relations"
        ].items()
    }
    cells = {}
    for cell_dir in sorted(args.challenger_root.iterdir()):
        if not (cell_dir / "rollout" / "manifest.json").exists():
            continue
        cell = cell_dir.name.removeprefix("league-cell-")
        opponent_dir = args.opponent_root / cell_dir.name
        if not opponent_dir.exists():
            opponent_dir = args.opponent_root / cell
        cells[cell] = build_cell(cell, {
            args.challenger_name: cell_dir,
            args.opponent_name: opponent_dir,
        }, args.configs)
    result = {
        "contract": "league_spectator_data_v1",
        "read_only_contract": (
            "spectating never tunes training; league results are not a"
            " training signal, by design review 2026-08-25"
        ),
        "match_id": args.match_id,
        "challenger": args.challenger_name,
        "opponent": args.opponent_name,
        "promoted": bool(report.get("promoted")),
        "counts": report["matches"][args.opponent_name]["counts"],
        "benchmarks": report.get("benchmarks", {}),
        "relations": relations,
        "cells": cells,
        "highlights": build_highlights(
            cells, relations, args.challenger_name, args.opponent_name,
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "cells": len(cells),
        "highlights": [h["cell"] for h in result["highlights"][:3]],
        "bytes": len(json.dumps(result)),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
