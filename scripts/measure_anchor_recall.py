from __future__ import annotations

import argparse
import contextlib
import copy
import dataclasses
import datetime as dt
import importlib.util
import io
import json
import os
import pathlib
import sys
import time
from typing import Any, Iterable

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "agent" / "agent.py"
SIMULATOR = ROOT / "simulator"
DEFAULT_CONFIG = SIMULATOR / "configs" / "sample_config.json"
DEFAULT_REPORT_ROOT = ROOT / "reports" / "anchor-recall"


def json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def candidate_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(record["item_index"]),
        int(record["pool_index"]),
        int(record["container_index"]),
        int(record["orientation"]),
        tuple(round(float(value), 6) for value in record["center"]),
        tuple(round(float(value), 6) for value in record["size"]),
    )


def unique_candidates(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in records:
        unique.setdefault(candidate_key(record), record)
    return list(unique.values())


def extract_anytime_candidates(
    diagnostics: dict[str, Any],
    *,
    candidate_kind: str = "settled",
) -> list[dict[str, Any]]:
    if candidate_kind not in {"settled", "release"}:
        raise ValueError("candidate_kind must be 'settled' or 'release'")
    audit_key = (
        "accepted_settled"
        if candidate_kind == "settled"
        else "accepted_release"
    )
    records = []
    for search in diagnostics.get("candidate_audit", []):
        records.extend(search.get(audit_key, []))
    return unique_candidates(records)


def policy_search_log(agent_solver) -> dict[str, Any]:
    diagnostics = agent_solver.last_candidate_diagnostics
    settled = extract_anytime_candidates(
        diagnostics,
        candidate_kind="settled",
    )
    release = extract_anytime_candidates(
        diagnostics,
        candidate_kind="release",
    )
    return {
        "action_source": agent_solver.last_action_source,
        "candidate_kind": agent_solver.last_candidate_kind,
        "top_candidate_count": int(agent_solver.last_top_candidate_count),
        "accepted_settled_count": len(settled),
        "accepted_release_count": len(release),
        "accepted_total_count": len(settled) + len(release),
        "search": json_safe(diagnostics.get("search", {})),
    }


def classify_failure_state(
    policy_log: dict[str, Any],
    *,
    settled_physical_safe_count: int,
    release_physical_safe_count: int,
    oracle_complete: bool,
    physics_complete: bool,
) -> str:
    if policy_log.get("action_source") != "fixed_fallback":
        return "action_selected"
    if (
        int(policy_log.get("accepted_settled_count", 0)) > 0
        or int(policy_log.get("accepted_release_count", 0)) > 0
    ):
        return "incumbent_invariant_violation"
    if not oracle_complete or not physics_complete:
        return "incomplete"
    if settled_physical_safe_count > 0:
        return "deadline_missed_safe_settled"
    if release_physical_safe_count > 0:
        return "safe_release_only"
    return "no_safe_candidate_in_oracle_sets"


def summarize_recall(
    oracle_candidates: list[dict[str, Any]],
    anytime_candidates: list[dict[str, Any]],
    physical_results: dict[tuple[Any, ...], dict[str, Any]] | None,
    *,
    oracle_complete: bool,
    physics_complete: bool,
) -> dict[str, Any]:
    oracle_by_key = {
        candidate_key(record): record for record in oracle_candidates
    }
    anytime_by_key = {
        candidate_key(record): record for record in anytime_candidates
    }
    oracle_keys = set(oracle_by_key)
    anytime_keys = set(anytime_by_key)
    matched_keys = oracle_keys & anytime_keys

    geometric_recall = (
        len(matched_keys) / len(oracle_keys) if oracle_keys else None
    )
    summary: dict[str, Any] = {
        "oracle_complete": bool(oracle_complete),
        "physics_complete": bool(physics_complete),
        "oracle_settled_count": len(oracle_keys),
        "anytime_settled_count": len(anytime_keys),
        "anytime_oracle_match_count": len(matched_keys),
        "geometric_recall": geometric_recall,
        "time_to_first_anytime_settled": min(
            (
                float(record["elapsed_seconds"])
                for record in anytime_candidates
                if record.get("elapsed_seconds") is not None
            ),
            default=None,
        ),
        "physical_recall": None,
        "oracle_physical_settled_count": None,
        "anytime_physical_settled_count": None,
        "best_score_regret": None,
        "classification": "incomplete",
    }
    if not oracle_complete or not physics_complete or physical_results is None:
        return summary

    safe_keys = {
        key
        for key, result in physical_results.items()
        if result.get("is_physically_valid") is True
    }
    anytime_safe_keys = safe_keys & anytime_keys
    summary["oracle_physical_settled_count"] = len(safe_keys)
    summary["anytime_physical_settled_count"] = len(anytime_safe_keys)
    if safe_keys:
        summary["physical_recall"] = len(anytime_safe_keys) / len(safe_keys)
        oracle_best = max(
            float(oracle_by_key[key].get("score", -float("inf")))
            for key in safe_keys
        )
        if anytime_safe_keys:
            anytime_best = max(
                float(anytime_by_key[key].get("score", -float("inf")))
                for key in anytime_safe_keys
            )
            summary["best_score_regret"] = oracle_best - anytime_best
            summary["classification"] = (
                "complete_physical_recall"
                if safe_keys <= anytime_keys
                else "anytime_missed_physical_settled"
            )
        else:
            summary["classification"] = (
                "anytime_found_no_physical_settled"
            )
    else:
        summary["classification"] = "oracle_found_no_physical_settled"
    return summary


def summarize_release_recall(
    oracle_candidates: list[dict[str, Any]],
    anytime_candidates: list[dict[str, Any]],
    physical_results: dict[tuple[Any, ...], dict[str, Any]] | None,
    *,
    oracle_complete: bool,
    physics_complete: bool,
) -> dict[str, Any]:
    oracle_keys = {
        candidate_key(record) for record in oracle_candidates
    }
    anytime_keys = {
        candidate_key(record) for record in anytime_candidates
    }
    matched_keys = oracle_keys & anytime_keys
    safe_keys: set[tuple[Any, ...]] = set()
    if physical_results is not None:
        safe_keys = {
            key
            for key, result in physical_results.items()
            if result.get("is_physically_valid") is True
        }
    return {
        "oracle_complete": bool(oracle_complete),
        "physics_complete": bool(physics_complete),
        "oracle_release_count": len(oracle_keys),
        "anytime_release_count": len(anytime_keys),
        "anytime_oracle_match_count": len(matched_keys),
        "oracle_physical_safe_count": (
            len(safe_keys)
            if oracle_complete and physics_complete
            else None
        ),
        "anytime_physical_safe_count": (
            len(safe_keys & anytime_keys)
            if oracle_complete and physics_complete
            else None
        ),
    }


def load_agent_module():
    spec = importlib.util.spec_from_file_location(
        "anchor_recall_agent",
        AGENT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load agent module: {AGENT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def enrich_score(
    agent_module,
    observation: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any]:
    pool_index = int(record["pool_index"])
    container_index = int(record["container_index"])
    item = observation["pool_list"][pool_index]
    container = observation["container_list"][container_index]
    candidate = agent_module.AABB(
        tuple(float(value) for value in record["center"]),
        tuple(float(value) for value in record["size"]),
        str(record.get("kind", "candidate")),
    )
    has_priority_container = any(
        bool(candidate_container.get("is_prioritized", False))
        for candidate_container in observation["container_list"]
    )
    enriched = dict(record)
    enriched["score"] = float(
        agent_module.Ranker.score(
            candidate,
            item,
            container,
            has_priority_container,
        )
    )
    return enriched


def enumerate_oracle_candidates(
    agent_module,
    observation: dict[str, Any],
    *,
    generator_mode: str = "cartesian",
    attempt_kind: str = "settled",
    max_candidates: int | None = None,
) -> tuple[list[dict[str, Any]], bool, dict[str, Any]]:
    if attempt_kind not in {"settled", "release"}:
        raise ValueError("attempt_kind must be 'settled' or 'release'")
    started = time.perf_counter()
    indexed_items = agent_module.online_item_order(
        observation.get("pool_list", [])
    )[: agent_module.MAX_POOL_ITEMS_EVALUATED]
    units = agent_module.prioritized_search_units(
        observation,
        indexed_items,
    )
    records: dict[tuple[Any, ...], dict[str, Any]] = {}
    attempts = 0
    candidate_units = 0
    candidate_units_total = sum(
        1 for candidate_unit in units
        if candidate_unit[-1] == attempt_kind
    )

    def enumeration_stats() -> dict[str, Any]:
        stats = {
            "generator_mode": generator_mode,
            "attempt_kind": attempt_kind,
            "attempts": attempts,
            "candidate_units_started": candidate_units,
            "candidate_units_total": candidate_units_total,
            "elapsed_seconds": time.perf_counter() - started,
        }
        if attempt_kind == "settled":
            stats["settled_units_started"] = candidate_units
            stats["settled_units_total"] = candidate_units_total
        return stats

    for unit in units:
        (
            _item_rank,
            _pose_rank,
            _container_rank,
            _kind_rank,
            item_idx,
            item,
            container_idx,
            orientation,
            unit_attempt_kind,
        ) = unit
        if unit_attempt_kind != attempt_kind:
            continue
        candidate_units += 1
        for candidate in agent_module.CandidateGenerator.iter_attempts(
            observation,
            item,
            container_idx,
            orientation,
            limit=sys.maxsize,
            deadline=None,
            diagnostics=None,
            item_idx=item_idx,
            attempt_kind=attempt_kind,
            generator_mode=generator_mode,
        ):
            attempts += 1
            if candidate is None:
                continue
            record = agent_module.candidate_audit_record(
                item_idx,
                item,
                container_idx,
                orientation,
                candidate,
                observation["container_list"][container_idx],
                elapsed_seconds=time.perf_counter() - started,
            )
            record = enrich_score(agent_module, observation, record)
            records.setdefault(candidate_key(record), record)
            if (
                max_candidates is not None
                and len(records) >= max_candidates
            ):
                return (
                    list(records.values()),
                    False,
                    enumeration_stats(),
                )
    return (
        list(records.values()),
        True,
        enumeration_stats(),
    )


def enumerate_dual_settled_oracle(
    agent_module,
    observation: dict[str, Any],
    *,
    max_candidates: int | None = None,
) -> tuple[list[dict[str, Any]], bool, dict[str, Any]]:
    started = time.perf_counter()
    records_by_mode: dict[str, list[dict[str, Any]]] = {}
    stats_by_mode: dict[str, dict[str, Any]] = {}
    complete_by_mode: dict[str, bool] = {}
    keys_by_mode: dict[str, set[tuple[Any, ...]]] = {}

    for generator_mode in ("cartesian", "support_plane"):
        records, complete, stats = enumerate_oracle_candidates(
            agent_module,
            observation,
            generator_mode=generator_mode,
            attempt_kind="settled",
            max_candidates=max_candidates,
        )
        records_by_mode[generator_mode] = records
        stats_by_mode[generator_mode] = stats
        complete_by_mode[generator_mode] = complete
        keys_by_mode[generator_mode] = {
            candidate_key(record) for record in records
        }

    union_records: dict[tuple[Any, ...], dict[str, Any]] = {}
    provenance: dict[tuple[Any, ...], list[str]] = {}
    for generator_mode, records in records_by_mode.items():
        for record in records:
            key = candidate_key(record)
            union_records.setdefault(key, dict(record))
            provenance.setdefault(key, []).append(generator_mode)
    for key, record in union_records.items():
        record["oracle_generators"] = provenance[key]

    cartesian_keys = keys_by_mode["cartesian"]
    support_plane_keys = keys_by_mode["support_plane"]
    return (
        list(union_records.values()),
        all(complete_by_mode.values()),
        {
            "generator_modes": ["cartesian", "support_plane"],
            "complete_by_generator": complete_by_mode,
            "stats_by_generator": stats_by_mode,
            "generator_counts": {
                mode: len(keys) for mode, keys in keys_by_mode.items()
            },
            "union_count": len(union_records),
            "overlap_count": len(cartesian_keys & support_plane_keys),
            "cartesian_only_count": len(
                cartesian_keys - support_plane_keys
            ),
            "support_plane_only_count": len(
                support_plane_keys - cartesian_keys
            ),
            "elapsed_seconds": time.perf_counter() - started,
        },
    )


def policy_observation(env, observation: dict[str, Any]) -> dict[str, Any]:
    return {
        "depth_map": np.array(env.shm_depth_map, copy=True),
        "optimize": bool(observation.get("optimize", env.optimize)),
        "lookahead_k": int(
            observation.get(
                "lookahead_k",
                env.stream_manager.lookahead_k,
            )
        ),
        "container_list": copy.deepcopy(
            observation.get(
                "container_list",
                env.container_manager.get_item_info_in_containers(),
            )
        ),
        "pool_list": copy.deepcopy(
            observation.get(
                "pool_list",
                env.stream_manager.get_items_of_visible_pool(),
            )
        ),
    }


def physical_snapshot(env) -> list[dict[str, Any]]:
    snapshots = []
    for container in env.container_manager.containers:
        for item in container.packed_items:
            if item.pybullet_id is None:
                continue
            position, quaternion = env.client.getBasePositionAndOrientation(
                item.pybullet_id
            )
            linear_velocity, angular_velocity = env.client.getBaseVelocity(
                item.pybullet_id
            )
            snapshots.append(
                {
                    "container_index": int(container.index),
                    "item_index": int(item.index),
                    "position": [float(value) for value in position],
                    "quaternion": [float(value) for value in quaternion],
                    "linear_velocity": [
                        float(value) for value in linear_velocity
                    ],
                    "angular_velocity": [
                        float(value) for value in angular_velocity
                    ],
                }
            )
    return snapshots


def state_snapshot(
    env,
    observation: dict[str, Any],
    *,
    case_id: str,
    step: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "case_id": str(case_id),
        "step": int(step),
        "coordinate_contract": {
            "candidate_positions": "container-local",
            "packed_item_positions": "world",
            "packed_item_orientations": "observed PyBullet quaternion",
        },
        "observation": json_safe(observation),
        "physics": {
            "packed_items": physical_snapshot(env),
            "validator": json_safe(env.config["validator"]),
            "orientations": json_safe(
                env.config["action"]["orientations"]
            ),
        },
    }


class LivePhysicsOracle:
    def __init__(self, env):
        self.env = env

    @staticmethod
    def _clone_item(item):
        values = {
            field.name: copy.deepcopy(getattr(item, field.name))
            for field in dataclasses.fields(type(item))
        }
        clone = type(item)(**values)
        clone.belongs_to = None
        clone.pos = None
        clone.orn = None
        return clone

    def validate_spawned(
        self,
        record: dict[str, Any],
        probe,
    ) -> dict[str, Any]:
        container_index = int(record["container_index"])
        orientation = int(record["orientation"])
        container = self.env.container_manager.get_container(container_index)
        local_target = np.asarray(
            record["action_center"],
            dtype=np.float64,
        )
        global_target = tuple(
            float(value) for value in container.local_to_global(local_target)
        )
        included = False
        placed_safe = False
        settle_metrics = None
        error = None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                included = self.env.validator.check_inclusion(
                    container,
                    probe,
                    global_target,
                    orientation,
                )
                if included:
                    placed_safe = self.env.validator.place_item(
                        probe,
                        global_target,
                        orientation,
                    )
                    settle_metrics = copy.deepcopy(
                        self.env.validator.last_settle_metrics
                    )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            self.env.validator.last_settle_metrics = None

        result = {
            "is_included": bool(included),
            "is_transport_valid": True,
            "transport_contract": "agent_geometry_prevalidated",
            "is_placed_safe": bool(placed_safe),
            "is_physically_valid": bool(included and placed_safe),
            "settle_metrics": json_safe(settle_metrics),
        }
        if error is not None:
            result["error"] = error
        return result


def validate_candidates(
    env,
    candidates: list[dict[str, Any]],
    *,
    max_candidates: int | None = None,
) -> tuple[dict[tuple[Any, ...], dict[str, Any]], bool, float]:
    started = time.perf_counter()
    validator = LivePhysicsOracle(env)
    results: dict[tuple[Any, ...], dict[str, Any]] = {}
    selected = candidates
    complete = True
    if max_candidates is not None and len(candidates) > max_candidates:
        selected = candidates[:max_candidates]
        complete = False
    base_state = env.client.saveState()
    completed = 0
    try:
        for candidate in selected:
            env.client.restoreState(stateId=base_state)
            pool_index = int(candidate["pool_index"])
            source_item = env.stream_manager.get_item(pool_index)
            if source_item is None:
                results[candidate_key(candidate)] = {
                    "is_included": False,
                    "is_transport_valid": False,
                    "is_placed_safe": False,
                    "is_physically_valid": False,
                    "error": "pool item is unavailable",
                }
                continue
            if int(candidate["item_index"]) != int(source_item.index):
                raise RuntimeError(
                    f"pool item {pool_index} changed during oracle validation"
                )
            probe = validator._clone_item(source_item)
            probe_id = probe.spawn(
                env.client,
                initial_pos=(0.0, 0.0, 5.0),
                initial_orn=(0.0, 0.0, 0.0, 1.0),
            )
            if probe_id is None:
                raise RuntimeError("failed to create physics probe item")
            try:
                results[candidate_key(candidate)] = (
                    validator.validate_spawned(
                        candidate,
                        probe,
                    )
                )
            finally:
                if probe.pybullet_id is not None:
                    probe.remove(client=env.client)
            completed += 1
            if completed % 100 == 0:
                print(
                    f"  physics {completed}/{len(selected)} "
                    f"({time.perf_counter() - started:.1f}s)",
                    flush=True,
                )
    finally:
        env.client.restoreState(stateId=base_state)
        env.client.removeState(base_state)
    return results, complete, time.perf_counter() - started


def write_candidate_jsonl(
    path: pathlib.Path,
    oracle_candidates: list[dict[str, Any]],
    anytime_candidates: list[dict[str, Any]],
    physical_results: dict[tuple[Any, ...], dict[str, Any]] | None,
) -> None:
    anytime_keys = {
        candidate_key(record) for record in anytime_candidates
    }
    with path.open("w", encoding="utf-8") as handle:
        for record in oracle_candidates:
            key = candidate_key(record)
            payload = dict(record)
            payload["found_by_anytime"] = key in anytime_keys
            payload["physical"] = (
                None
                if physical_results is None
                else physical_results.get(key)
            )
            handle.write(
                json.dumps(json_safe(payload), ensure_ascii=False) + "\n"
            )


def run_case(
    agent_module,
    task_config: dict[str, Any],
    *,
    case_id: str,
    target_steps: set[int],
    output_dir: pathlib.Path,
    oracle_limit: int | None,
    physical_limit: int | None,
    skip_physics: bool,
    skip_optimize: bool,
) -> dict[str, Any]:
    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(
        config=task_config,
        verbose=False,
        render_mode=None,
    )
    solver = agent_module.Agent("")
    results = []
    try:
        env.reset_settings()
        init_states = env.get_init_states()
        solver.get_init_states(init_states)
        if env.optimize and not skip_optimize:
            optimized_order = solver.optimize(
                env.get_info_for_optimization()
            )
            if not env.set_item_order(optimized_order):
                raise RuntimeError("agent returned an invalid optimized order")
        env.reset_item_stream()
        raw_observation, _info = env.reset(seed=42)
        terminated = False
        truncated = False
        step = 0
        final_step = max(target_steps)
        while not terminated and not truncated and step <= final_step:
            observation = policy_observation(env, raw_observation)
            snapshot = state_snapshot(
                env,
                observation,
                case_id=case_id,
                step=step,
            )
            policy_started = time.perf_counter()
            action = solver.policy(observation)
            policy_elapsed = time.perf_counter() - policy_started
            if step in target_steps:
                step_label = f"step-{step:03d}"
                snapshot_path = output_dir / f"{step_label}-state.json"
                snapshot_path.write_text(
                    json.dumps(snapshot, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                anytime_candidates = [
                    enrich_score(agent_module, observation, record)
                    for record in extract_anytime_candidates(
                        solver.last_candidate_diagnostics,
                        candidate_kind="settled",
                    )
                ]
                anytime_release_candidates = [
                    enrich_score(agent_module, observation, record)
                    for record in extract_anytime_candidates(
                        solver.last_candidate_diagnostics,
                        candidate_kind="release",
                    )
                ]
                policy_log = policy_search_log(solver)
                print(
                    f"{case_id} step {step}: "
                    f"anytime settled={len(anytime_candidates)} "
                    f"release={len(anytime_release_candidates)} "
                    f"source={policy_log['action_source']}",
                    flush=True,
                )
                (
                    oracle_candidates,
                    oracle_complete,
                    oracle_stats,
                ) = enumerate_dual_settled_oracle(
                    agent_module,
                    observation,
                    max_candidates=oracle_limit,
                )
                (
                    release_oracle_candidates,
                    release_oracle_complete,
                    release_oracle_stats,
                ) = enumerate_oracle_candidates(
                    agent_module,
                    observation,
                    generator_mode="cartesian",
                    attempt_kind="release",
                    max_candidates=oracle_limit,
                )
                print(
                    f"{case_id} step {step}: "
                    f"settled union={len(oracle_candidates)} "
                    f"complete={oracle_complete} "
                    f"elapsed={oracle_stats['elapsed_seconds']:.2f}s",
                    flush=True,
                )
                print(
                    f"{case_id} step {step}: "
                    f"release oracle={len(release_oracle_candidates)} "
                    f"complete={release_oracle_complete} "
                    f"elapsed="
                    f"{release_oracle_stats['elapsed_seconds']:.2f}s",
                    flush=True,
                )
                physical_results = None
                release_physical_results = None
                physics_complete = False
                release_physics_complete = False
                physics_seconds = 0.0
                release_physics_seconds = 0.0
                if not skip_physics:
                    (
                        physical_results,
                        physics_complete,
                        physics_seconds,
                    ) = validate_candidates(
                        env,
                        oracle_candidates,
                        max_candidates=physical_limit,
                    )
                    (
                        release_physical_results,
                        release_physics_complete,
                        release_physics_seconds,
                    ) = validate_candidates(
                        env,
                        release_oracle_candidates,
                        max_candidates=physical_limit,
                    )
                settled_summary = summarize_recall(
                    oracle_candidates,
                    anytime_candidates,
                    physical_results,
                    oracle_complete=oracle_complete,
                    physics_complete=physics_complete,
                )
                release_summary = summarize_release_recall(
                    release_oracle_candidates,
                    anytime_release_candidates,
                    release_physical_results,
                    oracle_complete=release_oracle_complete,
                    physics_complete=release_physics_complete,
                )
                all_oracles_complete = (
                    oracle_complete and release_oracle_complete
                )
                all_physics_complete = (
                    physics_complete and release_physics_complete
                )
                failure_classification = classify_failure_state(
                    policy_log,
                    settled_physical_safe_count=int(
                        settled_summary.get(
                            "oracle_physical_settled_count"
                        )
                        or 0
                    ),
                    release_physical_safe_count=int(
                        release_summary.get(
                            "oracle_physical_safe_count"
                        )
                        or 0
                    ),
                    oracle_complete=all_oracles_complete,
                    physics_complete=all_physics_complete,
                )
                summary = dict(settled_summary)
                summary.update(
                    {
                        "schema_version": 2,
                        "case_id": str(case_id),
                        "step": int(step),
                        "snapshot_path": snapshot_path.name,
                        "settled_candidate_path": (
                            f"{step_label}-settled-candidates.jsonl"
                        ),
                        "release_candidate_path": (
                            f"{step_label}-release-candidates.jsonl"
                        ),
                        "oracle_stats": oracle_stats,
                        "release_oracle": release_summary,
                        "release_oracle_stats": release_oracle_stats,
                        "physics_seconds": physics_seconds,
                        "release_physics_seconds": (
                            release_physics_seconds
                        ),
                        "policy_elapsed_seconds": policy_elapsed,
                        "policy_log": policy_log,
                        "failure_classification": (
                            failure_classification
                        ),
                        "action": json_safe(action),
                    }
                )
                settled_candidate_path = (
                    output_dir
                    / f"{step_label}-settled-candidates.jsonl"
                )
                release_candidate_path = (
                    output_dir
                    / f"{step_label}-release-candidates.jsonl"
                )
                write_candidate_jsonl(
                    settled_candidate_path,
                    oracle_candidates,
                    anytime_candidates,
                    physical_results,
                )
                write_candidate_jsonl(
                    release_candidate_path,
                    release_oracle_candidates,
                    anytime_release_candidates,
                    release_physical_results,
                )
                (output_dir / f"{step_label}-summary.json").write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                results.append(summary)

            (
                raw_observation,
                _reward,
                terminated,
                truncated,
                _info,
            ) = env.step(action)
            step += 1
    finally:
        env.close()
    return {
        "case_id": str(case_id),
        "target_steps": sorted(target_steps),
        "trajectory": (
            "skip_optimize"
            if env.optimize and skip_optimize
            else "competition_equivalent"
        ),
        "steps": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure anytime candidate recall against unlimited Cartesian "
            "and support-plane settled oracles plus a release oracle at "
            "identical pre-action simulator states."
        )
    )
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--case", default="001")
    parser.add_argument(
        "--steps",
        type=int,
        nargs="+",
        default=[0, 1, 2, 3, 4],
    )
    parser.add_argument("--mode", default="weighted")
    parser.add_argument("--output-dir", type=pathlib.Path)
    parser.add_argument("--oracle-limit", type=int)
    parser.add_argument("--physical-limit", type=int)
    parser.add_argument("--skip-physics", action="store_true")
    parser.add_argument("--skip-optimize", action="store_true")
    args = parser.parse_args()

    os.environ["NEDO_CANDIDATE_AUDIT"] = "1"
    os.environ["LOOKAHEAD_SELECTION_MODE"] = str(args.mode)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    case_id = str(args.case)
    if case_id not in config:
        available = ", ".join(config)
        raise SystemExit(
            f"unknown case '{case_id}'; available cases: {available}"
        )
    target_steps = {int(step) for step in args.steps}
    if not target_steps or min(target_steps) < 0:
        raise SystemExit("--steps must contain non-negative integers")

    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or (
        DEFAULT_REPORT_ROOT / f"{run_id}-{case_id}-{args.mode}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    agent_module = load_agent_module()
    payload = {
        "schema_version": 2,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "config": str(args.config.resolve()),
        "mode": str(args.mode),
        "oracle_limit": args.oracle_limit,
        "physical_limit": args.physical_limit,
        "skip_physics": bool(args.skip_physics),
        "skip_optimize": bool(args.skip_optimize),
        "case": run_case(
            agent_module,
            config[case_id],
            case_id=case_id,
            target_steps=target_steps,
            output_dir=output_dir,
            oracle_limit=args.oracle_limit,
            physical_limit=args.physical_limit,
            skip_physics=args.skip_physics,
            skip_optimize=args.skip_optimize,
        ),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
