"""Pure PUCT statistics and Self-Play policy/value target construction."""

from __future__ import annotations

import math
import random
from typing import Any


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
        targets.append({
            "step": step,
            "snapshot_path": capture.get("snapshot_path"),
            "player_to_move": player,
            "policy_target": policy_target,
            "policy_target_eligible": bool(policy_target),
            "return_to_go": player_returns[player],
            "return_to_go_player0": player_returns[0],
            "value_target_eligible": bool(value_target_eligible),
            "discount": 1.0,
        })
    return targets
