"""Deterministic storage contract for bounded counterfactual trajectories.

This module deliberately contains no simulator integration.  It is the
stable boundary between an expensive physical branch executor and later
dataset/model code.  In particular, a graph may only contain depths three to
five, and every branch must name the future stream it was evaluated against.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


SCHEMA_VERSION = 1
MIN_HORIZON = 3
MAX_HORIZON = 5


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
        observed = board_fingerprint(snapshot_factory(env, observation))
        error = None
        if observed != expected_fingerprint:
            error = "reconstruction_mismatch"
        return PrefixReplayResult(
            matched=observed == expected_fingerprint,
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
