"""Offline Layer 1 episode driver.

Runs rule-alpha against the analytic model of the official validator, which is
enough to answer the questions this prototype exists for (what does the first
layer look like?) without paying for PyBullet on every scenario.  ``physics.py``
runs the same planner inside the real simulator when the settle behaviour
itself is what is in question.

Deviation from the official environment, on purpose: the official env
terminates the episode the moment one placement fails.  Here an item that no
rule can place is *skipped* and recorded, because a board that stops after
three items shows nothing.  ``on_unplaceable="stop"`` restores the official
behaviour.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field

from . import classify as cls
from . import layer1
from .diagnostics import board_report


@dataclass
class StepLog:
    step: int
    placement: dict
    candidate_counts: dict
    veto_counts: dict
    considered: int
    ladder: list
    board: dict


@dataclass
class EpisodeResult:
    scenario: str
    config: dict
    containers: list
    containers_raw: list = field(default_factory=list)
    zone_scales: dict = field(default_factory=dict)
    steps: list[StepLog] = field(default_factory=list)
    snapshots: list = field(default_factory=list)
    sequence: list = field(default_factory=list)
    unplaced: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    board: layer1.Board | None = None

    def to_jsonl(self) -> str:
        lines = [
            json.dumps(
                {"record": "scenario", "scenario": self.scenario, "config": self.config,
                 "containers": self.containers},
                ensure_ascii=False,
            )
        ]
        for step in self.steps:
            lines.append(
                json.dumps(
                    {
                        "record": "step",
                        "step": step.step,
                        **step.placement,
                        "candidate_count_by_archetype": step.candidate_counts,
                        "veto_count_by_rule": step.veto_counts,
                        "candidates_considered": step.considered,
                        "archetype_ladder": step.ladder,
                        "board": step.board,
                    },
                    ensure_ascii=False,
                )
            )
        for item in self.unplaced:
            lines.append(json.dumps({"record": "unplaced", **item}, ensure_ascii=False))
        lines.append(
            json.dumps({"record": "summary", **self.summary}, ensure_ascii=False)
        )
        return "\n".join(lines) + "\n"


def _pool_order(profiles: list[cls.ItemProfile]) -> list[cls.ItemProfile]:
    """Which visible item to try first.  Same rule as the offline order."""
    return sorted(
        profiles,
        key=lambda p: (
            {cls.NORMAL_HARD: 0, cls.PRIORITY: 2, cls.SOFT_PRIORITY: 3, cls.SOFT: 4}[
                p.cargo_class
            ]
            + (1 if p.cargo_class == cls.NORMAL_HARD and p.is_elongated else 0),
            -round(p.max_footprint, 6),
            -round(p.mass, 6),
            p.index,
        ),
    )


def _compact_board(board: layer1.Board, config) -> dict:
    """One-line-per-step board digest (cheap grid) for the JSONL log."""
    out = {}
    for idx, model in enumerate(board.models):
        grid = board.grid(idx)
        free = grid.free_mask()
        reached = layer1.reachable_from_boundary(free, grid.usable)
        interior = free & ~reached
        wall_ratio = layer1._wall_height_ratio(board, idx, model)
        placements = board.placements[idx]
        from .diagnostics import plateau_report

        plateaus = plateau_report(grid, config)
        plateaus.pop("_labels", None)
        out[str(model.index)] = {
            "floor_coverage": round(grid.coverage(), 4),
            "wall_height_ratio": round(wall_ratio, 4),
            "largest_plateau_ratio": plateaus["largest_plateau_ratio"],
            "plateau_count": plateaus["plateau_count"],
            "interior_hole_count": int(
                layer1._count_components(interior)
            ),
            "interior_hole_area": round(float(interior.sum()) * grid.cell_area, 4),
            "largest_interior_hole_area": round(
                _largest_component_area(interior, grid.cell_area), 4
            ),
            "remaining_contiguous_free_area": round(
                _largest_component_area(reached, grid.cell_area), 4
            ),
            "placed": len(placements),
        }
    return out


def _largest_component_area(mask, cell_area: float) -> float:
    if not mask.any():
        return 0.0
    from .diagnostics import connected_components
    import numpy as np

    labels, count = connected_components(mask)
    if count == 0:
        return 0.0
    sizes = np.bincount(labels.ravel())[1:]
    return float(sizes.max()) * cell_area


def run_episode(scenario, config, snapshot_steps: int = 4,
                on_unplaceable: str = "skip", max_steps: int = 400) -> EpisodeResult:
    started = time.perf_counter()
    containers = copy.deepcopy(scenario.containers)
    board = layer1.Board(containers, config)

    profiles = [
        cls.classify_item(int(item["index"]), item, config)
        for item in scenario.items
    ]
    reference_model = next(
        (m for m in board.models if not m.is_prioritized), board.models[0]
    )
    zone_scales = board.set_zone_demand(profiles, config)
    triangle_demand = board.set_triangle_demand(profiles, config)
    order = layer1.constructive_order(profiles, config, reference_model)
    by_index = {p.index: p for p in profiles}
    queue = [by_index[i] for i in order]

    lookahead = max(1, int(scenario.look_ahead))
    pool: list[cls.ItemProfile] = []
    cursor = 0
    while len(pool) < lookahead and cursor < len(queue):
        pool.append(queue[cursor])
        cursor += 1

    result = EpisodeResult(
        scenario=scenario.name,
        config=config.to_dict(),
        containers=[m.describe() for m in board.models],
        containers_raw=copy.deepcopy(scenario.containers),
        zone_scales=zone_scales,
    )
    result.board = board

    step = 0
    stop_reason = "stream-exhausted"
    while pool and step < max_steps:
        decision = None
        chosen_profile = None
        for profile in _pool_order(pool):
            decision = layer1.choose_for_item(board, profile, config)
            if decision is not None:
                chosen_profile = profile
                break
        if decision is None or chosen_profile is None:
            if on_unplaceable == "stop":
                stop_reason = "layer1-saturated (official env would terminate here)"
                for profile in pool:
                    result.unplaced.append(
                        {**profile.summary(), "why": "no valid Layer 1 candidate"}
                    )
                break
            dropped = _pool_order(pool)[0]
            result.unplaced.append(
                {**dropped.summary(), "why": "no valid Layer 1 candidate"}
            )
            pool.remove(dropped)
            if cursor < len(queue):
                pool.append(queue[cursor])
                cursor += 1
            continue

        step += 1
        decision.placement.step = step
        board.apply(decision.placement)
        result.sequence.append(decision.placement)
        result.steps.append(
            StepLog(
                step=step,
                placement=decision.placement.as_dict(config),
                candidate_counts={
                    k: v for k, v in decision.candidate_counts.items() if v
                },
                veto_counts=decision.veto_counts,
                considered=decision.considered,
                ladder=decision.ladder,
                board=_compact_board(board, config),
            )
        )
        pool.remove(chosen_profile)
        if cursor < len(queue):
            pool.append(queue[cursor])
            cursor += 1
    else:
        if step >= max_steps:
            stop_reason = "max-steps"

    # snapshots: initial, evenly spaced intermediates, final
    total = len(result.steps)
    marks = {0, total}
    if snapshot_steps > 0 and total > 1:
        for i in range(1, snapshot_steps + 1):
            marks.add(round(total * i / (snapshot_steps + 1)))
    result.snapshots = sorted(m for m in marks if 0 <= m <= total)

    reports = [
        board_report(
            board.model(i), board.placements[i], config,
            triangle_state=board.triangle_state(i),
        )
        for i in range(len(board.models))
    ]
    placed = sum(len(p) for p in board.placements)
    result.summary = {
        "scenario": scenario.name,
        "description": scenario.description,
        "stop_reason": stop_reason,
        "items_in_stream": len(profiles),
        "items_placed": placed,
        "items_unplaced": len(result.unplaced),
        "runtime_seconds": round(time.perf_counter() - started, 2),
        "elongation_tau": config.elongation_tau,
        "zone_scales": zone_scales,
        "triangle_demand": triangle_demand,
        "containers": reports,
        "class_histogram": _class_histogram(profiles),
        "placed_class_histogram": _placed_histogram(board),
        "role_histogram": _role_histogram(board),
        "archetype_histogram": _archetype_histogram(result.steps),
    }
    return result


def _class_histogram(profiles) -> dict:
    out: dict[str, int] = {}
    for profile in profiles:
        out[profile.cargo_class] = out.get(profile.cargo_class, 0) + 1
        if profile.is_elongated:
            out["elongated(any class)"] = out.get("elongated(any class)", 0) + 1
    return out


def _placed_histogram(board: layer1.Board) -> dict:
    out: dict[str, int] = {}
    for placements in board.placements:
        for placement in placements:
            key = f"{placement.profile.cargo_class}/{placement.surface}"
            out[key] = out.get(key, 0) + 1
    return out


def _role_histogram(board: layer1.Board) -> dict:
    out: dict[str, int] = {}
    for placements in board.placements:
        for placement in placements:
            out[placement.role] = out.get(placement.role, 0) + 1
    return out


def _archetype_histogram(steps) -> dict:
    out: dict[str, int] = {}
    for step in steps:
        key = step.placement["archetype"]
        out[key] = out.get(key, 0) + 1
    return out
