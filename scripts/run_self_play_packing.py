"""Run the two-player packing game on the unchanged PyBullet simulator."""

from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import pathlib
import random
import sys
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]
SIMULATOR = ROOT / "simulator"
for path in (ROOT, SIMULATOR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

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
    canonical_action,
    capture_replay_contract,
    item_symmetry_action_orbit_key,
    replay_action_prefix,
    stable_id,
    state_tensor_from_snapshot,
)
from scripts.exogenous_world import ExogenousWorld  # noqa: E402
from scripts.self_play_packing_game import (  # noqa: E402
    GameRules,
    GameState,
    apply_attribute_reward,
    apply_terminal_loss,
    advance_after_placement,
    choose_candidate,
)
from scripts.self_play_packing_search import (  # noqa: E402
    PuctTree,
    build_multi_head_branch_sample,
    build_return_targets,
    candidate_id,
    candidate_rank,
    summarize_multi_head_branch_samples,
)


def _candidate_action(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return canonical_action(candidate["command_action"])
    return canonical_action(candidate.command_action)


def _candidate_selection(candidate: Any) -> dict[str, Any]:
    if isinstance(candidate, dict):
        return dict(candidate.get("selection", {}))
    return dict(candidate.selection)


def _candidate_provenance(
    candidate: Any, *, fallback_source: str = "legacy_provider",
) -> dict[str, Any]:
    explicit = (
        candidate.get("proposal_provenance", {})
        if isinstance(candidate, dict)
        else getattr(candidate, "proposal_provenance", {})
    ) or {}
    selection = _candidate_selection(candidate)
    result = {
        "schema_version": 1,
        "source": str(explicit.get("source", fallback_source)),
        "provider": explicit.get("provider", selection.get("provider")),
        "mixture_weight": explicit.get("mixture_weight"),
        "proposal_probability": explicit.get("proposal_probability"),
        "proposal_log_probability": explicit.get("proposal_log_probability"),
        "coverage_seed": explicit.get("coverage_seed"),
        "coverage_sequence_index": explicit.get("coverage_sequence_index"),
        "dedup_multiplicity": explicit.get("dedup_multiplicity", 1),
    }
    # Optional honest-provenance fields (beta contract): carried only
    # when the proposer recorded them.
    for key in (
        "coverage_z_mode", "acceptance_model_id",
        "conditional_resampling_probability", "beta_stage",
    ):
        if key in explicit:
            result[key] = explicit[key]
    return result


def _candidate_record(
    candidate: Any, *, fallback_source: str = "legacy_provider",
) -> dict[str, Any]:
    candidate_id = (
        candidate.get("candidate_id")
        if isinstance(candidate, dict)
        else getattr(candidate, "candidate_id", None)
    )
    return {
        "candidate_id": candidate_id,
        "command_action": _candidate_action(candidate),
        "selection": _candidate_selection(candidate),
        "proposal_provenance": _candidate_provenance(
            candidate, fallback_source=fallback_source,
        ),
    }


def _candidate_set_id(candidates: list[Any]) -> str:
    # This identifies action support, not the policy/proposal distribution that
    # happened to produce it. Provenance and behavior probabilities are stored
    # beside each candidate and may change without changing the support ID.
    actions_by_id = {
        stable_id("candidate-action-v1", action): action
        for action in (_candidate_action(candidate) for candidate in candidates)
    }
    actions = [actions_by_id[key] for key in sorted(actions_by_id)]
    return stable_id("candidate-set-v1", actions)


def _status(info: Any) -> dict[str, Any]:
    return info.get("status", {}) if isinstance(info, dict) else {}


def _safe(status: dict[str, Any]) -> bool:
    return all(status.get(key) is True for key in (
        "is_included", "is_valid", "is_placed_safe"
    ))


def build_exact_physical_legal_filter(
    task_config: dict[str, Any], *, case_id: str, environment_seed: int,
    env_factory: Callable[[], Any] | None = None,
    use_item_symmetry_orbits: bool = True,
) -> Callable[..., tuple[list[Any], dict[str, Any]]]:
    """Retain only proposals accepted by an independently replayed simulator.

    The live environment is never mutated during filtering.  Every proposal is
    tried in a fresh environment reconstructed from the same item order and
    accepted action prefix.  Rejected proposals remain in the returned audit as
    useful negative examples, but cannot be selected by the game policy.
    """
    if env_factory is None:
        from src.ground_handling.env import GroundHandlingEnv

        def env_factory():
            return GroundHandlingEnv(
                config=copy.deepcopy(task_config), verbose=False,
                render_mode=None,
            )

    def legal_filter(
        *, env, observation, candidates, actions, step,
        max_safe_candidates: int | None = None,
    ):
        if max_safe_candidates is not None and max_safe_candidates < 1:
            raise ValueError("max_safe_candidates must be positive when set")
        observed = policy_observation(env, observation)
        expected_snapshot = state_snapshot(
            env, observed, case_id=case_id, step=int(step)
        )
        expected_fingerprint = board_fingerprint(expected_snapshot)
        contract = capture_replay_contract(
            env, actions, seed=environment_seed
        )
        retained = []
        candidate_audits = []
        orbit_results: dict[str, dict[str, Any]] = {}
        physical_checked_count = 0
        physical_rejected_count = 0
        physical_step_equivalents = 0
        symmetry_reused_count = 0
        for candidate in candidates:
            orbit_key = (
                item_symmetry_action_orbit_key(
                    observed, _candidate_action(candidate)
                )
                if use_item_symmetry_orbits else None
            )
            cached = orbit_results.get(orbit_key) if orbit_key else None
            if cached is not None:
                symmetry_reused_count += 1
                is_safe = bool(cached["safe"])
                if is_safe:
                    retained.append(candidate)
                candidate_audits.append({
                    **_candidate_record(candidate),
                    "safe": is_safe,
                    "status": copy.deepcopy(cached["status"]),
                    "terminated": bool(cached["terminated"]),
                    "truncated": bool(cached["truncated"]),
                    "prefix_actions_replayed": 0,
                    "prefix_fingerprint": expected_fingerprint,
                    "physical_check": False,
                    "symmetry_reused": True,
                    "symmetry_orbit_key": orbit_key,
                    "symmetry_representative_candidate_id": cached[
                        "candidate_id"
                    ],
                })
                if (
                    max_safe_candidates is not None
                    and len(retained) >= max_safe_candidates
                ):
                    break
                continue
            preview_env = env_factory()
            try:
                rebuilt = replay_action_prefix(
                    preview_env, contract,
                    expected_fingerprint=expected_fingerprint,
                    expected_snapshot=expected_snapshot,
                    snapshot_factory=lambda current, raw: state_snapshot(
                        current, policy_observation(current, raw),
                        case_id=case_id, step=int(step),
                    ),
                )
                if not rebuilt.matched:
                    raise RuntimeError(
                        "legal-move preview reconstruction failed: "
                        f"{rebuilt.error}; expected={expected_fingerprint}; "
                        f"observed={rebuilt.observed_fingerprint}"
                    )
                _next, _reward, terminated, truncated, info = preview_env.step(
                    _candidate_action(candidate)
                )
                status = _status(info)
                is_safe = _safe(status)
                physical_checked_count += 1
                physical_rejected_count += int(not is_safe)
                physical_step_equivalents += int(
                    rebuilt.actions_replayed
                ) + 1
                if is_safe:
                    retained.append(candidate)
                candidate_record = {
                    **_candidate_record(candidate),
                    "safe": is_safe,
                    "status": status,
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "prefix_actions_replayed": rebuilt.actions_replayed,
                    "prefix_fingerprint": rebuilt.observed_fingerprint,
                    "physical_check": True,
                    "symmetry_reused": False,
                    "symmetry_orbit_key": orbit_key,
                    "symmetry_representative_candidate_id": None,
                }
                candidate_audits.append(candidate_record)
                if orbit_key:
                    orbit_results[orbit_key] = {
                        "candidate_id": candidate_record["candidate_id"],
                        "safe": bool(is_safe),
                        "status": copy.deepcopy(status),
                        "terminated": bool(terminated),
                        "truncated": bool(truncated),
                    }
            finally:
                preview_env.close()
            if (
                max_safe_candidates is not None
                and len(retained) >= max_safe_candidates
            ):
                break
        checked_count = len(candidate_audits)
        return retained, {
            "schema_version": 1,
            "mode": "fresh_pybullet_prefix_replay_item_orbit_v2",
            "step": int(step),
            "proposal_count": len(candidates),
            "checked_count": checked_count,
            "physical_checked_count": physical_checked_count,
            "physical_rejected_count": physical_rejected_count,
            "physical_step_equivalents": physical_step_equivalents,
            "symmetry_reused_count": symmetry_reused_count,
            "unchecked_count": len(candidates) - checked_count,
            "safe_count": len(retained),
            "rejected_count": checked_count - len(retained),
            "max_safe_candidates": max_safe_candidates,
            "candidates": candidate_audits,
        }

    return legal_filter


class BehaviorVectorLeaf:
    """Predict the leaf->terminal multi-head suffix vector at horizon leaves.

    Wraps the frozen V^pi_behavior ensemble. The prediction is recorded on
    the branch sample only — it never enters the scalar backup, the visit
    policy, or the executed action, so search behavior is bit-identical to
    a run without it.
    """

    contract = "V_pi_behavior_leaf_bootstrap_v1"

    def __init__(self, model_dir: pathlib.Path):
        from scripts.train_self_play_set_value import BehaviorValueEnsemble

        self.model_dir = str(model_dir)
        self.ensemble = BehaviorValueEnsemble(pathlib.Path(model_dir))
        self.calls = 0

    def __call__(
        self, *, state_tensor: dict[str, Any], game_state: Any,
    ) -> dict[str, Any]:
        self.calls += 1
        prediction = self.ensemble.predict(state_tensor, game_state)
        return {
            "prediction_contract": self.contract,
            "semantics": "V_pi_behavior_not_V_star",
            "model_dir": self.model_dir,
            "ensemble_size": len(self.ensemble.members),
            "heads": prediction,
        }


def build_physical_puct_search(
    task_config: dict[str, Any], *, case_id: str, environment_seed: int,
    candidate_provider: Callable, legal_filter_fn: Callable,
    provider_zero_rescue_fn: Callable | None = None,
    provider_zero_rescue_limit: int | None = None,
    provider_zero_rescue_safe_limit: int = 1,
    rules: GameRules, top_k: int, simulations: int = 6, horizon: int = 3,
    candidate_audit_limit: int | None = None,
    candidate_rescue_limit: int | None = None,
    cpuct: float = 2.0, prior_mode: str = "uniform",
    prior_temperature: float = 1.0, action_temperature: float = 1.0,
    temperature_drop_step: int | None = None,
    root_dirichlet_alpha: float = 0.0,
    root_dirichlet_epsilon: float = 0.0,
    root_allocation_mode: str = "scalar_puct",
    search_seed: int = 0,
    metrics_fn: Callable[[Any], dict[str, Any]] = cumulative_metrics,
    leaf_value_fn: Callable[..., float] | None = None,
    leaf_vector_fn: Callable[..., dict[str, Any]] | None = None,
    env_factory: Callable[[], Any] | None = None,
) -> Callable[..., tuple[Any, dict[str, Any]]]:
    """Build open-loop PUCT whose transitions are authoritative PyBullet steps."""
    if simulations < 1 or horizon < 1 or top_k < 1:
        raise ValueError("simulations, horizon, and top_k must be positive")
    if candidate_audit_limit is not None and candidate_audit_limit < 1:
        raise ValueError("candidate_audit_limit must be positive when set")
    if candidate_rescue_limit is not None and candidate_rescue_limit <= top_k:
        raise ValueError("candidate_rescue_limit must be greater than top_k")
    if (provider_zero_rescue_fn is None) != (provider_zero_rescue_limit is None):
        raise ValueError(
            "provider-zero rescue function and limit must be configured together"
        )
    if provider_zero_rescue_limit is not None and provider_zero_rescue_limit < 1:
        raise ValueError("provider_zero_rescue_limit must be positive")
    if provider_zero_rescue_safe_limit < 1:
        raise ValueError("provider_zero_rescue_safe_limit must be positive")
    if action_temperature < 0.0:
        raise ValueError("action_temperature must be non-negative")
    if temperature_drop_step is not None and temperature_drop_step < 0:
        raise ValueError("temperature_drop_step must be non-negative")
    if root_dirichlet_alpha < 0.0:
        raise ValueError("root_dirichlet_alpha must be non-negative")
    if not 0.0 <= root_dirichlet_epsilon <= 1.0:
        raise ValueError("root_dirichlet_epsilon must be in [0, 1]")
    if bool(root_dirichlet_alpha) != bool(root_dirichlet_epsilon):
        raise ValueError("Dirichlet alpha and epsilon must both be zero or positive")
    if root_allocation_mode not in {"scalar_puct", "paired_round_robin"}:
        raise ValueError(f"unsupported root allocation mode: {root_allocation_mode}")
    if (
        root_allocation_mode == "paired_round_robin"
        and root_dirichlet_epsilon > 0.0
    ):
        raise ValueError("paired round-robin does not use root Dirichlet noise")
    if env_factory is None:
        from src.ground_handling.env import GroundHandlingEnv

        def env_factory():
            return GroundHandlingEnv(
                config=copy.deepcopy(task_config), verbose=False,
                render_mode=None,
            )

    root_noise_rng = random.Random(search_seed + 1)
    value_scale = max(
        1.0, float(rules.terminal_reward), float(rules.attribute_penalty)
    )
    wider_limit = max(
        (
            limit for limit in (
                candidate_audit_limit, candidate_rescue_limit,
                provider_zero_rescue_limit,
            )
            if limit is not None
        ),
        default=None,
    )

    def search(*, env, observation, candidates, actions, state, step, policy_rng):
        expected_observation = policy_observation(env, observation)
        expected_snapshot = state_snapshot(
            env, expected_observation, case_id=case_id, step=int(step)
        )
        expected_fingerprint = board_fingerprint(expected_snapshot)
        contract = capture_replay_contract(
            env, actions, seed=environment_seed
        )
        tree = PuctTree(
            cpuct=cpuct, prior_mode=prior_mode,
            prior_temperature=prior_temperature,
        )
        root_key = stable_id("puct-root", {
            "board": expected_fingerprint,
            "player": state.current_player,
            "block_length": state.block_length,
        })
        root_candidate_set_id = _candidate_set_id(list(candidates))
        paired_root_candidates = sorted(
            list(candidates), key=lambda candidate: candidate_id(candidate)
        )
        if (
            root_allocation_mode == "paired_round_robin"
            and simulations % len(paired_root_candidates) != 0
        ):
            raise ValueError(
                "paired round-robin simulations must be a multiple of the "
                f"root candidate count ({len(paired_root_candidates)})"
            )
        root_noise = None
        if root_dirichlet_epsilon > 0.0:
            root_noise = tree.add_dirichlet_noise(
                root_key, list(candidates), alpha=root_dirichlet_alpha,
                epsilon=root_dirichlet_epsilon, rng=root_noise_rng,
            )
        candidate_cache: dict[str, list[Any]] = {root_key: list(candidates)}
        candidate_provenance_cache: dict[str, dict[str, dict[str, Any]]] = {
            root_key: {
                candidate_id(candidate): _candidate_provenance(candidate)
                for candidate in candidates
            }
        }
        root_world_replica_counts: collections.Counter[str] = (
            collections.Counter()
        )
        terminal_reasons: collections.Counter[str] = collections.Counter()
        search_prefilter_rejections = 0
        leaf_value_calls = 0
        exhaustion_node_keys: set[str] = set()
        candidate_exhaustion_audits: list[dict[str, Any]] = []
        multi_head_branch_samples: list[dict[str, Any]] = []
        candidate_rescue_summary: collections.Counter[str] = (
            collections.Counter()
        )
        provider_zero_rescue_summary: collections.Counter[str] = (
            collections.Counter()
        )
        exhaustion_shadow_summary: collections.Counter[str] = (
            collections.Counter()
        )

        for _simulation in range(simulations):
            simulation_env = env_factory()
            try:
                rebuilt = replay_action_prefix(
                    simulation_env, contract,
                    expected_fingerprint=expected_fingerprint,
                    expected_snapshot=expected_snapshot,
                    snapshot_factory=lambda current, raw: state_snapshot(
                        current, policy_observation(current, raw),
                        case_id=case_id, step=int(step),
                    ),
                )
                if not rebuilt.matched:
                    raise RuntimeError(
                        "MCTS root reconstruction failed: "
                        f"{rebuilt.error}; expected={expected_fingerprint}; "
                        f"observed={rebuilt.observed_fingerprint}"
                    )
                simulation_observation = rebuilt.observation
                simulation_state = copy.deepcopy(state)
                simulation_actions = list(actions)
                relative_actions: list[dict[str, Any]] = []
                simulation_rewards = [0.0, 0.0]
                search_path: list[tuple[str, str, int]] = []
                path_candidate_provenance: list[dict[str, Any]] = []
                exogenous_world: ExogenousWorld | None = None
                root_metrics = metrics_fn(simulation_env)
                ended = False
                termination = None

                for depth in range(horizon):
                    node_key = root_key if depth == 0 else stable_id(
                        "puct-node", {
                            "root": root_key,
                            "actions": relative_actions,
                            "player": simulation_state.current_player,
                            "block_length": simulation_state.block_length,
                        },
                    )
                    if node_key not in candidate_cache:
                        proposals = list(candidate_provider(
                            simulation_env, simulation_observation, int(top_k)
                        ))
                        legal = proposals
                        audit = {"rejected_count": 0}
                        if proposals:
                            legal, audit = legal_filter_fn(
                                env=simulation_env,
                                observation=simulation_observation,
                                candidates=proposals,
                                actions=list(simulation_actions),
                                step=int(step) + depth,
                            )
                        search_prefilter_rejections += int(
                            audit.get("rejected_count", 0)
                        )
                        candidate_cache[node_key] = list(legal)
                        candidate_provenance_cache[node_key] = {
                            candidate_id(candidate): _candidate_provenance(candidate)
                            for candidate in legal
                        }
                        if (
                            not legal
                            and wider_limit is not None
                            and wider_limit > top_k
                        ):
                            wider_proposals = list(candidate_provider(
                                simulation_env, simulation_observation,
                                int(wider_limit),
                            ))
                            proposal_ids = [
                                candidate_id(candidate)
                                for candidate in proposals
                            ]
                            wider_prefix_ids = [
                                candidate_id(candidate)
                                for candidate in wider_proposals[:len(proposals)]
                            ]
                            prefix_matches = proposal_ids == wider_prefix_ids
                            # When the wider call preserves the Top-K prefix,
                            # the prefix has already been physically rejected.
                            # Filter only newly exposed candidates so shadow
                            # accounting does not replay the same actions twice.
                            audit_proposals = (
                                wider_proposals[len(proposals):]
                                if prefix_matches else wider_proposals
                            )
                            newly_legal = list(audit_proposals)
                            wider_audit = {
                                "proposal_count": len(audit_proposals),
                                "safe_count": len(audit_proposals),
                                "rejected_count": 0,
                            }
                            if audit_proposals:
                                newly_legal, wider_audit = legal_filter_fn(
                                    env=simulation_env,
                                    observation=simulation_observation,
                                    candidates=audit_proposals,
                                    actions=list(simulation_actions),
                                    step=int(step) + depth,
                                )
                                newly_legal = list(newly_legal)
                            wider_legal = (
                                list(legal) + newly_legal
                                if prefix_matches else newly_legal
                            )
                            wider_rejected_count = (
                                int(audit.get("rejected_count", 0))
                                + int(wider_audit.get("rejected_count", 0))
                                if prefix_matches
                                else int(wider_audit.get("rejected_count", 0))
                            )
                            recovered_ids = [
                                candidate_id(candidate)
                                for candidate in wider_legal
                                if candidate_id(candidate) not in {
                                    candidate_id(row) for row in legal
                                }
                            ]
                            rescue_legal = []
                            if candidate_rescue_limit is not None:
                                rescue_ids = {
                                    candidate_id(candidate)
                                    for candidate in wider_proposals[
                                        :int(candidate_rescue_limit)
                                    ]
                                }
                                rescue_legal = [
                                    candidate for candidate in wider_legal
                                    if candidate_id(candidate) in rescue_ids
                                ]
                            provider_zero_proposals = []
                            provider_zero_legal = []
                            provider_zero_audit = {
                                "checked_count": 0,
                                "unchecked_count": 0,
                                "rejected_count": 0,
                            }
                            if (
                                not proposals
                                and not wider_proposals
                                and prefix_matches
                                and provider_zero_rescue_fn is not None
                                and provider_zero_rescue_limit is not None
                            ):
                                provider_zero_rescue_summary[
                                    "attempted_nodes"
                                ] += 1
                                provider_zero_proposals = list(
                                    provider_zero_rescue_fn(
                                        simulation_env,
                                        simulation_observation,
                                        int(provider_zero_rescue_limit),
                                    )
                                )
                                provider_zero_rescue_summary[
                                    "generated_candidates"
                                ] += len(provider_zero_proposals)
                                if provider_zero_proposals:
                                    (
                                        provider_zero_legal,
                                        provider_zero_audit,
                                    ) = legal_filter_fn(
                                        env=simulation_env,
                                        observation=simulation_observation,
                                        candidates=provider_zero_proposals,
                                        actions=list(simulation_actions),
                                        step=int(step) + depth,
                                        max_safe_candidates=(
                                            provider_zero_rescue_safe_limit
                                        ),
                                    )
                                    provider_zero_legal = list(
                                        provider_zero_legal
                                    )
                                provider_zero_rescue_summary[
                                    "physical_checks"
                                ] += int(
                                    provider_zero_audit.get(
                                        "physical_checked_count",
                                        provider_zero_audit.get(
                                            "checked_count",
                                            len(
                                                provider_zero_audit.get(
                                                    "candidates", []
                                                )
                                            ),
                                        ),
                                    )
                                )
                                provider_zero_rescue_summary[
                                    "physical_rejections"
                                ] += int(
                                    provider_zero_audit.get(
                                        "physical_rejected_count",
                                        provider_zero_audit.get(
                                            "rejected_count", 0
                                        ),
                                    )
                                )
                            exhaustion_shadow_summary["audited_nodes"] += 1
                            exhaustion_shadow_summary[
                                "top_k_proposal_empty_nodes"
                                if not proposals
                                else "top_k_all_rejected_nodes"
                            ] += 1
                            if not prefix_matches:
                                exhaustion_shadow_summary[
                                    "prefix_mismatch_nodes"
                                ] += 1
                            if wider_legal and prefix_matches:
                                exhaustion_shadow_summary[
                                    "wider_safe_recovered_nodes"
                                ] += 1
                            elif not wider_proposals:
                                exhaustion_shadow_summary[
                                    "wider_proposal_empty_nodes"
                                ] += 1
                            elif not wider_legal:
                                exhaustion_shadow_summary[
                                    "wider_all_rejected_nodes"
                                ] += 1
                            node_observation = policy_observation(
                                simulation_env, simulation_observation
                            )
                            node_snapshot = state_snapshot(
                                simulation_env, node_observation,
                                case_id=case_id,
                                step=int(step) + depth,
                            )
                            node_replay_contract = capture_replay_contract(
                                simulation_env, simulation_actions,
                                seed=environment_seed,
                            )
                            candidate_exhaustion_audits.append({
                                "root_id": root_key,
                                "node_key": node_key,
                                "depth": int(depth),
                                "relative_action_prefix": list(relative_actions),
                                "absolute_action_prefix": list(simulation_actions),
                                "board_fingerprint": board_fingerprint(
                                    node_snapshot
                                ),
                                "model_visible_state_signature": stable_id(
                                    "model-state",
                                    state_tensor_from_snapshot(node_snapshot),
                                ),
                                "replay_contract": node_replay_contract,
                                "top_k": int(top_k),
                                "audit_limit": (
                                    int(candidate_audit_limit)
                                    if candidate_audit_limit is not None else None
                                ),
                                "wider_limit": int(wider_limit),
                                "candidate_rescue_limit": candidate_rescue_limit,
                                "search_widening_applied": bool(
                                    rescue_legal or provider_zero_legal
                                ),
                                "top_k_proposal_count": len(proposals),
                                "top_k_safe_count": len(legal),
                                "top_k_rejected_count": int(
                                    audit.get("rejected_count", 0)
                                ),
                                "wider_proposal_count": len(wider_proposals),
                                "wider_safe_count": len(wider_legal),
                                "wider_rejected_count": int(
                                    wider_rejected_count
                                ),
                                "prefix_matches": prefix_matches,
                                "recovered_candidate_ids": recovered_ids,
                                "provider_zero_rescue_limit": (
                                    provider_zero_rescue_limit
                                ),
                                "provider_zero_rescue_safe_limit": (
                                    provider_zero_rescue_safe_limit
                                ),
                                "provider_zero_rescue_proposal_count": len(
                                    provider_zero_proposals
                                ),
                                "provider_zero_rescue_safe_count": len(
                                    provider_zero_legal
                                ),
                                "provider_zero_rescue_checked_count": int(
                                    provider_zero_audit.get(
                                        "checked_count", 0
                                    )
                                ),
                                "provider_zero_rescued_candidate_ids": [
                                    candidate_id(candidate)
                                    for candidate in provider_zero_legal
                                ],
                            })
                            if rescue_legal:
                                candidate_cache[node_key] = list(rescue_legal)
                                candidate_provenance_cache[node_key] = {
                                    candidate_id(candidate): _candidate_provenance(
                                        candidate, fallback_source="widening_rescue",
                                    )
                                    for candidate in rescue_legal
                                }
                                candidate_rescue_summary["applied_nodes"] += 1
                                candidate_rescue_summary[
                                    "recovered_candidates"
                                ] += len(rescue_legal)
                                search_prefilter_rejections += int(
                                    wider_audit.get("rejected_count", 0)
                                )
                            elif provider_zero_legal:
                                candidate_cache[node_key] = list(
                                    provider_zero_legal
                                )
                                candidate_provenance_cache[node_key] = {
                                    candidate_id(candidate): _candidate_provenance(
                                        candidate,
                                        fallback_source="provider_zero_rescue",
                                    )
                                    for candidate in provider_zero_legal
                                }
                                provider_zero_rescue_summary[
                                    "applied_nodes"
                                ] += 1
                                provider_zero_rescue_summary[
                                    "recovered_candidates"
                                ] += len(provider_zero_legal)
                                search_prefilter_rejections += int(
                                    provider_zero_audit.get(
                                        "rejected_count", 0
                                    )
                                )
                    node_candidates = candidate_cache[node_key]
                    if not node_candidates:
                        # The provider exposes only a bounded action subset.
                        # Its exhaustion is not proof that the true legal move
                        # set is empty, so censor the unknown continuation at
                        # zero instead of backing up a synthetic +/-50 loss.
                        exhaustion_node_keys.add(node_key)
                        terminal_reasons[
                            "bounded_candidate_exhaustion_censored"
                        ] += 1
                        termination = "bounded_candidate_exhaustion"
                        ended = True
                        break

                    mover = simulation_state.current_player
                    selected = (
                        paired_root_candidates[
                            _simulation % len(paired_root_candidates)
                        ]
                        if depth == 0
                        and root_allocation_mode == "paired_round_robin"
                        else tree.select(
                            node_key, player=mover, candidates=node_candidates
                        )
                    )
                    selected_id = candidate_id(selected)
                    search_path.append((node_key, selected_id, mover))
                    selected_provenance = candidate_provenance_cache[node_key][
                        selected_id
                    ]
                    path_candidate_provenance.append(selected_provenance)
                    if depth == 0:
                        sample_index = int(root_world_replica_counts[selected_id])
                        root_world_replica_counts[selected_id] += 1
                        exogenous_world = ExogenousWorld(
                            base_seed=search_seed,
                            root_id=root_key,
                            sample_index=sample_index,
                            future_stream_id=contract.get("future_stream_id"),
                        )
                    action = _candidate_action(selected)
                    before = metrics_fn(simulation_env)
                    (
                        simulation_observation, _reward, terminated,
                        truncated, info,
                    ) = simulation_env.step(action)
                    simulation_actions.append(action)
                    relative_actions.append(action)
                    status = _status(info)
                    if not _safe(status):
                        raise RuntimeError(
                            "MCTS selected an action rejected by its legal filter: "
                            f"{candidate_id(selected)} status={status}"
                        )
                    after = metrics_fn(simulation_env)
                    apply_attribute_reward(
                        simulation_rewards, mover=mover,
                        before=before, after=after, rules=rules,
                    )
                    if truncated:
                        terminal_reasons["simulator_truncated"] += 1
                        termination = "simulator_truncated"
                        ended = True
                        break
                    if terminated:
                        terminal_reasons["stream_exhausted"] += 1
                        termination = "stream_exhausted"
                        ended = True
                        break
                    if exogenous_world is None:
                        raise RuntimeError("root action did not bind an exogenous world")
                    advance_after_placement(
                        simulation_state, rules,
                        exogenous_world.event_rng(
                            "handoff_after_placement", int(depth)
                        ),
                    )

                normalized = [
                    max(-1.0, min(1.0, value / value_scale))
                    for value in simulation_rewards
                ]
                if not ended:
                    termination = "horizon"
                    leaf_value_calls += 1
                    leaf_value = 0.0 if leaf_value_fn is None else float(
                        leaf_value_fn(
                            env=simulation_env,
                            observation=simulation_observation,
                            state=simulation_state,
                        )
                    )
                    if not -1.0 <= leaf_value <= 1.0:
                        raise ValueError("leaf value must be normalized to [-1, 1]")
                    normalized = [
                        max(-1.0, min(1.0, normalized[0] + leaf_value)),
                        max(-1.0, min(1.0, normalized[1] - leaf_value)),
                    ]
                if not search_path or termination is None:
                    raise RuntimeError("physical rollout produced no root branch target")
                leaf_observation = policy_observation(
                    simulation_env, simulation_observation
                )
                leaf_snapshot = state_snapshot(
                    simulation_env, leaf_observation,
                    case_id=case_id,
                    step=int(step) + len(relative_actions),
                )
                leaf_state = state_tensor_from_snapshot(leaf_snapshot)
                leaf_metrics = metrics_fn(simulation_env)
                if exogenous_world is None:
                    raise RuntimeError("physical branch has no exogenous world")
                heads = build_multi_head_branch_sample(
                    root_metrics=root_metrics,
                    leaf_metrics=leaf_metrics,
                    rewards=simulation_rewards,
                    root_player=search_path[0][2],
                    termination=termination,
                )
                predicted_leaf_value = None
                if leaf_vector_fn is not None:
                    # A leaf->terminal bootstrap only makes sense where the
                    # continuation exists and is unobserved: the horizon cut.
                    # Censored terminations keep None with the reason.
                    if termination == "horizon":
                        predicted_leaf_value = leaf_vector_fn(
                            state_tensor=leaf_state,
                            game_state=simulation_state,
                        )
                    else:
                        predicted_leaf_value = {
                            "skipped_reason": termination,
                        }
                sample = {
                    "schema_version": 2,
                    "joint_outcome_contract_version": 2,
                    "metric_contract_version": "physical_branch_heads_v1",
                    "objective_contract_version": "vector_no_weighted_sum_v1",
                    "contract": (
                        "replayable_bounded_physical_branch_multi_head"
                    ),
                    "target_semantics": (
                        "root_action_bounded_outcome_not_leaf_value"
                    ),
                    "simulation_index": int(_simulation),
                    "root_id": root_key,
                    "candidate_set_id": root_candidate_set_id,
                    "root_candidate_id": search_path[0][1],
                    "root_candidate_provenance": path_candidate_provenance[0],
                    "path_candidate_ids": [row[1] for row in search_path],
                    "path_candidate_provenance": path_candidate_provenance,
                    "exogenous_world_id": exogenous_world.world_id,
                    "exogenous_world_sample_index": int(
                        exogenous_world.sample_index
                    ),
                    "exogenous_world": exogenous_world.identity,
                    "search_allocation": {
                        "reason": (
                            "paired_round_robin_root_scalar_puct_continuation"
                            if root_allocation_mode == "paired_round_robin"
                            else "scalar_puct_traversal"
                        ),
                        "configured_simulations": int(simulations),
                        "configured_horizon": int(horizon),
                        "simulation_index": int(_simulation),
                    },
                    "relative_action_prefix": list(relative_actions),
                    "absolute_action_prefix": list(simulation_actions),
                    "termination": termination,
                    "continuation_censored": termination not in {
                        "horizon", "stream_exhausted"
                    },
                    "leaf_board_fingerprint": board_fingerprint(leaf_snapshot),
                    "leaf_model_visible_state_signature": stable_id(
                        "model-state", leaf_state
                    ),
                    "leaf_state": leaf_state,
                    "root_game_state": {
                        "player_to_move": int(state.current_player),
                        "block_length": int(state.block_length),
                        "handoff_count": int(state.handoff_count),
                        "placements": int(state.placements),
                    },
                    "leaf_game_state": {
                        "player_to_move": int(
                            simulation_state.current_player
                        ),
                        "block_length": int(simulation_state.block_length),
                        "handoff_count": int(simulation_state.handoff_count),
                        "placements": int(simulation_state.placements),
                    },
                    "replay_contract": capture_replay_contract(
                        simulation_env, simulation_actions,
                        seed=environment_seed,
                    ),
                    "root_metrics": root_metrics,
                    "leaf_metrics": leaf_metrics,
                    "heads": heads,
                    "raw_outcome_vector": {
                        name: head.get("value") for name, head in heads.items()
                    },
                    "head_eligibility": {
                        name: bool(head.get("target_eligible"))
                        for name, head in heads.items()
                    },
                    # Predicted leaf->terminal suffix vector, kept strictly
                    # separate from the measured heads above. None when no
                    # leaf model is injected.
                    "predicted_leaf_value": predicted_leaf_value,
                }
                sample["outcome_sample_id"] = stable_id(
                    "joint-outcome-sample-v2", {
                        "root_id": root_key,
                        "candidate_set_id": root_candidate_set_id,
                        "root_candidate_id": search_path[0][1],
                        "exogenous_world_id": exogenous_world.world_id,
                        "path_candidate_ids": sample["path_candidate_ids"],
                        "termination": termination,
                    },
                )
                multi_head_branch_samples.append(sample)
                tree.backup(
                    search_path, normalized,
                    candidates=(
                        list(candidates)
                        if root_allocation_mode == "paired_round_robin" else None
                    ),
                )
            finally:
                simulation_env.close()

        effective_action_temperature = (
            0.0
            if temperature_drop_step is not None
            and int(step) >= temperature_drop_step
            else action_temperature
        )
        candidate_outcome_summaries = tree.policy(root_key)
        if root_allocation_mode == "paired_round_robin":
            chosen = min(
                candidates,
                key=lambda candidate: (
                    int(_candidate_selection(candidate).get("rank", 10**9)),
                    candidate_id(candidate),
                ),
            )
            policy_target = []
        else:
            chosen = tree.choose(
                root_key, list(candidates),
                temperature=effective_action_temperature, rng=policy_rng,
            )
            policy_target = candidate_outcome_summaries
        samples_by_root_candidate: dict[str, list[dict[str, Any]]] = (
            collections.defaultdict(list)
        )
        for sample in multi_head_branch_samples:
            samples_by_root_candidate[sample["root_candidate_id"]].append(sample)
        for row in candidate_outcome_summaries:
            row["multi_head_target"] = summarize_multi_head_branch_samples(
                samples_by_root_candidate.get(row["candidate_id"], [])
            )
        return chosen, {
            "schema_version": 3,
            "algorithm": "open_loop_physical_puct",
            "root_allocation_mode": root_allocation_mode,
            "policy_target_eligible": root_allocation_mode == "scalar_puct",
            "execution_policy": (
                "baseline_rank0_not_search_improvement"
                if root_allocation_mode == "paired_round_robin"
                else "search_visit_policy"
            ),
            "candidate_outcome_summaries": candidate_outcome_summaries,
            "candidate_set_id": root_candidate_set_id,
            "exogenous_world_contract": (
                "semantic_hash_v1_root_candidate_replica_paired"
            ),
            "simulations": int(simulations),
            "horizon": int(horizon),
            "cpuct": float(cpuct),
            "prior_mode": prior_mode,
            "prior_temperature": float(prior_temperature),
            "action_temperature": float(effective_action_temperature),
            "configured_action_temperature": float(action_temperature),
            "temperature_drop_step": temperature_drop_step,
            "root_dirichlet_alpha": float(root_dirichlet_alpha),
            "root_dirichlet_epsilon": float(root_dirichlet_epsilon),
            "root_dirichlet_noise": root_noise,
            "leaf_value_model": (
                "zero_untrained" if leaf_value_fn is None else "injected"
            ),
            "leaf_vector_model": (
                None if leaf_vector_fn is None
                else getattr(
                    leaf_vector_fn, "contract", "injected_leaf_vector"
                )
            ),
            "leaf_value_calls": leaf_value_calls,
            "expanded_nodes": tree.node_count,
            "search_prefilter_rejections": search_prefilter_rejections,
            "bounded_candidate_exhaustion_value": (
                "censored_zero_continuation"
            ),
            "candidate_audit_limit": candidate_audit_limit,
            "candidate_rescue_limit": candidate_rescue_limit,
            "candidate_rescue_summary": {
                key: int(candidate_rescue_summary.get(key, 0))
                for key in ("applied_nodes", "recovered_candidates")
            },
            "provider_zero_rescue_limit": provider_zero_rescue_limit,
            "provider_zero_rescue_safe_limit": (
                provider_zero_rescue_safe_limit
                if provider_zero_rescue_fn is not None else None
            ),
            "provider_zero_rescue_summary": {
                key: int(provider_zero_rescue_summary.get(key, 0))
                for key in (
                    "attempted_nodes",
                    "applied_nodes",
                    "generated_candidates",
                    "recovered_candidates",
                    "physical_checks",
                    "physical_rejections",
                )
            },
            "candidate_exhaustion_unique_nodes": len(exhaustion_node_keys),
            "candidate_exhaustion_shadow_summary": {
                key: int(exhaustion_shadow_summary.get(key, 0))
                for key in (
                    "audited_nodes",
                    "top_k_proposal_empty_nodes",
                    "top_k_all_rejected_nodes",
                    "wider_safe_recovered_nodes",
                    "wider_proposal_empty_nodes",
                    "wider_all_rejected_nodes",
                    "prefix_mismatch_nodes",
                )
            },
            "candidate_exhaustion_audits": candidate_exhaustion_audits,
            "multi_head_branch_samples": multi_head_branch_samples,
            "simulation_terminal_reasons": dict(terminal_reasons),
            "policy_target": policy_target,
            "chosen_candidate_id": candidate_id(chosen),
        }

    return search


def play_game(
    env, initial_observation: Any, candidate_provider: Callable, *,
    rules: GameRules, handoff_rng, policy_rng,
    metrics_fn: Callable[[Any], dict[str, Any]], max_steps: int,
    top_k: int = 3, selection_mode: str = "rank0",
    selection_temperature: float = 1.5, starting_player: int = 0,
    capture_fn: Callable[..., dict[str, Any] | None] | None = None,
    evaluate_fn: Callable[[Any], dict[str, Any]] | None = None,
    legal_filter_fn: Callable[..., tuple[list[Any], dict[str, Any]]] | None = None,
    search_fn: Callable[..., tuple[Any, dict[str, Any]]] | None = None,
    coverage_fn: Callable[..., list[Any]] | None = None,
    coverage_per_step: int = 0,
    paired_candidate_divisor: int | None = None,
) -> dict[str, Any]:
    """Play one game through injected candidate and physics boundaries.

    ``coverage_fn`` unions strategy-free coverage proposals into every
    step's candidate set for *measurement*: they pass the same physical
    filter and enter the searched (and recorded) support, but execution
    and termination stay on the ranked legacy support — a state where no
    legacy candidate survives ends the game even if safe coverage
    actions exist, so trajectories are bit-comparable with pre-union
    runs. ``paired_candidate_divisor`` (the paired simulation count)
    trims unranked coverage candidates so the union size divides it.
    """
    if max_steps < 1 or top_k < 1:
        raise ValueError("max_steps and top_k must be positive")
    state = GameState(current_player=starting_player)
    observation = initial_observation
    rewards = [0.0, 0.0]
    actions: list[dict[str, Any]] = []
    records = []
    captures = []
    completed_blocks = []
    terminal_reason = None
    loser = winner = None
    new_attribute_violations = 0.0
    non_rank0 = 0
    legal_move_audits = []

    for step in range(max_steps):
        mover = state.current_player
        state_capture = None
        if capture_fn is not None:
            state_capture = capture_fn(
                env=env, observation=observation, state=state,
                actions=list(actions), step=step,
            )
            if state_capture is not None:
                state_capture["step"] = int(step)
                state_capture["player_to_move"] = mover
                state_capture["rewards_before"] = list(rewards)
                state_capture["cumulative_metrics_before"] = metrics_fn(env)
                captures.append(state_capture)
        proposals = list(candidate_provider(env, observation, int(top_k)))
        coverage_proposals = (
            list(coverage_fn(env=env, observation=observation, step=step))
            if coverage_fn is not None else []
        )
        all_proposals = proposals + coverage_proposals
        legal_audit = {
            "schema_version": 1,
            "mode": "unfiltered",
            "step": int(step),
            "proposal_count": len(all_proposals),
            "safe_count": len(all_proposals),
            "rejected_count": 0,
            "candidates": [_candidate_record(row) for row in all_proposals],
        }
        candidates = all_proposals
        if all_proposals and legal_filter_fn is not None:
            candidates, legal_audit = legal_filter_fn(
                env=env, observation=observation, candidates=all_proposals,
                actions=list(actions), step=step,
            )
            candidates = list(candidates)
        legal_move_audits.append(legal_audit)
        # Execution and termination live on the ranked legacy support only;
        # coverage candidates are measured, never load-bearing for either.
        legacy_safe = [c for c in candidates if candidate_rank(c) < 10**9]
        if not legacy_safe:
            terminal_reason = (
                "no_safe_retained_candidate" if proposals
                else "no_retained_candidate"
            )
            terminal = apply_terminal_loss(rewards, loser=mover, rules=rules)
            loser, winner = terminal["loser"], terminal["winner"]
            break
        if coverage_fn is not None:
            coverage_safe = [
                c for c in candidates if candidate_rank(c) >= 10**9
            ]
            if coverage_per_step > 0:
                coverage_safe = coverage_safe[:coverage_per_step]
            if paired_candidate_divisor is not None:
                total = len(legacy_safe) + len(coverage_safe)
                while (
                    total > len(legacy_safe)
                    and paired_candidate_divisor % total != 0
                ):
                    total -= 1
                coverage_safe = coverage_safe[:total - len(legacy_safe)]
            candidates = legacy_safe + coverage_safe
        search_record = None
        if search_fn is not None:
            chosen, search_record = search_fn(
                env=env, observation=observation, candidates=candidates,
                actions=list(actions), state=copy.deepcopy(state), step=step,
                policy_rng=policy_rng,
            )
            legal_candidate_ids = {
                candidate_id(candidate) for candidate in candidates
            }
            if candidate_id(chosen) not in legal_candidate_ids:
                raise RuntimeError(
                    "search selected an action outside the bounded legal set: "
                    f"{candidate_id(chosen)}"
                )
        else:
            chosen = choose_candidate(
                candidates, mode=selection_mode,
                temperature=selection_temperature, rng=policy_rng,
            )
        selection = _candidate_selection(chosen)
        selected_candidate = _candidate_record(chosen)
        selected_rank = int(selection.get("rank", 0))
        non_rank0 += int(selected_rank != 0)
        action = _candidate_action(chosen)
        before = metrics_fn(env)
        observation, _reward, terminated, truncated, info = env.step(action)
        actions.append(action)
        status = _status(info)
        record: dict[str, Any] = {
            "step": step,
            "player": mover,
            "block_length_before": state.block_length,
            "proposal_count": len(proposals),
            "candidate_count": len(candidates),
            "candidate_set_id": _candidate_set_id(candidates),
            "candidate_set": [_candidate_record(row) for row in candidates],
            "legal_move_audit": legal_audit,
            "selected_candidate_id": selected_candidate["candidate_id"],
            "selected_rank": selected_rank,
            "selection": selection,
            "action": action,
            "status": status,
            "rewards_before": list(rewards),
        }
        if search_record is not None:
            record["search"] = search_record
        if state_capture is not None:
            record["state_snapshot_path"] = state_capture.get("snapshot_path")
        if not _safe(status):
            # The retained-action abstraction predicted that this move was
            # legal, but the authoritative simulator rejected it. Abort and
            # quarantine the episode; assigning +/- terminal reward here
            # would teach a proposal/retention error as if it were checkmate.
            terminal_reason = "selected_action_failure"
            record["terminal_reward"] = [0.0, 0.0]
            records.append(record)
            break

        after = metrics_fn(env)
        attribute = apply_attribute_reward(
            rewards, mover=mover, before=before, after=after, rules=rules
        )
        new_attribute_violations += float(attribute["new_violations"])
        record["attribute_reward"] = attribute
        if truncated:
            terminal_reason = "simulator_truncated"
            record["handoff"] = False
            records.append(record)
            break
        if terminated:
            # A safe terminating placement means the finite item stream was
            # exhausted. It is coverage completion, not one player's loss.
            state.placements += 1
            state.block_length += 1
            terminal_reason = "stream_exhausted"
            record["handoff"] = False
            records.append(record)
            break

        schedule = advance_after_placement(state, rules, handoff_rng)
        record.update(schedule)
        records.append(record)
        if schedule["completed_block_length"] is not None:
            completed_blocks.append(int(schedule["completed_block_length"]))
    else:
        terminal_reason = "max_steps"

    final_metrics = metrics_fn(env)
    evaluation = evaluate_fn(env) if evaluate_fn is not None else None
    if isinstance(evaluation, dict):
        shake = evaluation.get("shake_response") or {}
        for source, target in (
            ("shake_max_shift", "post_shake_max_shift"),
            (
                "shake_peak_kinetic_energy",
                "post_shake_peak_kinetic_energy",
            ),
            ("shake_items_toppled", "post_shake_items_toppled"),
        ):
            if source in shake:
                final_metrics[target] = shake[source]
    training_eligible = terminal_reason not in {
        "selected_action_failure", "simulator_truncated",
    }
    outcome_target_eligible = terminal_reason in {
        "no_retained_candidate", "no_safe_retained_candidate",
        "stream_exhausted",
    }
    learning_targets = build_return_targets(
        captures, records, final_rewards=rewards,
        value_target_eligible=training_eligible and outcome_target_eligible,
        final_metrics=final_metrics,
        terminal_reason=terminal_reason,
    )
    return {
        "starting_player": starting_player,
        "steps": len(records),
        "placements": state.placements,
        "handoff_count": state.handoff_count,
        "completed_block_lengths": completed_blocks,
        "final_block_length": state.block_length,
        "terminal_reason": terminal_reason,
        "training_eligible": training_eligible,
        "outcome_target_eligible": outcome_target_eligible,
        "loser": loser,
        "winner": winner,
        "rewards": rewards,
        "zero_sum_error": abs(sum(rewards)),
        "new_attribute_violations": new_attribute_violations,
        "non_rank0_action_count": non_rank0,
        "legal_move_audits": legal_move_audits,
        "candidate_proposals": sum(
            int(row.get("proposal_count", 0)) for row in legal_move_audits
        ),
        "legal_candidates": sum(
            int(row.get("safe_count", 0)) for row in legal_move_audits
        ),
        "prefilter_rejections": sum(
            int(row.get("rejected_count", 0)) for row in legal_move_audits
        ),
        "records": records,
        "captures": captures,
        "learning_targets": learning_targets,
        "evaluation": evaluation,
    }


def _compact_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in evaluation.items() if key != "step_metrics"}
    steps = evaluation.get("step_metrics") or []
    if steps:
        result["terminal_step_metrics"] = steps[-1]
    return json_safe(result)


def run_physical_game(
    agent_module, task_config: dict[str, Any], *, case_id: str,
    rules: GameRules, environment_seed: int, handoff_seed: int,
    policy_seed: int, attempt_budget: int, top_k: int, max_steps: int,
    selection_mode: str, selection_temperature: float,
    starting_player: int, policy_generation: str,
    output_dir: pathlib.Path,
    mcts_simulations: int = 6, mcts_horizon: int = 3,
    mcts_cpuct: float = 2.0, mcts_prior: str = "uniform",
    mcts_prior_temperature: float = 1.0,
    mcts_action_temperature: float = 1.0,
    mcts_temperature_drop_step: int | None = None,
    mcts_root_dirichlet_alpha: float = 0.0,
    mcts_root_dirichlet_epsilon: float = 0.0,
    mcts_root_allocation_mode: str = "scalar_puct",
    mcts_leaf_vector_model_dir: pathlib.Path | None = None,
    coverage_per_step: int = 0,
    coverage_sample_budget: int = 0,
    coverage_seed: int | None = None,
) -> dict[str, Any]:
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(
        config=copy.deepcopy(task_config), verbose=False, render_mode=None
    )
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    legal_filter = build_exact_physical_legal_filter(
        task_config, case_id=case_id, environment_seed=environment_seed,
    )
    search_fn = None
    coverage_fn = None
    if coverage_per_step > 0:
        if coverage_sample_budget < coverage_per_step:
            raise ValueError(
                "coverage_sample_budget must cover coverage_per_step"
            )
        if coverage_seed is None:
            raise ValueError("coverage collection needs an explicit seed")
        from scripts.coverage_action_sampler import coverage_candidates

        def coverage_fn(*, env, observation, step):
            return coverage_candidates(
                policy_observation(env, observation),
                coverage_seed=int(coverage_seed) + int(step),
                budget=int(coverage_sample_budget),
                z_mode="volume",
            )

    leaf_vector_fn = None
    if selection_mode == "mcts" and mcts_leaf_vector_model_dir is not None:
        leaf_vector_fn = BehaviorVectorLeaf(mcts_leaf_vector_model_dir)
    if selection_mode == "mcts":
        search_fn = build_physical_puct_search(
            task_config, case_id=case_id,
            environment_seed=environment_seed,
            candidate_provider=provider, legal_filter_fn=legal_filter,
            rules=rules, top_k=top_k, simulations=mcts_simulations,
            horizon=mcts_horizon, cpuct=mcts_cpuct,
            prior_mode=mcts_prior,
            prior_temperature=mcts_prior_temperature,
            action_temperature=mcts_action_temperature,
            temperature_drop_step=mcts_temperature_drop_step,
            root_dirichlet_alpha=mcts_root_dirichlet_alpha,
            root_dirichlet_epsilon=mcts_root_dirichlet_epsilon,
            root_allocation_mode=mcts_root_allocation_mode,
            leaf_vector_fn=leaf_vector_fn,
            search_seed=policy_seed + 20000,
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        env.reset_settings()
        env.reset_item_stream()
        raw_observation, _info = env.reset(seed=environment_seed)
        task_config_signature = stable_id("self-play-task-config", task_config)
        trajectory_id = stable_id("self-play-trajectory", {
            "case_id": case_id,
            "task_config_signature": task_config_signature,
            "environment_seed": environment_seed,
            "handoff_seed": handoff_seed,
            "policy_seed": policy_seed,
            "selection_mode": selection_mode,
            # Included only when coverage union is on so pre-union
            # trajectory ids stay stable.
            **(
                {
                    "coverage_union": {
                        "per_step": int(coverage_per_step),
                        "sample_budget": int(coverage_sample_budget),
                        "seed": int(coverage_seed),
                    },
                }
                if coverage_per_step > 0 else {}
            ),
            "mcts": (
                {
                    "simulations": mcts_simulations,
                    "horizon": mcts_horizon,
                    "cpuct": mcts_cpuct,
                    "prior": mcts_prior,
                    "prior_temperature": mcts_prior_temperature,
                    "action_temperature": mcts_action_temperature,
                    "temperature_drop_step": mcts_temperature_drop_step,
                    "root_dirichlet_alpha": mcts_root_dirichlet_alpha,
                    "root_dirichlet_epsilon": mcts_root_dirichlet_epsilon,
                    "root_allocation_mode": mcts_root_allocation_mode,
                    "leaf_value_model": "zero_untrained",
                    "bounded_candidate_exhaustion_value": (
                        "censored_zero_continuation"
                    ),
                    # Included only when set so existing trajectory ids
                    # stay stable for runs without a leaf vector model.
                    **(
                        {
                            "leaf_vector_model_dir": str(
                                mcts_leaf_vector_model_dir
                            ),
                        }
                        if mcts_leaf_vector_model_dir is not None else {}
                    ),
                }
                if selection_mode == "mcts" else None
            ),
        })

        def capture_fn(*, env, observation, state, actions, step):
            observed = policy_observation(env, observation)
            snapshot = state_snapshot(
                env, observed, case_id=case_id, step=int(step)
            )
            snapshot["snapshot_id"] = (
                f"self-play:{trajectory_id}:step-{step:03d}"
            )
            snapshot["replay_contract"] = capture_replay_contract(
                env, actions, seed=environment_seed
            )
            snapshot["board_fingerprint"] = board_fingerprint(snapshot)
            physical_state = state_tensor_from_snapshot(snapshot)
            snapshot["model_visible_state_signature"] = stable_id(
                "model-state", physical_state
            )
            snapshot["game_state_signature"] = stable_id(
                "self-play-game-state", {
                    "physical_state": physical_state,
                    "player_to_move": state.current_player,
                    "block_length": state.block_length,
                },
            )
            snapshot["self_play_game"] = {
                "trajectory_id": trajectory_id,
                "policy_generation": policy_generation,
                "behavior_source": f"self_play:{selection_mode}",
                "player_to_move": state.current_player,
                "block_length": state.block_length,
                "handoff_count": state.handoff_count,
                "is_handoff_state": bool(
                    state.handoff_count > 0 and state.block_length == 0
                ),
            }
            path = output_dir / f"step-{step:03d}-state.json"
            path.write_text(
                json.dumps(json_safe(snapshot), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return {
                "step": int(step),
                "handoff_count": state.handoff_count,
                "is_handoff_state": snapshot["self_play_game"][
                    "is_handoff_state"
                ],
                "snapshot_path": path.name,
                "board_fingerprint": snapshot["board_fingerprint"],
                "model_visible_state_signature": snapshot[
                    "model_visible_state_signature"
                ],
                "game_state_signature": snapshot["game_state_signature"],
            }

        result = play_game(
            env, raw_observation, provider, rules=rules,
            handoff_rng=random.Random(handoff_seed),
            policy_rng=random.Random(policy_seed),
            metrics_fn=lambda current: cumulative_metrics(current),
            max_steps=max_steps, top_k=top_k,
            selection_mode=selection_mode,
            selection_temperature=selection_temperature,
            starting_player=starting_player, capture_fn=capture_fn,
            evaluate_fn=lambda current: _compact_evaluation(current.evaluate()),
            legal_filter_fn=legal_filter,
            search_fn=search_fn,
            coverage_fn=coverage_fn,
            coverage_per_step=coverage_per_step,
            paired_candidate_divisor=(
                mcts_simulations
                if selection_mode == "mcts"
                and mcts_root_allocation_mode == "paired_round_robin"
                and coverage_fn is not None
                else None
            ),
        )
        result.update({
            "trajectory_id": trajectory_id,
            "environment_seed": environment_seed,
            "handoff_seed": handoff_seed,
            "policy_seed": policy_seed,
            "selection_mode": selection_mode,
            "task_config_signature": task_config_signature,
        })
        return result
    finally:
        env.close()


def _write_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
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
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--game-seed", type=int, default=20260821)
    parser.add_argument("--minimum-block", type=int, default=3)
    parser.add_argument("--handoff-probability", type=float, default=0.6)
    parser.add_argument("--terminal-reward", type=float, default=50.0)
    parser.add_argument("--attribute-penalty", type=float, default=5.0)
    parser.add_argument("--attempt-budget", type=int, default=512)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=18)
    parser.add_argument(
        "--selection-mode", choices=("rank0", "temperature", "mcts"),
        default="rank0",
    )
    parser.add_argument("--selection-temperature", type=float, default=1.5)
    parser.add_argument("--mcts-simulations", type=int, default=6)
    parser.add_argument("--mcts-horizon", type=int, default=3)
    parser.add_argument("--mcts-cpuct", type=float, default=2.0)
    parser.add_argument(
        "--mcts-prior", choices=("uniform", "rank"), default="uniform"
    )
    parser.add_argument("--mcts-prior-temperature", type=float, default=1.0)
    parser.add_argument("--mcts-action-temperature", type=float, default=1.0)
    parser.add_argument(
        "--mcts-temperature-drop-step", type=int, default=-1,
        help="Use greedy root visits from this real step; -1 disables",
    )
    parser.add_argument("--mcts-root-dirichlet-alpha", type=float, default=0.0)
    parser.add_argument("--mcts-root-dirichlet-epsilon", type=float, default=0.0)
    parser.add_argument(
        "--mcts-root-allocation-mode",
        choices=("scalar_puct", "paired_round_robin"),
        default="scalar_puct",
    )
    parser.add_argument(
        "--coverage-candidates-per-step", type=int, default=0,
        help="max safe coverage candidates unioned into each step's "
        "searched support (0 disables the union; execution stays rank-0 "
        "legacy either way)",
    )
    parser.add_argument("--coverage-sample-budget", type=int, default=0)
    parser.add_argument("--coverage-seed", type=int, default=None)
    parser.add_argument(
        "--mcts-leaf-vector-model-dir", type=pathlib.Path, default=None,
        help="frozen V^pi_behavior ensemble directory; when set, horizon "
        "leaves record a predicted leaf->terminal suffix vector on each "
        "branch sample (shadow only: backup and execution are unchanged)",
    )
    parser.add_argument("--policy-generation", default="pi0")
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    if args.episodes < 1:
        raise SystemExit("--episodes must be positive")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    if args.case not in config:
        raise SystemExit(f"unknown case: {args.case}")
    rules = GameRules(
        minimum_block=args.minimum_block,
        handoff_probability=args.handoff_probability,
        terminal_reward=args.terminal_reward,
        attribute_penalty=args.attribute_penalty,
    )
    os.environ["NEDO_CANDIDATE_AUDIT"] = "1"
    agent_module = load_agent_module()
    games = []
    for episode in range(args.episodes):
        game_dir = args.output_dir / f"game-{episode:03d}"
        games.append(run_physical_game(
            agent_module, config[args.case], case_id=args.case, rules=rules,
            environment_seed=args.environment_seed,
            handoff_seed=args.game_seed + episode,
            policy_seed=args.game_seed + 10000 + episode,
            attempt_budget=args.attempt_budget, top_k=args.top_k,
            max_steps=args.max_steps, selection_mode=args.selection_mode,
            selection_temperature=args.selection_temperature,
            starting_player=episode % 2,
            policy_generation=args.policy_generation,
            output_dir=game_dir,
            mcts_simulations=args.mcts_simulations,
            mcts_horizon=args.mcts_horizon,
            mcts_cpuct=args.mcts_cpuct,
            mcts_prior=args.mcts_prior,
            mcts_prior_temperature=args.mcts_prior_temperature,
            mcts_action_temperature=args.mcts_action_temperature,
            mcts_temperature_drop_step=(
                None if args.mcts_temperature_drop_step < 0
                else args.mcts_temperature_drop_step
            ),
            mcts_root_dirichlet_alpha=args.mcts_root_dirichlet_alpha,
            mcts_root_dirichlet_epsilon=args.mcts_root_dirichlet_epsilon,
            mcts_root_allocation_mode=args.mcts_root_allocation_mode,
            mcts_leaf_vector_model_dir=args.mcts_leaf_vector_model_dir,
            coverage_per_step=args.coverage_candidates_per_step,
            coverage_sample_budget=args.coverage_sample_budget,
            coverage_seed=args.coverage_seed,
        ))
    manifest = {
        "schema_version": 1,
        "experiment": "self-play packing game",
        "case_id": args.case,
        "policy_generation": args.policy_generation,
        "rules": {
            "minimum_block": rules.minimum_block,
            "handoff_probability": rules.handoff_probability,
            "terminal_reward": rules.terminal_reward,
            "attribute_penalty": rules.attribute_penalty,
        },
        "candidate_contract": {
            "provider": "placement_core_item_stratified_fixed_attempts",
            "attempt_budget": args.attempt_budget,
            "top_k": args.top_k,
            "legal_filter": "fresh_pybullet_prefix_replay",
            "legal_definition": (
                "all status flags true: is_included, is_valid, is_placed_safe"
            ),
            "rejected_proposals_retained_for_audit": True,
            "soft_priority": "dense_zero_sum_penalty_not_hard_filter",
            "coverage_union": (
                {
                    "z_mode": "volume",
                    "candidates_per_step": args.coverage_candidates_per_step,
                    "sample_budget": args.coverage_sample_budget,
                    "seed": args.coverage_seed,
                    "execution_and_termination": "legacy_rank0_only",
                }
                if args.coverage_candidates_per_step > 0 else None
            ),
        },
        "selection": {
            "mode": args.selection_mode,
            "temperature": args.selection_temperature,
            "shared_between_players": True,
            "mcts": (
                {
                    "simulations": args.mcts_simulations,
                    "horizon": args.mcts_horizon,
                    "cpuct": args.mcts_cpuct,
                    "prior": args.mcts_prior,
                    "prior_temperature": args.mcts_prior_temperature,
                    "action_temperature": args.mcts_action_temperature,
                    "temperature_drop_step": (
                        None if args.mcts_temperature_drop_step < 0
                        else args.mcts_temperature_drop_step
                    ),
                    "root_dirichlet_alpha": args.mcts_root_dirichlet_alpha,
                    "root_dirichlet_epsilon": args.mcts_root_dirichlet_epsilon,
                    "root_allocation_mode": args.mcts_root_allocation_mode,
                    "leaf_value_model": "zero_untrained",
                    "leaf_vector_model_dir": (
                        None if args.mcts_leaf_vector_model_dir is None
                        else str(args.mcts_leaf_vector_model_dir)
                    ),
                    "bounded_candidate_exhaustion_value": (
                        "censored_zero_continuation"
                    ),
                }
                if args.selection_mode == "mcts" else None
            ),
        },
        "games": games,
    }
    path = args.output_dir / "manifest.json"
    _write_json(path, manifest)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
