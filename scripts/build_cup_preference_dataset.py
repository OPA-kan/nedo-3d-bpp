"""Convert preregistered Diversity Cup forks into preference examples.

The Cup aggregate intentionally publishes only a compact pair index.  The
cell artifacts retain the actual pre-action snapshot and the physically
screened root candidates.  This importer joins those two sources without
re-running physics and emits the same geometry-only dataset contract used by
the production preference learner.

Only strict, genuine-terminal actor-vs-champion forks are eligible.  Course
cells, not individual horse trajectories, are the split groups so two views
of the same exogenous stream can never cross a held-out boundary.
"""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_terminal_rollout_trigger_dataset import (
    _dominates,
    _oriented,
)


def _candidate_map(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["root_candidate_id"]): row
        for row in (record.get("search") or {}).get("root_candidates") or []
    }


def _pair_map(mining: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row["root_candidate_id"]): row
        for row in mining.get("pair_rows") or []
    }


def _relative_snapshot(
    cup_root: pathlib.Path, manifest_path: pathlib.Path, snapshot: str,
) -> str:
    path = manifest_path.parent / "episode-000" / snapshot
    if not path.is_file():
        raise ValueError(f"missing Cup snapshot: {path}")
    return path.relative_to(cup_root).as_posix()


def row_from_record(
    record: dict[str, Any], *, cup_root: pathlib.Path,
    manifest_path: pathlib.Path, cell: str, stud: str,
    stats: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    mining = record.get("mining") or {}
    winner = mining.get("winner_candidate_id")
    champion = mining.get("champion_candidate_id")
    actor = mining.get("actor_candidate_id") or mining.get(
        "rule_candidate_id"
    )
    if winner is None or champion is None or actor is None:
        return None
    ids = (str(champion), str(actor))
    if ids[0] == ids[1] or str(winner) not in ids:
        raise ValueError(
            f"{cell}/{stud}/{record.get('root_id')}: invalid strict pair ids"
        )
    candidates = _candidate_map(record)
    terminals = _pair_map(mining)
    oriented = {
        candidate_id: _oriented(
            (terminals.get(candidate_id) or {}).get("terminal_vector")
        )
        for candidate_id in ids
    }
    if any(value is None for value in oriented.values()):
        # Not a pair, so not an error.  Miners before the
        # ``pair_fork_winner`` fix could record a winner for a fork whose
        # loser dropped out of the terminal audit entirely (its action
        # turned out physically unsafe), leaving the survivor alone on a
        # one-candidate frontier with terminal_truth_complete still True.
        # A one-horse race is not strict dominance; skip it rather than
        # import it or abort the whole Cup on a legacy artifact.
        if stats is not None:
            stats["one_sided_verdicts_skipped"] = (
                stats.get("one_sided_verdicts_skipped", 0) + 1
            )
        return None
    actor_wins = _dominates(oriented[ids[1]], oriented[ids[0]])
    champion_wins = _dominates(oriented[ids[0]], oriented[ids[1]])
    expected_winner = ids[1] if actor_wins else ids[0] if champion_wins else None
    if expected_winner != str(winner):
        raise ValueError(
            f"{cell}/{stud}/{record.get('root_id')}: stored winner does not "
            "match current 4-head strict dominance"
        )
    joined = []
    for candidate_id in ids:
        if candidate_id not in candidates:
            raise ValueError(
                f"{cell}/{stud}/{record.get('root_id')}: "
                f"candidate {candidate_id} absent from root support"
            )
        terminal = terminals.get(candidate_id)
        if not terminal or not terminal.get("terminal_genuine"):
            raise ValueError(
                f"{cell}/{stud}/{record.get('root_id')}: "
                f"candidate {candidate_id} lacks genuine terminal truth"
            )
        candidate = copy.deepcopy(candidates[candidate_id])
        candidate.update({
            "terminal_genuine": True,
            "terminal_termination": terminal.get("terminal_termination"),
            "terminal_vector": terminal.get("terminal_vector"),
        })
        joined.append(candidate)
    timing = record.get("timing") or {}
    full_seconds = timing.get("decision_total_seconds")
    fork_seconds = mining.get("fork_seconds")
    if not isinstance(full_seconds, (int, float)):
        raise ValueError(
            f"{cell}/{stud}/{record.get('root_id')}: decision timing missing"
        )
    shallow_seconds = float(full_seconds)
    if isinstance(fork_seconds, (int, float)):
        shallow_seconds = max(0.0, shallow_seconds - float(fork_seconds))
    return {
        "contract": "cup_preference_row_v1",
        "cell": cell,
        "stud": stud,
        "root_id": f"{cell}:{stud}:{record.get('root_id')}",
        "source_root_id": record.get("root_id"),
        "step": int(record.get("step", 0)),
        "board_fingerprint": record.get("board_fingerprint"),
        "snapshot_path": _relative_snapshot(
            cup_root, manifest_path, str(record.get("snapshot_path"))
        ),
        "incumbent_candidate_id": ids[0],
        "selected_candidate_id": str(winner),
        "terminal_intervention": str(winner) != ids[0],
        "terminal_truth_complete": True,
        "decision_timing": {"decision_total_seconds": float(full_seconds)},
        "estimated_no_terminal_decision_seconds": shallow_seconds,
        "candidate_count": 2,
        "safe_candidate_count": 2,
        "candidates": joined,
    }


def build_dataset(cup_root: pathlib.Path) -> dict[str, Any]:
    rows = []
    stats: dict[str, int] = {}
    manifests = sorted(cup_root.rglob("manifest.json"))
    for manifest_path in manifests:
        # The compact aggregate has no episodes and is ignored here.
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        episodes = payload.get("episodes") or []
        if not episodes:
            continue
        horse_dir = manifest_path.parent.parent
        stud = horse_dir.name
        if stud == "learned":
            continue
        cell_dir = horse_dir.parent
        cell = cell_dir.name.removeprefix("cup-cell-")
        for record in episodes[0].get("records") or []:
            row = row_from_record(
                record, cup_root=cup_root, manifest_path=manifest_path,
                cell=cell, stud=stud, stats=stats,
            )
            if row is not None:
                rows.append(row)
    if not rows:
        raise ValueError(f"no strict Cup preference pairs below {cup_root}")
    groups = sorted({row["cell"] for row in rows})
    if len(groups) < 2:
        raise ValueError("Cup preference distillation requires >=2 course cells")
    return {
        "schema_version": 1,
        "contract": "terminal_rollout_trigger_dataset_with_actions_v1",
        "source_contract": "diversity_cup_strict_pairs_v1",
        "label": "actor_terminal_dominates_champion_terminal",
        "feature_horizon": "pre_action_state_and_action_geometry",
        "split_unit": "whole_cup_course_cell",
        "root_count": len(rows),
        "group_count": len(groups),
        "groups": groups,
        "actor_wins": sum(row["terminal_intervention"] for row in rows),
        "champion_wins": sum(not row["terminal_intervention"] for row in rows),
        "one_sided_verdicts_skipped": stats.get(
            "one_sided_verdicts_skipped", 0
        ),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cup-root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--expected-pairs", type=int, default=None)
    args = parser.parse_args()
    dataset = build_dataset(args.cup_root)
    if (
        args.expected_pairs is not None
        and dataset["root_count"] != args.expected_pairs
    ):
        raise ValueError(
            f"expected {args.expected_pairs} pairs, "
            f"found {dataset['root_count']}"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        key: dataset[key]
        for key in (
            "root_count", "group_count", "actor_wins", "champion_wins",
            "one_sided_verdicts_skipped",
        )
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
