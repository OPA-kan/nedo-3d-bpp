"""Replay budgeted PUCT-style search over already executed physical DAGs.

The graph is the environment: selecting an unread edge reveals at most one
already-recorded physical transition.  This isolates the search question from
PyBullet throughput and does not claim online-agent improvement.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
from typing import Any


FAILURE_REASONS = {
    "physical_failure", "no_candidate", "protocol_truncated",
    "reconstruction_mismatch",
}
SUCCESS_REASONS = {"stream_exhausted"}
STATUS_FLAGS = ("is_included", "is_valid", "is_placed_safe")
ATTRIBUTE_NONREGRESSION_DELTAS = (
    "priority_misrouted_delta",
    "priority_covered_by_other_delta",
    "soft_covered_by_other_delta",
    "post_shake_priority_misrouted_delta",
    "post_shake_priority_covered_by_other_delta",
    "post_shake_soft_covered_by_other_delta",
    "post_shake_soft_clean_to_covered_events_delta",
)


def _index(graph: dict[str, Any]) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    str,
]:
    nodes = {node["node_id"]: node for node in graph.get("nodes", [])}
    outgoing: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    incoming = set()
    for edge in graph.get("edges", []):
        if edge.get("source") not in nodes or edge.get("target") not in nodes:
            raise ValueError("graph edge references a missing node")
        outgoing[edge["source"]].append(edge)
        incoming.add(edge["target"])
    roots = [node_id for node_id in nodes if node_id not in incoming]
    if len(roots) != 1:
        raise ValueError(f"expected one root, found {len(roots)}")
    for edges in outgoing.values():
        edges.sort(key=_edge_order)
    return nodes, outgoing, roots[0]


def _edge_order(edge: dict[str, Any]) -> tuple[int, str]:
    return (
        int(edge.get("selection", {}).get("rank", 10**9)),
        str(edge.get("edge_id", "")),
    )


def edge_passes_hard_constraints(
    edge: dict[str, Any], *, hard_attributes: bool = True,
) -> bool:
    outcomes = edge.get("immediate_outcomes", {})
    if not all(outcomes.get(flag) is True for flag in STATUS_FLAGS):
        return False
    if not hard_attributes:
        return True
    return all(
        float(outcomes.get(name, 0.0) or 0.0) <= 1e-12
        for name in ATTRIBUTE_NONREGRESSION_DELTAS
    )


def _is_failed(node: dict[str, Any]) -> bool:
    return node.get("terminal_reason") in FAILURE_REASONS


def _is_goal(node: dict[str, Any], horizon: int) -> bool:
    return (
        int(node.get("depth", 0)) >= horizon
        or node.get("terminal_reason") in SUCCESS_REASONS
    ) and not _is_failed(node)


def _metric(node: dict[str, Any], name: str) -> float:
    outcomes = node.get("cumulative_outcomes", {})
    if name not in outcomes:
        raise ValueError(f"node {node.get('node_id')} lacks metric {name}")
    return float(outcomes[name])


def _oracle_values(
    graph: dict[str, Any], *, metric: str, hard_attributes: bool,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    str,
    dict[str, float | None],
]:
    nodes, outgoing, root_id = _index(graph)
    horizon = int(graph.get("budget", {}).get("horizon", 0))
    memo: dict[str, float | None] = {}
    visiting = set()

    def best(node_id: str) -> float | None:
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            raise ValueError("counterfactual graph contains a cycle")
        visiting.add(node_id)
        node = nodes[node_id]
        if _is_failed(node):
            value = None
        elif _is_goal(node, horizon):
            value = _metric(node, metric)
        else:
            children = [
                best(edge["target"])
                for edge in outgoing.get(node_id, [])
                if edge_passes_hard_constraints(
                    edge, hard_attributes=hard_attributes
                )
            ]
            valid = [child for child in children if child is not None]
            value = max(valid) if valid else None
        visiting.remove(node_id)
        memo[node_id] = value
        return value

    best(root_id)
    return nodes, outgoing, root_id, memo


def constrained_root_oracle(
    graph: dict[str, Any], *, metric: str = "fill_score_proxy",
    hard_attributes: bool = True,
) -> dict[str, Any]:
    nodes, outgoing, root_id, memo = _oracle_values(
        graph, metric=metric, hard_attributes=hard_attributes
    )
    root_values = {}
    for edge in outgoing.get(root_id, []):
        root_values[edge["edge_id"]] = (
            memo.get(edge["target"])
            if edge_passes_hard_constraints(
                edge, hard_attributes=hard_attributes
            )
            else None
        )
    feasible = [value for value in root_values.values() if value is not None]
    best_value = max(feasible) if feasible else None
    optimal = [
        edge["edge_id"] for edge in outgoing.get(root_id, [])
        if best_value is not None
        and root_values[edge["edge_id"]] is not None
        and math.isclose(
            float(root_values[edge["edge_id"]]), best_value,
            rel_tol=0.0, abs_tol=1e-12,
        )
    ]
    return {
        "root_id": root_id,
        "root_metric": _metric(nodes[root_id], metric),
        "root_values": root_values,
        "best_value": best_value,
        "optimal_edge_ids": optimal,
        "feasible_root_count": len(feasible),
        "root_action_count": len(outgoing.get(root_id, [])),
    }


def _priors(
    edges: list[dict[str, Any]], mode: str, temperature: float,
) -> dict[str, float]:
    if mode not in ("uniform", "rank"):
        raise ValueError(f"unsupported prior: {mode}")
    if temperature <= 0.0:
        raise ValueError("prior temperature must be positive")
    if not edges:
        return {}
    weights = []
    for edge in edges:
        rank = int(edge.get("selection", {}).get("rank", len(edges)))
        weights.append(1.0 if mode == "uniform" else math.exp(-rank / temperature))
    total = sum(weights)
    return {
        edge["edge_id"]: weight / total
        for edge, weight in zip(edges, weights)
    }


def puct_search(
    graph: dict[str, Any], *, simulations: int,
    prior: str = "rank", leaf_value: str = "prefix", cpuct: float = 2.0,
    prior_temperature: float = 1.0,
    metric: str = "fill_score_proxy", hard_attributes: bool = True,
) -> dict[str, Any]:
    """Return a root visit policy after a deterministic partial-DAG replay."""
    if simulations < 0:
        raise ValueError("simulations must be non-negative")
    if leaf_value not in ("prefix", "oracle"):
        raise ValueError(f"unsupported leaf value: {leaf_value}")
    if cpuct < 0.0:
        raise ValueError("cpuct must be non-negative")
    nodes, outgoing, root_id, oracle_values = _oracle_values(
        graph, metric=metric, hard_attributes=hard_attributes
    )
    horizon = int(graph.get("budget", {}).get("horizon", 0))
    root_metric = _metric(nodes[root_id], metric)
    value_scale = max(1.0, float(horizon))
    failure_value = -1.0
    stats = {
        edge["edge_id"]: {
            "visits": 0, "value_sum": 0.0,
            "revealed": False, "valid": None,
        }
        for edge in graph.get("edges", [])
    }
    prior_cache = {
        node_id: _priors(edges, prior, prior_temperature)
        for node_id, edges in outgoing.items()
    }

    def value(node_id: str) -> float:
        node = nodes[node_id]
        if _is_failed(node):
            return failure_value
        if leaf_value == "oracle":
            oracle = oracle_values.get(node_id)
            if oracle is None:
                return failure_value
            return (float(oracle) - root_metric) / value_scale
        if not _is_goal(node, horizon) and not outgoing.get(node_id):
            return failure_value
        return (_metric(node, metric) - root_metric) / value_scale

    revealed = set()
    for _ in range(simulations):
        node_id = root_id
        path = []
        while True:
            node = nodes[node_id]
            if _is_failed(node) or _is_goal(node, horizon):
                leaf = value(node_id)
                break
            edges = outgoing.get(node_id, [])
            if not edges:
                leaf = failure_value
                break
            total_visits = sum(stats[edge["edge_id"]]["visits"] for edge in edges)

            def selection_key(edge: dict[str, Any]) -> tuple[float, int, str]:
                row = stats[edge["edge_id"]]
                q_value = (
                    row["value_sum"] / row["visits"]
                    if row["visits"] else 0.0
                )
                exploration = (
                    cpuct * prior_cache[node_id][edge["edge_id"]]
                    * math.sqrt(total_visits + 1.0)
                    / (1.0 + row["visits"])
                )
                rank = int(edge.get("selection", {}).get("rank", 10**9))
                return q_value + exploration, -rank, str(edge["edge_id"])

            edge = max(edges, key=selection_key)
            edge_id = edge["edge_id"]
            path.append(edge_id)
            row = stats[edge_id]
            # The oracle-v arm represents an exact leaf evaluator. Once it
            # prices the selected child there is no information to gain by
            # descending and replacing that exact value with exploratory
            # sub-action returns. This is an upper control, not a deployable
            # model and not charged as additional physical edge reads.
            if leaf_value == "oracle":
                if not row["revealed"]:
                    row["revealed"] = True
                    row["valid"] = edge_passes_hard_constraints(
                        edge, hard_attributes=hard_attributes
                    )
                    revealed.add(edge_id)
                leaf = value(edge["target"]) if row["valid"] else failure_value
                break
            if not row["revealed"]:
                row["revealed"] = True
                row["valid"] = edge_passes_hard_constraints(
                    edge, hard_attributes=hard_attributes
                )
                revealed.add(edge_id)
                leaf = value(edge["target"]) if row["valid"] else failure_value
                break
            if not row["valid"]:
                leaf = failure_value
                break
            node_id = edge["target"]

        for edge_id in path:
            stats[edge_id]["visits"] += 1
            stats[edge_id]["value_sum"] += leaf

    root_edges = outgoing.get(root_id, [])
    if not root_edges:
        chosen = None
    else:
        def final_key(edge: dict[str, Any]) -> tuple[int, float, int, str]:
            row = stats[edge["edge_id"]]
            q_value = (
                row["value_sum"] / row["visits"]
                if row["visits"] else float("-inf")
            )
            rank = int(edge.get("selection", {}).get("rank", 10**9))
            return row["visits"], q_value, -rank, str(edge["edge_id"])
        chosen = max(root_edges, key=final_key)
    root_visits = {
        edge["edge_id"]: int(stats[edge["edge_id"]]["visits"])
        for edge in root_edges
    }
    visit_total = sum(root_visits.values())
    policy = {
        edge_id: visits / visit_total if visit_total else 0.0
        for edge_id, visits in root_visits.items()
    }
    root_q = {
        edge["edge_id"]: (
            stats[edge["edge_id"]]["value_sum"]
            / stats[edge["edge_id"]]["visits"]
            if stats[edge["edge_id"]]["visits"] else None
        )
        for edge in root_edges
    }
    q_candidates = [
        edge for edge in root_edges if root_q[edge["edge_id"]] is not None
    ]
    chosen_by_q = max(
        q_candidates,
        key=lambda edge: (
            float(root_q[edge["edge_id"]]),
            root_visits[edge["edge_id"]],
            -int(edge.get("selection", {}).get("rank", 10**9)),
        ),
        default=None,
    )
    return {
        "prior": prior,
        "leaf_value": leaf_value,
        "cpuct": cpuct,
        "simulations": simulations,
        "chosen_edge_id": chosen["edge_id"] if chosen is not None else None,
        "root_visits": root_visits,
        "root_q": root_q,
        "policy": policy,
        "chosen_by_q_edge_id": (
            chosen_by_q["edge_id"] if chosen_by_q is not None else None
        ),
        "revealed_edge_count": len(revealed),
        "total_edge_count": len(graph.get("edges", [])),
    }


def root_scan(
    graph: dict[str, Any], *, probes: int,
    metric: str = "fill_score_proxy", hard_attributes: bool = True,
) -> dict[str, Any]:
    """Probe root actions in incumbent rank order and keep the best H1 fill."""
    nodes, outgoing, root_id = _index(graph)
    root_edges = outgoing.get(root_id, [])
    selected = root_edges[:max(0, probes)]
    valid = [
        edge for edge in selected
        if edge_passes_hard_constraints(
            edge, hard_attributes=hard_attributes
        )
        and not _is_failed(nodes[edge["target"]])
    ]
    chosen = max(
        valid,
        key=lambda edge: (
            _metric(nodes[edge["target"]], metric),
            -int(edge.get("selection", {}).get("rank", 10**9)),
        ),
        default=None,
    )
    visits = {
        edge["edge_id"]: int(edge in selected) for edge in root_edges
    }
    total = sum(visits.values())
    return {
        "prior": "rank",
        "leaf_value": "prefix",
        "cpuct": 0.0,
        "simulations": probes,
        "chosen_edge_id": chosen["edge_id"] if chosen is not None else None,
        "root_visits": visits,
        "policy": {
            edge_id: count / total if total else 0.0
            for edge_id, count in visits.items()
        },
        "revealed_edge_count": len(selected),
        "total_edge_count": len(graph.get("edges", [])),
    }


def evaluate_graph(
    graph: dict[str, Any], *, simulation_budgets: list[int],
    cpuct_values: list[float], metric: str = "fill_score_proxy",
    hard_attributes: bool = True,
) -> dict[str, Any]:
    oracle = constrained_root_oracle(
        graph, metric=metric, hard_attributes=hard_attributes
    )
    _nodes, outgoing, root_id = _index(graph)
    root_edges = outgoing.get(root_id, [])
    incumbent = next(
        (
            edge for edge in root_edges
            if int(edge.get("selection", {}).get("rank", -1)) == 0
        ),
        root_edges[0] if root_edges else None,
    )
    incumbent_id = incumbent["edge_id"] if incumbent is not None else None
    full_scan = root_scan(
        graph, probes=len(root_edges), metric=metric,
        hard_attributes=hard_attributes,
    )
    full_scan_id = full_scan["chosen_edge_id"]
    full_scan_optimal = full_scan_id in oracle["optimal_edge_ids"]
    searches = []
    arms = (
        ("puct-uniform-prefix-v", "uniform", "prefix"),
        ("puct-rank-prefix-v", "rank", "prefix"),
        ("puct-rank-oracle-v", "rank", "oracle"),
    )
    for simulations in simulation_budgets:
        scan = root_scan(
            graph, probes=simulations, metric=metric,
            hard_attributes=hard_attributes,
        )
        scan_id = scan["chosen_edge_id"]
        scan_value = oracle["root_values"].get(scan_id)
        searches.append({
            **scan,
            "algorithm": "rank-root-scan-prefix-v",
            "chosen_oracle_value": scan_value,
            "oracle_optimal": scan_id in oracle["optimal_edge_ids"],
            "oracle_regret": (
                float(oracle["best_value"]) - float(scan_value)
                if oracle["best_value"] is not None
                and scan_value is not None else None
            ),
        })
        for cpuct in cpuct_values:
            for name, prior, leaf_value in arms:
                search = puct_search(
                    graph,
                    simulations=simulations,
                    prior=prior,
                    leaf_value=leaf_value,
                    cpuct=cpuct,
                    metric=metric,
                    hard_attributes=hard_attributes,
                )
                chosen_id = search["chosen_edge_id"]
                chosen_value = oracle["root_values"].get(chosen_id)
                regret = (
                    float(oracle["best_value"]) - float(chosen_value)
                    if oracle["best_value"] is not None
                    and chosen_value is not None else None
                )
                searches.append({
                    **search,
                    "algorithm": name,
                    "chosen_oracle_value": chosen_value,
                    "oracle_optimal": chosen_id in oracle["optimal_edge_ids"],
                    "oracle_regret": regret,
                })
                q_chosen_id = search["chosen_by_q_edge_id"]
                q_chosen_value = oracle["root_values"].get(q_chosen_id)
                searches.append({
                    **search,
                    "chosen_edge_id": q_chosen_id,
                    "algorithm": name + "-q-selection",
                    "chosen_oracle_value": q_chosen_value,
                    "oracle_optimal": q_chosen_id in oracle["optimal_edge_ids"],
                    "oracle_regret": (
                        float(oracle["best_value"]) - float(q_chosen_value)
                        if oracle["best_value"] is not None
                        and q_chosen_value is not None else None
                    ),
                })
    return {
        "graph_id": graph.get("graph_id"),
        "case_id": graph.get("case_id"),
        "root_step": graph.get("root_step"),
        "horizon": graph.get("budget", {}).get("horizon"),
        "branch_factor": graph.get("budget", {}).get("branch_factor"),
        "oracle": oracle,
        "incumbent_edge_id": incumbent_id,
        "incumbent_oracle_value": oracle["root_values"].get(incumbent_id),
        "incumbent_optimal": incumbent_id in oracle["optimal_edge_ids"],
        "full_root_scan_edge_id": full_scan_id,
        "full_root_scan_optimal": full_scan_optimal,
        "future_sensitive": bool(
            oracle["best_value"] is not None and not full_scan_optimal
        ),
        "searches": searches,
    }


def evaluate_corpus(
    graphs: list[dict[str, Any]], *, simulation_budgets: list[int],
    cpuct_values: list[float], metric: str = "fill_score_proxy",
    hard_attributes: bool = True,
) -> dict[str, Any]:
    results = [
        evaluate_graph(
            graph,
            simulation_budgets=simulation_budgets,
            cpuct_values=cpuct_values,
            metric=metric,
            hard_attributes=hard_attributes,
        )
        for graph in graphs
    ]
    eligible = [
        result for result in results
        if result["oracle"]["best_value"] is not None
        and result["oracle"]["root_action_count"] >= 2
    ]
    rows: dict[tuple[str, int, float], list[dict[str, Any]]] = (
        collections.defaultdict(list)
    )
    for result in eligible:
        for search in result["searches"]:
            rows[(
                search["algorithm"], int(search["simulations"]),
                float(search["cpuct"]),
            )].append(search)
    aggregate = []
    for (algorithm, simulations, cpuct), members in sorted(rows.items()):
        feasible = [
            member for member in members
            if member["chosen_oracle_value"] is not None
        ]
        regrets = [
            float(member["oracle_regret"])
            for member in members if member["oracle_regret"] is not None
        ]
        future_sensitive_members = [
            member for result in eligible if result["future_sensitive"]
            for member in result["searches"]
            if member["algorithm"] == algorithm
            and int(member["simulations"]) == simulations
            and float(member["cpuct"]) == cpuct
        ]
        aggregate.append({
            "algorithm": algorithm,
            "simulations": simulations,
            "cpuct": cpuct,
            "eligible_graphs": len(members),
            "optimal_roots": sum(member["oracle_optimal"] for member in members),
            "optimal_root_rate": (
                sum(member["oracle_optimal"] for member in members) / len(members)
                if members else None
            ),
            "feasible_choices": len(feasible),
            "feasible_choice_rate": len(feasible) / len(members) if members else None,
            "mean_oracle_regret_when_feasible": (
                sum(regrets) / len(regrets) if regrets else None
            ),
            "mean_revealed_edges": (
                sum(member["revealed_edge_count"] for member in members)
                / len(members) if members else None
            ),
            "future_sensitive_graphs": len(future_sensitive_members),
            "future_sensitive_optimal_roots": sum(
                member["oracle_optimal"]
                for member in future_sensitive_members
            ),
        })
    rejection_counts = collections.Counter()
    for graph in graphs:
        for edge in graph.get("edges", []):
            outcomes = edge.get("immediate_outcomes", {})
            for flag in STATUS_FLAGS:
                if outcomes.get(flag) is not True:
                    rejection_counts[flag] += 1
            for name in ATTRIBUTE_NONREGRESSION_DELTAS:
                if float(outcomes.get(name, 0.0) or 0.0) > 1e-12:
                    rejection_counts[name] += 1
    physical_oracles = (
        [
            constrained_root_oracle(
                graph, metric=metric, hard_attributes=False
            )
            for graph in graphs
        ]
        if hard_attributes else []
    )
    attribute_eliminated = (
        sum(
            physical["best_value"] is not None
            and result["oracle"]["best_value"] is None
            for physical, result in zip(physical_oracles, results)
        )
        if hard_attributes else 0
    )
    return {
        "schema_version": 1,
        "experiment": "partial-read PUCT replay on executed physical DAGs",
        "metric": metric,
        "hard_constraints": {
            "physical_status_flags": list(STATUS_FLAGS),
            "attribute_nonregression": hard_attributes,
            "attribute_delta_fields": (
                list(ATTRIBUTE_NONREGRESSION_DELTAS)
                if hard_attributes else []
            ),
        },
        "graph_count": len(graphs),
        "eligible_graph_count": len(eligible),
        "graphs_without_constrained_oracle": sum(
            result["oracle"]["best_value"] is None for result in results
        ),
        "attribute_constraint_eliminated_oracle_graphs": attribute_eliminated,
        "edge_rejection_signal_counts": dict(sorted(rejection_counts.items())),
        "single_root_action_graphs": sum(
            result["oracle"]["root_action_count"] < 2 for result in results
        ),
        "incumbent_optimal_graphs": sum(
            result["incumbent_optimal"] for result in eligible
        ),
        "incumbent_optimal_rate": (
            sum(result["incumbent_optimal"] for result in eligible) / len(eligible)
            if eligible else None
        ),
        "full_root_scan_optimal_graphs": sum(
            result["full_root_scan_optimal"] for result in eligible
        ),
        "future_sensitive_graph_count": sum(
            result["future_sensitive"] for result in eligible
        ),
        "simulation_budgets": simulation_budgets,
        "cpuct_values": cpuct_values,
        "aggregate": aggregate,
        "graphs": results,
        "claim_limit": (
            "retrospective search-mechanics evidence on a retained B3 DAG; "
            "oracle-v is a diagnostic ceiling, not a deployable value model"
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    rate = report["incumbent_optimal_rate"]
    lines = [
        "# Budgeted physical-DAG search replay", "",
        f"- graphs: {report['graph_count']}",
        f"- eligible graphs: {report['eligible_graph_count']}",
        f"- no constrained horizon oracle: "
        f"{report['graphs_without_constrained_oracle']}",
        f"- oracle removed only by attribute hard constraints: "
        f"{report['attribute_constraint_eliminated_oracle_graphs']}",
        f"- rank-0 incumbent oracle-optimal: "
        f"{report['incumbent_optimal_graphs']}/"
        f"{report['eligible_graph_count']} "
        f"({rate:.1%})" if rate is not None else "- rank-0 incumbent: n/a",
        f"- full H1 root scan oracle-optimal: "
        f"{report['full_root_scan_optimal_graphs']}/"
        f"{report['eligible_graph_count']}",
        f"- genuinely future-sensitive roots: "
        f"{report['future_sensitive_graph_count']}",
        "- soft/priority non-regression is a hard edge constraint: "
        f"{report['hard_constraints']['attribute_nonregression']}",
        "",
        "| algorithm | sims | c_puct | optimal root | feasible | mean regret | "
        "edges read |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["aggregate"]:
        regret = row["mean_oracle_regret_when_feasible"]
        lines.append(
            f"| {row['algorithm']} | {row['simulations']} | {row['cpuct']} | "
            f"{row['optimal_roots']}/{row['eligible_graphs']} "
            f"({row['optimal_root_rate']:.1%}) | "
            f"{row['feasible_choices']}/{row['eligible_graphs']} "
            f"({row['feasible_choice_rate']:.1%}) | "
            f"{regret if regret is not None else 'n/a'} | "
            f"{row['mean_revealed_edges']:.2f} |"
        )
    lines.extend(["", f"> {report['claim_limit']}", ""])
    return "\n".join(lines)


def _load_graphs(root: pathlib.Path) -> list[dict[str, Any]]:
    graphs = []
    seen = set()
    for path in sorted(root.rglob("graph.json")):
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph_id = graph.get("graph_id")
        if graph_id in seen:
            continue
        seen.add(graph_id)
        graphs.append(graph)
    if not graphs:
        raise ValueError(f"no graph.json files found below {root}")
    return graphs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument("--metric", default="fill_score_proxy")
    parser.add_argument(
        "--simulation-budget", type=int, action="append",
        dest="simulation_budgets",
    )
    parser.add_argument("--cpuct", type=float, action="append", dest="cpuct_values")
    parser.add_argument(
        "--hard-attributes", action=argparse.BooleanOptionalAction,
        default=True,
    )
    args = parser.parse_args()
    report = evaluate_corpus(
        _load_graphs(args.graph_root),
        simulation_budgets=args.simulation_budgets or [1, 3, 6, 12, 24, 40],
        cpuct_values=args.cpuct_values or [0.5, 1.0, 2.0, 4.0],
        metric=args.metric,
        hard_attributes=args.hard_attributes,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
