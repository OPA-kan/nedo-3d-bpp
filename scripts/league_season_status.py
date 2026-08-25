"""Validate and summarize the checked-in packing-league season state.

This is the single operator entrypoint after a manual recovery or merge:

    python scripts/league_season_status.py

It never changes files or calls GitHub.  A zero exit code means the state,
registry, preregistered wave and both workflow matrices describe one season.
"""

from __future__ import annotations

import json
import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def status(root: pathlib.Path = ROOT) -> dict:
    state = _read(root / "reports/league/season/state.json")
    plan = _read(root / "reports/league/season/waves.json")
    registry = _read(root / "reports/league/registry.json")
    collection = (root / ".github/workflows/terminal-rollout-hard-state.yml").read_text(
        encoding="utf-8"
    )
    learning = (root / ".github/workflows/rollout-geometry-policy-learning.yml").read_text(
        encoding="utf-8"
    )
    champions = [row for row in registry["members"] if row.get("role") == "champion"]
    errors: list[str] = []
    if len(champions) != 1:
        errors.append(f"registry has {len(champions)} champions")
        champion_name = None
    else:
        champion_name = champions[0]["name"]
        if champion_name != state.get("champion"):
            errors.append(
                f"state champion {state.get('champion')} != registry {champion_name}"
            )

    wave = str(state["wave"])
    spec = plan["waves"].get(wave)
    if spec is None:
        errors.append(f"wave {wave} is not preregistered")
        expected = None
    else:
        expected = int(spec["expected_cells"])
        if int(state["round"]) != int(spec["round"]):
            errors.append(f"wave {wave} round does not match the plan")
        if int(state["expected_cells"]) != expected:
            errors.append(f"wave {wave} expected_cells does not match the plan")

    collection_cells = re.findall(r"- cell: (\S+)", collection)
    learning_cells = re.findall(r"- \{cell: ([^,]+),", learning)
    collection_guard = int(re.search(
        r"--expected-manifests (\d+)", collection
    ).group(1))
    learning_guard = int(re.search(r"--expected-cells (\d+)", learning).group(1))
    observed = {
        "collection": len(collection_cells),
        "learning": len(learning_cells),
        "collection_guard": collection_guard,
        "learning_guard": learning_guard,
    }
    if expected is not None and any(value != expected for value in observed.values()):
        errors.append(f"workflow matrix/guard counts {observed} != {expected}")
    if sorted(collection_cells) != sorted(learning_cells):
        errors.append("collection and learning matrices differ")

    return {
        "ok": not errors,
        "stage": state["stage"],
        "round": state["round"],
        "wave": state["wave"],
        "challenger": state.get("challenger"),
        "champion": champion_name,
        "runs": state.get("runs", {}),
        "expected_cells": expected,
        "matrix_counts": observed,
        "errors": errors,
    }


def main() -> int:
    result = status()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
