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
import hashlib
import io
import json
import math
import os
import pathlib
import platform
import random
import subprocess
import sys
import time
import uuid
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
    policy_indexed_items,
    policy_observation,
    policy_search_log,
    state_snapshot,
)
from scripts.summarize_task_b import (  # noqa: E402
    separated_physical_labels,
)
from scripts.residual_diversity import (  # noqa: E402
    constrained_residual_diversity_sample,
    global_constrained_residual_diversity_sample,
    residual_diversity_sample,
    residual_proxy_coverage,
    settled_proxy_record,
    settled_portfolio_comparison,
)
from scripts.observed_state_swap import (  # noqa: E402
    annotate_swapped_portfolio,
    optimize_observed_state_portfolio,
    seed_keys_from_control,
)

SCHEMA_VERSION = 3
DEFAULT_REPORT_ROOT = ROOT / "reports" / "replay-dataset"
ACTION_MATCH_TOLERANCE = 1e-4
# simulator/src/ground_handling/validator.py uses PEP 701 nested-quote
# f-strings, which only parse on 3.12+.
REQUIRED_PYTHON = (3, 12)
# Local search rounds for the safe-split positive arm. Each round applies at
# most one swap, so this also caps how far the portfolio can travel from the
# control seed.
DEFAULT_SWAP_ROUNDS = 64
DIVERSITY_SAMPLING_MODES = frozenset(
    {
        "residual_diversity",
        "residual_diversity_constrained",
        "residual_diversity_global_constrained",
        "residual_diversity_safe_split",
    }
)


def require_supported_python() -> None:
    if sys.version_info[:2] < REQUIRED_PYTHON:
        raise SystemExit(
            "this tool needs Python "
            f"{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ but is running on "
            f"{sys.version_info.major}.{sys.version_info.minor}; the bundled "
            "simulator uses PEP 701 f-strings and would otherwise fail later "
            "with a confusing SyntaxError during import"
        )


class OutputDirectoryClaimed(RuntimeError):
    """Another dataset already owns this output directory."""


def build_dataset_id(
    *,
    run_id: str,
    case_id: str,
    selection_mode: str,
    coverage_mode: str,
    risk_gate_mode: str,
    config_digest: str,
) -> str:
    """
    Identifier for one dataset run.

    The random suffix is load-bearing: seconds plus the settings are not
    unique, so two runs of the same configuration started in the same
    second would otherwise share an id and an output directory.
    """
    return "-".join(
        (
            run_id,
            str(case_id),
            str(selection_mode),
            str(coverage_mode),
            str(risk_gate_mode),
            config_digest[:8],
            uuid.uuid4().hex[:12],
        )
    )


def claim_output_directory(
    output_dir: pathlib.Path,
    *,
    overwrite: bool = False,
) -> pathlib.Path:
    """
    Take exclusive ownership of an output directory and return its manifest.

    Creating the manifest with ``O_CREAT | O_EXCL`` is what makes this safe.
    Checking ``exists()`` after ``mkdir(exist_ok=True)`` leaves a window in
    which two processes aimed at the same absent or empty directory both see
    no manifest and then interleave two different datasets under the same
    file names -- the snapshot and candidate JSONL paths are derived from the
    step, not from the dataset id, so they collide.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    if overwrite:
        return manifest_path
    try:
        with manifest_path.open("x", encoding="utf-8") as handle:
            handle.write("{}")
    except FileExistsError as exc:
        raise OutputDirectoryClaimed(
            f"{manifest_path} already exists or was claimed by a concurrent "
            "run; refusing to mix two datasets in one directory. Choose "
            "another --output-dir or pass --overwrite."
        ) from exc
    return manifest_path


def file_digest(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def scenario_context(task_config: dict[str, Any]) -> dict[str, Any]:
    """Return explicit conditioning variables for one simulator scenario.

    A one-container no-shelf state and a two-container mixed-shelf state are
    different problems even when a candidate's local geometry happens to be
    identical.  Keep those setup variables beside every training row so a
    later model cannot mistake between-scenario variation for action value.
    """
    containers = list(
        (task_config.get("containers") or {}).get("container_list") or []
    )
    item_stream = task_config.get("item_stream") or {}
    container_rows = []
    for position, container in enumerate(containers):
        has_shelf = bool(
            container.get("require_shelf", container.get("shelf", False))
        )
        is_priority = bool(container.get("is_prioritized", False))
        packed_count = len(container.get("packed_items") or [])
        container_rows.append(
            {
                "index": int(container.get("index", position)),
                "has_shelf": has_shelf,
                "is_prioritized": is_priority,
                "initial_packed_item_count": packed_count,
                "geometry": {
                    name: float(container.get(name, 0.0))
                    for name in (
                        "length",
                        "width",
                        "height",
                        "thickness",
                        "buffer",
                        "cut_x",
                        "cut_y",
                    )
                },
            }
        )
    shelf_pattern = [row["has_shelf"] for row in container_rows]
    priority_pattern = [row["is_prioritized"] for row in container_rows]
    packed_counts = [
        row["initial_packed_item_count"] for row in container_rows
    ]
    return {
        "container_count": len(container_rows),
        "shelf_pattern": shelf_pattern,
        "shelf_count": sum(shelf_pattern),
        "priority_container_pattern": priority_pattern,
        "priority_container_count": sum(priority_pattern),
        "initial_packed_item_counts": packed_counts,
        "initial_preloaded_count": sum(packed_counts),
        "look_ahead": int(item_stream.get("look_ahead", 0)),
        "max_space": int(item_stream.get("max_space", 0)),
        "stream_item_count": len(item_stream.get("item_list") or []),
        "containers": container_rows,
    }


def _git(*arguments: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def git_sha() -> str | None:
    return _git("rev-parse", "HEAD")


def git_dirty() -> bool | None:
    status = _git("status", "--porcelain")
    return None if status is None else bool(status)


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
    forced_keys: set[tuple[Any, ...]] | dict[tuple[Any, ...], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Draw up to ``per_stratum`` candidates from each stratum.

    Forced candidates (the action the policy actually selected, and any
    hypothetical shadow-rerank selection) are always included with
    probability 1.0; the remainder of their stratum is then sampled from
    what is left, so the design stays a valid unequal-probability sample
    rather than a biased top-up. ``forced_keys`` may be a mapping from
    candidate key to the forced reason; a plain set keeps the historical
    reason ``selected_action``.

    Returns the sampled records and a per-stratum table.
    """
    if not isinstance(forced_keys, dict):
        forced_keys = {key: "selected_action" for key in forced_keys}
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
                "design": "stratified_random_without_replacement",
                "stratum_key": stratum_key,
                "stratum_size": len(group),
                "stratum_sampled": len(forced) + take,
                "inclusion_probability": 1.0,
                "sampling_weight": 1.0,
                "forced": True,
                "forced_reason": forced_keys[candidate_key(record)],
            }
        for record in drawn:
            record["sampling"] = {
                "design": "stratified_random_without_replacement",
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


def sample_candidate_population(
    records: list[dict[str, Any]],
    *,
    sampling_mode: str,
    per_stratum: int,
    rng: random.Random,
    forced_keys: set[tuple[Any, ...]] | dict[tuple[Any, ...], str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Route population-inference and state-coverage designs explicitly."""
    if sampling_mode == "stratified_random":
        return stratified_sample(
            records,
            per_stratum=per_stratum,
            rng=rng,
            forced_keys=forced_keys,
        )
    if sampling_mode == "residual_diversity":
        return residual_diversity_sample(
            records,
            per_stratum=per_stratum,
            forced_keys=forced_keys,
        )
    if sampling_mode == "residual_diversity_constrained":
        return constrained_residual_diversity_sample(
            records,
            per_stratum=per_stratum,
            forced_keys=forced_keys,
        )
    if sampling_mode == "residual_diversity_global_constrained":
        return global_constrained_residual_diversity_sample(
            records,
            per_stratum=per_stratum,
            forced_keys=forced_keys,
        )
    if sampling_mode == "residual_diversity_safe_split":
        return global_constrained_residual_diversity_sample(
            records,
            per_stratum=per_stratum,
            forced_keys=forced_keys,
        )
    raise ValueError(f"unknown sampling mode: {sampling_mode!r}")


def sampling_coverage_comparison(
    records: list[dict[str, Any]],
    *,
    diversity_sample: list[dict[str, Any]],
    random_sample: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare coverage designs on one identical candidate population.

    The caller samples the random control from a copy because both sampling
    implementations annotate selected rows. These diagnostics compare
    portfolio coverage only; they do not turn the deterministic diversity
    sample into a probability sample.
    """
    random_coverage = residual_proxy_coverage(
        random_sample, reference_records=records
    )
    diversity_coverage = residual_proxy_coverage(
        diversity_sample, reference_records=records
    )

    def difference(name: str) -> float | int | None:
        left = diversity_coverage.get(name)
        right = random_coverage.get(name)
        if left is None or right is None:
            return None
        return left - right

    return {
        "contract": "same_snapshot_same_candidate_population",
        "population": len(records),
        "stratified_random": random_coverage,
        "residual_diversity": diversity_coverage,
        "diversity_minus_random": {
            name: difference(name)
            for name in (
                "mean_nearest_neighbor_distance",
                "minimum_nearest_neighbor_distance",
                "unique_items",
                "unique_item_orientations",
                "spatial_cell_count",
            )
        },
    }


def split_observed_outcomes(
    primary_overdraw: list[dict[str, Any]],
    random_overdraw: list[dict[str, Any]],
    *,
    results: dict[tuple[Any, ...], dict[str, Any]],
    per_stratum: int,
    rng: random.Random,
    forced_keys: set[tuple[Any, ...]] | dict[tuple[Any, ...], str],
    swap_rounds: int = DEFAULT_SWAP_ROUNDS,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    """Split replayed rows into safe transitions and physical-risk labels."""
    if not isinstance(forced_keys, dict):
        forced_keys = {key: "selected_action" for key in forced_keys}

    def is_safe(record: dict[str, Any]) -> bool:
        physical = results.get(candidate_key(record)) or {}
        return bool(physical.get("is_placed_safe"))

    for record in primary_overdraw + random_overdraw:
        record["overdraw_sampling"] = copy.deepcopy(record.get("sampling"))

    primary_safe = [record for record in primary_overdraw if is_safe(record)]
    random_safe = [record for record in random_overdraw if is_safe(record)]
    safe_union_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in primary_safe + random_safe:
        safe_union_by_key.setdefault(candidate_key(record), record)
    safe_union = [safe_union_by_key[key] for key in sorted(safe_union_by_key)]
    safe_union_keys = set(safe_union_by_key)
    safe_control_keys = {candidate_key(record) for record in random_safe}
    positive_forced = {
        key: reason
        for key, reason in forced_keys.items()
        if key in safe_union_keys
    }
    control_forced = {
        key: reason
        for key, reason in forced_keys.items()
        if key in safe_control_keys
    }
    observed_afterstates = {
        candidate_key(record): settled
        for record in safe_union
        if (
            settled := settled_proxy_record(
                record, results.get(candidate_key(record))
            )
        )
        is not None
    }
    # The control draws from copies. A candidate that only the control
    # overdraw reached is the *same dict* in the safe union, so annotating one
    # arm would otherwise rewrite the other arm's recorded sampling design --
    # and the control seed deliberately makes that overlap the common case.
    random_positive, control_table = stratified_sample(
        [copy.deepcopy(record) for record in random_safe],
        per_stratum=per_stratum,
        rng=rng,
        forced_keys=control_forced,
    )
    for record in random_positive:
        record["sampling"].update(
            {
                "design": "observed_safe_stratified_random_control",
                "inclusion_probability": None,
                "sampling_weight": None,
            }
        )

    # The paired control is drawn first because it is the seed. Constructing
    # the positive arm from an unrelated greedy start is what let the reported
    # objective move the wrong way while the construction's own objective --
    # minimum distance -- improved.
    # ``--observed-swap-rounds 0`` restores the unseeded greedy construction
    # as an ablation arm: seeding and swapping are one instrument, so one
    # switch turns both off.
    seed_keys = (
        seed_keys_from_control(
            pool=safe_union,
            control=random_positive,
            per_stratum=per_stratum,
            forced_keys=positive_forced,
        )
        if int(swap_rounds) > 0
        else dict(positive_forced)
    )
    seeded, positive_table = global_constrained_residual_diversity_sample(
        safe_union,
        per_stratum=per_stratum,
        forced_keys=seed_keys,
        distance_records=observed_afterstates,
        design=(
            "deterministic_global_item_matching_then_"
            "observed_afterstate_maximin"
        ),
    )
    positive, swap_trace = optimize_observed_state_portfolio(
        seeded,
        pool=safe_union,
        control=random_positive,
        observed=observed_afterstates,
        forced_keys=positive_forced,
        max_rounds=int(swap_rounds),
    )
    if int(swap_rounds) > 0:
        positive_table = annotate_swapped_portfolio(
            positive,
            pool=safe_union,
            observed=observed_afterstates,
            forced_keys=positive_forced,
            seed_keys=seed_keys,
        )

    negative_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    for record in primary_overdraw + random_overdraw:
        if not is_safe(record):
            negative_by_key.setdefault(candidate_key(record), record)
    negative = [negative_by_key[key] for key in sorted(negative_by_key)]
    return positive, negative, random_positive, {
        "contract": "observed_pybullet_outcome_split",
        "primary_overdraw": len(primary_overdraw),
        "random_overdraw": len(random_overdraw),
        "primary_safe_pool": len(primary_safe),
        "random_safe_pool": len(random_safe),
        "positive_safe_union": len(safe_union),
        "positive_transition": len(positive),
        "random_positive_control": len(random_positive),
        "negative_physical_risk": len(negative),
        "positive_strata": positive_table,
        "random_positive_strata": control_table,
        "positive_labels": {"is_placed_safe": True},
        "negative_labels": {"is_placed_safe": False},
        "selection_distance_basis": "official_replay_observed_x_plus",
        "control_seeded_positive": sum(
            1
            for record in positive
            if seed_keys.get(candidate_key(record)) == "paired_control_seed"
        ),
        "swap_optimizer": swap_trace,
    }


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


FALLBACK_ACTION_SOURCES = frozenset(
    {"fixed_fallback", "unsafe_protocol_fallback"}
)


def selected_action_error(
    policy_log: dict[str, Any],
    selected_key: tuple[Any, ...] | None,
) -> str | None:
    """
    Report when the chosen action is missing from the sampled population.

    A protocol fallback is legitimately outside the candidate population, so
    it is not an error. Anything sourced from a real placement candidate must
    be present, otherwise the population is not the set the policy searched
    and the forced-inclusion contract is void.
    """
    if selected_key is not None:
        return None
    action_source = policy_log.get("action_source")
    if action_source in FALLBACK_ACTION_SOURCES:
        return None
    return (
        "selected action was not found in the enumerated population "
        f"(action_source={action_source!r}); the population does not match "
        "the item set the policy searched, so forced inclusion of the "
        "selected candidate did not happen"
    )


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
def modelling_features(
    features: dict[str, Any] | None,
    availability: dict[str, str],
) -> dict[str, Any] | None:
    """
    Drop features that are recorded but carry no information.

    `phi` keeps every field so a replay stays faithful; `phi_modelling` is
    what may be fed to a model. Without this split a constant placeholder
    such as `initial_tilt_deg` looks like an ordinary explanatory variable
    to anything that reads the dataset on its own.
    """
    if not isinstance(features, dict):
        return None
    return {
        name: value
        for name, value in features.items()
        if availability.get(name, "available") == "available"
    }


def build_row(
    record: dict[str, Any],
    *,
    dataset_id: str,
    snapshot_id: str,
    case_id: str,
    step: int,
    snapshot_name: str,
    selected_key: tuple[Any, ...] | None,
    anytime_keys: set[tuple[Any, ...]],
    physical: dict[str, Any] | None,
    feature_availability: dict[str, str],
    shadow_key: tuple[Any, ...] | None = None,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    key = candidate_key(record)
    risk = record.get("release_risk")
    features = (risk or {}).get("features")
    unavailable = sorted(
        name
        for name, state in feature_availability.items()
        if state != "available"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "snapshot_id": snapshot_id,
        "case_id": str(case_id),
        "step": int(step),
        "scenario_context": copy.deepcopy(scenario),
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
        # Phi. `phi` is the complete recorded vector; `phi_modelling` is the
        # subset that is safe to learn on, with the availability map carried
        # alongside so a consumer can check rather than assume.
        "phi": features,
        "phi_modelling": modelling_features(features, feature_availability),
        "phi_availability": (
            dict(feature_availability) if features is not None else None
        ),
        "phi_unavailable": unavailable if features is not None else None,
        "gate_passed": (risk or {}).get("passed"),
        "gate_reasons": (risk or {}).get("reasons"),
        # Q
        "score_immediate": float(record.get("score", 0.0)),
        "score_rank": int(record.get("score_rank", -1)),
        "score_population": int(record.get("score_population", 0)),
        "preview": record.get("preview"),
        # selected
        "selected": key == selected_key,
        # The hypothetical shadow-rerank choice: what the risk-adjusted
        # stack would have selected instead. Its physical labels are the
        # counterfactual outcome of adopting the risk rule at this step.
        "shadow_rerank_selected": (
            shadow_key is not None and key == shadow_key
        ),
        "found_by_anytime": key in anytime_keys,
        # sampling design
        "stratum": record["stratum"],
        "sampling": record["sampling"],
        "overdraw_sampling": record.get("overdraw_sampling"),
        "residual_proxy": record.get("residual_proxy"),
        "selection_distance_proxy": record.get(
            "selection_distance_proxy"
        ),
        # labels
        "physical": physical,
    }


def dataset_problems(case: dict[str, Any]) -> tuple[list[str], list[int]]:
    """Separate "the episode ended" from "a step went wrong".

    Asking for step 18 of a sixteen-step episode is not a defect; it is how
    you find out how long the episode is. Treating it as one made the whole
    scenario fail, dropped it from the matrix verdict, and so put a ceiling on
    the step axis -- which is one of only two ways this project can generate
    more distinct states. A step that the episode never reached because it
    ended is reported separately and does not fail the run. A step that was
    reachable and did not produce a usable sample still does.
    """
    unreached = [int(step) for step in case.get("unreached_steps") or []]
    ended = bool(
        case.get("episode_terminated") or case.get("episode_truncated")
    )
    executed = int(case.get("episode_steps_executed", 0))
    beyond_end = (
        [step for step in unreached if step > executed] if ended else []
    )
    missing = [step for step in unreached if step not in beyond_end]

    problems: list[str] = []
    if missing:
        problems.append(f"unreached steps {missing}")
    if case.get("failed_steps"):
        problems.append(f"failed steps {case['failed_steps']}")
    empty = [
        int(entry["step"])
        for entry in case.get("steps") or []
        if int(entry["sampling"]["sampled"]) == 0
    ]
    if empty:
        problems.append(f"empty samples at steps {empty}")
    return problems, beyond_end


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------
def run_case(
    agent_module,
    task_config: dict[str, Any],
    *,
    dataset_id: str,
    case_id: str,
    target_steps: set[int],
    output_dir: pathlib.Path,
    per_stratum: int,
    seed: int,
    oracle_limit: int | None,
    preview_limit: int,
    skip_optimize: bool,
    sampling_mode: str = "stratified_random",
    overdraw_factor: int = 2,
    swap_rounds: int = DEFAULT_SWAP_ROUNDS,
    on_progress=None,
) -> dict[str, Any]:
    if str(SIMULATOR) not in sys.path:
        sys.path.insert(0, str(SIMULATOR))
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(config=task_config, verbose=False, render_mode=None)
    solver = agent_module.Agent("")
    scenario = scenario_context(task_config)
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
                        dataset_id=dataset_id,
                        case_id=case_id,
                        step=step,
                        output_dir=output_dir,
                        per_stratum=per_stratum,
                        sampling_mode=sampling_mode,
                        overdraw_factor=overdraw_factor,
                        swap_rounds=swap_rounds,
                        seed=seed,
                        oracle_limit=oracle_limit,
                        preview_limit=preview_limit,
                        scenario=scenario,
                    )
                )
                # Persist after every completed step so an interrupted run
                # leaves a manifest that agrees with the JSONL on disk.
                if on_progress is not None:
                    on_progress(steps)
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
    failed_steps = [
        int(entry["step"])
        for entry in steps
        if entry.get("status") != "ok"
    ]
    return {
        "case_id": str(case_id),
        "scenario_context": scenario,
        "target_steps": sorted(target_steps),
        "reached_steps": sorted(reached),
        "unreached_steps": unreached,
        "failed_steps": failed_steps,
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
    dataset_id: str,
    case_id: str,
    step: int,
    output_dir: pathlib.Path,
    per_stratum: int,
    sampling_mode: str,
    overdraw_factor: int,
    swap_rounds: int,
    seed: int,
    oracle_limit: int | None,
    preview_limit: int,
    scenario: dict[str, Any],
) -> dict[str, Any]:
    step_label = f"step-{step:03d}"
    snapshot_id = f"{dataset_id}:{case_id}:{step_label}"
    snapshot_path = output_dir / f"{step_label}-state.json"
    snapshot_path.write_text(
        json.dumps(
            state_snapshot(env, observation, case_id=case_id, step=step),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # The population must be the item set the policy itself searched. Under
    # the default class_aware coverage that is NOT the legacy ordered prefix:
    # the prefix drops the reserved soft/priority representatives and adds
    # normal items the policy never considered, which both breaks the forced
    # inclusion of the selected action and silently changes what is estimated.
    indexed_items = policy_indexed_items(agent_module, observation)
    settled, settled_complete, settled_stats = enumerate_dual_settled_oracle(
        agent_module,
        observation,
        max_candidates=oracle_limit,
        indexed_items=indexed_items,
    )
    release, release_complete, release_stats = enumerate_oracle_candidates(
        agent_module,
        observation,
        generator_mode="cartesian",
        attempt_kind="release",
        max_candidates=oracle_limit,
        indexed_items=indexed_items,
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
    policy_log = policy_search_log(solver)
    selected_key = match_selected(action, population)
    selection_error = selected_action_error(policy_log, selected_key)
    if selection_error is not None:
        # A placement-sourced action that is absent from the population means
        # the population is not the set the policy searched. Nothing sampled
        # from it can be trusted, so this must not read as a clean step.
        print(f"{case_id} step {step}: ERROR {selection_error}", flush=True)

    # Shadow rerank: when the risk-adjusted stack would have chosen a
    # different candidate, force-include that hypothetical selection so its
    # counterfactual physical labels are collected alongside the real one.
    shadow_record = solver.last_candidate_diagnostics.get("shadow_rerank")
    shadow_key: tuple[Any, ...] | None = None
    if isinstance(shadow_record, dict) and isinstance(
        shadow_record.get("risk_selection"), dict
    ):
        # applies=False (settled baseline) still matches: the risk stack
        # would select the same candidate, so the selected row doubles as
        # the shadow selection instead of reading as "unmatched".
        shadow_key = match_selected(
            shadow_record["risk_selection"].get("action_command"),
            population,
        )

    forced_reasons: dict[tuple[Any, ...], str] = {}
    if shadow_key is not None:
        forced_reasons[shadow_key] = "shadow_rerank_selection"
    if selected_key is not None:
        # The real selection wins when both point at the same candidate.
        forced_reasons[selected_key] = "selected_action"

    safe_split_mode = sampling_mode == "residual_diversity_safe_split"
    sampling_quota = (
        per_stratum * max(1, int(overdraw_factor))
        if safe_split_mode
        else per_stratum
    )
    rng = random.Random(f"{seed}:{case_id}:{step}")
    sample, stratum_table = sample_candidate_population(
        population,
        sampling_mode=sampling_mode,
        per_stratum=sampling_quota,
        rng=rng,
        forced_keys=forced_reasons,
    )
    coverage_comparison = None
    overdraw_coverage_comparison = None
    random_control: list[dict[str, Any]] = []
    if sampling_mode in DIVERSITY_SAMPLING_MODES:
        random_control, _control_table = stratified_sample(
            copy.deepcopy(population),
            per_stratum=sampling_quota,
            rng=random.Random(
                f"{seed}:{case_id}:{step}:residual-coverage-control"
            ),
            forced_keys=forced_reasons,
        )
        overdraw_coverage_comparison = sampling_coverage_comparison(
            population,
            diversity_sample=sample,
            random_sample=random_control,
        )
        coverage_comparison = overdraw_coverage_comparison
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

    replay_population = list(sample)
    replay_keys = {candidate_key(record) for record in replay_population}
    for record in random_control:
        if candidate_key(record) not in replay_keys:
            replay_population.append(record)
            replay_keys.add(candidate_key(record))
    results, replay_seconds = replay_sample(env, replay_population)
    physical_coverage_comparison = None
    outcome_split = None
    negative_sample: list[dict[str, Any]] = []
    if safe_split_mode:
        sample, negative_sample, random_control, outcome_split = (
            split_observed_outcomes(
                sample,
                random_control,
                results=results,
                per_stratum=per_stratum,
                rng=random.Random(
                    f"{seed}:{case_id}:{step}:safe-positive-control"
                ),
                forced_keys=forced_reasons,
                swap_rounds=swap_rounds,
            )
        )
        stratum_table = outcome_split["positive_strata"]
        coverage_comparison = sampling_coverage_comparison(
            population,
            diversity_sample=sample,
            random_sample=random_control,
        )
    if sampling_mode in DIVERSITY_SAMPLING_MODES:
        physical_coverage_comparison = settled_portfolio_comparison(
            diversity_sample=sample,
            random_sample=random_control,
            results=results,
        )

    dataset_path = output_dir / f"{step_label}-candidates.jsonl"
    control_dataset_path = (
        output_dir / f"{step_label}-random-control.jsonl"
        if sampling_mode in DIVERSITY_SAMPLING_MODES
        else None
    )
    negative_dataset_path = (
        output_dir / f"{step_label}-negative-risk.jsonl"
        if safe_split_mode
        else None
    )
    availability = agent_module.ReleaseRiskFeatures.feature_availability()
    with dataset_path.open("w", encoding="utf-8") as handle:
        for record in sample:
            row = build_row(
                record,
                dataset_id=dataset_id,
                snapshot_id=snapshot_id,
                case_id=case_id,
                step=step,
                snapshot_name=snapshot_path.name,
                selected_key=selected_key,
                anytime_keys=anytime_keys,
                physical=results.get(candidate_key(record)),
                feature_availability=availability,
                shadow_key=shadow_key,
                scenario=scenario,
            )
            row["portfolio_role"] = (
                "positive_transition" if safe_split_mode else sampling_mode
            )
            handle.write(
                json.dumps(json_safe(row), ensure_ascii=False) + "\n"
            )
    if control_dataset_path is not None:
        with control_dataset_path.open("w", encoding="utf-8") as handle:
            for record in random_control:
                row = build_row(
                    record,
                    dataset_id=dataset_id,
                    snapshot_id=snapshot_id,
                    case_id=case_id,
                    step=step,
                    snapshot_name=snapshot_path.name,
                    selected_key=selected_key,
                    anytime_keys=anytime_keys,
                    physical=results.get(candidate_key(record)),
                    feature_availability=availability,
                    shadow_key=shadow_key,
                    scenario=scenario,
                )
                row["portfolio_role"] = (
                    "positive_transition_random_control"
                    if safe_split_mode
                    else "stratified_random_control"
                )
                handle.write(
                    json.dumps(json_safe(row), ensure_ascii=False) + "\n"
                )
    if negative_dataset_path is not None:
        with negative_dataset_path.open("w", encoding="utf-8") as handle:
            for record in negative_sample:
                row = build_row(
                    record,
                    dataset_id=dataset_id,
                    snapshot_id=snapshot_id,
                    case_id=case_id,
                    step=step,
                    snapshot_name=snapshot_path.name,
                    selected_key=selected_key,
                    anytime_keys=anytime_keys,
                    physical=results.get(candidate_key(record)),
                    feature_availability=availability,
                    shadow_key=shadow_key,
                    scenario=scenario,
                )
                row["portfolio_role"] = "negative_physical_risk"
                handle.write(
                    json.dumps(json_safe(row), ensure_ascii=False) + "\n"
                )

    return {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "snapshot_id": snapshot_id,
        "case_id": str(case_id),
        "scenario_context": copy.deepcopy(scenario),
        "step": int(step),
        "status": "ok" if selection_error is None else "selection_mismatch",
        "error": selection_error,
        "snapshot_path": snapshot_path.name,
        "dataset_path": dataset_path.name,
        "control_dataset_path": (
            control_dataset_path.name
            if control_dataset_path is not None
            else None
        ),
        "negative_dataset_path": (
            negative_dataset_path.name
            if negative_dataset_path is not None
            else None
        ),
        "population": {
            "settled": len(settled),
            "release": len(release),
            "total": len(population),
            "settled_complete": bool(settled_complete),
            "release_complete": bool(release_complete),
            # Provenance of the item set: this must be the policy's own
            # capped set, not the legacy ordered prefix.
            "item_coverage_mode": str(agent_module.ITEM_COVERAGE_MODE),
            "item_source": "policy_capped_online_items",
            "pool_indices": [int(index) for index, _item in indexed_items],
            "item_indices": [
                int(item.get("index", index))
                for index, item in indexed_items
            ],
        },
        "sampling": {
            "mode": str(sampling_mode),
            "design": (
                "stratified without replacement, unequal probability"
                if sampling_mode == "stratified_random"
                else (
                    "overdraw global matching, observed PyBullet outcome "
                    "split, paired-control seed, then observed-state swaps "
                    "on the reported mean-nearest-neighbour objective"
                    if sampling_mode == "residual_diversity_safe_split"
                    else (
                        "deterministic global item matching then "
                        "residual-proxy maximin coverage"
                        if sampling_mode
                        == "residual_diversity_global_constrained"
                        else (
                            "deterministic item-coverage-constrained "
                            "residual-proxy maximin coverage"
                            if sampling_mode
                            == "residual_diversity_constrained"
                            else (
                                "deterministic residual-proxy maximin "
                                "coverage"
                            )
                        )
                    )
                )
            ),
            "per_stratum": int(per_stratum),
            "overdraw_factor": (
                int(overdraw_factor) if safe_split_mode else 1
            ),
            "overdraw_per_stratum": int(sampling_quota),
            "seed": int(seed),
            "sampled": len(sample),
            "selected_matched": selected_key is not None,
            "residual_proxy_coverage": residual_proxy_coverage(
                sample, reference_records=population
            ),
            "coverage_comparison": coverage_comparison,
            "overdraw_coverage_comparison": (
                overdraw_coverage_comparison
            ),
            "physical_coverage_comparison": (
                physical_coverage_comparison
            ),
            "unique_replayed": len(replay_population),
            "outcome_split": outcome_split,
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
        "shadow_rerank": json_safe(shadow_record),
        "shadow_rerank_matched": shadow_key is not None,
        # Join key for the counterfactual pair: on changed snapshots both
        # candidates are force-included, so their rows carry the physical
        # labels of the real and the hypothetical selection side by side.
        "shadow_pair": {
            "changed": (
                bool(shadow_record.get("changed"))
                if isinstance(shadow_record, dict)
                else None
            ),
            "baseline_candidate_id": (
                "|".join(str(part) for part in selected_key)
                if selected_key is not None
                else None
            ),
            "shadow_candidate_id": (
                "|".join(str(part) for part in shadow_key)
                if shadow_key is not None
                else None
            ),
        },
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
    parser.add_argument(
        "--split",
        choices=("development", "validation", "final_holdout"),
        default="development",
        help=(
            "Evaluation split recorded in the manifest. final_holdout "
            "datasets are mechanically skipped by the analysis tools "
            "until the one-shot final evaluation; see "
            "docs/RELEASE_RISK_PROTOCOL.md section 3.1."
        ),
    )
    parser.add_argument("--output-dir", type=pathlib.Path)
    parser.add_argument("--per-stratum", type=int, default=16)
    parser.add_argument(
        "--sampling-mode",
        choices=(
            "stratified_random",
            "residual_diversity",
            "residual_diversity_constrained",
            "residual_diversity_global_constrained",
            "residual_diversity_safe_split",
        ),
        default="stratified_random",
        help=(
            "stratified_random supports population-rate estimation with "
            "sampling weights; residual_diversity modes deterministically "
            "cover candidate-induced afterstate proxies and deliberately do "
            "not emit probability weights"
        ),
    )
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument(
        "--overdraw-factor",
        type=int,
        default=2,
        help=(
            "For residual_diversity_safe_split, replay this multiple of the "
            "requested per-stratum quota before observed-outcome splitting."
        ),
    )
    parser.add_argument(
        "--observed-swap-rounds",
        type=int,
        default=DEFAULT_SWAP_ROUNDS,
        help=(
            "For residual_diversity_safe_split, seed the positive arm with "
            "the paired safe-random control and run at most this many "
            "observed-afterstate swap rounds against the same "
            "mean-nearest-neighbour objective the acceptance guard reports. "
            "0 restores the unseeded greedy construction as an ablation arm."
        ),
    )
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
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "Allow an explicit --output-dir that already holds a manifest to "
            "be reused. Without this a second run into the same directory is "
            "refused rather than interleaved."
        ),
    )
    args = parser.parse_args()

    require_supported_python()
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
    if int(args.overdraw_factor) < 1:
        raise SystemExit("--overdraw-factor must be at least 1")
    if int(args.observed_swap_rounds) < 0:
        raise SystemExit("--observed-swap-rounds must not be negative")

    config_bytes = args.config.read_bytes()
    run_id = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    config_digest = hashlib.sha256(config_bytes).hexdigest()
    dataset_id = build_dataset_id(
        run_id=run_id,
        case_id=case_id,
        selection_mode=args.mode,
        coverage_mode=args.coverage_mode,
        risk_gate_mode=args.risk_gate_mode,
        config_digest=config_digest,
    )
    output_dir = args.output_dir or (DEFAULT_REPORT_ROOT / dataset_id)
    try:
        manifest_path = claim_output_directory(
            output_dir, overwrite=args.overwrite
        )
    except OutputDirectoryClaimed as exc:
        raise SystemExit(str(exc)) from exc

    agent_module = load_agent_module()
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "status": "running",
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "selection_mode": str(args.mode),
        "coverage_mode": str(args.coverage_mode),
        "risk_gate_mode": str(args.risk_gate_mode),
        "split": str(args.split),
        "per_stratum": int(args.per_stratum),
        "sampling_mode": str(args.sampling_mode),
        "overdraw_factor": int(args.overdraw_factor),
        "observed_swap_rounds": int(args.observed_swap_rounds),
        "seed": int(args.seed),
        "oracle_limit": args.oracle_limit,
        "preview_limit": int(args.preview_limit),
        # Enough to reproduce the run without the original workspace: an
        # absolute path from an Actions runner is not reproducible on its own.
        "provenance": {
            "git_sha": git_sha(),
            "git_dirty": git_dirty(),
            "config_path": str(args.config.resolve()),
            "config_sha256": config_digest,
            "agent_sha256": file_digest(ROOT / "agent" / "agent.py"),
            "python": sys.version.replace("\n", " "),
            "platform": platform.platform(),
            "case_id": case_id,
            "target_steps": sorted(target_steps),
            "sampling_mode": str(args.sampling_mode),
            "overdraw_factor": int(args.overdraw_factor),
            "observed_swap_rounds": int(args.observed_swap_rounds),
        },
        "label_contract": {
            "transport": "official_check_transport_path",
            "settle": "official_place_item",
            "note": (
                "Rows are an unequal-probability sample. Re-weight by "
                "sampling.sampling_weight before reading any rate as a "
                "population rate."
                if args.sampling_mode == "stratified_random"
                else
                "Rows are a deterministic state-coverage sample. Inclusion "
                "probabilities and weights are null; do not use these rows "
                "to estimate population rates."
            ),
        },
        "case": None,
    }

    def write_manifest() -> None:
        # Atomic replace so an interrupted run never leaves a half-written
        # manifest next to complete JSONL files.
        temporary = manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(json_safe(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(manifest_path)

    write_manifest()

    def on_progress(steps: list[dict[str, Any]]) -> None:
        payload["case"] = {"partial": True, "steps": steps}
        write_manifest()

    try:
        payload["case"] = run_case(
            agent_module,
            config[case_id],
            dataset_id=dataset_id,
            case_id=case_id,
            target_steps=target_steps,
            output_dir=output_dir,
            per_stratum=int(args.per_stratum),
            sampling_mode=str(args.sampling_mode),
            seed=int(args.seed),
            oracle_limit=args.oracle_limit,
            preview_limit=int(args.preview_limit),
            skip_optimize=args.skip_optimize,
            overdraw_factor=int(args.overdraw_factor),
            swap_rounds=int(args.observed_swap_rounds),
            on_progress=on_progress,
        )
    except BaseException as exc:
        payload["status"] = "failed"
        payload["error"] = f"{type(exc).__name__}: {exc}"
        write_manifest()
        raise

    problems, beyond_end = dataset_problems(payload["case"])
    payload["status"] = "complete" if not problems else "incomplete"
    payload["problems"] = problems
    payload["steps_beyond_episode_end"] = beyond_end
    write_manifest()

    print(manifest_path)
    if problems:
        # Silence here would let CI and downstream tooling treat a dataset
        # with missing or untrustworthy steps as a good one.
        print(
            "dataset is incomplete: " + "; ".join(problems),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
