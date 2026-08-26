"""Score a Diversity Cup: research standings first, race standings second.

Reads the cup episode tree (``<root>/cup-cell-<cell>/<horse>/rollout/``),
computes per-stud teacher-mining metrics (novel board fingerprints
versus the champion's runs of the same streams, action disagreements,
strict dominance pairs and their physics yield, event coverage), builds
all pairwise W-L-D-incomparable tables from the shared terminal
relation, and extracts the mined preference pairs as the side corpus.

The cup is preregistered in
``reports/self-play-packing/diversity-cup-design.md``: cells never touch
the season matrices, and mined pairs feed training only through a
separately preregistered step.
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

from scripts.league import episode_outcome, paired_relation  # noqa: E402

CHAMPION = "learned"
MINERS = ("current-agent", "rule-grid", "rule-lowcog", "rule-edge")
HORSES = (CHAMPION,) + MINERS
EVENT_HEADS = (
    "soft_violation_gain", "priority_covered_gain",
    "priority_misrouted_gain",
)


def load_cup(root: pathlib.Path) -> dict[str, dict[str, dict[str, Any]]]:
    """{cell: {horse: manifest}} from the cup artifact tree."""
    cup: dict[str, dict[str, dict[str, Any]]] = {}
    for path in sorted(root.rglob("manifest.json")):
        horse_dir = path.parent
        if horse_dir.name == "rollout":
            horse_dir = horse_dir.parent
        horse = horse_dir.name
        cell = horse_dir.parent.name
        if cell.startswith("cup-cell-"):
            cell = cell[len("cup-cell-"):]
        cup.setdefault(cell, {})[horse] = json.loads(
            path.read_text(encoding="utf-8")
        )
    if not cup:
        raise ValueError(f"no manifest.json under {root}")
    return cup


def _fingerprints(manifest: dict[str, Any]) -> set[str]:
    episode = manifest["episodes"][0]
    return {
        str(record["board_fingerprint"])
        for record in episode.get("records", [])
    }


def _mining_events(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    episode = manifest["episodes"][0]
    return [
        {**record["mining"], "step": record["step"],
         "snapshot_path": record.get("snapshot_path"),
         "root_id": record.get("root_id")}
        for record in episode.get("records", [])
        if record.get("mining")
    ]


def stud_metrics(
    cell: str, horse: str, manifest: dict[str, Any],
    champion_manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    episode = manifest["episodes"][0]
    boards = _fingerprints(manifest)
    champion_boards = (
        _fingerprints(champion_manifest) if champion_manifest else set()
    )
    events = _mining_events(manifest)
    forked = [event for event in events if "pair_rows" in event]
    strict = [
        event for event in forked
        if event.get("winner_candidate_id") is not None
    ]
    actor_wins = 0
    champion_wins = 0
    for event in strict:
        actor_id = event.get("actor_candidate_id") or event.get(
            "rule_candidate_id"
        )
        if event.get("winner_candidate_id") == actor_id:
            actor_wins += 1
        elif event.get("winner_candidate_id") == event.get(
            "champion_candidate_id"
        ):
            champion_wins += 1
    coverage = {head: 0 for head in EVENT_HEADS}
    for event in strict:
        for row in event.get("pair_rows", []):
            vector = row.get("terminal_vector") or {}
            for head in EVENT_HEADS:
                if abs(float(vector.get(head, 0.0) or 0.0)) > 1e-9:
                    coverage[head] += 1
    fork_equiv = int(
        episode.get("mining_fork_physical_step_equivalents") or 0
    )
    strict_pairs = int(episode.get("mining_strict_pairs") or 0)
    return {
        "cell": cell,
        "horse": horse,
        "steps": int(episode.get("steps", 0)),
        "termination": episode.get("termination"),
        "boards": len(boards),
        "novel_boards": len(boards - champion_boards),
        "novel_board_rate": (
            len(boards - champion_boards) / len(boards) if boards else 0.0
        ),
        "disagreements": int(episode.get("mining_disagreements") or 0),
        "forks": int(episode.get("mining_forks") or 0),
        "strict_pairs": strict_pairs,
        "actor_wins": actor_wins,
        "champion_wins": champion_wins,
        "candidate_support_misses": int(
            episode.get("current_agent_support_misses") or 0
        ),
        "fork_physical_step_equivalents": fork_equiv,
        "pairs_per_million_step_equivalents": (
            strict_pairs / fork_equiv * 1e6 if fork_equiv else 0.0
        ),
        "event_coverage": coverage,
        "final_metrics": {
            key: manifest["episodes"][0]["final_metrics"].get(key)
            for key in ("placed_count", "fill_score_proxy",
                        "soft_covered_by_other",
                        "priority_covered_by_other", "priority_misrouted")
        },
    }


def pairwise_tables(
    cup: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    tables: dict[str, dict[str, Any]] = {}
    for index, first in enumerate(HORSES):
        for second in HORSES[index + 1:]:
            counts = {
                "challenger_wins": 0, "member_wins": 0,
                "equal": 0, "incomparable": 0, "unmeasured": 0,
            }
            relations = {}
            for cell, horses in sorted(cup.items()):
                if first not in horses or second not in horses:
                    continue
                # current-agent always executes its own action, including
                # a physically rejected one (diversity-cup-design.md), so
                # its episode can legitimately end in a non-genuine
                # termination with no shake test and thus no
                # post_shake_* heads. league.episode_outcome() is
                # deliberately strict for the frozen league eval cells,
                # where every episode is guaranteed to reach genuine
                # termination; here that guarantee doesn't hold, so treat
                # the missing-head ValueError as an honest "unmeasured"
                # cell instead of failing the whole report.
                try:
                    relation = paired_relation(
                        episode_outcome(horses[first])["heads"],
                        episode_outcome(horses[second])["heads"],
                    )
                except ValueError:
                    relation = "unmeasured"
                relations[cell] = relation
                counts[relation] += 1
            tables[f"{first}_vs_{second}"] = {
                "counts": counts, "relations": relations,
            }
    return tables


def side_corpus(
    cup: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    pairs = []
    for cell, horses in sorted(cup.items()):
        for horse in MINERS:
            manifest = horses.get(horse)
            if not manifest:
                continue
            for event in _mining_events(manifest):
                winner = event.get("winner_candidate_id")
                if winner is None or "pair_rows" not in event:
                    continue
                pairs.append({
                    "cell": cell,
                    "stud": horse,
                    "actor_policy": event.get("actor_policy") or horse,
                    "step": event["step"],
                    "root_id": event.get("root_id"),
                    "snapshot_path": event.get("snapshot_path"),
                    "actor_candidate_id": (
                        event.get("actor_candidate_id")
                        or event.get("rule_candidate_id")
                    ),
                    "rule_candidate_id": event.get("rule_candidate_id"),
                    "champion_candidate_id": event["champion_candidate_id"],
                    "champion_probability": event.get(
                        "champion_probability"
                    ),
                    "winner_candidate_id": winner,
                    "pair_rows": event.get("pair_rows"),
                })
    return pairs


def analyze(root: pathlib.Path) -> dict[str, Any]:
    cup = load_cup(root)
    studs = [
        stud_metrics(cell, horse, horses[horse], horses.get(CHAMPION))
        for cell, horses in sorted(cup.items())
        for horse in MINERS if horse in horses
    ]
    totals = {}
    for horse in MINERS:
        rows = [row for row in studs if row["horse"] == horse]
        boards = sum(row["boards"] for row in rows)
        novel = sum(row["novel_boards"] for row in rows)
        equiv = sum(row["fork_physical_step_equivalents"] for row in rows)
        pairs = sum(row["strict_pairs"] for row in rows)
        totals[horse] = {
            "cells": len(rows),
            "boards": boards,
            "novel_boards": novel,
            "novel_board_rate": novel / boards if boards else 0.0,
            "disagreements": sum(row["disagreements"] for row in rows),
            "forks": sum(row["forks"] for row in rows),
            "strict_pairs": pairs,
            "actor_wins": sum(row["actor_wins"] for row in rows),
            "champion_wins": sum(row["champion_wins"] for row in rows),
            "candidate_support_misses": sum(
                row["candidate_support_misses"] for row in rows
            ),
            "fork_physical_step_equivalents": equiv,
            "pairs_per_million_step_equivalents": (
                pairs / equiv * 1e6 if equiv else 0.0
            ),
        }
    terminal_rows = []
    for cell, horses in sorted(cup.items()):
        for horse, manifest in sorted(horses.items()):
            final = manifest["episodes"][0].get("final_metrics") or {}
            fill = final.get("fill_score_proxy")
            if isinstance(fill, (int, float)):
                terminal_rows.append({
                    "cell": cell,
                    "horse": horse,
                    "fill_score_proxy": float(fill),
                    "placed_count": final.get("placed_count"),
                })
    max_by_horse = {}
    for row in terminal_rows:
        previous = max_by_horse.get(row["horse"])
        if previous is None or row["fill_score_proxy"] > previous[
            "fill_score_proxy"
        ]:
            max_by_horse[row["horse"]] = row
    max_terminal_fill = (
        max(
            terminal_rows,
            key=lambda row: (
                row["fill_score_proxy"], row["horse"], row["cell"]
            ),
        )
        if terminal_rows else None
    )
    corpus = side_corpus(cup)
    return {
        "contract": "diversity_cup_report_v1",
        "design": "reports/self-play-packing/diversity-cup-design.md",
        "cells": sorted(cup),
        "horses": {
            cell: sorted(horses) for cell, horses in sorted(cup.items())
        },
        "stud_rows": studs,
        "stud_totals": totals,
        "race_tables": pairwise_tables(cup),
        "side_corpus_pairs": len(corpus),
        "max_terminal_fill": max_terminal_fill,
        "max_terminal_fill_by_horse": max_by_horse,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument(
        "--pairs-out", type=pathlib.Path, default=None,
        help="side-corpus preference pairs (jsonl)",
    )
    args = parser.parse_args()
    report = analyze(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.pairs_out is not None:
        pairs = side_corpus(load_cup(args.root))
        args.pairs_out.parent.mkdir(parents=True, exist_ok=True)
        args.pairs_out.write_text(
            "".join(
                json.dumps(pair, ensure_ascii=False) + "\n"
                for pair in pairs
            ),
            encoding="utf-8",
        )
    print(json.dumps({
        "cells": len(report["cells"]),
        "side_corpus_pairs": report["side_corpus_pairs"],
        "stud_totals": {
            horse: {
                key: row[key]
                for key in ("novel_board_rate", "disagreements",
                            "strict_pairs")
            }
            for horse, row in report["stud_totals"].items()
        },
        "max_terminal_fill": report["max_terminal_fill"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
