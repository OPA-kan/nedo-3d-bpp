"""Apply one preregistered league-season wave to the two workflow matrices.

Reads the season plan, appends the wave's fresh cells to the hard-state
collection matrix, mirrors the full matrix into the learning workflow's
recovery matrix, and bumps both expected-count guards.  Purely textual
and deterministic so a season round is one reviewable diff.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLAN = ROOT / "reports" / "league" / "season" / "waves.json"
COLLECTION = ROOT / ".github" / "workflows" / "terminal-rollout-hard-state.yml"
LEARNING = (
    ROOT / ".github" / "workflows" / "rollout-geometry-policy-learning.yml"
)


def wave_cells(plan: dict, wave: str) -> list[tuple[str, str]]:
    spec = plan["waves"][wave]
    cells = []
    for prime in spec["primes_000"]:
        for scenario in plan["scenarios_000"]:
            cells.append((scenario, f"permute-000-{prime}"))
    for prime in spec["primes_001"]:
        for scenario in plan["scenarios_001"]:
            cells.append((scenario, f"permute-001-{prime}"))
    return cells


def apply(wave: str) -> dict:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    spec = plan["waves"][wave]
    fresh = wave_cells(plan, wave)
    forbidden = set(plan["eval_variants_forbidden"])
    if any(stream in forbidden for _scenario, stream in fresh):
        raise SystemExit("wave would touch a frozen eval variant")

    text = COLLECTION.read_text(encoding="utf-8")
    existing = re.findall(
        r"- cell: (\S+)\n\s+scenario: (\S+)\n\s+stream: (\S+)", text
    )
    existing_cells = {cell for cell, _s, _v in existing}
    additions = []
    for scenario, stream in fresh:
        cell = f"{scenario}-{stream}"
        if cell in existing_cells:
            continue
        additions.append(
            f"          - cell: {cell}\n"
            f"            scenario: {scenario}\n"
            f"            stream: {stream}\n"
        )
    if additions:
        last_cell, last_scenario, last_stream = existing[-1]
        anchor = (
            f"          - cell: {last_cell}\n"
            f"            scenario: {last_scenario}\n"
            f"            stream: {last_stream}\n"
        )
        if anchor not in text:
            raise SystemExit("collection matrix anchor entry not found")
        text = text.replace(anchor, anchor + "".join(additions), 1)
    text, manifests_subs = re.subn(
        r"--expected-manifests \d+",
        f"--expected-manifests {spec['expected_cells']}",
        text,
    )
    if manifests_subs != 1:
        raise SystemExit("expected exactly one --expected-manifests guard")
    COLLECTION.write_text(text, encoding="utf-8")

    rows = re.findall(
        r"- cell: (\S+)\n\s+scenario: (\S+)\n\s+stream: (\S+)", text
    )
    if len(rows) != spec["expected_cells"]:
        raise SystemExit(
            f"collection matrix has {len(rows)} cells, expected "
            f"{spec['expected_cells']}"
        )

    learning = LEARNING.read_text(encoding="utf-8")
    matrix_lines = "\n".join(
        f"          - {{cell: {cell}, scenario: {scenario}, stream: {stream}}}"
        for cell, scenario, stream in rows
    )
    start = learning.index("        include:\n") + len("        include:\n")
    end = learning.index("    runs-on:", start)
    learning = learning[:start] + matrix_lines + "\n" + learning[end:]
    learning, cells_subs = re.subn(
        r"--expected-cells \d+",
        f"--expected-cells {spec['expected_cells']}",
        learning,
    )
    if cells_subs != 1:
        raise SystemExit("expected exactly one --expected-cells guard")
    LEARNING.write_text(learning, encoding="utf-8")
    return {
        "wave": wave,
        "round": spec["round"],
        "new_cells": len(additions),
        "total_cells": spec["expected_cells"],
        "already_applied": not additions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave", required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.wave)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
