"""
Do the two board-feature fixes actually FIRE on the development configs?

`board-receptivity-still-mixed-with-the-instrument-fixed` compared
board_k3 against board_fixed_k3 and found the fixes moved one cell. Two
readings survive that: either the filters fire and the ranking is
genuinely insensitive to them, or the filters almost never fire on these
five configs and the comparison measured nothing.

This separates them. It runs one episode per config under the
board_fixed_k3 arm and, at every board_features_after call, recomputes
the site counts under all four filter settings. The per-call deltas are
the firing rate; they do not depend on whether the argmax moved.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path("/home/user/nedo-3d-bpp")
SIMULATOR = ROOT / "simulator"
sys.path.insert(0, str(SIMULATOR))
os.chdir(SIMULATOR)

LOG = pathlib.Path(os.environ["BOARD_FIRING_LOG"])

import time  # noqa: E402

import agent as A  # noqa: E402

_board_choice_calls = []
_original_choice = A.Agent._board_choice


def traced_choice(self, top, observation, ordered_items):
    start = time.perf_counter()
    out = _original_choice(self, top, observation, ordered_items)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "event": "board_choice",
                    "candidates": len(top),
                    "seconds": time.perf_counter() - start,
                }
            )
            + "\n"
        )
    return out


A.Agent._board_choice = traced_choice

_original_top = A.PlacementCore.top_candidates


def traced_top(observation, ordered_items, top_k, **kwargs):
    start = time.perf_counter()
    out = _original_top(observation, ordered_items, top_k, **kwargs)
    end = time.perf_counter()
    search_deadline = kwargs.get("deadline")
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "event": "search",
                    "seconds": end - start,
                    "slack_at_return": (
                        None
                        if search_deadline is None
                        else float(search_deadline) - end
                    ),
                    "candidates": len(out),
                }
            )
            + "\n"
        )
    return out


A.PlacementCore.top_candidates = staticmethod(traced_top)

_original_policy = A.Agent.policy


def traced_policy(self, observation):
    out = _original_policy(self, observation)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "event": "step",
                    "top_candidate_count": int(
                        getattr(self, "last_top_candidate_count", 0) or 0
                    ),
                }
            )
            + "\n"
        )
    return out


A.Agent.policy = traced_policy

_original = A.board_features_after


def _counts(grid, top, filled, shapes, landable, reach):
    headroom = grid.ceiling - top
    total = 0
    accepted = 0
    for shape in shapes:
        n = A._board_site_count(
            grid, top, headroom, shape, landable=landable, reach=reach
        )
        total += n
        accepted += 1 if n > 0 else 0
    return total, accepted


def traced(container, candidate, shapes, item=None):
    grid = A.board_grid(container)
    base_top, base_filled, base_landable = A.board_occupancy(container, grid)
    top = base_top.copy()
    filled = base_filled.copy()
    landable = base_landable.copy()
    A._board_stamp(
        grid,
        top,
        filled,
        A.settled_proxy_candidate(candidate, container),
        landable=landable,
        can_land=not (
            bool((item or {}).get("is_soft", False))
            or bool((item or {}).get("is_prioritized", False))
        ),
    )
    reach = A.board_reach_headroom(grid, top)
    row = {
        "event": "features",
        "none": _counts(grid, top, filled, shapes, None, None),
        "land": _counts(grid, top, filled, shapes, landable, None),
        "reach": _counts(grid, top, filled, shapes, None, reach),
        "both": _counts(grid, top, filled, shapes, landable, reach),
        "non_landable_cells": int((~landable).sum()),
        "cells": int(landable.size),
    }
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    return _original(container, candidate, shapes, item)


A.board_features_after = traced

from src.ground_handling.app import EvaluationApp  # noqa: E402

config_path = sys.argv[1]
result_dir = sys.argv[2]
pathlib.Path(result_dir).mkdir(parents=True, exist_ok=True)
EvaluationApp(
    config_path=config_path,
    module_path="",
    agent_module="agent",
    agent_class="Agent",
    result_dir=result_dir,
    result_fname="evaluation_results.json",
).run(render_mode=None, verbose=False)
