"""Pure PUCT statistics and Self-Play policy/value target construction."""

from __future__ import annotations

import math
import random
from typing import Any


MULTI_HEAD_SPECS = {
    "game_reward": "maximize",
    "fill_gain": "maximize",
    "placed_gain": "diagnostic",
    "survival_to_rollout_end": "maximize",
    "soft_violation_gain": "minimize",
    "priority_covered_gain": "minimize",
    "priority_misrouted_gain": "minimize",
    "center_of_mass_z_delta": "diagnostic",
    "surface_total_variation_delta": "minimize_proxy",
    "stability_max_shift": "minimize",
    "stability_peak_kinetic_energy": "minimize",
    "stability_items_toppled": "minimize",
}

TRAJECTORY_VALUE_HEAD_SPECS = {
    "game_return": "maximize",
    "fill_return": "maximize",
    "placed_return": "diagnostic",
    "stream_completed": "maximize",
    "soft_violation_return": "minimize",
    "priority_covered_return": "minimize",
    "priority_misrouted_return": "minimize",
    "center_of_mass_z_return": "diagnostic",
    "surface_total_variation_return": "minimize_proxy",
    "terminal_stability_max_shift": "minimize",
    "terminal_stability_peak_kinetic_energy": "minimize",
    "terminal_stability_items_toppled": "minimize",
}


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _delta(
    before: dict[str, Any], after: dict[str, Any], *keys: str,
) -> float | None:
    for key in keys:
        left = _numeric(before.get(key))
        right = _numeric(after.get(key))
        if left is not None and right is not None:
            return right - left
    return None


def build_multi_head_branch_sample(
    *, root_metrics: dict[str, Any], leaf_metrics: dict[str, Any],
    rewards: list[float], root_player: int, termination: str,
) -> dict[str, dict[str, Any]]:
    """Build separately masked outcomes for one bounded physical rollout.

    A completed horizon is a valid H-step target, not a claim about the full
    episode return. Candidate exhaustion and simulator truncation leave the
    continuation unknown, so even observed partial deltas are retained only as
    diagnostics and are excluded from supervised loss.
    """
    if len(rewards) != 2 or root_player not in (0, 1):
        raise ValueError("branch rewards need both players and a valid root player")
    complete = termination in {"horizon", "stream_exhausted"}
    values = {
        "game_reward": _numeric(rewards[root_player]),
        "fill_gain": _delta(
            root_metrics, leaf_metrics, "fill_score_proxy", "fill_percent_proxy"
        ),
        "placed_gain": _delta(root_metrics, leaf_metrics, "placed_count"),
        "survival_to_rollout_end": 1.0 if complete else None,
        "soft_violation_gain": _delta(
            root_metrics, leaf_metrics, "soft_covered_by_other"
        ),
        "priority_covered_gain": _delta(
            root_metrics, leaf_metrics, "priority_covered_by_other"
        ),
        "priority_misrouted_gain": _delta(
            root_metrics, leaf_metrics, "priority_misrouted"
        ),
        "center_of_mass_z_delta": _delta(
            root_metrics, leaf_metrics, "center_of_mass_z", "com_z"
        ),
        "surface_total_variation_delta": _delta(
            root_metrics, leaf_metrics, "surface_total_variation"
        ),
        "stability_max_shift": _numeric(
            leaf_metrics.get("post_shake_max_shift")
        ),
        "stability_peak_kinetic_energy": _numeric(
            leaf_metrics.get("post_shake_peak_kinetic_energy")
        ),
        "stability_items_toppled": _numeric(
            leaf_metrics.get("post_shake_items_toppled")
        ),
    }
    result = {}
    for name, objective in MULTI_HEAD_SPECS.items():
        value = values[name]
        eligible = bool(complete and value is not None)
        result[name] = {
            "value": value,
            "target_eligible": eligible,
            "censor_reason": (
                None if eligible else termination if not complete else "unmeasured"
            ),
            "objective": objective,
        }
    return result


def summarize_multi_head_branch_samples(
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate only eligible values while preserving censor counts."""
    heads = {}
    for name, objective in MULTI_HEAD_SPECS.items():
        targets = [sample["heads"][name] for sample in samples]
        values = [
            float(target["value"])
            for target in targets
            if target.get("target_eligible") and target.get("value") is not None
        ]
        heads[name] = {
            "objective": objective,
            "eligible_count": len(values),
            "censored_count": len(targets) - len(values),
            "mean": sum(values) / len(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
        }
    complete = sum(
        sample.get("termination") in {"horizon", "stream_exhausted"}
        for sample in samples
    )
    return {
        "schema_version": 1,
        "contract": "bounded_physical_rollout_multi_head_no_weighted_sum",
        "samples": len(samples),
        "complete_samples": complete,
        "censored_samples": len(samples) - complete,
        "heads": heads,
    }


def build_trajectory_value_heads(
    *, metrics_before: dict[str, Any], final_metrics: dict[str, Any],
    player_return: float, terminal_reason: str | None,
    target_eligible: bool,
) -> dict[str, dict[str, Any]]:
    """Build state-to-episode-end targets for a value model."""
    stream_completed = (
        1.0 if terminal_reason == "stream_exhausted"
        else 0.0 if terminal_reason in {
            "no_retained_candidate", "no_safe_retained_candidate"
        }
        else None
    )
    values = {
        "game_return": _numeric(player_return),
        "fill_return": _delta(
            metrics_before, final_metrics,
            "fill_score_proxy", "fill_percent_proxy",
        ),
        "placed_return": _delta(
            metrics_before, final_metrics, "placed_count"
        ),
        "stream_completed": stream_completed,
        "soft_violation_return": _delta(
            metrics_before, final_metrics, "soft_covered_by_other"
        ),
        "priority_covered_return": _delta(
            metrics_before, final_metrics, "priority_covered_by_other"
        ),
        "priority_misrouted_return": _delta(
            metrics_before, final_metrics, "priority_misrouted"
        ),
        "center_of_mass_z_return": _delta(
            metrics_before, final_metrics, "center_of_mass_z", "com_z"
        ),
        "surface_total_variation_return": _delta(
            metrics_before, final_metrics, "surface_total_variation"
        ),
        "terminal_stability_max_shift": _numeric(
            final_metrics.get("post_shake_max_shift")
        ),
        "terminal_stability_peak_kinetic_energy": _numeric(
            final_metrics.get("post_shake_peak_kinetic_energy")
        ),
        "terminal_stability_items_toppled": _numeric(
            final_metrics.get("post_shake_items_toppled")
        ),
    }
    heads = {}
    for name, objective in TRAJECTORY_VALUE_HEAD_SPECS.items():
        value = values[name]
        eligible = bool(target_eligible and value is not None)
        heads[name] = {
            "value": value,
            "target_eligible": eligible,
            "censor_reason": (
                None if eligible
                else "episode_ineligible" if not target_eligible
                else "unmeasured"
            ),
            "objective": objective,
        }
    return heads


def candidate_id(candidate: Any) -> str:
    value = (
        candidate.get("candidate_id")
        if isinstance(candidate, dict)
        else getattr(candidate, "candidate_id", None)
    )
    if value is None:
        raise ValueError("every search candidate needs a stable candidate_id")
    return str(value)


def candidate_rank(candidate: Any) -> int:
    selection = (
        candidate.get("selection", {})
        if isinstance(candidate, dict)
        else getattr(candidate, "selection", {})
    )
    return int(selection.get("rank", 10**9))


class PuctTree:
    """PUCT edge statistics with values stored in node-player perspective."""

    def __init__(
        self, *, cpuct: float = 2.0, prior_mode: str = "uniform",
        prior_temperature: float = 1.0,
    ) -> None:
        if cpuct < 0.0:
            raise ValueError("cpuct must be non-negative")
        if prior_mode not in ("uniform", "rank"):
            raise ValueError(f"unsupported prior mode: {prior_mode}")
        if prior_temperature <= 0.0:
            raise ValueError("prior_temperature must be positive")
        self.cpuct = float(cpuct)
        self.prior_mode = prior_mode
        self.prior_temperature = float(prior_temperature)
        self._nodes: dict[str, dict[str, dict[str, Any]]] = {}

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def _register(self, node_key: str, candidates: list[Any]) -> None:
        ordered = sorted(
            candidates,
            key=lambda row: (candidate_rank(row), candidate_id(row)),
        )
        identifiers = [candidate_id(row) for row in ordered]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f"duplicate candidate_id at node {node_key}")
        if node_key in self._nodes:
            known = list(self._nodes[node_key])
            if known != identifiers:
                raise RuntimeError(
                    f"candidate set changed inside one search at {node_key}: "
                    f"{known} != {identifiers}"
                )
            return
        weights = [
            1.0 if self.prior_mode == "uniform"
            else math.exp(-candidate_rank(row) / self.prior_temperature)
            for row in ordered
        ]
        total = sum(weights)
        self._nodes[node_key] = {
            candidate_id(row): {
                "candidate": row,
                "rank": candidate_rank(row),
                "base_prior": weight / total,
                "prior": weight / total,
                "visits": 0,
                "value_sum": 0.0,
            }
            for row, weight in zip(ordered, weights)
        }

    def add_dirichlet_noise(
        self, node_key: str, candidates: list[Any], *, alpha: float,
        epsilon: float, rng: random.Random,
    ) -> list[float]:
        """Mix seeded Dirichlet exploration into one already bounded root."""
        if alpha <= 0.0:
            raise ValueError("Dirichlet alpha must be positive")
        if not 0.0 <= epsilon <= 1.0:
            raise ValueError("Dirichlet epsilon must be in [0, 1]")
        self._register(node_key, candidates)
        edges = self._nodes[node_key]
        samples = [rng.gammavariate(alpha, 1.0) for _ in edges]
        total = sum(samples)
        if total <= 0.0:
            raise RuntimeError("Dirichlet sampler produced zero total mass")
        noise = [sample / total for sample in samples]
        for row, eta in zip(edges.values(), noise):
            row["prior"] = (
                (1.0 - epsilon) * float(row["base_prior"])
                + epsilon * eta
            )
        return noise

    def select(self, node_key: str, *, player: int, candidates: list[Any]) -> Any:
        if player not in (0, 1):
            raise ValueError("player must be 0 or 1")
        if not candidates:
            raise ValueError("cannot select from an empty candidate set")
        self._register(node_key, candidates)
        edges = self._nodes[node_key]
        total_visits = sum(int(row["visits"]) for row in edges.values())
        ordered = sorted(
            edges.values(),
            key=lambda row: (row["rank"], candidate_id(row["candidate"])),
        )

        def score(row: dict[str, Any]) -> float:
            visits = int(row["visits"])
            q_value = float(row["value_sum"]) / visits if visits else 0.0
            exploration = (
                self.cpuct * float(row["prior"])
                * math.sqrt(total_visits + 1.0) / (1.0 + visits)
            )
            return q_value + exploration

        return max(ordered, key=score)["candidate"]

    def backup(
        self, path: list[tuple[str, str, int]], returns: list[float], *,
        candidates: list[Any] | None = None,
    ) -> None:
        if len(returns) != 2:
            raise ValueError("returns must contain both players")
        if candidates is not None and path:
            self._register(path[0][0], candidates)
        for node_key, identifier, player in path:
            if node_key not in self._nodes or identifier not in self._nodes[node_key]:
                raise KeyError(f"unknown search edge {node_key}/{identifier}")
            row = self._nodes[node_key][identifier]
            row["visits"] += 1
            row["value_sum"] += float(returns[player])

    def policy(self, node_key: str) -> list[dict[str, Any]]:
        edges = self._nodes.get(node_key, {})
        total = sum(int(row["visits"]) for row in edges.values())
        result = []
        for identifier, row in edges.items():
            visits = int(row["visits"])
            result.append({
                "candidate_id": identifier,
                "rank": int(row["rank"]),
                "base_prior": float(row["base_prior"]),
                "prior": float(row["prior"]),
                "visits": visits,
                "probability": visits / total if total else 0.0,
                "q": float(row["value_sum"]) / visits if visits else None,
            })
        return result

    def choose(self, node_key: str, candidates: list[Any], *, temperature: float, rng) -> Any:
        if temperature < 0.0:
            raise ValueError("temperature must be non-negative")
        self._register(node_key, candidates)
        policy = self.policy(node_key)
        by_id = {candidate_id(row): row for row in candidates}
        if temperature == 0.0:
            best = max(
                policy,
                key=lambda row: (
                    row["visits"],
                    row["q"] if row["q"] is not None else float("-inf"),
                    -row["rank"],
                ),
            )
            return by_id[best["candidate_id"]]
        weights = [float(row["visits"]) ** (1.0 / temperature) for row in policy]
        if not any(weights):
            weights = [float(row["prior"]) for row in policy]
        selected = rng.choices(policy, weights=weights, k=1)[0]
        return by_id[selected["candidate_id"]]


def build_return_targets(
    captures: list[dict[str, Any]], records: list[dict[str, Any]], *,
    final_rewards: list[float], value_target_eligible: bool,
    final_metrics: dict[str, Any] | None = None,
    terminal_reason: str | None = None,
) -> list[dict[str, Any]]:
    """Attach undiscounted suffix return G_t and search policy to each state."""
    if len(final_rewards) != 2:
        raise ValueError("final_rewards must contain both players")
    by_step = {int(row["step"]): row for row in records}
    targets = []
    for capture in sorted(captures, key=lambda row: int(row["step"])):
        step = int(capture["step"])
        player = int(capture["player_to_move"])
        rewards_before = [float(value) for value in capture["rewards_before"]]
        record = by_step.get(step)
        policy_target = []
        if record is not None:
            search = record.get("search", {})
            if search.get("policy_target") is not None:
                policy_target = list(search["policy_target"])
            elif record.get("selected_candidate_id") is not None:
                policy_target = [{
                    "candidate_id": record["selected_candidate_id"],
                    "probability": 1.0,
                    "visits": None,
                }]
        player_returns = [
            float(final_rewards[index]) - rewards_before[index]
            for index in range(2)
        ]
        if not math.isclose(sum(player_returns), 0.0, abs_tol=1e-9):
            raise ValueError(
                "Self-Play returns must remain zero-sum: "
                f"{player_returns}"
            )
        target = {
            "step": step,
            "snapshot_path": capture.get("snapshot_path"),
            "player_to_move": player,
            "policy_target": policy_target,
            "policy_target_eligible": bool(policy_target),
            "return_to_go": player_returns[player],
            "return_to_go_player0": player_returns[0],
            "value_target_eligible": bool(value_target_eligible),
            "discount": 1.0,
        }
        target["value_heads"] = build_trajectory_value_heads(
            metrics_before=dict(
                capture.get("cumulative_metrics_before") or {}
            ),
            final_metrics=dict(final_metrics or {}),
            player_return=player_returns[player],
            terminal_reason=terminal_reason,
            target_eligible=value_target_eligible,
        )
        targets.append(target)
    return targets
