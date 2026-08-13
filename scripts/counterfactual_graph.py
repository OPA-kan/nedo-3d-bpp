"""Deterministic storage contract for bounded counterfactual trajectories.

This module deliberately contains no simulator integration.  It is the
stable boundary between an expensive physical branch executor and later
dataset/model code.  In particular, a graph may only contain depths three to
five, and every branch must name the future stream it was evaluated against.
"""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable


SCHEMA_VERSION = 2
MIN_HORIZON = 3
MAX_HORIZON = 5

CONTAINER_TENSOR_FEATURES = (
    "length", "width", "height", "cut_x", "cut_y", "thickness",
    "buffer", "has_shelf", "is_priority_dedicated",
)
ITEM_TENSOR_FEATURES = (
    "length", "width", "height", "mass", "is_prioritized", "is_soft",
    "lateralFriction", "rollingFriction", "spinningFriction",
    "restitution", "angularDamping", "contactStiffness",
    "contactDamping", "linearDamping",
)
PACKED_TENSOR_FEATURES = (
    "container_index", "local_x", "local_y", "local_z",
    "quaternion_x", "quaternion_y", "quaternion_z", "quaternion_w",
) + ITEM_TENSOR_FEATURES


def _item_tensor_row(item: dict[str, Any]) -> list[float]:
    return [
        float(bool(item.get(name)))
        if name in ("is_prioritized", "is_soft")
        else float(item.get(name, 0.0) or 0.0)
        for name in ITEM_TENSOR_FEATURES
    ]


def state_tensor_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Encode observed state as permutation-ready numeric set tensors.

    The representation preserves exact settled poses, physical item fields,
    container geometry and the visible pool. It deliberately excludes the
    step index and every future/outcome label so a learner cannot recover the
    trajectory clock or its target through leakage. Variable-length sets are
    padded only by the downstream batch loader; counts serve as masks.
    """
    observation = snapshot.get("observation", {})
    containers = sorted(
        observation.get("container_list", []),
        key=lambda row: int(row.get("index", -1)),
    )
    container_centres = {
        int(container.get("index", -1)): [
            float(value) for value in container.get("center", [0.0, 0.0, 0.0])
        ]
        for container in containers
    }
    item_records = {}
    for container in containers:
        container_index = int(container.get("index", -1))
        for item in container.get("packed_items", []):
            item_records[(container_index, int(item["index"]))] = item

    packed_rows = []
    packed_indices = []
    for physical in sorted(
        snapshot.get("physics", {}).get("packed_items", []),
        key=lambda row: (
            int(row.get("container_index", -1)),
            int(row.get("item_index", -1)),
        ),
    ):
        container_index = int(physical["container_index"])
        item_index = int(physical["item_index"])
        centre = container_centres.get(container_index, [0.0, 0.0, 0.0])
        position = [float(value) for value in physical["position"]]
        quaternion = [float(value) for value in physical["quaternion"]]
        item = item_records.get((container_index, item_index), {})
        packed_rows.append(
            [float(container_index)]
            + [position[index] - centre[index] for index in range(3)]
            + quaternion
            + _item_tensor_row(item)
        )
        packed_indices.append(item_index)

    pool = sorted(
        observation.get("pool_list", []),
        key=lambda row: int(row.get("index", -1)),
    )
    container_rows = [
        [
            float(container.get("length", 0.0) or 0.0),
            float(container.get("width", 0.0) or 0.0),
            float(container.get("height", 0.0) or 0.0),
            float(container.get("cut_x", 0.0) or 0.0),
            float(container.get("cut_y", 0.0) or 0.0),
            float(container.get("thickness", 0.0) or 0.0),
            float(container.get("buffer", 0.0) or 0.0),
            float(bool(container.get("shelf"))),
            float(bool(container.get("is_prioritized"))),
        ]
        for container in containers
    ]

    return {
        "schema_version": 1,
        "contract": "observed_set_tensors_no_step_no_future_labels",
        "coordinate_frame": "container_local",
        "container_features": list(CONTAINER_TENSOR_FEATURES),
        "container_values": container_rows,
        "container_count": len(container_rows),
        "packed_item_features": list(PACKED_TENSOR_FEATURES),
        "packed_item_values": packed_rows,
        "packed_item_indices": packed_indices,
        "packed_item_count": len(packed_rows),
        "visible_item_features": list(ITEM_TENSOR_FEATURES),
        "visible_item_values": [_item_tensor_row(item) for item in pool],
        "visible_item_indices": [int(item["index"]) for item in pool],
        "visible_item_count": len(pool),
    }


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_id(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:20]}"


def canonical_action(action: dict[str, Any]) -> dict[str, Any]:
    """Return the command fields needed to replay one official env step."""
    return {
        "item_idx": int(action["item_idx"]),
        "container_idx": int(action["container_idx"]),
        "place_pos": [float(value) for value in action["place_pos"]],
        "orientation": int(action["orientation"]),
    }


def capture_replay_contract(
    env,
    action_prefix: Iterable[dict[str, Any]],
    *,
    seed: int,
) -> dict[str, Any]:
    """Capture Python-side state that PyBullet ``saveState`` omits."""
    stream = env.stream_manager
    prefix = [canonical_action(action) for action in action_prefix]
    item_order = [int(item.index) for item in stream.all_items]
    visible_pool = [int(item.index) for item in stream.visible_pool]
    payload = {
        "seed": int(seed),
        "item_order": item_order,
        "stream_current_index": int(stream.current_index),
        "visible_pool_item_indices": visible_pool,
        "action_prefix": prefix,
    }
    payload["future_stream_id"] = stable_id(
        "stream",
        {"item_order": item_order, "seed": int(seed)},
    )
    payload["action_prefix_id"] = stable_id("prefix", prefix)
    return payload


def board_fingerprint(snapshot: dict[str, Any], *, digits: int = 6) -> str:
    """Fingerprint the observed board and pool, excluding run-local IDs."""
    packed = []
    for item in snapshot.get("physics", {}).get("packed_items", []):
        packed.append(
            {
                "container_index": int(item["container_index"]),
                "item_index": int(item["item_index"]),
                "position": [
                    round(float(value), digits)
                    for value in item.get("position", [])
                ],
                "quaternion": [
                    round(float(value), digits)
                    for value in item.get("quaternion", [])
                ],
            }
        )
    pool = [
        int(item["index"])
        for item in snapshot.get("observation", {}).get("pool_list", [])
    ]
    return stable_id(
        "board",
        {
            "packed": sorted(
                packed,
                key=lambda item: (
                    item["container_index"], item["item_index"]
                ),
            ),
            "pool": pool,
        },
    )


def board_difference(
    expected: dict[str, Any], observed: dict[str, Any]
) -> dict[str, Any]:
    """Describe why two board fingerprints differ without hiding the gap."""

    def packed_by_key(
        snapshot: dict[str, Any],
    ) -> dict[tuple[int, int], dict[str, Any]]:
        return {
            (int(item["container_index"]), int(item["item_index"])): item
            for item in snapshot.get("physics", {}).get("packed_items", [])
        }

    expected_items = packed_by_key(expected)
    observed_items = packed_by_key(observed)
    common = sorted(expected_items.keys() & observed_items.keys())
    position_differences = []
    quaternion_differences = []
    for key in common:
        expected_item = expected_items[key]
        observed_item = observed_items[key]
        position_differences.extend(
            abs(float(left) - float(right))
            for left, right in zip(
                expected_item.get("position", []),
                observed_item.get("position", []),
            )
        )
        expected_quaternion = [
            float(value) for value in expected_item.get("quaternion", [])
        ]
        observed_quaternion = [
            float(value) for value in observed_item.get("quaternion", [])
        ]
        if len(expected_quaternion) == len(observed_quaternion):
            direct = max(
                (
                    abs(left - right)
                    for left, right in zip(
                        expected_quaternion, observed_quaternion
                    )
                ),
                default=0.0,
            )
            negated = max(
                (
                    abs(left + right)
                    for left, right in zip(
                        expected_quaternion, observed_quaternion
                    )
                ),
                default=0.0,
            )
            quaternion_differences.append(min(direct, negated))

    def pool(snapshot: dict[str, Any]) -> list[int]:
        return [
            int(item["index"])
            for item in snapshot.get("observation", {}).get("pool_list", [])
        ]

    return {
        "expected_only_items": [
            list(key)
            for key in sorted(expected_items.keys() - observed_items.keys())
        ],
        "observed_only_items": [
            list(key)
            for key in sorted(observed_items.keys() - expected_items.keys())
        ],
        "expected_pool": pool(expected),
        "observed_pool": pool(observed),
        "max_position_abs_delta": max(position_differences, default=0.0),
        "max_quaternion_abs_delta_sign_invariant": max(
            quaternion_differences, default=0.0
        ),
    }


def boards_equivalent(
    expected: dict[str, Any],
    observed: dict[str, Any],
    *,
    position_tolerance_m: float = 1e-3,
    quaternion_tolerance: float = 2e-3,
) -> bool:
    """Require identical contents/pool and millimetre-bounded settle agreement.

    The simulator declares a preloaded scene asleep below 1 mm/s linear and
    angular velocity. Reconstructing that scene in a fresh PyBullet process
    can therefore stop at a nearby pose. Runs 31658418482/31718222625 and
    31658422923/31718245113 reproduced prefix-specific quaternion-component
    drift of 0.001409 and 0.001617 respectively. Identity and pool checks
    remain exact, position drift stays capped at 1 mm, and quaternion-component
    drift is capped at 0.002.
    """
    difference = board_difference(expected, observed)
    return bool(
        not difference["expected_only_items"]
        and not difference["observed_only_items"]
        and difference["expected_pool"] == difference["observed_pool"]
        and difference["max_position_abs_delta"] <= position_tolerance_m
        and difference["max_quaternion_abs_delta_sign_invariant"]
        <= quaternion_tolerance
    )


@dataclass(frozen=True)
class GraphBudget:
    horizon: int = 3
    branch_factor: int = 3
    max_nodes: int = 128
    max_edges: int = 256

    def __post_init__(self) -> None:
        if not MIN_HORIZON <= self.horizon <= MAX_HORIZON:
            raise ValueError("counterfactual horizon must be between 3 and 5")
        if self.branch_factor < 1:
            raise ValueError("branch_factor must be positive")
        if self.max_nodes < 1 or self.max_edges < 1:
            raise ValueError("graph budgets must be positive")


@dataclass
class GraphNode:
    node_id: str
    depth: int
    board_fingerprint: str
    state_ref: str | None
    pool_item_indices: list[int]
    future_stream_offset: int
    cumulative_outcomes: dict[str, float | int | bool | None]
    state_tensor: dict[str, Any] | None = None
    terminal_reason: str | None = None


@dataclass
class GraphEdge:
    edge_id: str
    source: str
    target: str
    candidate_id: str
    command_action: dict[str, Any]
    immediate_outcomes: dict[str, Any]
    selection: dict[str, Any]


@dataclass(frozen=True)
class PrefixReplayResult:
    matched: bool
    expected_fingerprint: str
    observed_fingerprint: str | None
    actions_replayed: int
    error: str | None
    observation: dict[str, Any] | None = field(
        default=None,
        compare=False,
        repr=False,
    )


def replay_action_prefix(
    env,
    contract: dict[str, Any],
    *,
    expected_fingerprint: str,
    snapshot_factory,
    expected_snapshot: dict[str, Any] | None = None,
) -> PrefixReplayResult:
    """Rebuild one root in an independent env and verify state identity.

    ``snapshot_factory`` receives ``(env, observation)``.  Keeping it
    injectable lets this module stay independent of the existing oracle and
    makes the restore boundary directly testable.
    """
    actions_replayed = 0
    try:
        env.reset_settings()
        if not env.set_item_order(list(contract["item_order"])):
            raise RuntimeError("recorded item order is invalid for this env")
        env.reset_item_stream()
        observation, _info = env.reset(seed=int(contract["seed"]))
        for action in contract["action_prefix"]:
            observation, _reward, terminated, truncated, _info = env.step(
                canonical_action(action)
            )
            actions_replayed += 1
            if (terminated or truncated) and actions_replayed < len(
                contract["action_prefix"]
            ):
                raise RuntimeError(
                    "episode ended before the recorded prefix was replayed"
                )
        observed_snapshot = snapshot_factory(env, observation)
        observed = board_fingerprint(observed_snapshot)
        matched = observed == expected_fingerprint or (
            expected_snapshot is not None
            and boards_equivalent(expected_snapshot, observed_snapshot)
        )
        error = None
        if not matched:
            error = "reconstruction_mismatch"
        return PrefixReplayResult(
            matched=matched,
            expected_fingerprint=expected_fingerprint,
            observed_fingerprint=observed,
            actions_replayed=actions_replayed,
            error=error,
            observation=observation,
        )
    except Exception as exc:
        return PrefixReplayResult(
            matched=False,
            expected_fingerprint=expected_fingerprint,
            observed_fingerprint=None,
            actions_replayed=actions_replayed,
            error=f"{type(exc).__name__}: {exc}",
            observation=None,
        )


@dataclass(frozen=True)
class BranchCandidate:
    candidate_id: str
    command_action: dict[str, Any]
    selection: dict[str, Any]


class BoundedGraphExecutor:
    """Expand a graph by replaying every path in an independent environment."""

    def __init__(
        self,
        *,
        env_factory: Callable[[], Any],
        snapshot_factory: Callable[[Any, dict[str, Any]], dict[str, Any]],
        candidate_provider: Callable[
            [Any, dict[str, Any], int], list[BranchCandidate]
        ],
        outcome_provider: Callable[
            [Any, dict[str, Any], dict[str, Any]],
            tuple[dict[str, Any], dict[str, Any]],
        ],
        state_tensor_factory: Callable[
            [dict[str, Any]], dict[str, Any] | None
        ] | None = None,
        forced_candidate_indices_by_path: dict[
            tuple[int, ...], list[int]
        ] | None = None,
    ) -> None:
        self.env_factory = env_factory
        self.snapshot_factory = snapshot_factory
        self.candidate_provider = candidate_provider
        self.outcome_provider = outcome_provider
        self.state_tensor_factory = state_tensor_factory
        self.forced_candidate_indices_by_path = {
            tuple(int(value) for value in path): [
                int(value) for value in indices
            ]
            for path, indices in (forced_candidate_indices_by_path or {}).items()
        }

    def _candidates_for_path(
        self, env, observation: dict[str, Any], path: tuple[int, ...], limit: int,
    ) -> list[BranchCandidate]:
        required = self.forced_candidate_indices_by_path.get(path, [])
        scan_limit = 1_000_000 if required else limit
        population = self.candidate_provider(env, observation, scan_limit)
        if not required:
            return population[:limit]
        by_item = {
            int(candidate.selection["stable_item_index"]): candidate
            for candidate in population
        }
        missing = [item for item in required if item not in by_item]
        if missing:
            raise RuntimeError(
                f"forced candidate item unavailable at path {path}: {missing}"
            )
        selected = [by_item[item] for item in required]
        selected.extend(
            candidate for candidate in population
            if int(candidate.selection["stable_item_index"]) not in required
        )
        return selected[:limit]

    def _reconstruct(
        self,
        contract: dict[str, Any],
        path: list[dict[str, Any]],
        expected_fingerprint: str,
        expected_snapshot: dict[str, Any] | None = None,
    ) -> tuple[Any, PrefixReplayResult]:
        env = self.env_factory()
        branch_contract = copy.deepcopy(contract)
        branch_contract["action_prefix"] = (
            list(contract["action_prefix"]) + list(path)
        )
        result = replay_action_prefix(
            env,
            branch_contract,
            expected_fingerprint=expected_fingerprint,
            snapshot_factory=self.snapshot_factory,
            expected_snapshot=expected_snapshot,
        )
        return env, result

    @staticmethod
    def _close(env) -> None:
        close = getattr(env, "close", None)
        if callable(close):
            close()

    def expand(
        self,
        graph: "CounterfactualGraph",
        root_contract: dict[str, Any],
        *,
        root_snapshot: dict[str, Any] | None = None,
    ) -> "CounterfactualGraph":
        """Breadth-first expansion with deterministic provider ordering."""
        paths: dict[str, list[dict[str, Any]]] = {graph.root_id: []}
        item_paths: dict[str, tuple[int, ...]] = {graph.root_id: ()}
        expected_snapshots: dict[str, dict[str, Any]] = {}
        if root_snapshot is not None:
            expected_snapshots[graph.root_id] = copy.deepcopy(root_snapshot)
        frontier = [graph.root_id]
        while frontier:
            parent_id = frontier.pop(0)
            parent = graph.nodes[parent_id]
            if parent.depth >= graph.budget.horizon or parent.terminal_reason:
                continue

            env, rebuilt = self._reconstruct(
                root_contract,
                paths[parent_id],
                parent.board_fingerprint,
                expected_snapshots.get(parent_id),
            )
            try:
                if not rebuilt.matched or rebuilt.observation is None:
                    raise RuntimeError(
                        rebuilt.error or "reconstruction_mismatch"
                    )
                candidates = self._candidates_for_path(
                    env, rebuilt.observation, item_paths[parent_id],
                    graph.budget.branch_factor,
                )
            finally:
                self._close(env)
            if not candidates:
                parent.terminal_reason = "no_candidate"
                continue

            for candidate in candidates:
                env, rebuilt = self._reconstruct(
                    root_contract,
                    paths[parent_id],
                    parent.board_fingerprint,
                    expected_snapshots.get(parent_id),
                )
                try:
                    if not rebuilt.matched or rebuilt.observation is None:
                        raise RuntimeError(
                            rebuilt.error or "reconstruction_mismatch"
                        )
                    (
                        observation,
                        _reward,
                        terminated,
                        truncated,
                        info,
                    ) = env.step(canonical_action(candidate.command_action))
                    snapshot = self.snapshot_factory(env, observation)
                    fingerprint = board_fingerprint(snapshot)
                    immediate, cumulative = self.outcome_provider(
                        env,
                        info,
                        parent.cumulative_outcomes,
                    )
                    status = (
                        info.get("status", {})
                        if isinstance(info, dict)
                        else {}
                    )
                    terminal_reason = None
                    if truncated:
                        terminal_reason = "protocol_truncated"
                    elif terminated and not bool(status.get("is_placed_safe")):
                        terminal_reason = "physical_failure"
                    elif terminated:
                        terminal_reason = "stream_exhausted"
                    pool_indices = [
                        int(item["index"])
                        for item in snapshot.get("observation", {}).get(
                            "pool_list", []
                        )
                    ]
                    child, _edge = graph.add_transition(
                        parent_id=parent_id,
                        candidate_id=candidate.candidate_id,
                        command_action=canonical_action(
                            candidate.command_action
                        ),
                        child_board_fingerprint=fingerprint,
                        child_state_ref=None,
                        child_pool_item_indices=pool_indices,
                        immediate_outcomes=immediate,
                        cumulative_outcomes=cumulative,
                        child_state_tensor=(
                            self.state_tensor_factory(snapshot)
                            if self.state_tensor_factory is not None
                            else None
                        ),
                        selection=candidate.selection,
                        terminal_reason=terminal_reason,
                    )
                    expected_snapshots.setdefault(
                        child.node_id, copy.deepcopy(snapshot)
                    )
                    if child.node_id not in paths:
                        paths[child.node_id] = paths[parent_id] + [
                            canonical_action(candidate.command_action)
                        ]
                        item_paths[child.node_id] = item_paths[parent_id] + (
                            int(candidate.selection["stable_item_index"]),
                        )
                    if (
                        terminal_reason is None
                        and child.depth < graph.budget.horizon
                        and child.node_id not in frontier
                    ):
                        frontier.append(child.node_id)
                finally:
                    self._close(env)
        graph.validate()
        return graph


@dataclass
class CounterfactualGraph:
    graph_id: str
    root_snapshot_id: str
    case_id: str
    root_step: int
    future_stream_id: str
    budget: GraphBudget
    provenance: dict[str, Any]
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    _state_index: dict[tuple[int, str], str] = field(
        default_factory=dict,
        repr=False,
    )

    @classmethod
    def create(
        cls,
        *,
        root_snapshot_id: str,
        case_id: str,
        root_step: int,
        future_stream_id: str,
        budget: GraphBudget,
        provenance: dict[str, Any],
        board_fingerprint: str,
        state_ref: str | None,
        pool_item_indices: Iterable[int],
        cumulative_outcomes: dict[str, Any] | None = None,
        state_tensor: dict[str, Any] | None = None,
    ) -> "CounterfactualGraph":
        identity = {
            "root_snapshot_id": root_snapshot_id,
            "case_id": case_id,
            "root_step": root_step,
            "future_stream_id": future_stream_id,
            "budget": asdict(budget),
            "provenance": provenance,
        }
        graph = cls(
            graph_id=stable_id("cfg", identity),
            root_snapshot_id=root_snapshot_id,
            case_id=case_id,
            root_step=int(root_step),
            future_stream_id=future_stream_id,
            budget=budget,
            provenance=dict(provenance),
        )
        graph._add_node(
            depth=0,
            board_fingerprint=board_fingerprint,
            state_ref=state_ref,
            pool_item_indices=pool_item_indices,
            future_stream_offset=0,
            cumulative_outcomes=cumulative_outcomes or {},
            state_tensor=state_tensor,
            terminal_reason=None,
        )
        return graph

    @property
    def root_id(self) -> str:
        return self._state_index[(0, next(
            node.board_fingerprint
            for node in self.nodes.values()
            if node.depth == 0
        ))]

    def _add_node(
        self,
        *,
        depth: int,
        board_fingerprint: str,
        state_ref: str | None,
        pool_item_indices: Iterable[int],
        future_stream_offset: int,
        cumulative_outcomes: dict[str, Any],
        state_tensor: dict[str, Any] | None = None,
        terminal_reason: str | None,
    ) -> GraphNode:
        key = (int(depth), str(board_fingerprint))
        existing = self._state_index.get(key)
        if existing is not None:
            return self.nodes[existing]
        if len(self.nodes) >= self.budget.max_nodes:
            raise RuntimeError("counterfactual graph node budget exhausted")
        node_id = stable_id(
            "state",
            {
                "graph_id": self.graph_id,
                "depth": depth,
                "board_fingerprint": board_fingerprint,
            },
        )
        node = GraphNode(
            node_id=node_id,
            depth=int(depth),
            board_fingerprint=str(board_fingerprint),
            state_ref=state_ref,
            pool_item_indices=[int(value) for value in pool_item_indices],
            future_stream_offset=int(future_stream_offset),
            cumulative_outcomes=dict(cumulative_outcomes),
            state_tensor=copy.deepcopy(state_tensor),
            terminal_reason=terminal_reason,
        )
        self.nodes[node_id] = node
        self._state_index[key] = node_id
        return node

    def add_transition(
        self,
        *,
        parent_id: str,
        candidate_id: str,
        command_action: dict[str, Any],
        child_board_fingerprint: str,
        child_state_ref: str | None,
        child_pool_item_indices: Iterable[int],
        immediate_outcomes: dict[str, Any],
        cumulative_outcomes: dict[str, Any],
        child_state_tensor: dict[str, Any] | None = None,
        selection: dict[str, Any],
        terminal_reason: str | None = None,
    ) -> tuple[GraphNode, GraphEdge]:
        if parent_id not in self.nodes:
            raise KeyError(f"unknown parent node: {parent_id}")
        parent = self.nodes[parent_id]
        depth = parent.depth + 1
        if depth > self.budget.horizon:
            raise ValueError("transition exceeds configured horizon")
        if len(self.edges) >= self.budget.max_edges:
            raise RuntimeError("counterfactual graph edge budget exhausted")
        sibling_count = sum(edge.source == parent_id for edge in self.edges)
        if sibling_count >= self.budget.branch_factor:
            raise RuntimeError("counterfactual branch-factor budget exhausted")
        child = self._add_node(
            depth=depth,
            board_fingerprint=child_board_fingerprint,
            state_ref=child_state_ref,
            pool_item_indices=child_pool_item_indices,
            future_stream_offset=parent.future_stream_offset + 1,
            cumulative_outcomes=cumulative_outcomes,
            state_tensor=child_state_tensor,
            terminal_reason=terminal_reason,
        )
        edge_id = stable_id(
            "action",
            {
                "graph_id": self.graph_id,
                "source": parent_id,
                "target": child.node_id,
                "candidate_id": candidate_id,
                "command_action": command_action,
            },
        )
        if any(edge.edge_id == edge_id for edge in self.edges):
            return child, next(
                edge for edge in self.edges if edge.edge_id == edge_id
            )
        edge = GraphEdge(
            edge_id=edge_id,
            source=parent_id,
            target=child.node_id,
            candidate_id=str(candidate_id),
            command_action=dict(command_action),
            immediate_outcomes=dict(immediate_outcomes),
            selection=dict(selection),
        )
        self.edges.append(edge)
        return child, edge

    def validate(self) -> None:
        roots = [node for node in self.nodes.values() if node.depth == 0]
        if len(roots) != 1:
            raise ValueError("graph must contain exactly one root")
        for edge in self.edges:
            if edge.source not in self.nodes or edge.target not in self.nodes:
                raise ValueError("edge references an unknown node")
            if self.nodes[edge.target].depth != self.nodes[edge.source].depth + 1:
                raise ValueError("edges must increase depth by exactly one")
        if any(node.depth > self.budget.horizon for node in self.nodes.values()):
            raise ValueError("node exceeds configured horizon")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema_version": SCHEMA_VERSION,
            "graph_id": self.graph_id,
            "root_snapshot_id": self.root_snapshot_id,
            "case_id": self.case_id,
            "root_step": self.root_step,
            "future_stream_id": self.future_stream_id,
            "budget": asdict(self.budget),
            "provenance": self.provenance,
            "nodes": [
                asdict(node)
                for node in sorted(
                    self.nodes.values(), key=lambda item: item.node_id
                )
            ],
            "edges": [
                asdict(edge) for edge in sorted(
                    self.edges, key=lambda item: item.edge_id
                )
            ],
        }


def write_graph(path: pathlib.Path, graph: CounterfactualGraph) -> None:
    """Atomically write one complete graph; partial graphs are not datasets."""
    payload = graph.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
