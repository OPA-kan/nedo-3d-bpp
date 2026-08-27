"""Layer 1 only vs Layer 1 + Layer 2, and which family paid for it.

    python3 -m scripts.rule_alpha_layer2_ab

Runs every scenario twice per Layer 1 seed (``frontier_prefers_lying`` on and
off), with Layer 2 disabled and enabled, and reports the metrics Layer 2 is
actually supposed to move: connected hard plateau, reachable hard support,
stranded floor, back-half reachability by working height, and the placement
counts broken down by proposal family.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import statistics as st
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from rule_alpha import layer2 as l2, terrain as trn  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402
from rule_alpha.diagnostics import SUPPORT_HARD  # noqa: E402
from rule_alpha.episode import run_episode  # noqa: E402
from rule_alpha.scenarios import build_scenarios  # noqa: E402


def measure(result, config) -> dict:
    board = result.board
    model = board.model(0)
    placements = board.placements[0]
    terrain = trn.build_terrain(model, placements, config)
    grid = terrain.grid
    plateau = l2.hard_plateau_stats(
        grid, model.z_floor, config.plateau_height_tolerance
    )

    # reachable hard support: hard top that a straight-in sweep can still get to
    height = grid.height - model.z_floor
    running = np.maximum.accumulate(height, axis=1)
    before = np.concatenate(
        [np.zeros((height.shape[0], 1)), running[:, :-1]], axis=1
    )
    hard = grid.usable & (grid.support == SUPPORT_HARD)
    reachable_hard = float(
        (hard & (before <= height + 1e-9)).sum()
    ) * grid.cell_area

    reach = trn.reach_report(terrain, model, heights=(0.0, 0.20, 0.40, 0.60))
    bare = sum(
        v for k, v in trn.support_area_report(terrain, model).items()
        if k == "free-floor"
    )
    from rule_alpha.diagnostics import volume_report

    volume = volume_report(model, placements, config)

    families: dict[str, int] = {}
    layer2_volume = 0.0
    for placement in placements:
        family = (
            l2.FAMILY_SHELF if placement.surface == "shelf"
            else l2.FAMILY_FLOOR if placement.surface == "floor"
            else {
                l2.ROLE_TERRACE: l2.FAMILY_TERRACE,
                l2.ROLE_BRIDGE: l2.FAMILY_BRIDGE,
                l2.ROLE_WEDGE_BRIDGE: l2.FAMILY_WEDGE_BRIDGE,
            }.get(placement.role, l2.FAMILY_WEDGE_STEP)
        )
        families[family] = families.get(family, 0) + 1
        if family in (l2.FAMILY_TERRACE, l2.FAMILY_BRIDGE, l2.FAMILY_WEDGE_BRIDGE):
            layer2_volume += placement.volume

    return {
        "placed": result.summary["items_placed"],
        "fill": volume["volume_fill_ratio"],
        "plateau_largest": round(plateau["largest"], 4),
        "plateau_total": round(plateau["total"], 4),
        "plateau_count": plateau["count"],
        "reachable_hard": round(reachable_hard, 4),
        "stranded": round(
            bare - reach["0.00"]["reachable_free_m2"], 4
        ),
        "reach_back": {k: reach[k]["reachable_back_ratio"] for k in reach},
        "adherence": trn.order_report(model, placements)["back_to_front_adherence"],
        "families": families,
        "layer2_volume": round(layer2_volume, 4),
        "support_gain_efficiency": (
            round(plateau["total"] / layer2_volume, 3) if layer2_volume > 0 else None
        ),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=pathlib.Path,
                        default=pathlib.Path("reports/rule_alpha/layer2_ab.json"))
    parser.add_argument("--scenarios", type=str, default="")
    args = parser.parse_args(argv)

    scenarios = build_scenarios()
    if args.scenarios:
        wanted = {s.strip() for s in args.scenarios.split(",") if s.strip()}
        scenarios = [s for s in scenarios if s.name in wanted]

    payload: dict = {"arms": {}}
    for lying in (True, False):
        for layer2_on in (False, True):
            arm = f"lying={'on' if lying else 'off'} layer2={'on' if layer2_on else 'off'}"
            config = dataclasses.replace(
                DEFAULT_CONFIG,
                frontier_prefers_lying=lying,
                layer2_enabled=layer2_on,
            )
            rows = {}
            for scenario in scenarios:
                result = run_episode(scenario, config)
                rows[scenario.name] = measure(result, config)
                print(f"[{arm}] {scenario.name} placed={rows[scenario.name]['placed']}",
                      flush=True)
            payload["arms"][arm] = rows

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {args.out}")

    print(f"\n{'arm':<28}{'placed':>8}{'fill':>8}{'plateau':>9}{'hard':>8}"
          f"{'reach hard':>11}{'stranded':>10}{'adher':>7}")
    for arm, rows in payload["arms"].items():
        values = list(rows.values())
        print(
            f"{arm:<28}{sum(v['placed'] for v in values):>8}"
            f"{st.mean(v['fill'] for v in values):>8.3f}"
            f"{st.mean(v['plateau_largest'] for v in values):>9.4f}"
            f"{st.mean(v['plateau_total'] for v in values):>8.4f}"
            f"{st.mean(v['reachable_hard'] for v in values):>11.4f}"
            f"{st.mean(v['stranded'] for v in values):>10.4f}"
            f"{st.mean(v['adherence'] for v in values):>7.3f}"
        )

    print("\nplacements by family")
    for arm, rows in payload["arms"].items():
        totals: dict[str, int] = {}
        for row in rows.values():
            for family, count in row["families"].items():
                totals[family] = totals.get(family, 0) + count
        print(f"  {arm:<28}{totals}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
