"""Deadline-aware, lockstep physical continuation of root candidates.

Each candidate owns a persistent simulator session.  The root action is
forced once, then all still-live candidates advance one frozen-policy action
per round.  A new round starts only when its conservative wall-clock estimate
fits the remaining decision budget.  This preserves a common comparison
horizon without replaying prefixes after every continuation step.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from scripts.build_counterfactual_graph import cumulative_metrics
from scripts.run_self_play_packing import (
    _candidate_action,
    _candidate_record,
    _safe,
    _status,
)
from scripts.run_single_agent_packing import _fresh_env
from scripts.run_vector_mcts import (
    GENUINE_TERMINATIONS,
    _component_values,
)


def can_start_round(
    *, now: float, deadline_at: float, last_round_seconds: float | None,
    initial_round_seconds: float, safety_factor: float,
    minimum_reserve_seconds: float,
) -> bool:
    """Return whether a complete lockstep round is predicted to fit."""
    if safety_factor < 1.0:
        raise ValueError("safety_factor must be at least one")
    estimate = (
        last_round_seconds
        if last_round_seconds is not None
        else initial_round_seconds
    )
    reserve = max(minimum_reserve_seconds, estimate * safety_factor)
    return now + reserve <= deadline_at


class CandidateRolloutSession:
    """Persistent physical state for one root candidate continuation."""

    def __init__(
        self, task_config: dict[str, Any], *, environment_seed: int,
        prefix_actions: list[Any], forced_action: Any, provider, legal_filter,
        top_k: int, root_step: int, clock: Callable[[], float],
    ) -> None:
        self.clock = clock
        self.provider = provider
        self.legal_filter = legal_filter
        self.top_k = int(top_k)
        self.root_step = int(root_step)
        self.prefix_actions = list(prefix_actions)
        self.forced_action = forced_action
        self.executed = list(prefix_actions)
        self.continuation_actions: list[Any] = []
        self.continuation_steps = 0
        self.legal_filter_physical_step_equivalents = 0
        self.legal_filter_symmetry_reused = 0
        self.termination: str | None = None
        self.timing = {
            "setup_seconds": 0.0,
            "prefix_replay_seconds": 0.0,
            "forced_action_seconds": 0.0,
            "continuation_provider_seconds": 0.0,
            "continuation_legal_filter_seconds": 0.0,
            "continuation_action_seconds": 0.0,
        }
        started = clock()
        self.env = _fresh_env(task_config)
        self.env.reset_settings()
        self.env.reset_item_stream()
        self.observation, _info = self.env.reset(seed=environment_seed)
        self.timing["setup_seconds"] = clock() - started

        started = clock()
        for index, action in enumerate(prefix_actions):
            self.observation, _reward, terminated, truncated, info = (
                self.env.step(action)
            )
            if not _safe(_status(info)) or terminated or truncated:
                self.close()
                raise RuntimeError(
                    f"deadline-rollout prefix failed at action {index}"
                )
        self.timing["prefix_replay_seconds"] = clock() - started
        self.root_metrics = cumulative_metrics(self.env)

        started = clock()
        self.observation, _reward, terminated, truncated, info = self.env.step(
            forced_action
        )
        self.timing["forced_action_seconds"] = clock() - started
        self.executed.append(forced_action)
        if not _safe(_status(info)):
            self.termination = "forced_action_failure"
        elif truncated:
            self.termination = "simulator_truncated"
        elif terminated:
            self.termination = "stream_exhausted"

    @property
    def active(self) -> bool:
        return self.termination is None

    def advance_one(self) -> None:
        if not self.active:
            return
        started = self.clock()
        proposals = list(
            self.provider(self.env, self.observation, self.top_k)
        )
        self.timing["continuation_provider_seconds"] += self.clock() - started
        if not proposals:
            self.termination = "no_retained_candidate"
            return

        started = self.clock()
        retained, audit = self.legal_filter(
            env=self.env,
            observation=self.observation,
            candidates=proposals,
            actions=list(self.executed),
            step=self.root_step + 1 + self.continuation_steps,
            max_safe_candidates=1,
        )
        self.timing["continuation_legal_filter_seconds"] += (
            self.clock() - started
        )
        self.legal_filter_physical_step_equivalents += int(
            audit.get("physical_step_equivalents", 0)
        )
        self.legal_filter_symmetry_reused += int(
            audit.get("symmetry_reused_count", 0)
        )
        if not retained:
            self.termination = "no_safe_retained_candidate"
            return

        action = _candidate_action(retained[0])
        started = self.clock()
        self.observation, _reward, terminated, truncated, info = self.env.step(
            action
        )
        self.timing["continuation_action_seconds"] += self.clock() - started
        self.executed.append(action)
        self.continuation_actions.append(action)
        if not _safe(_status(info)):
            self.termination = "selected_action_failure"
            return
        self.continuation_steps += 1
        if truncated:
            self.termination = "simulator_truncated"
        elif terminated:
            self.termination = "stream_exhausted"

    def result(self) -> dict[str, Any]:
        metrics = cumulative_metrics(self.env)
        return {
            "termination": self.termination or "deadline_or_depth_cap",
            "safe": self.termination != "forced_action_failure",
            "genuine_terminal": self.termination in GENUINE_TERMINATIONS,
            "continuation_steps": self.continuation_steps,
            "checkpoint_vector": _component_values(self.root_metrics, metrics),
            "physical_step_equivalents": (
                len(self.prefix_actions)
                + 1
                + self.continuation_steps
                + self.legal_filter_physical_step_equivalents
            ),
            "legal_filter_symmetry_reused": (
                self.legal_filter_symmetry_reused
            ),
            "continuation_actions": list(self.continuation_actions),
            "timing": dict(self.timing),
        }

    def close(self) -> None:
        env = getattr(self, "env", None)
        if env is not None:
            env.close()
            self.env = None


def deadline_checkpoint_search(
    task_config: dict[str, Any], *, environment_seed: int,
    prefix_actions: list[Any], candidates: list[Any], provider, legal_filter,
    top_k: int, root_step: int, deadline_at: float,
    max_continuation_steps: int = 2, safety_factor: float = 1.35,
    minimum_reserve_seconds: float = 0.25,
    clock: Callable[[], float] = time.perf_counter,
    session_factory: Callable[..., CandidateRolloutSession] = (
        CandidateRolloutSession
    ),
) -> dict[str, Any]:
    """Advance candidates in equal-depth rounds until depth or budget stops."""
    if not candidates:
        raise ValueError("deadline rollout needs at least one candidate")
    if max_continuation_steps < 0:
        raise ValueError("max_continuation_steps must be non-negative")
    started = clock()
    sessions: list[tuple[str, CandidateRolloutSession]] = []
    try:
        for candidate in candidates:
            candidate_id = str(_candidate_record(candidate)["candidate_id"])
            session = session_factory(
                task_config,
                environment_seed=environment_seed,
                prefix_actions=prefix_actions,
                forced_action=_candidate_action(candidate),
                provider=provider,
                legal_filter=legal_filter,
                top_k=top_k,
                root_step=root_step,
                clock=clock,
            )
            sessions.append((candidate_id, session))
        initial_round_seconds = clock() - started
        round_seconds: list[float] = []
        stop_reason = "depth_cap"
        rounds_completed = 0
        for _round in range(max_continuation_steps):
            active = [session for _candidate_id, session in sessions if session.active]
            if not active:
                stop_reason = "all_genuine_or_failed"
                break
            now = clock()
            if not can_start_round(
                now=now,
                deadline_at=deadline_at,
                last_round_seconds=(round_seconds[-1] if round_seconds else None),
                initial_round_seconds=initial_round_seconds,
                safety_factor=safety_factor,
                minimum_reserve_seconds=minimum_reserve_seconds,
            ):
                stop_reason = "predicted_deadline"
                break
            round_started = clock()
            for session in active:
                session.advance_one()
            round_seconds.append(clock() - round_started)
            rounds_completed += 1
            if clock() >= deadline_at:
                stop_reason = "deadline_overrun_after_round"
                break
        rows = []
        for candidate_id, session in sessions:
            rows.append({"root_candidate_id": candidate_id, **session.result()})
        finished = clock()
        return {
            "contract": "deadline_lockstep_physical_rollout_v1",
            "candidate_count": len(rows),
            "max_continuation_steps": max_continuation_steps,
            "rounds_completed": rounds_completed,
            "common_total_depth": 1 + rounds_completed,
            "stop_reason": stop_reason,
            "deadline_seconds": deadline_at - started,
            "search_seconds": finished - started,
            "deadline_met": finished <= deadline_at,
            "initial_round_seconds": initial_round_seconds,
            "continuation_round_seconds": round_seconds,
            "candidates": rows,
        }
    finally:
        for _candidate_id, session in sessions:
            session.close()
