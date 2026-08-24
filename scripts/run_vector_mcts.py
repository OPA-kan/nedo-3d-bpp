"""Phase 4: vector search over the single-agent mainline.

A depth-limited physical tree search with vector-valued outcomes:

- **Vector backup.** Component deltas are additive along a path, so
  every explored node carries the accumulated outcome vector from the
  root state; a root action's search value Q_search(s,a) is the *set*
  of vectors its explored subtree reached.
- **Selectable allocation.** ``frontier`` preserves v0: among
  unexpanded explored nodes on the current global Pareto frontier,
  choose the least-deep node. ``pareto-puct`` instead backs up edge visit
  counts and mean vectors, forms an optimistic Pareto set with a
  count-based confidence bonus, then uses prior/low visits only within
  that set. Neither mode introduces objective exchange weights.
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

The default ``--leaf-eval measured`` preserves v0.  The opt-in
``--leaf-eval rollout`` is an oracle/reference arm: every reached node is
continued by the frozen rank-0 policy to a genuine terminal, while one-step,
bounded-search and terminal Pareto membership remain separately recorded.
It does not load V and uses a distinct output contract so it cannot silently
become the existing acceptance-head teacher.

For allocation benchmarks, ``--terminal-audit`` keeps measured leaf values
inside search and runs the genuine-terminal continuation only for each safe
root action after its one-step transition. Thus terminal outcomes can score
``frontier`` and ``pareto-puct`` without leaking oracle values into either
allocation policy.

The controlled ``--leaf-eval value`` arm is valid only with
``--allocation pareto-puct``. It composes measured root-to-leaf component
deltas with a group-excluded single-agent multi-head suffix V. Terminal-only
stability predictions remain separate fields; no scalar utility is invented.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from typing import Any, Callable

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
    board_fingerprint,
    item_symmetry_board_fingerprint,
    state_tensor_from_snapshot,
    stable_id,
)
from scripts.coverage_action_sampler import coverage_candidates  # noqa: E402
from scripts.item_symmetry_transposition_shadow import (  # noqa: E402
    ItemSymmetryTranspositionShadow,
)
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _candidate_record,
    _candidate_selection,
    _compact_evaluation,
    _safe,
    _status,
    build_exact_physical_legal_filter,
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
GENUINE_TERMINATIONS = {
    "stream_exhausted", "no_retained_candidate", "no_safe_retained_candidate",
}
LEAF_SUFFIX_TO_COMPONENT = {
    "fill_return": "fill_gain",
    "placed_return": "placed_gain",
    "soft_violation_return": "soft_violation_gain",
    "priority_covered_return": "priority_covered_gain",
    "priority_misrouted_return": "priority_misrouted_gain",
    "center_of_mass_z_return": "center_of_mass_z_delta",
    "surface_total_variation_return": "surface_total_variation_delta",
}


def _output_contract(
    leaf_eval: str, *, terminal_audit: bool = False,
    allocation: str = "frontier",
) -> tuple[int, str, str | None]:
    if allocation not in {"frontier", "pareto-puct"}:
        raise ValueError(f"unsupported allocation: {allocation}")
    if terminal_audit:
        if leaf_eval == "rollout":
            raise ValueError(
                "terminal_audit cannot accompany rollout-guided allocation"
            )
        if leaf_eval == "value":
            return (
                4, "pareto_puct_value_terminal_audit_v4",
                "terminal_frontier_resurrection_v1",
            )
        return (
            3, "pareto_search_terminal_audit_v3",
            "terminal_frontier_resurrection_v1",
        )
    if leaf_eval == "measured" and allocation == "frontier":
        return 1, "vector_mcts_search_pareto_v1", None
    if leaf_eval == "measured":
        return 2, "vector_pareto_puct_search_v1", None
    if leaf_eval == "rollout":
        return (
            2, "pareto_tree_search_terminal_oracle_v2",
            "terminal_frontier_resurrection_v1",
        )
    if leaf_eval == "value":
        return 4, "vector_pareto_puct_value_shadow_v4", None
    raise ValueError(f"unsupported leaf evaluator: {leaf_eval}")


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


def _new_edge_stat(*, prior: float) -> dict[str, Any]:
    """Create one objective-neutral vector edge-statistics record."""
    if prior <= 0.0:
        raise ValueError("Pareto-PUCT prior must be positive")
    width = len(DOMINANCE_HEADS)
    return {
        "visits": 0,
        "prior": float(prior),
        "mean_oriented": [0.0] * width,
        "m2_oriented": [0.0] * width,
        "last_confidence_bonus": None,
        "last_optimistic_vector": None,
    }


def _update_edge_stat(
    edge: dict[str, Any], vector: dict[str, Any],
) -> bool:
    """Online-backup one achieved vector into an incoming tree edge."""
    oriented = _oriented(vector)
    if oriented is None:
        return False
    old_n = int(edge["visits"])
    new_n = old_n + 1
    means = list(edge["mean_oriented"])
    m2 = list(edge["m2_oriented"])
    for index, value in enumerate(oriented):
        delta = value - means[index]
        means[index] += delta / new_n
        m2[index] += delta * (value - means[index])
    edge["visits"] = new_n
    edge["mean_oriented"] = means
    edge["m2_oriented"] = m2
    return True


def _pareto_puct_choice(
    edges: dict[str, dict[str, Any]], *, c_puct: float,
) -> str:
    """Choose an edge by optimistic Pareto membership, then prior/visits.

    Confidence optimism and exploration prior are intentionally separate.
    Sibling Q means are standardized by their observed per-head range, a
    scale statistic rather than a utility exchange rate.  The same count
    bonus is then added to every standardized head.
    """
    if c_puct < 0.0:
        raise ValueError("c_puct must be non-negative")
    eligible = {
        key: edge for key, edge in edges.items()
        if int(edge.get("visits", 0)) > 0
    }
    if not eligible:
        raise ValueError("Pareto-PUCT needs at least one visited edge")
    width = len(DOMINANCE_HEADS)
    centers = []
    scales = []
    for index in range(width):
        values = [
            float(edge["mean_oriented"][index])
            for edge in eligible.values()
        ]
        centers.append(sum(values) / len(values))
        span = max(values) - min(values)
        scales.append(span if span > EPS else 1.0)
    total_visits = sum(int(edge["visits"]) for edge in eligible.values())
    optimistic: dict[str, tuple[float, ...]] = {}
    for key, edge in eligible.items():
        visits = int(edge["visits"])
        bonus = c_puct * math.sqrt(total_visits) / (1.0 + visits)
        vector = tuple(
            (
                float(edge["mean_oriented"][index]) - centers[index]
            ) / scales[index] + bonus
            for index in range(width)
        )
        edge["last_confidence_bonus"] = [bonus] * width
        edge["last_optimistic_vector"] = list(vector)
        optimistic[key] = vector
    frontier = pareto_frontier(optimistic)
    return min(
        frontier,
        key=lambda key: (
            int(eligible[key]["visits"]) / float(eligible[key]["prior"]),
            int(eligible[key]["visits"]),
            key,
        ),
    )


def _candidate_frontier(
    vectors: dict[str, tuple[str, dict[str, Any] | None]],
) -> set[str]:
    """Map a frontier over achieved vectors back to root candidates."""
    oriented = {
        key: value
        for key, (_candidate, raw) in vectors.items()
        if raw is not None and (value := _oriented(raw)) is not None
    }
    return {
        vectors[key][0] for key in pareto_frontier(oriented)
    } if oriented else set()


def _recall(found: set[str], truth: set[str]) -> float | None:
    return len(found & truth) / len(truth) if truth else None


def build_resurrection_audit(
    root_rows: list[dict[str, Any]], nodes: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compare shallow, searched and genuine-terminal Pareto membership.

    Terminal truth is emitted only when every safe root candidate has a
    genuine terminal rollout.  A capped or failed continuation therefore
    censors the root audit instead of silently shrinking the comparison set.
    """
    root_nodes = {
        str(row["root_candidate_id"]): nodes[row["node"]]
        for row in root_rows if row.get("safe", True) and row.get("node")
    }
    root_candidates = set(root_nodes)
    h1 = _candidate_frontier({
        f"h1:{candidate}": (candidate, node.get("vector"))
        for candidate, node in root_nodes.items()
    })
    measured_search = _candidate_frontier({
        f"measured:{key}": (str(node["root_candidate_id"]), node.get("vector"))
        for key, node in nodes.items()
    })
    evaluated_search = _candidate_frontier({
        f"evaluated:{key}": (
            str(node["root_candidate_id"]), node.get("evaluation_vector")
        )
        for key, node in nodes.items()
    })
    terminal_eligible = {
        candidate for candidate, node in root_nodes.items()
        if node.get("terminal_genuine") is True
        and _oriented(node.get("terminal_vector") or {}) is not None
    }
    terminal_censored = root_candidates - terminal_eligible
    terminal_truth_complete = (
        bool(root_candidates) and not terminal_censored
    )
    terminal = (
        _candidate_frontier({
            f"terminal:{candidate}": (
                candidate, root_nodes[candidate].get("terminal_vector")
            )
            for candidate in terminal_eligible
        })
        if terminal_truth_complete else set()
    )
    resurrected = terminal - h1
    deepened = {
        str(node["root_candidate_id"])
        for node in nodes.values() if int(node.get("depth", 0)) > 1
    }
    measured_found = resurrected & measured_search
    evaluated_found = resurrected & evaluated_search
    deepened_found = resurrected & deepened
    max_depth_by_candidate = {
        candidate: max(
            (
                int(node.get("depth", 0)) for node in nodes.values()
                if str(node["root_candidate_id"]) == candidate
            ),
            default=0,
        )
        for candidate in root_candidates
    }
    return {
        "contract": "terminal_frontier_resurrection_v1",
        "root_candidate_ids": sorted(root_candidates),
        "h1_pareto_candidates": sorted(h1),
        "measured_search_pareto_candidates": sorted(measured_search),
        "evaluated_search_pareto_candidates": sorted(evaluated_search),
        "terminal_truth_complete": terminal_truth_complete,
        "terminal_eligible_candidates": sorted(terminal_eligible),
        "terminal_censored_candidates": sorted(terminal_censored),
        "terminal_pareto_candidates": sorted(terminal),
        "terminal_frontier_resurrection_candidates": sorted(resurrected),
        "deepened_candidates": sorted(deepened),
        "deepened_resurrection_candidates": sorted(deepened_found),
        "measured_frontier_resurrection_candidates": sorted(measured_found),
        "evaluated_frontier_resurrection_candidates": sorted(evaluated_found),
        "deepened_resurrection_recall": _recall(deepened, resurrected),
        "measured_frontier_resurrection_recall": _recall(
            measured_search, resurrected
        ),
        "evaluated_frontier_resurrection_recall": _recall(
            evaluated_search, resurrected
        ),
        "candidate_audit": {
            candidate: {
                "in_h1_pareto": candidate in h1,
                "in_measured_search_pareto": candidate in measured_search,
                "in_evaluated_search_pareto": candidate in evaluated_search,
                "terminal_eligible": candidate in terminal_eligible,
                "in_terminal_pareto": candidate in terminal,
                "terminal_frontier_resurrection": candidate in resurrected,
                "max_explored_depth": max_depth_by_candidate[candidate],
                "deepened": candidate in deepened,
            }
            for candidate in sorted(root_candidates)
        },
    }


def summarize_resurrection_audits(
    roots: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate action-level resurrection recall over complete roots."""
    complete = [root for root in roots if root.get("terminal_truth_complete")]
    truth = sum(
        len(root.get("terminal_frontier_resurrection_candidates") or [])
        for root in complete
    )

    def count(field: str) -> int:
        return sum(len(root.get(field) or []) for root in complete)

    deepened = count("deepened_resurrection_candidates")
    measured = count("measured_frontier_resurrection_candidates")
    evaluated = count("evaluated_frontier_resurrection_candidates")
    return {
        "contract": "terminal_frontier_resurrection_summary_v1",
        "roots": len(roots),
        "terminal_truth_complete_roots": len(complete),
        "terminal_truth_censored_roots": len(roots) - len(complete),
        "roots_with_terminal_resurrection": sum(
            bool(root.get("terminal_frontier_resurrection_candidates"))
            for root in complete
        ),
        "terminal_resurrection_actions": truth,
        "deepened_resurrection_actions": deepened,
        "measured_frontier_resurrection_actions": measured,
        "evaluated_frontier_resurrection_actions": evaluated,
        "deepened_resurrection_recall": deepened / truth if truth else None,
        "measured_frontier_resurrection_recall": (
            measured / truth if truth else None
        ),
        "evaluated_frontier_resurrection_recall": (
            evaluated / truth if truth else None
        ),
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


def _component_values(
    before: dict[str, Any], after: dict[str, Any],
) -> dict[str, float | None]:
    return {
        head: target.get("value")
        for head, target in component_delta_vector(before, after).items()
    }


def compose_leaf_value(
    achieved: dict[str, float | None],
    prediction: dict[str, dict[str, Any]],
) -> dict[str, float | None]:
    """Compose measured prefix deltas with remaining-delta/terminal heads."""
    result = dict(achieved)
    for suffix, component in LEAF_SUFFIX_TO_COMPONENT.items():
        head = prediction.get(suffix) or {}
        value = (
            0.0 if head.get("oof_inference_eligible") is False
            else head.get("mean")
        )
        prefix = result.get(component)
        result[component] = (
            None if prefix is None or not isinstance(value, (int, float))
            else float(prefix) + float(value)
        )
    completed = (prediction.get("stream_completed") or {}).get("mean")
    result["stream_completed_probability"] = (
        float(completed) if isinstance(completed, (int, float)) else None
    )
    for name in (
        "terminal_stability_max_shift",
        "terminal_stability_peak_kinetic_energy",
        "terminal_stability_items_toppled",
    ):
        value = (prediction.get(name) or {}).get("mean")
        result[name] = float(value) if isinstance(value, (int, float)) else None
    return result


def _merge_terminal_shake(
    final_metrics: dict[str, Any], evaluation: Any,
) -> None:
    if not isinstance(evaluation, dict):
        return
    shake = evaluation.get("shake_response") or {}
    for source, target in (
        ("shake_max_shift", "post_shake_max_shift"),
        ("shake_peak_kinetic_energy", "post_shake_peak_kinetic_energy"),
        ("shake_items_toppled", "post_shake_items_toppled"),
    ):
        if source in shake:
            final_metrics[target] = shake[source]


def _terminal_rollout(
    task_config: dict[str, Any], *, environment_seed: int,
    prefix_actions: list[Any], forced_actions: list[Any], provider,
    legal_filter, top_k: int, root_step: int,
    max_continuation_steps: int,
) -> dict[str, Any]:
    """Force a search path, then follow frozen rank-0 to termination."""
    env = _fresh_env(task_config)
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        executed = []
        for action in prefix_actions:
            observation, _r, terminated, truncated, info = env.step(action)
            if not _safe(_status(info)) or terminated or truncated:
                raise RuntimeError(
                    f"terminal-rollout prefix failed at action {len(executed)}"
                )
            executed.append(action)
        root_metrics = cumulative_metrics(env)
        termination = None
        forced_steps = 0
        for action in forced_actions:
            observation, _r, terminated, truncated, info = env.step(action)
            executed.append(action)
            forced_steps += 1
            if not _safe(_status(info)):
                termination = "forced_action_failure"
                break
            if truncated:
                termination = "simulator_truncated"
                break
            if terminated:
                termination = "stream_exhausted"
                break
        continuation_steps = 0
        continuation_actions = []
        while termination is None:
            if continuation_steps >= max_continuation_steps:
                termination = "continuation_cap"
                break
            proposals = list(provider(env, observation, int(top_k)))
            if not proposals:
                termination = "no_retained_candidate"
                break
            retained, _audit = legal_filter(
                env=env, observation=observation, candidates=proposals,
                actions=list(executed),
                step=root_step + forced_steps + continuation_steps,
                max_safe_candidates=1,
            )
            if not retained:
                termination = "no_safe_retained_candidate"
                break
            action = _candidate_action(retained[0])
            observation, _r, terminated, truncated, info = env.step(action)
            executed.append(action)
            continuation_actions.append(action)
            if not _safe(_status(info)):
                termination = "selected_action_failure"
                break
            continuation_steps += 1
            if truncated:
                termination = "simulator_truncated"
            elif terminated:
                termination = "stream_exhausted"
        genuine = termination in GENUINE_TERMINATIONS
        terminal_metrics = cumulative_metrics(env)
        evaluation = None
        if genuine:
            evaluation = _compact_evaluation(env.evaluate())
            _merge_terminal_shake(terminal_metrics, evaluation)
        return {
            "termination": termination,
            "genuine_terminal": genuine,
            "continuation_steps": continuation_steps,
            "physical_steps": forced_steps + continuation_steps,
            "forced_actions": [json_safe(action) for action in forced_actions],
            "continuation_actions": [
                json_safe(action) for action in continuation_actions
            ],
            "terminal_vector": (
                _component_values(root_metrics, terminal_metrics)
                if genuine else None
            ),
            "terminal_metrics": terminal_metrics,
            "evaluation": evaluation,
        }
    finally:
        env.close()


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
    leaf_eval: str = "measured", rollout_top_k: int = 3,
    rollout_max_steps: int = 40,
    terminal_audit: bool = False,
    allocation: str = "frontier", c_puct: float = 2.0,
    terminal_rollout_fn: Callable[[list[Any]], dict[str, Any]] | None = None,
    leaf_vector_fn: Callable[..., dict[str, Any]] | None = None,
    item_symmetry_cache_shadow: bool = False,
    leaf_state_key_fn: Callable[..., tuple[str, str]] | None = None,
) -> dict[str, Any]:
    if leaf_eval not in {"measured", "rollout", "value"}:
        raise ValueError(f"unsupported leaf evaluator: {leaf_eval}")
    if rollout_top_k < 1:
        raise ValueError("rollout_top_k must be positive")
    if rollout_max_steps < 0:
        raise ValueError("rollout_max_steps must be non-negative")
    if not root_candidates:
        raise ValueError("vector search needs at least one root candidate")
    if terminal_audit and leaf_eval == "rollout":
        raise ValueError("terminal_audit cannot accompany rollout leaf allocation")
    if allocation not in {"frontier", "pareto-puct"}:
        raise ValueError(f"unsupported allocation: {allocation}")
    if c_puct < 0.0:
        raise ValueError("c_puct must be non-negative")
    if leaf_eval == "value" and allocation != "pareto-puct":
        raise ValueError("value shadow requires frozen Pareto-PUCT allocation")
    if leaf_eval == "value" and leaf_vector_fn is None:
        raise ValueError("value leaf evaluation requires leaf_vector_fn")
    if item_symmetry_cache_shadow and leaf_state_key_fn is None:
        def leaf_state_key_fn(*, env, observation, state_step):
            observed = policy_observation(env, observation)
            snapshot = state_snapshot(
                env, observed, case_id=case_id, step=int(state_step),
            )
            return (
                board_fingerprint(snapshot),
                item_symmetry_board_fingerprint(snapshot),
            )
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    if (leaf_eval == "rollout" or terminal_audit) and terminal_rollout_fn is None:
        legal_filter = build_exact_physical_legal_filter(
            task_config, case_id=case_id, environment_seed=environment_seed,
        )

        def terminal_rollout_fn(actions: list[Any]) -> dict[str, Any]:
            return _terminal_rollout(
                task_config, environment_seed=environment_seed,
                prefix_actions=prefix_actions, forced_actions=actions,
                provider=provider, legal_filter=legal_filter,
                top_k=rollout_top_k, root_step=step,
                max_continuation_steps=rollout_max_steps,
            )
    # node: key -> {actions, vector (accumulated), root_candidate_id,
    #               parent, depth, expanded, alive}.  Every node also owns
    # the statistics for its incoming edge.
    nodes: dict[str, dict[str, Any]] = {}
    edge_stats: dict[str, dict[str, Any]] = {}
    children: dict[str | None, list[str]] = {None: []}
    physical_steps = 0
    terminal_rollout_physical_steps = 0
    symmetry_shadow = (
        ItemSymmetryTranspositionShadow()
        if item_symmetry_cache_shadow else None
    )

    def try_action_path(actions, root_candidate_id, *, parent=None, prior=1.0):
        nonlocal physical_steps, terminal_rollout_physical_steps
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
            leaf_exact_fingerprint = None
            leaf_symmetry_fingerprint = None
            if symmetry_shadow is not None:
                leaf_exact_fingerprint, leaf_symmetry_fingerprint = (
                    leaf_state_key_fn(
                        env=env, observation=result["observation"],
                        state_step=step + len(actions),
                    )
                )
            terminal_result = None
            run_terminal = (
                leaf_eval == "rollout"
                or (terminal_audit and len(actions) == 1)
            )
            if run_terminal:
                if terminal_rollout_fn is None:
                    raise RuntimeError("rollout leaf evaluator was not configured")
                terminal_result = terminal_rollout_fn(list(actions))
                terminal_rollout_physical_steps += int(
                    terminal_result.get("physical_steps", 0)
                )
            leaf_prediction = None
            if leaf_eval == "measured":
                evaluation_vector = accumulated
            elif leaf_eval == "rollout":
                evaluation_vector = (
                    terminal_result.get("terminal_vector")
                    if terminal_result
                    and terminal_result.get("genuine_terminal")
                    else None
                )
            elif ended:
                evaluation_vector = accumulated
            else:
                leaf_prediction = leaf_vector_fn(
                    env=env, observation=result["observation"],
                    step=step + len(actions),
                )
                evaluation_vector = compose_leaf_value(
                    accumulated, leaf_prediction
                )
            symmetry_event = None
            if symmetry_shadow is not None:
                value_signature = (
                    stable_id("leaf-value-shadow-v1", json_safe(leaf_prediction))
                    if leaf_prediction is not None else None
                )
                symmetry_event = symmetry_shadow.observe(
                    exact_key=leaf_exact_fingerprint,
                    symmetry_key=leaf_symmetry_fingerprint,
                    value_signature=value_signature,
                )
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
                "evaluation_vector": evaluation_vector,
                "leaf_value_prediction": leaf_prediction,
                "leaf_board_fingerprint": leaf_exact_fingerprint,
                "leaf_item_symmetry_fingerprint": leaf_symmetry_fingerprint,
                "item_symmetry_cache_shadow_event": symmetry_event,
                "root_candidate_id": root_candidate_id,
                "parent": parent,
                "depth": len(actions),
                "ended": ended,
                "continuations": candidates,
                "expanded": False,
                "terminal_genuine": (
                    bool(terminal_result.get("genuine_terminal"))
                    if terminal_result else False
                ),
                "terminal_termination": (
                    terminal_result.get("termination")
                    if terminal_result else None
                ),
                "terminal_continuation_steps": (
                    int(terminal_result.get("continuation_steps", 0))
                    if terminal_result else None
                ),
                "terminal_vector": (
                    terminal_result.get("terminal_vector")
                    if terminal_result else None
                ),
                "terminal_metrics": (
                    terminal_result.get("terminal_metrics")
                    if terminal_result else None
                ),
                "terminal_evaluation": (
                    terminal_result.get("evaluation")
                    if terminal_result else None
                ),
                "terminal_forced_actions": (
                    terminal_result.get("forced_actions")
                    if terminal_result else None
                ),
                "terminal_continuation_actions": (
                    terminal_result.get("continuation_actions")
                    if terminal_result else None
                ),
            }
            edge_stats[key] = _new_edge_stat(prior=prior)
            children.setdefault(parent, []).append(key)
            children.setdefault(key, [])
            if _oriented(evaluation_vector or {}) is not None:
                cursor: str | None = key
                while cursor is not None:
                    _update_edge_stat(edge_stats[cursor], evaluation_vector)
                    cursor = nodes[cursor]["parent"]
            return key
        finally:
            env.close()

    root_rows = []
    root_prior = 1.0 / len(root_candidates)
    for candidate in root_candidates:
        record = _candidate_record(candidate)
        key = try_action_path(
            [_candidate_action(candidate)], record["candidate_id"],
            parent=None, prior=root_prior,
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

    def expandable(key: str) -> bool:
        node = nodes[key]
        if node["ended"]:
            return False
        if not node["expanded"]:
            return bool(node["continuations"])
        return any(expandable(child) for child in children[key])

    def choose_puct(parent: str | None = None) -> str | None:
        active = [key for key in children[parent] if expandable(key)]
        if not active:
            return None
        chosen_edge = _pareto_puct_choice(
            {key: edge_stats[key] for key in active}, c_puct=c_puct
        )
        if not nodes[chosen_edge]["expanded"]:
            return chosen_edge
        return choose_puct(chosen_edge)

    for _expansion in range(expansions):
        if allocation == "frontier":
            frontier_vectors = {
                key: oriented
                for key, node in nodes.items()
                if not node["expanded"] and not node["ended"]
                and node["continuations"]
                and (
                    oriented := _oriented(node.get("evaluation_vector") or {})
                ) is not None
            }
            if not frontier_vectors:
                break
            frontier = pareto_frontier(frontier_vectors)
            chosen = min(
                frontier, key=lambda key: (nodes[key]["depth"], key)
            )
        else:
            chosen = choose_puct()
            if chosen is None:
                break
        node = nodes[chosen]
        node["expanded"] = True
        continuation_prior = 1.0 / len(node["continuations"])
        for action in node["continuations"]:
            try_action_path(
                [*(node["actions"]), action], node["root_candidate_id"],
                parent=chosen, prior=continuation_prior,
            )

    achieved = {
        key: oriented
        for key, node in nodes.items()
        if (
            oriented := _oriented(node.get("evaluation_vector") or {})
        ) is not None
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
            root_node = nodes[row["node"]]
            row["one_step_vector"] = root_node["vector"]
            row["terminal_genuine"] = root_node["terminal_genuine"]
            row["terminal_termination"] = root_node["terminal_termination"]
            row["terminal_vector"] = root_node["terminal_vector"]
            row["terminal_metrics"] = root_node["terminal_metrics"]
            row["terminal_evaluation"] = root_node["terminal_evaluation"]
            row["terminal_continuation_actions"] = root_node[
                "terminal_continuation_actions"
            ]
    audit = build_resurrection_audit(root_rows, nodes)
    for row in root_rows:
        row["frontier_audit"] = audit["candidate_audit"].get(
            str(row["root_candidate_id"]), {}
        )
    root_visit_counts = {
        str(row["root_candidate_id"]): (
            int(edge_stats[row["node"]]["visits"])
            if row.get("node") else 0
        )
        for row in root_rows
    }
    total_root_visits = sum(root_visit_counts.values())
    return {
        "step": int(step),
        "leaf_eval": leaf_eval,
        "terminal_audit": bool(terminal_audit),
        "allocation": allocation,
        "c_puct": c_puct if allocation == "pareto-puct" else None,
        "search_horizon": int(max_depth),
        "root_candidates": root_rows,
        "explored_nodes": len(nodes),
        "physical_steps": physical_steps,
        "terminal_rollout_physical_steps": terminal_rollout_physical_steps,
        "item_symmetry_cache_shadow": (
            symmetry_shadow.summary() if symmetry_shadow is not None else None
        ),
        "global_frontier_size": len(global_frontier),
        "search_pareto_candidates": sorted(frontier_candidates),
        "root_visit_counts": root_visit_counts,
        "root_visit_policy": {
            candidate: (
                visits / total_root_visits if total_root_visits else 0.0
            )
            for candidate, visits in root_visit_counts.items()
        },
        "edge_statistics": edge_stats,
        **audit,
        "nodes": {
            key: {
                field: node[field]
                for field in (
                    "actions", "vector", "root_candidate_id", "depth",
                    "ended", "expanded", "evaluation_vector",
                    "leaf_value_prediction",
                    "leaf_board_fingerprint",
                    "leaf_item_symmetry_fingerprint",
                    "item_symmetry_cache_shadow_event",
                    "terminal_genuine", "terminal_termination",
                    "terminal_continuation_steps", "terminal_vector",
                    "terminal_metrics", "terminal_evaluation",
                    "terminal_forced_actions",
                    "terminal_continuation_actions",
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
    parser.add_argument(
        "--leaf-eval", choices=("measured", "rollout", "value"),
        default="measured",
        help=(
            "Use measured deltas, genuine-terminal rank-0 rollouts, or a "
            "single-agent multi-head suffix V at each reached leaf"
        ),
    )
    parser.add_argument("--rollout-top-k", type=int, default=3)
    parser.add_argument("--rollout-max-steps", type=int, default=40)
    parser.add_argument(
        "--terminal-audit", action="store_true",
        help=(
            "Score every safe root action by genuine-terminal rollout "
            "without exposing that result to measured search allocation"
        ),
    )
    parser.add_argument(
        "--allocation", choices=("frontier", "pareto-puct"),
        default="frontier",
    )
    parser.add_argument("--c-puct", type=float, default=2.0)
    parser.add_argument("--leaf-vector-model-dir", type=pathlib.Path)
    parser.add_argument(
        "--item-symmetry-cache-shadow", action="store_true",
        help=(
            "Measure exact-versus-identical-item leaf cache reuse and value "
            "conflicts without suppressing evaluator calls"
        ),
    )
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
    leaf_adapter = None
    if args.beta_model_dir is not None:
        from scripts.train_feasibility_head import FeasibilityEnsemble

        beta_ensemble = FeasibilityEnsemble(args.beta_model_dir)
    if args.leaf_eval == "value":
        if args.leaf_vector_model_dir is None:
            raise SystemExit("--leaf-eval value requires --leaf-vector-model-dir")
        from scripts.train_self_play_set_value import (
            BehaviorValueEnsemble, SingleAgentLeafVector,
        )

        excluded_group = f"{args.manifest.parent.name}:episode-000"
        leaf_adapter = SingleAgentLeafVector(BehaviorValueEnsemble(
            args.leaf_vector_model_dir, excluded_group=excluded_group,
        ))

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
                leaf_eval=args.leaf_eval,
                rollout_top_k=args.rollout_top_k,
                rollout_max_steps=args.rollout_max_steps,
                terminal_audit=args.terminal_audit,
                allocation=args.allocation,
                c_puct=args.c_puct,
                leaf_vector_fn=leaf_adapter,
                item_symmetry_cache_shadow=args.item_symmetry_cache_shadow,
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
    resurrection_summary = summarize_resurrection_audits(roots)
    schema_version, contract, oracle_contract = _output_contract(
        args.leaf_eval, terminal_audit=args.terminal_audit,
        allocation=args.allocation,
    )
    payload = {
        "schema_version": schema_version,
        "contract": contract,
        "oracle_contract": oracle_contract,
        "case_id": args.case,
        "dominance_heads": {k: v for k, v in DOMINANCE_HEADS.items()},
        "allocation": (
            "pareto_frontier_first_least_depth"
            if args.allocation == "frontier"
            else "pareto_puct_batched_expansion_v1"
        ),
        "allocation_mode": args.allocation,
        "c_puct": args.c_puct if args.allocation == "pareto-puct" else None,
        "backup": "additive_component_vector_sets",
        "leaf_eval": args.leaf_eval,
        "terminal_audit": bool(args.terminal_audit),
        "item_symmetry_cache_shadow_enabled": bool(
            args.item_symmetry_cache_shadow
        ),
        "leaf_vector_model": (
            None if leaf_adapter is None else {
                "semantics": "V^pi_behavior_not_V_star",
                "behavior_contract": "single_agent_v1",
                "excluded_groups": list(
                    leaf_adapter.ensemble.excluded_groups
                ),
                "calls": len(leaf_adapter.calls),
                "active_suffix_heads": sorted(
                    name for name, audit in
                    leaf_adapter.ensemble.head_audit.items()
                    if float((audit.get("ensemble") or {}).get("pearson", 0.0)) > 0.0
                    and float((audit.get("ensemble") or {}).get("rmse", float("inf")))
                    < float((audit.get("constant") or {}).get("rmse", float("inf")))
                ),
            }
        ),
        "terminal_rollout_policy": (
            {
                "policy": "frozen_rank0_exact_physical_filter",
                "top_k": args.rollout_top_k,
                "max_continuation_steps": args.rollout_max_steps,
                "censor_on_cap": True,
            }
            if args.leaf_eval == "rollout" or args.terminal_audit else None
        ),
        "expansions_per_root": args.expansions,
        "max_depth": args.max_depth,
        "beta_model": (
            None if beta_ensemble is None else beta_ensemble.model_id
        ),
        "resurrection_summary": resurrection_summary,
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
    if args.leaf_eval == "rollout" or args.terminal_audit:
        print(
            "terminal resurrection: "
            f"actions={resurrection_summary['terminal_resurrection_actions']} "
            "deepened_recall="
            f"{resurrection_summary['deepened_resurrection_recall']} "
            "measured_frontier_recall="
            f"{resurrection_summary['measured_frontier_resurrection_recall']} "
            "evaluated_frontier_recall="
            f"{resurrection_summary['evaluated_frontier_resurrection_recall']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
