"""Attach recovered command actions to a frozen rollout trigger dataset."""

from __future__ import annotations

import argparse
import copy
import json
import pathlib
from typing import Any


def attach(
    dataset: dict[str, Any], recoveries: list[dict[str, Any]],
    *, expected_cells: int,
) -> dict[str, Any]:
    if len(recoveries) != expected_cells:
        raise ValueError(
            f"expected {expected_cells} recoveries, found {len(recoveries)}"
        )
    if {row.get("contract") for row in recoveries} != {
        "trigger_candidate_action_recovery_v1"
    }:
        raise ValueError("unexpected candidate action recovery contract")
    cells = [str(row["cell"]) for row in recoveries]
    if len(cells) != len(set(cells)):
        raise ValueError("duplicate candidate action recovery cells")
    action_maps = {
        str(root_id): actions
        for recovery in recoveries
        for root_id, actions in recovery["actions"].items()
    }
    result = copy.deepcopy(dataset)
    result["contract"] = "terminal_rollout_trigger_dataset_with_actions_v1"
    attached = 0
    for row in result.get("rows") or []:
        root_id = str(row["root_id"])
        if root_id not in action_maps:
            raise ValueError(f"missing action recovery for root {root_id}")
        for candidate in row.get("candidates") or []:
            candidate_id = str(candidate["root_candidate_id"])
            action = action_maps[root_id].get(candidate_id)
            if action is None:
                raise ValueError(
                    f"missing action for {root_id}/{candidate_id}"
                )
            candidate["command_action"] = action
            attached += 1
    result["candidate_action_contract"] = {
        "contract": "root_candidate_command_action_v1",
        "source": "deterministic_provider_replay",
        "cells": len(recoveries),
        "candidate_actions": attached,
        "future_collection": "stored_directly_in_search_record",
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=pathlib.Path, required=True)
    parser.add_argument("--recovery-root", type=pathlib.Path, required=True)
    parser.add_argument("--expected-cells", type=int, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    recoveries = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(args.recovery_root.rglob("actions.json"))
    ]
    result = attach(
        json.loads(args.dataset.read_text(encoding="utf-8")),
        recoveries,
        expected_cells=args.expected_cells,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["candidate_action_contract"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
