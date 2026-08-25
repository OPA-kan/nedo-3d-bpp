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
from typing import Any

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
    payload = json.loads(
        (configs / stream / f"{scenario}.json").read_text(encoding="utf-8")
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
    snapshot = json.loads(sorted(
        (cell_dir / "rollout" / "episode-000").glob("step-*-state.json")
    )[0].read_text(encoding="utf-8"))
    containers = [
        {
            "index": int(row.get("index", 0)),
            "center": [float(v) for v in row.get("center", [0, 0, 0])],
            "length": float(row.get("length", 0) or 0),
            "width": float(row.get("width", 0) or 0),
            "height": float(row.get("height", 0) or 0),
            "shelf": bool(row.get("shelf")),
        }
        for row in snapshot["observation"]["container_list"]
    ]
    return {"episode": episode, "containers": containers}


def arm_steps(
    episode: dict[str, Any], items: dict[int, tuple[float, float, float]],
) -> list[dict[str, Any]]:
    records = episode.get("records") or []
    steps = []
    for position, record in enumerate(records):
        action = record["action"]
        selection = record.get("selection") or {}
        if position + 1 < len(records):
            after = records[position + 1].get("metrics_before") or {}
        else:
            after = episode.get("final_metrics") or {}
        scores = selection.get("learned_scores") or {}
        selected_score = scores.get(selection.get("selected_candidate_id"))
        item_index = int(action["item_idx"])
        steps.append({
            "t": int(record.get("step", position)),
            "item": item_index,
            "cont": int(action["container_idx"]),
            "pos": [round(float(v), 4) for v in action["place_pos"]],
            "o": int(action["orientation"]),
            "dims": [
                round(v, 4)
                for v in rotated(items[item_index], action["orientation"])
            ],
            "switched": bool(selection.get("switched")),
            "reason": selection.get("reason"),
            "conf": (
                round(float(selected_score), 4)
                if isinstance(selected_score, (int, float)) else None
            ),
            "placed": int(after.get("placed_count", 0)),
            "fill": round(float(after.get("fill_score_proxy", 0.0)), 4),
        })
    return steps


def violations(final: dict[str, Any]) -> float:
    return float(sum(float(final.get(head, 0) or 0)
                     for head in VIOLATION_HEADS))


def build_cell(
    cell: str, arms: dict[str, pathlib.Path], configs: pathlib.Path,
) -> dict[str, Any]:
    scenario, stream = cell.rsplit("-permute-", 1)
    stream = f"permute-{stream}"
    items = load_config_items(configs, stream, scenario)
    payloads = {name: episode_payload(path) for name, path in arms.items()}
    used = set()
    arm_data = {}
    for name, payload in payloads.items():
        episode = payload["episode"]
        steps = arm_steps(episode, items)
        used.update(step["item"] for step in steps)
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
    divergence = None
    if len(names) == 2:
        first, second = (arm_data[name]["steps"] for name in names)
        for a, b in zip(first, second):
            if (a["item"], a["cont"], a["pos"], a["o"]) != (
                b["item"], b["cont"], b["pos"], b["o"]
            ):
                divergence = a["t"]
                break
        else:
            if len(first) != len(second):
                divergence = min(len(first), len(second))
    return {
        "scenario": scenario,
        "stream": stream,
        "containers": payloads[names[0]]["containers"],
        "items": {str(index): list(items[index]) for index in sorted(used)},
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
        cell = cell_dir.name
        cells[cell] = build_cell(cell, {
            args.challenger_name: cell_dir,
            args.opponent_name: args.opponent_root / cell,
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
