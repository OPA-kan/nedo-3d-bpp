"""Phase 4: vector search over the single-agent mainline.

A depth-limited physical tree search with no scalar anywhere:

- **Vector backup.** Component deltas are additive along a path, so
  every explored node carries the accumulated outcome vector from the
  root state; a root action's search value Q_search(s,a) is the *set*
  of vectors its explored subtree reached.
- **Objective-neutral allocation.** The next node to expand is always a
  frontier node: among unexpanded explored nodes whose accumulated
  vector lies on the current global Pareto frontier (dominance heads
  only), pick the least-deep, then lexicographically smallest — no
  weights, no scalarized exploration bonus.
- **Search-Pareto labels.** After the budget, a root candidate is on
  the search frontier iff its subtree contributes at least one vector
  to the global frontier over all achieved vectors: "this action
  enables a future on the frontier". These labels are the strategic
  teacher the beta contract reserves for search (never rank-0
  continuation).

Root candidate sets take the full union (legacy + measured coverage +
optional beta proposals) so the search also judges proposed actions;
deeper nodes expand with legacy top-k only, keeping physics cost
bounded. The environment is deterministic (degenerate world), so one
rollout per action sequence is exact.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from scripts.build_counterfactual_graph import (  # noqa: E402
    build_candidate_provider,
    cumulative_metrics,
)
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
    state_snapshot,
)
from scripts.counterfactual_graph import (  # noqa: E402
    state_tensor_from_snapshot,
    stable_id,
)
from scripts.coverage_action_sampler import coverage_candidates  # noqa: E402
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _candidate_record,
    _candidate_selection,
    _safe,
    _status,
)
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402
from scripts.single_agent_packing import (  # noqa: E402
    component_delta_vector,
)

DOMINANCE_HEADS = {
    "fill_gain": +1.0,
    "soft_violation_gain": -1.0,
    "priority_covered_gain": -1.0,
    "priority_misrouted_gain": -1.0,
    "surface_total_variation_delta": -1.0,
}
EPS = 1e-9


def _oriented(vector: dict[str, Any]) -> tuple[float, ...] | None:
    values = []
    for head, sign in DOMINANCE_HEADS.items():
        value = vector.get(head)
        if value is None:
            return None
        values.append(sign * float(value))
    return tuple(values)


def _dominates(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return all(x >= y - EPS for x, y in zip(a, b)) and any(
        x > y + EPS for x, y in zip(a, b)
    )


def pareto_frontier(vectors: dict[str, tuple[float, ...]]) -> set[str]:
    keys = sorted(vectors)
    return {
        key for key in keys
        if not any(
            _dominates(vectors[other], vectors[key])
            for other in keys if other != key
        )
    }


def _accumulate(
    base: dict[str, float | None], delta: dict[str, dict[str, Any]],
) -> dict[str, float | None]:
    result = {}
    for head in delta:
        value = delta[head].get("value")
        prior = base.get(head, 0.0)
        result[head] = (
            None if value is None or prior is None
            else float(prior) + float(value)
        )
    return result


def _rollout(
    task_config, *, environment_seed: int, prefix_actions, actions,
) -> dict[str, Any]:
    """Replay prefix + tree actions in a fresh env; step-by-step metrics."""
    env = _fresh_env(task_config)
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        for action in prefix_actions:
            observation, _r, terminated, truncated, info = env.step(action)
            if not _safe(_status(info)) or terminated or truncated:
                raise RuntimeError("prefix replay failed")
        vectors = []
        terminated = truncated = False
        safe = True
        for action in actions:
            before = cumulative_metrics(env)
            observation, _r, terminated, truncated, info = env.step(action)
            safe = _safe(_status(info))
            if not safe:
                break
            vectors.append(component_delta_vector(before, cumulative_metrics(env)))
            if terminated or truncated:
                break
        return {
            "safe": safe,
            "terminated": terminated,
            "truncated": truncated,
            "step_deltas": vectors,
            "observation": observation,
            "env": env,
        }
    except Exception:
        env.close()
        raise


def vector_search_root(
    agent_module, task_config: dict[str, Any], *, case_id: str,
    environment_seed: int, prefix_actions: list[Any],
    root_candidates: list[dict[str, Any]], attempt_budget: int,
    deep_top_k: int, expansions: int, max_depth: int, step: int,
) -> dict[str, Any]:
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    # node: key -> {actions, vector (accumulated), root_candidate_id,
    #               depth, expanded, alive}
    nodes: dict[str, dict[str, Any]] = {}
    physical_steps = 0

    def try_action_path(actions, root_candidate_id):
        nonlocal physical_steps
        result = _rollout(
            task_config, environment_seed=environment_seed,
            prefix_actions=prefix_actions, actions=actions,
        )
        physical_steps += len(actions)
        env = result.pop("env")
        try:
            if not result["safe"] or len(result["step_deltas"]) < len(actions):
                return None
            accumulated: dict[str, Any] = {
                head: 0.0 for head in DOMINANCE_HEADS
            }
            for delta in result["step_deltas"]:
                accumulated = _accumulate(accumulated, delta)
            key = stable_id("vector-node", {
                "actions": [json_safe(a) for a in actions],
            })
            ended = result["terminated"] or result["truncated"]
            candidates = []
            if not ended and len(actions) < max_depth:
                observation = result["observation"]
                candidates = [
                    _candidate_action(candidate)
                    for candidate in provider(
                        env, observation, int(deep_top_k)
                    )
                ]
            nodes[key] = {
                "actions": [json_safe(a) for a in actions],
                "vector": accumulated,
                "root_candidate_id": root_candidate_id,
                "depth": len(actions),
                "ended": ended,
                "continuations": candidates,
                "expanded": False,
            }
            return key
        finally:
            env.close()

    root_rows = []
    for candidate in root_candidates:
        record = _candidate_record(candidate)
        key = try_action_path(
            [_candidate_action(candidate)], record["candidate_id"]
        )
        root_rows.append({
            "root_candidate_id": record["candidate_id"],
            "command_action": record["command_action"],
            "stable_item_index": _candidate_selection(candidate).get(
                "stable_item_index"
            ),
            "provenance": record["proposal_provenance"],
            "safe": key is not None,
            "node": key,
        })

    for _expansion in range(expansions):
        frontier_vectors = {
            key: oriented
            for key, node in nodes.items()
            if not node["expanded"] and not node["ended"]
            and node["continuations"]
            and (oriented := _oriented(node["vector"])) is not None
        }
        if not frontier_vectors:
            break
        frontier = pareto_frontier(frontier_vectors)
        chosen = min(
            frontier, key=lambda key: (nodes[key]["depth"], key)
        )
        node = nodes[chosen]
        node["expanded"] = True
        for action in node["continuations"]:
            try_action_path(
                [*(node["actions"]), action], node["root_candidate_id"]
            )

    achieved = {
        key: oriented
        for key, node in nodes.items()
        if (oriented := _oriented(node["vector"])) is not None
    }
    global_frontier = pareto_frontier(achieved)
    frontier_candidates = {
        nodes[key]["root_candidate_id"] for key in global_frontier
    }
    for row in root_rows:
        row["in_search_pareto"] = (
            row["safe"] and row["root_candidate_id"] in frontier_candidates
        )
        if row["node"]:
            row["one_step_vector"] = nodes[row["node"]]["vector"]
    return {
        "step": int(step),
        "root_candidates": root_rows,
        "explored_nodes": len(nodes),
        "physical_steps": physical_steps,
        "global_frontier_size": len(global_frontier),
        "search_pareto_candidates": sorted(frontier_candidates),
        "nodes": {
            key: {
                field: node[field]
                for field in (
                    "actions", "vector", "root_candidate_id", "depth",
                    "ended", "expanded",
                )
            }
            for key, node in nodes.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--manifest", type=pathlib.Path, required=True,
                        help="single-agent v3 manifest supplying trajectory "
                        "prefixes and measured root candidates")
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--deep-top-k", type=int, default=3)
    parser.add_argument("--expansions", type=int, default=10)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--max-roots", type=int, default=None)
    parser.add_argument("--beta-model-dir", type=pathlib.Path, default=None)
    parser.add_argument("--beta-proposals", type=int, default=6)
    parser.add_argument("--beta-floor", type=int, default=2)
    parser.add_argument("--beta-sample-budget", type=int, default=48)
    parser.add_argument("--beta-seed", type=int, default=888000)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    config = json.loads(args.config.read_text())
    task_config = config[args.case] if args.case in config else config
    manifest = json.loads(args.manifest.read_text())
    episode = manifest["episodes"][0]
    agent_module = load_agent_module()
    beta_ensemble = None
    if args.beta_model_dir is not None:
        from scripts.train_feasibility_head import FeasibilityEnsemble

        beta_ensemble = FeasibilityEnsemble(args.beta_model_dir)

    env = _fresh_env(task_config)
    roots = []
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=args.environment_seed)
        executed: list[Any] = []
        for record in episode.get("records") or []:
            if args.max_roots is not None and len(roots) >= args.max_roots:
                break
            step = int(record["step"])
            # root candidate union: every measured-safe candidate of the
            # collection run (legacy + coverage), plus beta proposals
            union: list[dict[str, Any]] = []
            for sample in record.get("measurement_samples") or []:
                if not sample.get("physical_safe"):
                    continue
                if sample.get("command_action") is None:
                    continue
                union.append({
                    "candidate_id": sample["root_candidate_id"],
                    "command_action": sample["command_action"],
                    "selection": {
                        "stable_item_index": sample.get("stable_item_index"),
                    },
                    "proposal_provenance": sample[
                        "root_candidate_provenance"
                    ],
                })
            if beta_ensemble is not None:
                observed = policy_observation(env, observation)
                snapshot = state_snapshot(
                    env, observed, case_id=args.case, step=step
                )
                from scripts.beta_proposal import beta_feasibility_proposals

                proposals, _base = beta_feasibility_proposals(
                    observed, state_tensor_from_snapshot(snapshot),
                    ensemble=beta_ensemble,
                    coverage_seed=args.beta_seed + step,
                    sample_budget=args.beta_sample_budget,
                    keep=args.beta_proposals - args.beta_floor,
                    floor=args.beta_floor,
                    draw_seed=args.beta_seed * 7 + step,
                )
                known = {row["candidate_id"] for row in union}
                union.extend(
                    row for row in proposals
                    if row["candidate_id"] not in known
                )
            result = vector_search_root(
                agent_module, task_config, case_id=args.case,
                environment_seed=args.environment_seed,
                prefix_actions=list(executed),
                root_candidates=union,
                attempt_budget=args.attempt_budget,
                deep_top_k=args.deep_top_k,
                expansions=args.expansions,
                max_depth=args.max_depth, step=step,
            )
            result["root_id"] = record["root_id"]
            result["snapshot_path"] = record.get("snapshot_path")
            roots.append(result)
            print(
                f"root step={step} candidates={len(union)} "
                f"explored={result['explored_nodes']} "
                f"frontier={result['search_pareto_candidates'] and len(result['search_pareto_candidates'])} "
                f"physical_steps={result['physical_steps']}",
                flush=True,
            )
            action = record["action"]
            observation, _r, terminated, truncated, info = env.step(action)
            executed.append(action)
            if terminated or truncated or not _safe(_status(info)):
                break
    finally:
        env.close()
    payload = {
        "schema_version": 1,
        "contract": "vector_mcts_search_pareto_v1",
        "case_id": args.case,
        "dominance_heads": {k: v for k, v in DOMINANCE_HEADS.items()},
        "allocation": "pareto_frontier_first_least_depth",
        "backup": "additive_component_vector_sets",
        "expansions_per_root": args.expansions,
        "max_depth": args.max_depth,
        "beta_model": (
            None if beta_ensemble is None else beta_ensemble.model_id
        ),
        "roots": roots,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    labeled = sum(len(root["root_candidates"]) for root in roots)
    on_frontier = sum(
        row["in_search_pareto"]
        for root in roots for row in root["root_candidates"]
    )
    print(
        f"roots={len(roots)} labeled_candidates={labeled} "
        f"search_pareto={on_frontier}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
