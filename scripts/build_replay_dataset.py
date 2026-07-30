"""
Stratified counterfactual replay dataset.

At a target step the policy is asked for its action as usual, the full
candidate population is enumerated from the *same* simulator state, a
stratified sample of that population is replayed through the official
validator, and every sampled candidate is written out with both sides of
the join:

    (s, a, Phi, Q, selected)  x  (x_plus, delta_theta, d_xy, d_z, Y)

Sampling is deliberately unequal-probability: without stratifying on the
gate verdict the top of the ranking contains almost no rejected
candidates, so the rejected cells stay unestimable. Every row therefore
carries its stratum and its inclusion probability, so a consumer can
re-weight (Horvitz-Thompson) back to the population instead of reading
the sample as if it were the population.

The trajectory itself stays competition-equivalent: each candidate replay
is bracketed by save/restore, and the step is finally advanced with the
action the policy actually returned.
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import copy
import datetime as dt
import io
import json
import math
import os
import pathlib
import random
import sys
import time
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measure_anchor_recall import (  # noqa: E402
    DEFAULT_CONFIG,
    SIMULATOR,
    LivePhysicsOracle,
    candidate_key,
    enumerate_dual_settled_oracle,
    enumerate_oracle_candidates,
    extract_anytime_candidates,
    json_safe,
    load_agent_module,
    policy_observation,
    policy_search_log,
    state_snapshot,
)
from scripts.summarize_task_b import (  # noqa: E402
    separated_physical_labels,
)

SCHEMA_VERSION = 1
DEFAULT_REPORT_ROOT = ROOT / "reports" / "replay-dataset"
ACTION_MATCH_TOLERANCE = 1e-4


# --------------------------------------------------------------------------
# strata
# --------------------------------------------------------------------------
def score_band(rank: int, population: int) -> str:
    """Coarse position in the ranking the policy would have seen."""
    if rank == 0:
        return "top1"
    if rank < 10:
        return "top10"
    if population > 0 and rank < math.ceil(0.1 * population):
        return "top10pct"
    return "tail"


def gate_verdict(record: dict[str, Any]) -> str:
    risk = record.get("release_risk")
    if not isinstance(risk, dict):
        # Settled candidates never reach the release risk gate.
        return "not_applicable"
    return "pass" if risk.get("passed") else "reject"


def assign_strata(records: list[dict[str, Any]]) -> None:
    """
    Attach a stratum to every candidate, in place.

    Ranking is computed per kind because settled and release candidates
    are drawn from different populations even though both are scored by
    the same ranker.
    """
    by_kind: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        by_kind[str(record.get("kind", "candidate"))].append(record)

    for kind, group in by_kind.items():
        group.sort(key=lambda item: -float(item.get("score", 0.0)))
        population = len(group)
        for rank, record in enumerate(group):
            stratum = {
                "kind": kind,
                "gate": gate_verdict(record),
                "score_band": score_band(rank, population),
            }
            record["score_rank"] = rank
            record["score_population"] = population
            record["stratum"] = stratum
            record["stratum_key"] = "|".join(
                f"{name}={stratum[name]}"
                for name in ("kind", "gate", "score_band")
            )


def stratified_sample(
    records: list[dict[str, Any]],
    *,
    per_stratum: int,
    rng: random.Random,
    forced_keys: set[tuple[Any, ...]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Draw up to ``per_stratum`` candidates from each stratum.

    Forced candidates (the action the policy actually selected) are always
    included with probability 1.0; the remainder of their stratum is then
    sampled from what is left, so the design stays a valid
    unequal-probability sample rather than a biased top-up.

    Returns the sampled records and a per-stratum table.
    """
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        groups[record["stratum_key"]].append(record)

    sampled: list[dict[str, Any]] = []
    table: list[dict[str, Any]] = []
    for stratum_key in sorted(groups):
        group = groups[stratum_key]
        forced = [
            record
            for record in group
            if candidate_key(record) in forced_keys
        ]
        rest = [
            record
            for record in group
            if candidate_key(record) not in forced_keys
        ]
        quota = max(0, per_stratum - len(forced))
        take = min(quota, len(rest))
        drawn = rng.sample(rest, take) if take else []
        probability = (take / len(rest)) if rest else 0.0

        for record in forced:
            record["sampling"] = {
                "stratum_key": stratum_key,
                "stratum_size": len(group),
                "stratum_sampled": len(forced) + take,
                "inclusion_probability": 1.0,
                "sampling_weight": 1.0,
                "forced": True,
                "forced_reason": "selected_action",
            }
        for record in drawn:
            record["sampling"] = {
                "stratum_key": stratum_key,
                "stratum_size": len(group),
                "stratum_sampled": len(forced) + take,
                "inclusion_probability": probability,
                "sampling_weight": (
                    1.0 / probability if probability > 0.0 else None
                ),
                "forced": False,
                "forced_reason": None,
            }
        sampled.extend(forced)
        sampled.extend(drawn)
        table.append(
            {
                "stratum_key": stratum_key,
                "stratum": group[0]["stratum"],
                "population": len(group),
                "forced": len(forced),
                "sampled": len(forced) + take,
                # Probability for the non-forced members only. None when the
                # stratum held nothing but forced rows, so a reader never
                # mistakes "no draw was needed" for "drawn with probability 0".
                "inclusion_probability": probability if rest else None,
            }
        )
    return sampled, table


# --------------------------------------------------------------------------
# counterfactual replay
# --------------------------------------------------------------------------
class CounterfactualReplay:
    """
    Run one candidate through the official validator from a restored state.

    The call order mirrors ``GroundHandlingEnv.step`` exactly -- inclusion,
    then the official transport sweep, then release and settle -- so the
    labels are the same three flags the competition scores against. The
    anchor-recall oracle deliberately skips the transport sweep; this one
    does not, because ``is_valid`` is one of the labels being collected.
    """

    def __init__(self, env):
        self.env = env

    def run(self, record: dict[str, Any], probe) -> dict[str, Any]:
        container_index = int(record["container_index"])
        orientation = int(record["orientation"])
        container = self.env.container_manager.get_container(container_index)
        global_target = tuple(
            float(value)
            for value in container.local_to_global(
                np.asarray(record["action_center"], dtype=np.float64)
            )
        )

        included = False
        transport_valid = False
        placed_safe = False
        settle_metrics = None
        error = None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                included = bool(
                    self.env.validator.check_inclusion(
                        container, probe, global_target, orientation
                    )
                )
                if included:
                    transport_valid = bool(
                        self.env.validator.check_transport_path(
                            container, probe, global_target, orientation
                        )
                    )
                if transport_valid:
                    placed_safe = bool(
                        self.env.validator.place_item(
                            probe, global_target, orientation
                        )
                    )
                    settle_metrics = copy.deepcopy(
                        self.env.validator.last_settle_metrics
                    )
        except Exception as exc:  # pragma: no cover - defensive
            error = f"{type(exc).__name__}: {exc}"
        finally:
            self.env.validator.last_settle_metrics = None

        result = {
            "is_included": included,
            "is_valid": transport_valid,
            "is_placed_safe": placed_safe,
            "transport_contract": "official_check_transport_path",
            "settle_metrics": json_safe(settle_metrics),
        }
        result.update(outcome_labels(result))
        if error is not None:
            result["error"] = error
        return result


def outcome_labels(result: dict[str, Any]) -> dict[str, Any]:
    """
    Split one replay result into the regression targets and the labels.

    Label definitions are imported from the Task B summary rather than
    restated, so the dataset and the benchmark can never drift apart.
    """
    settle = result.get("settle_metrics")
    settle = settle if isinstance(settle, dict) else {}
    metric = dict(settle)
    metric["status"] = {
        "is_included": result.get("is_included"),
        "is_valid": result.get("is_valid"),
        "is_placed_safe": result.get("is_placed_safe"),
    }
    labels = separated_physical_labels(metric)
    return {
        "x_plus": {
            "position": settle.get("settle_final_position"),
            "quaternion": settle.get("settle_final_quaternion"),
            "aabb_dimensions": settle.get("settle_aabb_dimensions"),
        },
        "delta_theta_deg": labels["settle_angle_deg"],
        "d_xy": labels["settle_displacement_xy"],
        "d_z": labels["settle_displacement_z"],
        "d_norm": labels["settle_displacement_norm"],
        "footprint": labels["settle_footprint"],
        "settled": bool(settle),
        "Y": {
            name: labels[name]
            for name in (
                "rotated_over_30",
                "displaced_over_half_footprint",
                "horizontal_displaced_over_half_footprint",
                "not_placed_safe",
                "not_valid",
                "not_included",
                "physically_dangerous",
            )
        },
    }


def replay_sample(
    env,
    sample: list[dict[str, Any]],
) -> tuple[dict[tuple[Any, ...], dict[str, Any]], float]:
    started = time.perf_counter()
    replay = CounterfactualReplay(env)
    results: dict[tuple[Any, ...], dict[str, Any]] = {}
    base_state = env.client.saveState()
    try:
        for index, record in enumerate(sample, start=1):
            env.client.restoreState(stateId=base_state)
            pool_index = int(record["pool_index"])
            source_item = env.stream_manager.get_item(pool_index)
            if source_item is None:
                results[candidate_key(record)] = {
                    "is_included": False,
                    "is_valid": False,
                    "is_placed_safe": False,
                    "error": "pool item is unavailable",
                }
                continue
            if int(record["item_index"]) != int(source_item.index):
                raise RuntimeError(
                    f"pool item {pool_index} changed during replay"
                )
            probe = LivePhysicsOracle._clone_item(source_item)
            try:
                results[candidate_key(record)] = replay.run(record, probe)
            finally:
                if probe.pybullet_id is not None:
                    probe.remove(client=env.client)
            if index % 25 == 0:
                print(
                    f"  replay {index}/{len(sample)} "
                    f"({time.perf_counter() - started:.1f}s)",
                    flush=True,
                )
    finally:
        env.client.restoreState(stateId=base_state)
        env.client.removeState(base_state)
    return results, time.perf_counter() - started


# --------------------------------------------------------------------------
# selection / preview value
# --------------------------------------------------------------------------
def match_selected(
    action: dict[str, Any],
    records: list[dict[str, Any]],
) -> tuple[Any, ...] | None:
    if not isinstance(action, dict):
        return None
    try:
        pool_index = int(action["item_idx"])
        container_index = int(action["container_idx"])
        orientation = int(action["orientation"])
        target = np.asarray(action["place_pos"], dtype=np.float64)
    except (KeyError, TypeError, ValueError):
        return None
    best = None
    best_distance = ACTION_MATCH_TOLERANCE
    for record in records:
        if (
            int(record["pool_index"]) != pool_index
            or int(record["container_index"]) != container_index
            or int(record["orientation"]) != orientation
        ):
            continue
        distance = float(
            np.linalg.norm(
                np.asarray(record["action_center"], dtype=np.float64) - target
            )
        )
        if distance <= best_distance:
            best_distance = distance
            best = record
    return None if best is None else candidate_key(best)


def preview_value(
    agent_module,
    observation: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Recompute the preview term the weighted/depth2 modes add on top of the
    immediate score, for one candidate. Off by default: it costs a full
    visible-pool feasibility scan per candidate.
    """
    pool_list = observation.get("pool_list", [])
    pool_index = int(record["pool_index"])
    if not (0 <= pool_index < len(pool_list)):
        return None
    candidate = agent_module.AABB(
        tuple(float(value) for value in record["center"]),
        tuple(float(value) for value in record["size"]),
        str(record.get("kind", "candidate")),
    )
    container_index = int(record["container_index"])
    sim_containers = copy.deepcopy(observation.get("container_list", []))
    decision = agent_module.PlacementDecision(
        action={
            "item_idx": pool_index,
            "container_idx": container_index,
            "place_pos": np.asarray(
                record["action_center"], dtype=np.float32
            ),
            "orientation": int(record["orientation"]),
        },
        candidate=candidate,
        score=float(record.get("score", 0.0)),
    )
    agent_module.apply_placement_decision(
        pool_list[pool_index], decision, sim_containers
    )
    indexed_items = agent_module.online_item_order(pool_list)[
        : agent_module.LOOKAHEAD_INNER_ITEMS
    ]
    remaining = [
        (index, item)
        for index, item in indexed_items
        if index != pool_index
    ]
    if not remaining:
        return {
            "feasible_next_items": 0,
            "total_next_items": 0,
            "best_next_score": 0.0,
        }
    feasibility = agent_module.evaluate_visible_pool_feasibility(
        {"pool_list": pool_list, "container_list": sim_containers},
        remaining,
    )
    if feasibility is None:
        return None
    return {
        "feasible_next_items": int(feasibility.feasible_items),
        "total_next_items": len(remaining),
        "best_next_score": float(feasibility.best_score),
    }


# --------------------------------------------------------------------------
# rows
# --------------------------------------------------------------------------
def build_row(
    record: dict[str, Any],
    *,
    case_id: str,
    step: int,
    snapshot_name: str,
    selected_key: tuple[Any, ...] | None,
    anytime_keys: set[tuple[Any, ...]],
    physical: dict[str, Any] | None,
) -> dict[str, Any]:
    key = candidate_key(record)
    risk = record.get("release_risk")
    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": str(case_id),
        "step": int(step),
        # s
        "snapshot_path": snapshot_name,
        # a
        "candidate_id": "|".join(str(part) for part in key),
        "pool_index": int(record["pool_index"]),
        "item_index": int(record["item_index"]),
        "container_index": int(record["container_index"]),
        "orientation": int(record["orientation"]),
        "kind": str(record.get("kind", "candidate")),
        "center": record["center"],
        "size": record["size"],
        "action_center": record["action_center"],
        # Phi
        "phi": (risk or {}).get("features"),
        "gate_passed": (risk or {}).get("passed"),
        "gate_reasons": (risk or {}).get("reasons"),
        # Q
        "score_immediate": float(record.get("score", 0.0)),
        "score_rank": int(record.get("score_rank", -1)),
        "score_population": int(record.get("score_population", 0)),
        "preview": record.get("preview"),
        # selected
        "selected": key == selected_key,
        "found_by_anytime": key in anytime_keys,
        # sampling design
        "stratum": record["stratum"],
        "sampling": record["sampling"],
        # labels
        "physical": physical,
    }


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def run_case(
    agent_module,
    task_config: dict[str, Any],
    *,
    case_id: str,
    target_steps: set[int],
    output_dir: pathlib.Path,
    per_stratum: int,
    seed: int,
    oracle_limit: int | None,
    preview_limit: int,
    skip_optimize: bool,
) -> dict[str, Any]:
    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(config=task_config, verbose=False, render_mode=None)
    solver = agent_module.Agent("")
    steps: list[dict[str, Any]] = []
    try:
        env.reset_settings()
        init_states = env.get_init_states()
        solver.get_init_states(init_states)
        if env.optimize and not skip_optimize:
            optimized_order = solver.optimize(env.get_info_for_optimization())
            if not env.set_item_order(optimized_order):
                raise RuntimeError("agent returned an invalid optimized order")
        env.reset_item_stream()
        raw_observation, _info = env.reset(seed=42)
        terminated = False
        truncated = False
        last_info: dict[str, Any] | None = None
        step = 0
        final_step = max(target_steps)
        while not terminated and not truncated and step <= final_step:
            observation = policy_observation(env, raw_observation)
            action = solver.policy(observation)
            if step in target_steps:
                steps.append(
                    collect_step(
                        agent_module,
                        env,
                        solver,
                        observation,
                        action,
                        case_id=case_id,
                        step=step,
                        output_dir=output_dir,
                        per_stratum=per_stratum,
                        seed=seed,
                        oracle_limit=oracle_limit,
                        preview_limit=preview_limit,
                    )
                )
            (
                raw_observation,
                _reward,
                terminated,
                truncated,
                info,
            ) = env.step(action)
            last_info = info
            step += 1
    finally:
        env.close()
    reached = {int(entry["step"]) for entry in steps}
    unreached = sorted(target_steps - reached)
    if unreached:
        # An empty dataset must never look like a successful empty run.
        print(
            f"{case_id}: episode ended at step {step} before reaching "
            f"{unreached}; no candidates were sampled for those steps",
            flush=True,
        )
    return {
        "case_id": str(case_id),
        "target_steps": sorted(target_steps),
        "reached_steps": sorted(reached),
        "unreached_steps": unreached,
        "episode_steps_executed": step,
        "episode_terminated": bool(terminated),
        "episode_truncated": bool(truncated),
        "final_status": json_safe((last_info or {}).get("status")),
        "trajectory": (
            "skip_optimize"
            if env.optimize and skip_optimize
            else "competition_equivalent"
        ),
        "steps": steps,
    }


def collect_step(
    agent_module,
    env,
    solver,
    observation: dict[str, Any],
    action: dict[str, Any],
    *,
    case_id: str,
    step: int,
    output_dir: pathlib.Path,
    per_stratum: int,
    seed: int,
    oracle_limit: int | None,
    preview_limit: int,
) -> dict[str, Any]:
    step_label = f"step-{step:03d}"
    snapshot_path = output_dir / f"{step_label}-state.json"
    snapshot_path.write_text(
        json.dumps(
            state_snapshot(env, observation, case_id=case_id, step=step),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    settled, settled_complete, settled_stats = enumerate_dual_settled_oracle(
        agent_module, observation, max_candidates=oracle_limit
    )
    release, release_complete, release_stats = enumerate_oracle_candidates(
        agent_module,
        observation,
        generator_mode="cartesian",
        attempt_kind="release",
        max_candidates=oracle_limit,
    )
    population = settled + release
    assign_strata(population)

    anytime_keys = {
        candidate_key(record)
        for kind in ("settled", "release")
        for record in extract_anytime_candidates(
            solver.last_candidate_diagnostics, candidate_kind=kind
        )
    }
    selected_key = match_selected(action, population)

    rng = random.Random(f"{seed}:{case_id}:{step}")
    sample, stratum_table = stratified_sample(
        population,
        per_stratum=per_stratum,
        rng=rng,
        forced_keys={selected_key} if selected_key is not None else set(),
    )
    print(
        f"{case_id} step {step}: population={len(population)} "
        f"strata={len(stratum_table)} sample={len(sample)} "
        f"selected_matched={selected_key is not None}",
        flush=True,
    )

    preview_started = time.perf_counter()
    for record in sorted(
        sample, key=lambda item: int(item.get("score_rank", 0))
    )[: max(0, preview_limit)]:
        record["preview"] = preview_value(agent_module, observation, record)
    preview_seconds = time.perf_counter() - preview_started

    results, replay_seconds = replay_sample(env, sample)

    dataset_path = output_dir / f"{step_label}-candidates.jsonl"
    with dataset_path.open("w", encoding="utf-8") as handle:
        for record in sample:
            row = build_row(
                record,
                case_id=case_id,
                step=step,
                snapshot_name=snapshot_path.name,
                selected_key=selected_key,
                anytime_keys=anytime_keys,
                physical=results.get(candidate_key(record)),
            )
            handle.write(
                json.dumps(json_safe(row), ensure_ascii=False) + "\n"
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "case_id": str(case_id),
        "step": int(step),
        "snapshot_path": snapshot_path.name,
        "dataset_path": dataset_path.name,
        "population": {
            "settled": len(settled),
            "release": len(release),
            "total": len(population),
            "settled_complete": bool(settled_complete),
            "release_complete": bool(release_complete),
        },
        "sampling": {
            "design": "stratified without replacement, unequal probability",
            "per_stratum": int(per_stratum),
            "seed": int(seed),
            "sampled": len(sample),
            "selected_matched": selected_key is not None,
            "strata": stratum_table,
        },
        "preview": {
            "requested": int(preview_limit),
            "computed": sum(
                1 for record in sample if record.get("preview") is not None
            ),
            "seconds": preview_seconds,
        },
        "replay_seconds": replay_seconds,
        "settled_oracle_stats": settled_stats,
        "release_oracle_stats": release_stats,
        "policy_log": policy_search_log(solver),
        "action": json_safe(action),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a candidate-level counterfactual replay dataset by "
            "stratified sampling the candidate population at a target step "
            "and labelling each sample with the official validator."
        )
    )
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--case", default="000")
    parser.add_argument("--steps", type=int, nargs="+", default=[0])
    parser.add_argument("--mode", default="weighted")
    parser.add_argument("--coverage-mode", default="class_aware")
    parser.add_argument("--risk-gate-mode", default="shadow")
    parser.add_argument("--output-dir", type=pathlib.Path)
    parser.add_argument("--per-stratum", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument("--oracle-limit", type=int)
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=0,
        help=(
            "Recompute the preview term for this many top-ranked sampled "
            "candidates. Costs a visible-pool feasibility scan each, so it "
            "is off by default."
        ),
    )
    parser.add_argument("--skip-optimize", action="store_true")
    args = parser.parse_args()

    os.environ["NEDO_CANDIDATE_AUDIT"] = "1"
    os.environ["LOOKAHEAD_SELECTION_MODE"] = str(args.mode)
    os.environ["ITEM_COVERAGE_MODE"] = str(args.coverage_mode)
    # The gate must annotate the population, never filter it: enforce would
    # remove the rejected candidates this dataset exists to label.
    if str(args.risk_gate_mode) == "enforce":
        raise SystemExit(
            "risk-gate-mode 'enforce' would filter the population before "
            "sampling; use 'shadow' so rejected candidates stay labelled"
        )
    os.environ["RELEASE_RISK_GATE_MODE"] = str(args.risk_gate_mode)

    config = json.loads(args.config.read_text(encoding="utf-8"))
    case_id = str(args.case)
    if case_id not in config:
        raise SystemExit(
            f"unknown case '{case_id}'; available cases: {', '.join(config)}"
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
        "schema_version": SCHEMA_VERSION,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "config": str(args.config.resolve()),
        "selection_mode": str(args.mode),
        "coverage_mode": str(args.coverage_mode),
        "risk_gate_mode": str(args.risk_gate_mode),
        "per_stratum": int(args.per_stratum),
        "seed": int(args.seed),
        "oracle_limit": args.oracle_limit,
        "preview_limit": int(args.preview_limit),
        "label_contract": {
            "transport": "official_check_transport_path",
            "settle": "official_place_item",
            "note": (
                "Rows are an unequal-probability sample. Re-weight by "
                "sampling.sampling_weight before reading any rate as a "
                "population rate."
            ),
        },
        "case": run_case(
            agent_module,
            config[case_id],
            case_id=case_id,
            target_steps=target_steps,
            output_dir=output_dir,
            per_stratum=int(args.per_stratum),
            seed=int(args.seed),
            oracle_limit=args.oracle_limit,
            preview_limit=int(args.preview_limit),
            skip_optimize=args.skip_optimize,
        ),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
