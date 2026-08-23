"""Fork baseline and confidence-gated search actions into fresh trajectories.

The bounded DAG is a teacher, not an oracle.  A search action is followed only
when independent horizon/width views contain the same root actions, preserve
the physical and soft/priority hard constraints, and agree on a minimum fill
advantage.  Accepted roots are then replayed twice from the same exact prefix:
once with the current rank-0 action and once with the search action.  Both arms
continue under the unchanged policy and retain downstream replayable roots.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
for path in (ROOT, SIMULATOR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.build_behavior_policy_roots import action_was_accepted  # noqa: E402
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
    state_snapshot,
)
from scripts.counterfactual_graph import (  # noqa: E402
    board_fingerprint,
    canonical_action,
    capture_replay_contract,
    stable_id,
    state_tensor_from_snapshot,
)
from scripts.evaluate_budgeted_dag_search import (  # noqa: E402
    _index,
    constrained_root_oracle,
)
from scripts.score_components import components, dominates  # noqa: E402


TOLERANCE = 1e-12


def _action_key(action: dict[str, Any]) -> str:
    normalized = canonical_action(action)
    normalized["place_pos"] = [
        round(float(value), 6) for value in normalized["place_pos"]
    ]
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def _root_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    _nodes, outgoing, root_id = _index(graph)
    return outgoing.get(root_id, [])


def _root_fingerprint(graph: dict[str, Any]) -> str:
    nodes, _outgoing, root_id = _index(graph)
    return str(nodes[root_id].get("board_fingerprint", ""))


def _incumbent(edges: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next(
        (edge for edge in edges if int(edge.get("selection", {}).get("rank", -1)) == 0),
        edges[0] if edges else None,
    )


def _best_edge(
    edges: list[dict[str, Any]], values: dict[str, float | None],
) -> dict[str, Any] | None:
    feasible = [edge for edge in edges if values.get(edge["edge_id"]) is not None]
    return max(
        feasible,
        key=lambda edge: (
            float(values[edge["edge_id"]]),
            -int(edge.get("selection", {}).get("rank", 10**9)),
            str(edge["edge_id"]),
        ),
        default=None,
    )


def select_follow_decision(
    graphs: list[dict[str, Any]], *, metric: str = "fill_score_proxy",
    min_advantage: float = 0.5, required_horizons: set[int] | None = None,
    required_branch_factors: set[int] | None = None,
    incumbent_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ``follow`` only when every declared search view agrees."""
    if not graphs:
        raise ValueError("at least one graph view is required")
    if min_advantage < 0.0:
        raise ValueError("min_advantage must be non-negative")
    identity_fields = ("root_snapshot_id", "case_id", "root_step", "future_stream_id")
    reference = graphs[0]
    for graph in graphs[1:]:
        if any(graph.get(name) != reference.get(name) for name in identity_fields):
            raise ValueError("search views do not describe the same replay root")
        if _root_fingerprint(graph) != _root_fingerprint(reference):
            raise ValueError("search views have different root board fingerprints")

    horizons = {int(graph.get("budget", {}).get("horizon", 0)) for graph in graphs}
    branch_factors = {
        int(graph.get("budget", {}).get("branch_factor", 0)) for graph in graphs
    }
    reasons = []
    if required_horizons and not required_horizons.issubset(horizons):
        reasons.append("missing_required_horizon")
    if required_branch_factors and not required_branch_factors.issubset(branch_factors):
        reasons.append("missing_required_branch_factor")

    primary_edges = _root_edges(reference)
    primary_oracle = constrained_root_oracle(
        reference, metric=metric, hard_attributes=True
    )
    if incumbent_action is None:
        primary_incumbent = _incumbent(primary_edges)
    else:
        incumbent_key = _action_key(incumbent_action)
        primary_incumbent = next(
            (
                edge for edge in primary_edges
                if _action_key(edge["command_action"]) == incumbent_key
            ),
            None,
        )
        if primary_incumbent is None:
            reasons.append("live_incumbent_missing_from_primary_view")
    primary_best = _best_edge(primary_edges, primary_oracle["root_values"])
    if primary_incumbent is None or primary_best is None:
        reasons.append("no_feasible_root_pair")
        incumbent_action = search_action = None
    else:
        incumbent_action = canonical_action(primary_incumbent["command_action"])
        search_action = canonical_action(primary_best["command_action"])
        if _action_key(incumbent_action) == _action_key(search_action):
            reasons.append("no_search_disagreement")

    views = []
    if incumbent_action is not None and search_action is not None:
        incumbent_key = _action_key(incumbent_action)
        search_key = _action_key(search_action)
        for graph in graphs:
            edges = _root_edges(graph)
            by_action = {_action_key(edge["command_action"]): edge for edge in edges}
            incumbent = by_action.get(incumbent_key)
            candidate = by_action.get(search_key)
            oracle = constrained_root_oracle(
                graph, metric=metric, hard_attributes=True
            )
            incumbent_value = (
                oracle["root_values"].get(incumbent["edge_id"])
                if incumbent is not None else None
            )
            candidate_value = (
                oracle["root_values"].get(candidate["edge_id"])
                if candidate is not None else None
            )
            advantage = (
                float(candidate_value) - float(incumbent_value)
                if candidate_value is not None and incumbent_value is not None
                else None
            )
            agrees = bool(
                candidate is not None
                and candidate["edge_id"] in oracle["optimal_edge_ids"]
                and advantage is not None
                and advantage > float(min_advantage) - TOLERANCE
            )
            views.append({
                "graph_id": graph.get("graph_id"),
                "horizon": int(graph.get("budget", {}).get("horizon", 0)),
                "branch_factor": int(
                    graph.get("budget", {}).get("branch_factor", 0)
                ),
                "incumbent_edge_id": (
                    None if incumbent is None else incumbent["edge_id"]
                ),
                "search_edge_id": None if candidate is None else candidate["edge_id"],
                "incumbent_value": incumbent_value,
                "search_value": candidate_value,
                "advantage": advantage,
                "agrees": agrees,
            })
        if not all(view["agrees"] for view in views):
            reasons.append("view_disagreement")

    return {
        "status": "hold" if reasons else "follow",
        "reasons": sorted(set(reasons)),
        "metric": metric,
        "min_advantage": float(min_advantage),
        "root_snapshot_id": reference.get("root_snapshot_id"),
        "root_board_fingerprint": _root_fingerprint(reference),
        "case_id": reference.get("case_id"),
        "root_step": int(reference.get("root_step", 0)),
        "future_stream_id": reference.get("future_stream_id"),
        "incumbent_action": incumbent_action,
        "search_action": search_action,
        "observed_horizons": sorted(horizons),
        "observed_branch_factors": sorted(branch_factors),
        "views": views,
    }


def _compact_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in evaluation.items() if key != "step_metrics"}
    steps = evaluation.get("step_metrics") or []
    if steps:
        result["terminal_step_metrics"] = steps[-1]
    return json_safe(result)


def _arm_components(arm: dict[str, Any]) -> dict[str, Any]:
    return arm.get("components") or components({"evaluation": arm["evaluation"]})


def compare_arms(
    baseline: dict[str, Any], search: dict[str, Any],
) -> dict[str, Any]:
    baseline_components = _arm_components(baseline)
    search_components = _arm_components(search)
    raw_deltas: dict[str, Any] = {}
    for name in ("fill", "cog", "placement", "soft", "gate"):
        left = baseline_components.get(name, {}).get("raw")
        right = search_components.get(name, {}).get("raw")
        raw_deltas[name] = (
            float(right) - float(left)
            if isinstance(left, (int, float)) and isinstance(right, (int, float))
            else None
        )
    for key in (
        "max_shift", "peak_kinetic_energy", "items_shifted", "items_toppled"
    ):
        left = (baseline_components.get("stability", {}).get("raw") or {}).get(key)
        right = (search_components.get("stability", {}).get("raw") or {}).get(key)
        raw_deltas[f"stability.{key}"] = (
            float(right) - float(left)
            if isinstance(left, (int, float)) and isinstance(right, (int, float))
            else None
        )
    if dominates(search_components, baseline_components):
        pareto = "search_dominates"
    elif dominates(baseline_components, search_components):
        pareto = "baseline_dominates"
    else:
        pareto = "incomparable"
    baseline_states = {
        row.get("model_visible_state_signature")
        for row in baseline.get("captures", [])
        if row.get("model_visible_state_signature")
    }
    search_states = {
        row.get("model_visible_state_signature")
        for row in search.get("captures", [])
        if row.get("model_visible_state_signature")
    }
    return {
        "fill_delta": raw_deltas["fill"],
        "placed_delta": raw_deltas["gate"],
        "step_delta": int(search.get("steps", 0)) - int(baseline.get("steps", 0)),
        "raw_deltas": raw_deltas,
        "pareto_relation": pareto,
        "new_downstream_state_count": len(search_states - baseline_states),
        "shared_downstream_state_count": len(search_states & baseline_states),
    }


def run_arm(
    agent_module, task_config: dict[str, Any], snapshot: dict[str, Any], *,
    arm: str, root_action: dict[str, Any], incumbent_action: dict[str, Any],
    capture_offsets: set[int], output_dir: pathlib.Path,
    policy_generation: str, require_live_incumbent: bool = True,
) -> dict[str, Any]:
    """Replay an exact root, force one action, then return to the policy."""
    from src.ground_handling.env import GroundHandlingEnv

    contract = snapshot["replay_contract"]
    root_step = len(contract["action_prefix"])
    expected_step = int(snapshot.get("step", root_step))
    if root_step != expected_step:
        raise ValueError("snapshot step does not match replay prefix length")
    env = GroundHandlingEnv(
        config=copy.deepcopy(task_config), verbose=False, render_mode=None
    )
    solver = agent_module.Agent("")
    executed_actions: list[dict[str, Any]] = []
    captures = []
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        env.reset_settings()
        solver.get_init_states(env.get_init_states())
        env.reset_item_stream()
        raw_observation, _info = env.reset(seed=int(contract["seed"]))
        terminated = truncated = False
        for prefix_action in contract["action_prefix"]:
            observation = policy_observation(env, raw_observation)
            solver.policy(observation)
            command = canonical_action(prefix_action)
            raw_observation, _reward, terminated, truncated, _info = env.step(command)
            if terminated or truncated:
                raise RuntimeError("trajectory ended while replaying the root prefix")
            executed_actions.append(command)

        observation = policy_observation(env, raw_observation)
        observed_root = state_snapshot(
            env, observation, case_id=str(snapshot.get("case_id", "")), step=root_step
        )
        observed_fingerprint = board_fingerprint(observed_root)
        expected_fingerprint = str(
            snapshot.get("board_fingerprint") or board_fingerprint(snapshot)
        )
        if observed_fingerprint != expected_fingerprint:
            raise RuntimeError("replayed root board fingerprint does not match snapshot")
        live_action = canonical_action(solver.policy(observation))
        live_matches_incumbent = _action_key(live_action) == _action_key(incumbent_action)
        if require_live_incumbent and not live_matches_incumbent:
            raise RuntimeError("live policy action does not match graph rank-0 incumbent")

        command = canonical_action(root_action)
        raw_observation, _reward, terminated, truncated, info = env.step(command)
        root_action_accepted = action_was_accepted(info)
        executed_actions.append(command)
        step = root_step + 1
        while not terminated and not truncated:
            observation = policy_observation(env, raw_observation)
            offset = step - root_step
            if offset in capture_offsets:
                captured = state_snapshot(
                    env, observation,
                    case_id=str(snapshot.get("case_id", "")), step=step,
                )
                captured["snapshot_id"] = (
                    f"search-follow:{policy_generation}:{arm}:"
                    f"step-{step:03d}"
                )
                captured["replay_contract"] = capture_replay_contract(
                    env, executed_actions, seed=int(contract["seed"])
                )
                captured["board_fingerprint"] = board_fingerprint(captured)
                captured["model_visible_state_signature"] = stable_id(
                    "model-state", state_tensor_from_snapshot(captured)
                )
                captured["dataset_lineage"] = {
                    "generation": policy_generation,
                    "behavior_source": f"paired_search_follow:{arm}",
                    "future_stream_id": contract["future_stream_id"],
                    "root_trajectory_id": stable_id(
                        "root-trajectory",
                        {
                            "case_id": snapshot.get("case_id"),
                            "future_stream_id": contract["future_stream_id"],
                            "root_prefix_id": contract["action_prefix_id"],
                        },
                    ),
                    "parent_snapshot_id": snapshot.get("snapshot_id"),
                }
                path = output_dir / f"step-{step:03d}-state.json"
                path.write_text(
                    json.dumps(json_safe(captured), ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                captures.append({
                    "step": step,
                    "offset": offset,
                    "snapshot_path": path.name,
                    "board_fingerprint": captured["board_fingerprint"],
                    "model_visible_state_signature": captured[
                        "model_visible_state_signature"
                    ],
                })
            action = canonical_action(solver.policy(observation))
            raw_observation, _reward, terminated, truncated, _info = env.step(action)
            executed_actions.append(action)
            step += 1
        evaluation = env.evaluate()
        score_vector = components({"evaluation": evaluation})
    finally:
        env.close()
    return {
        "arm": arm,
        "steps": step,
        "terminated": bool(terminated),
        "truncated": bool(truncated),
        "root_action": canonical_action(root_action),
        "root_action_accepted": bool(root_action_accepted),
        "root_fingerprint_matches": True,
        "live_action_matches_incumbent": bool(live_matches_incumbent),
        "live_incumbent_required": bool(require_live_incumbent),
        "captures": captures,
        "missing_capture_offsets": sorted(
            capture_offsets - {int(row["offset"]) for row in captures}
        ),
        "components": json_safe(score_vector),
        "evaluation": _compact_evaluation(evaluation),
    }


def _write_manifest(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--graph", type=pathlib.Path, action="append", required=True)
    parser.add_argument("--metric", default="fill_score_proxy")
    parser.add_argument("--min-advantage", type=float, default=0.5)
    parser.add_argument("--require-horizon", type=int, action="append", default=[])
    parser.add_argument(
        "--require-branch-factor", type=int, action="append", default=[]
    )
    parser.add_argument("--capture-offset", type=int, action="append", default=[])
    parser.add_argument("--policy-generation", default="pi0")
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    graphs = [json.loads(path.read_text(encoding="utf-8")) for path in args.graph]
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    live_incumbent = snapshot.get("behavior_policy", {}).get("root_live_action")
    if live_incumbent is None:
        raise SystemExit(
            "snapshot lacks behavior_policy.root_live_action; regenerate the root"
        )
    decision = select_follow_decision(
        graphs,
        metric=args.metric,
        min_advantage=args.min_advantage,
        required_horizons=set(args.require_horizon),
        required_branch_factors=set(args.require_branch_factor),
        incumbent_action=live_incumbent,
    )
    payload: dict[str, Any] = {
        "schema_version": 1,
        "experiment": "confidence-gated paired search-follow",
        "policy_generation": args.policy_generation,
        "source_snapshot": args.snapshot.as_posix(),
        "source_graphs": [path.as_posix() for path in args.graph],
        "gate": decision,
    }
    manifest_path = args.output_dir / "manifest.json"
    if decision["status"] != "follow":
        _write_manifest(manifest_path, payload)
        print(manifest_path)
        return 0

    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.case not in config:
        raise SystemExit(f"unknown case: {args.case}")
    if decision["case_id"] != args.case or snapshot.get("case_id") != args.case:
        raise SystemExit("case does not match graph and snapshot provenance")
    if snapshot.get("replay_contract", {}).get("future_stream_id") != decision[
        "future_stream_id"
    ]:
        raise SystemExit("snapshot future stream does not match graph views")
    agent_module = load_agent_module()
    offsets = set(args.capture_offset or [3, 6])
    baseline = run_arm(
        agent_module, config[args.case], snapshot,
        arm="baseline", root_action=decision["incumbent_action"],
        incumbent_action=decision["incumbent_action"],
        capture_offsets=offsets, output_dir=args.output_dir / "baseline",
        policy_generation=args.policy_generation,
    )
    search = run_arm(
        agent_module, config[args.case], snapshot,
        arm="search", root_action=decision["search_action"],
        incumbent_action=decision["incumbent_action"],
        capture_offsets=offsets, output_dir=args.output_dir / "search",
        policy_generation=args.policy_generation,
    )
    execution_valid = bool(
        baseline["root_action_accepted"] and search["root_action_accepted"]
        and baseline["root_fingerprint_matches"]
        and search["root_fingerprint_matches"]
        and baseline["live_action_matches_incumbent"]
        and search["live_action_matches_incumbent"]
    )
    payload.update({
        "execution": {
            "valid": execution_valid,
            "same_future_stream": True,
            "capture_offsets": sorted(offsets),
        },
        "arms": {"baseline": baseline, "search": search},
        "comparison": compare_arms(baseline, search),
    })
    _write_manifest(manifest_path, payload)
    print(manifest_path)
    return 0 if execution_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
