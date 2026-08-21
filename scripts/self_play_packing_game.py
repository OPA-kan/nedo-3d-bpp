"""Pure rules for the two-player shared-board packing game.

This module owns turn scheduling and zero-sum rewards.  It deliberately knows
nothing about PyBullet or candidate generation so the game rules can be tested
without weakening the production simulator contract.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


ATTRIBUTE_VIOLATION_KEYS = (
    "soft_covered_by_other",
    "priority_covered_by_other",
    "priority_misrouted",
)


@dataclass(frozen=True)
class GameRules:
    minimum_block: int = 3
    handoff_probability: float = 0.6
    terminal_reward: float = 50.0
    attribute_penalty: float = 5.0

    def __post_init__(self) -> None:
        if self.minimum_block < 1:
            raise ValueError("minimum_block must be positive")
        if not 0.0 <= self.handoff_probability <= 1.0:
            raise ValueError("handoff_probability must be in [0, 1]")
        if self.terminal_reward < 0.0 or self.attribute_penalty < 0.0:
            raise ValueError("reward magnitudes must be non-negative")


@dataclass
class GameState:
    current_player: int = 0
    block_length: int = 0
    placements: int = 0
    handoff_count: int = 0

    def __post_init__(self) -> None:
        if self.current_player not in (0, 1):
            raise ValueError("current_player must be 0 or 1")


def _selection(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return candidate.get("selection", {})
    return getattr(candidate, "selection", {})


def choose_candidate(
    candidates: list[Any], *, mode: str, temperature: float, rng,
) -> Any:
    """Apply one shared policy distribution, independent of player identity."""
    if not candidates:
        raise ValueError("cannot choose from an empty candidate set")
    ordered = sorted(
        candidates,
        key=lambda row: (
            int(_selection(row).get("rank", 10**9)),
            str(getattr(row, "candidate_id", "")),
        ),
    )
    if mode == "rank0":
        return ordered[0]
    if mode != "temperature":
        raise ValueError(f"unknown selection mode: {mode}")
    if temperature <= 0.0:
        raise ValueError("temperature must be positive")
    weights = [
        math.exp(-int(_selection(row).get("rank", index)) / temperature)
        for index, row in enumerate(ordered)
    ]
    return rng.choices(ordered, weights=weights, k=1)[0]


def advance_after_placement(state: GameState, rules: GameRules, rng) -> dict[str, Any]:
    """Record one successful placement and draw a handoff when eligible."""
    mover = state.current_player
    state.placements += 1
    state.block_length += 1
    eligible = state.block_length >= rules.minimum_block
    handoff = bool(eligible and rng.random() < rules.handoff_probability)
    completed = None
    if handoff:
        completed = state.block_length
        state.current_player = 1 - state.current_player
        state.block_length = 0
        state.handoff_count += 1
    return {
        "mover": mover,
        "handoff_eligible": eligible,
        "handoff": handoff,
        "completed_block_length": completed,
        "next_player": state.current_player,
        "next_block_length": state.block_length,
    }


def apply_attribute_reward(
    rewards: list[float], *, mover: int, before: dict[str, Any],
    after: dict[str, Any], rules: GameRules,
) -> dict[str, Any]:
    """Charge only newly created soft/priority violations, never old debt."""
    deltas = {}
    for key in ATTRIBUTE_VIOLATION_KEYS:
        previous = float(before.get(key, 0.0) or 0.0)
        current = float(after.get(key, 0.0) or 0.0)
        deltas[key] = max(0.0, current - previous)
    new_violations = sum(deltas.values())
    charge = float(rules.attribute_penalty) * new_violations
    reward_delta = [0.0, 0.0]
    reward_delta[mover] -= charge
    reward_delta[1 - mover] += charge
    rewards[0] += reward_delta[0]
    rewards[1] += reward_delta[1]
    return {
        "violation_deltas": deltas,
        "new_violations": new_violations,
        "reward_delta": reward_delta,
    }


def apply_terminal_loss(
    rewards: list[float], *, loser: int, rules: GameRules,
) -> dict[str, Any]:
    winner = 1 - loser
    reward_delta = [0.0, 0.0]
    reward_delta[loser] -= float(rules.terminal_reward)
    reward_delta[winner] += float(rules.terminal_reward)
    rewards[0] += reward_delta[0]
    rewards[1] += reward_delta[1]
    return {"loser": loser, "winner": winner, "reward_delta": reward_delta}
