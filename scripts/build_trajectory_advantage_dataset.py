"""Build direct, multi-head trajectory advantages from physical H3/H5 DAGs.

The target is G_H(s, a) - G_H(s, a0), where a0 is the retained rank-zero
behaviour-policy action at the same source node.  G includes the first action
and every searched suffix outcome.  The hand-written immediate score is used
only upstream to identify the already-recorded incumbent; it is never exported
as a model input or target.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import pathlib
from typing import Any

try:
    from scripts.summarize_counterfactual_graph_signal import (
        METRIC_DIRECTIONS,
        POST_SHAKE_METRIC_DIRECTIONS,
        _action_tensor,
    )
except ModuleNotFoundError:  # direct `python scripts/...py` execution
    from summarize_counterfactual_graph_signal import (
        METRIC_DIRECTIONS,
        POST_SHAKE_METRIC_DIRECTIONS,
        _action_tensor,
    )


DERIVED_HEAD_DIRECTIONS = {
    "survival_steps": 1,
    "horizon_survival_rate": 1,
    "physical_failure_rate": -1,
    "terminal_failure_rate": -1,
}
FAILURE_REASONS = {
    "physical_failure", "no_candidate", "protocol_truncated",
}


def _graph_index(graph: dict[str, Any]) -> tuple[
    dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]
]:
    nodes = {node["node_id"]: node for node in graph.get("nodes", [])}
    outgoing: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for edge in graph.get("edges", []):
        if edge.get("source") not in nodes or edge.get("target") not in nodes:
            raise ValueError("graph edge references a missing node")
        outgoing[edge["source"]].append(edge)
    return nodes, outgoing


def _leaf_paths(
    start: str,
    nodes: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
) -> list[tuple[list[dict[str, Any]], dict[str, Any], float]]:
    paths = []
    stack = [(start, [], 1.0)]
    while stack:
        node_id, edges, weight = stack.pop()
        children = outgoing.get(node_id, [])
        if not children:
            paths.append((edges, nodes[node_id], weight))
            continue
        child_weight = weight / len(children)
        for edge in children:
            stack.append((edges + [edge], nodes[edge["target"]], child_weight))
    return paths


def _metric_directions(graph: dict[str, Any]) -> dict[str, int]:
    directions = dict(METRIC_DIRECTIONS)
    if graph.get("provenance", {}).get("post_shake_labels"):
        directions.update(POST_SHAKE_METRIC_DIRECTIONS)
    directions.update(DERIVED_HEAD_DIRECTIONS)
    return directions


def _trajectory_samples(
    *,
    source: dict[str, Any],
    first_edge: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    outgoing: dict[str, list[dict[str, Any]]],
    horizon: int,
    metric_directions: dict[str, int],
) -> list[dict[str, Any]]:
    source_outcomes = source.get("cumulative_outcomes", {})
    samples = []
    for suffix_edges, leaf, weight in _leaf_paths(
        first_edge["target"], nodes, outgoing
    ):
        leaf_outcomes = leaf.get("cumulative_outcomes", {})
        outcomes = {
            metric: float(leaf_outcomes[metric]) - float(source_outcomes[metric])
            for metric in metric_directions
            if metric not in DERIVED_HEAD_DIRECTIONS
            and metric in leaf_outcomes
            and metric in source_outcomes
        }
        terminal_reason = leaf.get("terminal_reason")
        survival_steps = int(leaf.get("depth", 0)) - int(source["depth"])
        outcomes.update({
            "survival_steps": float(survival_steps),
            "horizon_survival_rate": float(
                int(leaf.get("depth", 0)) >= horizon
                and terminal_reason not in FAILURE_REASONS
            ),
            "physical_failure_rate": float(
                terminal_reason == "physical_failure"
            ),
            "terminal_failure_rate": float(
                terminal_reason in FAILURE_REASONS
            ),
        })
        samples.append({
            "leaf_node_id": leaf["node_id"],
            "terminal_reason": terminal_reason or (
                "horizon" if int(leaf.get("depth", 0)) >= horizon
                else "open_leaf"
            ),
            "path_stable_item_indices": [
                first_edge.get("selection", {}).get("stable_item_index"),
                *[
                    edge.get("selection", {}).get("stable_item_index")
                    for edge in suffix_edges
                ],
            ],
            "search_policy_weight": float(weight),
            "outcomes": outcomes,
        })
    return samples


def _weighted_quantile(
    values: list[float], weights: list[float], probability: float,
) -> float:
    ordered = sorted(zip(values, weights), key=lambda item: item[0])
    total = sum(weights)
    if not ordered or total <= 0.0:
        raise ValueError("weighted quantile requires positive sample weight")
    threshold = probability * total
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative + 1e-15 >= threshold:
            return float(value)
    return float(ordered[-1][0])


def _head_summary(
    metric: str,
    direction: int,
    incumbent_samples: list[dict[str, Any]],
    candidate_samples: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not all(
        metric in sample["outcomes"]
        for sample in incumbent_samples + candidate_samples
    ):
        return None

    def statistics(samples: list[dict[str, Any]]) -> dict[str, float]:
        weights = [float(sample["search_policy_weight"]) for sample in samples]
        total = sum(weights)
        normalized = [weight / total for weight in weights]
        values = [float(sample["outcomes"][metric]) for sample in samples]
        pessimistic_probability = 0.25 if direction > 0 else 0.75
        return {
            "mean": sum(value * weight for value, weight in zip(values, normalized)),
            "pessimistic_quantile": _weighted_quantile(
                values, normalized, pessimistic_probability
            ),
        }

    incumbent = statistics(incumbent_samples)
    candidate = statistics(candidate_samples)
    raw_advantage = candidate["mean"] - incumbent["mean"]
    directed_advantage = direction * raw_advantage
    if math.isclose(directed_advantage, 0.0, rel_tol=0.0, abs_tol=1e-12):
        relation = "equal"
    elif directed_advantage > 0.0:
        relation = "candidate_better"
    else:
        relation = "incumbent_better"
    return {
        "direction": direction,
        "incumbent_mean_return": incumbent["mean"],
        "candidate_mean_return": candidate["mean"],
        "raw_advantage": raw_advantage,
        "directed_advantage": directed_advantage,
        "relation": relation,
        "incumbent_pessimistic_return": incumbent["pessimistic_quantile"],
        "candidate_pessimistic_return": candidate["pessimistic_quantile"],
    }


def _score_free_action_tensor(
    edge: dict[str, Any], source_state_tensor: dict[str, Any] | None,
) -> dict[str, Any] | None:
    tensor = _action_tensor(edge, source_state_tensor)
    if tensor is None:
        return None
    names = list(tensor["feature_names"])
    values = list(tensor["values"])
    retained = [index for index, name in enumerate(names) if name != "immediate_score"]
    if len(retained) != len(names) - 1:
        raise ValueError("candidate action tensor must contain one immediate_score")
    return {
        **tensor,
        "schema_version": 2,
        "contract": "observed_candidate_action_no_heuristic_or_future_labels",
        "feature_names": [names[index] for index in retained],
        "values": [values[index] for index in retained],
    }


def trajectory_advantage_rows(
    graph: dict[str, Any], *, policy_generation: str,
) -> list[dict[str, Any]]:
    """Return candidate-vs-incumbent rows for every branching source state."""
    if not policy_generation:
        raise ValueError("policy_generation must be non-empty")
    nodes, outgoing = _graph_index(graph)
    horizon = int(graph.get("budget", {}).get("horizon", 0))
    if horizon not in (3, 4, 5):
        raise ValueError(f"unsupported graph horizon: {horizon}")
    directions = _metric_directions(graph)
    scenario_axes = graph.get(
        "scenario_axes", graph.get("provenance", {}).get("scenario_axes", {})
    )
    collection_identity = {
        "policy_generation": policy_generation,
        "future_stream_id": graph.get("future_stream_id"),
        "case_id": graph.get("case_id"),
        "scenario_axes": scenario_axes,
    }
    collection_group_id = "trajectory-group-" + hashlib.sha256(
        json.dumps(collection_identity, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    evaluation_fold = int(hashlib.sha256(
        collection_group_id.encode("utf-8")
    ).hexdigest()[:8], 16) % 5
    rows = []
    for source_id, edges in sorted(outgoing.items()):
        if len(edges) < 2:
            continue
        incumbents = [
            edge for edge in edges
            if int(edge.get("selection", {}).get("rank", -1)) == 0
        ]
        if len(incumbents) != 1:
            raise ValueError(
                f"source {source_id} must have exactly one rank-0 incumbent"
            )
        source = nodes[source_id]
        incumbent = incumbents[0]
        incumbent_samples = _trajectory_samples(
            source=source, first_edge=incumbent, nodes=nodes,
            outgoing=outgoing, horizon=horizon,
            metric_directions=directions,
        )
        source_tensor = source.get("state_tensor")
        for candidate in sorted(
            (edge for edge in edges if edge is not incumbent),
            key=lambda edge: int(edge.get("selection", {}).get("rank", 10**9)),
        ):
            candidate_samples = _trajectory_samples(
                source=source, first_edge=candidate, nodes=nodes,
                outgoing=outgoing, horizon=horizon,
                metric_directions=directions,
            )
            heads = {}
            for metric, direction in directions.items():
                head = _head_summary(
                    metric, direction, incumbent_samples, candidate_samples
                )
                if head is not None:
                    heads[metric] = head
            incumbent_index = int(
                incumbent["selection"]["stable_item_index"]
            )
            candidate_index = int(
                candidate["selection"]["stable_item_index"]
            )
            identity = {
                "graph_id": graph["graph_id"],
                "source_node_id": source_id,
                "incumbent_stable_item_index": incumbent_index,
                "candidate_stable_item_index": candidate_index,
                "policy_generation": policy_generation,
            }
            rows.append({
                "teacher_id": "trajectory-advantage-" + hashlib.sha256(
                    json.dumps(identity, sort_keys=True).encode("utf-8")
                ).hexdigest()[:20],
                "schema_version": 1,
                "target_contract": (
                    "direct_multi_head_G_H_candidate_minus_rank0_incumbent"
                ),
                "return_contract": (
                    "source_to_leaf_physical_outcome_including_first_action"
                ),
                "suffix_search_policy": (
                    "uniform_over_retained_children_at_each_future_node"
                ),
                "policy_generation": policy_generation,
                "graph_id": graph["graph_id"],
                "split_group_id": collection_group_id,
                "evaluation_fold": evaluation_fold,
                "root_regime": (
                    "discovery" if int(graph.get("root_step", 0)) < 15
                    else "late_holdout"
                ),
                "case_id": graph.get("case_id"),
                "root_step": int(graph.get("root_step", 0)),
                "source_node_id": source_id,
                "source_depth": int(source["depth"]),
                "remaining_horizon": horizon - int(source["depth"]),
                "future_stream_id": graph.get("future_stream_id"),
                "scenario_axes": scenario_axes,
                "source_state_tensor": source_tensor,
                "incumbent_action_tensor": _score_free_action_tensor(
                    incumbent, source_tensor
                ),
                "candidate_action_tensor": _score_free_action_tensor(
                    candidate, source_tensor
                ),
                "incumbent_afterstate_tensor": nodes[
                    incumbent["target"]
                ].get("state_tensor"),
                "candidate_afterstate_tensor": nodes[
                    candidate["target"]
                ].get("state_tensor"),
                "incumbent_stable_item_index": incumbent_index,
                "candidate_stable_item_index": candidate_index,
                "incumbent_trajectory_samples": incumbent_samples,
                "candidate_trajectory_samples": candidate_samples,
                "advantage_heads": heads,
            })
    return rows


def build_trajectory_advantage_corpus(
    graphs: list[dict[str, Any]], *, policy_generation: str,
    expected_horizon: int | None = None,
    expected_branch_factor: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = []
    graph_ids = set()
    for graph in graphs:
        graph_id = graph["graph_id"]
        if graph_id in graph_ids:
            raise ValueError(f"duplicate graph ID: {graph_id}")
        graph_ids.add(graph_id)
        horizon = int(graph.get("budget", {}).get("horizon", 0))
        branch_factor = int(graph.get("budget", {}).get("branch_factor", 0))
        if expected_horizon is not None and horizon != expected_horizon:
            raise ValueError(f"expected H{expected_horizon}, found H{horizon}")
        if (
            expected_branch_factor is not None
            and branch_factor != expected_branch_factor
        ):
            raise ValueError(
                f"expected B{expected_branch_factor}, found B{branch_factor}"
            )
        rows.extend(trajectory_advantage_rows(
            graph, policy_generation=policy_generation
        ))

    folds_by_group: dict[str, set[int]] = collections.defaultdict(set)
    for row in rows:
        folds_by_group[row["split_group_id"]].add(row["evaluation_fold"])
    rows_with_score = sum(
        any(
            "immediate_score" in (row.get(key) or {}).get("feature_names", [])
            for key in ("incumbent_action_tensor", "candidate_action_tensor")
        )
        for row in rows
    )
    head_counts = collections.Counter(
        metric for row in rows for metric in row["advantage_heads"]
    )
    manifest = {
        "schema_version": 1,
        "teacher": "paired trajectory advantage",
        "target": "G_H(s,a)-G_H(s,a0) without a weighted total",
        "policy_generation": policy_generation,
        "graph_count": len(graphs),
        "row_count": len(rows),
        "split_group_contract": (
            "policy_generation x future_stream x case x scenario"
        ),
        "evaluation_group_count": len(folds_by_group),
        "evaluation_group_fold_consistent": all(
            len(folds) == 1 for folds in folds_by_group.values()
        ),
        "root_regime_counts": dict(collections.Counter(
            row["root_regime"] for row in rows
        )),
        "rows_with_immediate_score_input": rows_with_score,
        "rows_with_paired_action_tensors": sum(
            isinstance(row.get("incumbent_action_tensor"), dict)
            and isinstance(row.get("candidate_action_tensor"), dict)
            for row in rows
        ),
        "rows_with_paired_afterstate_tensors": sum(
            isinstance(row.get("incumbent_afterstate_tensor"), dict)
            and isinstance(row.get("candidate_afterstate_tensor"), dict)
            for row in rows
        ),
        "advantage_head_row_counts": dict(sorted(head_counts.items())),
    }
    return manifest, rows


def _load_graphs(root: pathlib.Path) -> list[dict[str, Any]]:
    graphs = []
    for path in sorted(root.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if all(key in payload for key in ("graph_id", "nodes", "edges")):
            graphs.append(payload)
    if not graphs:
        raise ValueError(f"no counterfactual graphs found under {root}")
    return graphs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph-root", type=pathlib.Path, required=True)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--policy-generation", required=True)
    parser.add_argument("--expected-horizon", type=int)
    parser.add_argument("--expected-branch-factor", type=int)
    args = parser.parse_args()

    manifest, rows = build_trajectory_advantage_corpus(
        _load_graphs(args.graph_root),
        policy_generation=args.policy_generation,
        expected_horizon=args.expected_horizon,
        expected_branch_factor=args.expected_branch_factor,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "trajectory_advantage.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
