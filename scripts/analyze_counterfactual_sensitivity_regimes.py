"""Discover label-blind physical-response regimes and test them across runs.

A regime is defined by how candidate PyBullet afterstates differ at one source
state, not by root step or by a continuation label.  Cluster count, scaling,
centroids and per-cluster decisions are frozen from the training run before a
different physical run is evaluated.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
from collections import defaultdict
from typing import Any, Iterable

import numpy as np

try:
    from scripts.develop_post_shake_soft_reranker import (
        DIRECTIONAL,
        LABEL_FAMILY,
        METRIC,
        _eligible,
        _extent,
        _named,
        soft_topology_summary,
    )
    from scripts.evaluate_counterfactual_afterstate_value import _read_jsonl
    from scripts.train_phase_conditioned_soft_policy import teacher_signature
except ModuleNotFoundError:
    from develop_post_shake_soft_reranker import (
        DIRECTIONAL,
        LABEL_FAMILY,
        METRIC,
        _eligible,
        _extent,
        _named,
        soft_topology_summary,
    )
    from evaluate_counterfactual_afterstate_value import _read_jsonl
    from train_phase_conditioned_soft_policy import teacher_signature


OBSERVABLE_NAMES = (
    "fill_fraction",
    "maximum_height_fraction",
    "horizontal_cog_radius",
    "direct_soft_coverage_per_item",
    "stack_soft_coverage_per_item",
    "ordinary_overlap_on_soft_fraction",
    "ordinary_load_on_soft_fraction",
    "minimum_soft_wall_clearance_fraction",
)
FEATURE_NAMES = tuple(
    f"{stat}_{name}" for stat in ("mean_abs_response", "max_abs_response")
    for name in OBSERVABLE_NAMES
)


def _state_observables(state: dict[str, Any]) -> list[float]:
    containers = _named(state, "container")
    packed = _named(state, "packed_item")
    container_volume = sum(
        item.get("length", 0.0) * item.get("width", 0.0) * item.get("height", 0.0)
        for item in containers
    ) or 1.0
    packed_volume = sum(
        item.get("length", 0.0) * item.get("width", 0.0) * item.get("height", 0.0)
        for item in packed
    )
    maximum_height = 0.0
    weighted_x = weighted_y = total_mass = 0.0
    for item in packed:
        index = int(item.get("container_index", -1))
        container = containers[index] if 0 <= index < len(containers) else {}
        height = container.get("height", 1.0) or 1.0
        maximum_height = max(
            maximum_height,
            (item.get("local_z", 0.0) + _extent(item)[2]) / height,
        )
        mass = item.get("mass", 1.0)
        half_length = (container.get("length", 2.0) or 2.0) / 2.0
        half_width = (container.get("width", 2.0) or 2.0) / 2.0
        weighted_x += mass * item.get("local_x", 0.0) / half_length
        weighted_y += mass * item.get("local_y", 0.0) / half_width
        total_mass += mass
    cog_radius = math.hypot(weighted_x, weighted_y) / (total_mass or 1.0)

    topology = soft_topology_summary(state)
    offsets = range(0, len(topology), 15)
    packed_count = float(len(packed) or 1)
    footprint = sum(
        item.get("length", 0.0) * item.get("width", 0.0)
        for item in containers
    ) or 1.0
    clearance_scale = max(
        (max(item.get("length", 0.0), item.get("width", 0.0)) for item in containers),
        default=1.0,
    ) or 1.0
    clearances = [topology[offset + 13] for offset in offsets]
    return [
        packed_volume / container_volume,
        maximum_height,
        cog_radius,
        sum(topology[offset + 3] for offset in offsets) / packed_count,
        sum(topology[offset + 5] for offset in offsets) / packed_count,
        sum(topology[offset + 7] for offset in offsets) / footprint,
        sum(topology[offset + 8] for offset in offsets) / (total_mass or 1.0),
        min(clearances, default=0.0) / clearance_scale,
    ]


def physical_response_vector(row: dict[str, Any]) -> list[float]:
    """Unsigned physical response, invariant to lower/higher pair ordering."""
    lower = _state_observables(row["lower_afterstate_tensor"])
    higher = _state_observables(row["higher_afterstate_tensor"])
    return [abs(right - left) for left, right in zip(lower, higher)]


def _group_key(row: dict[str, Any]) -> str:
    return f"{row.get('graph_id', '')}:{row.get('source_node_id', '')}"


def aggregate_source_sensitivities(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate the full candidate-pair envelope at every source state."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_group_key(row)].append(row)
    results = []
    for key in sorted(grouped):
        current = grouped[key]
        responses = [physical_response_vector(row) for row in current]
        columns = list(zip(*responses))
        directional = [
            row for row in current
            if row.get(LABEL_FAMILY, {}).get(METRIC, {}).get("relation") in DIRECTIONAL
        ]
        if not directional:
            continue
        results.append({
            "source_key": key,
            "graph_id": str(current[0].get("graph_id", "")),
            "source_node_id": str(current[0].get("source_node_id", "")),
            "root_step_telemetry_only": int(current[0].get("root_step", 0)),
            "candidate_pairs": len(current),
            "directional_rows": len(directional),
            "features": [statistics.fmean(column) for column in columns]
            + [max(column) for column in columns],
            "relations": [
                row[LABEL_FAMILY][METRIC]["relation"] for row in directional
            ],
            "teacher_ids": [row["teacher_id"] for row in directional],
        })
    return results


def _standardize(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    means = values.mean(axis=0)
    scales = values.std(axis=0)
    scales[scales == 0.0] = 1.0
    return (values - means) / scales, means, scales


def _kmeans(values: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    if len(values) < k:
        raise ValueError(f"cannot fit {k} regimes from {len(values)} source states")
    center = values.mean(axis=0)
    first = int(np.argmax(np.sum((values - center) ** 2, axis=1)))
    selected = [first]
    while len(selected) < k:
        distances = np.min(
            np.stack([np.sum((values - values[index]) ** 2, axis=1) for index in selected]),
            axis=0,
        )
        distances[selected] = -1.0
        selected.append(int(np.argmax(distances)))
    centroids = values[selected].copy()
    assignments = np.zeros(len(values), dtype=int)
    for _ in range(100):
        distances = np.stack(
            [np.sum((values - centroid) ** 2, axis=1) for centroid in centroids],
            axis=1,
        )
        updated = np.argmin(distances, axis=1)
        next_centroids = centroids.copy()
        for cluster in range(k):
            members = values[updated == cluster]
            if len(members):
                next_centroids[cluster] = members.mean(axis=0)
        if np.array_equal(updated, assignments) and np.allclose(next_centroids, centroids):
            assignments = updated
            centroids = next_centroids
            break
        assignments = updated
        centroids = next_centroids
    order = sorted(range(k), key=lambda index: tuple(centroids[index].tolist()))
    remap = {old: new for new, old in enumerate(order)}
    return np.asarray([remap[int(value)] for value in assignments]), centroids[order]


def _silhouette(values: np.ndarray, assignments: np.ndarray) -> float:
    if len(set(assignments.tolist())) < 2:
        return -1.0
    scores = []
    for index, cluster in enumerate(assignments):
        own = np.where(assignments == cluster)[0]
        if len(own) <= 1:
            scores.append(0.0)
            continue
        a = statistics.fmean(
            float(np.linalg.norm(values[index] - values[other]))
            for other in own if other != index
        )
        b = min(
            statistics.fmean(
                float(np.linalg.norm(values[index] - values[other]))
                for other in np.where(assignments == candidate)[0]
            )
            for candidate in set(assignments.tolist()) if candidate != cluster
        )
        scores.append((b - a) / max(a, b, 1e-12))
    return statistics.fmean(scores)


def fit_sensitivity_regimes(
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    k_candidates: Iterable[int] = (2, 3),
) -> dict[str, Any]:
    groups = aggregate_source_sensitivities(rows)
    if len(groups) < 4:
        raise ValueError("sensitivity regimes require at least four directional source states")
    raw = np.asarray([group["features"] for group in groups], dtype=float)
    normalized, means, scales = _standardize(raw)
    candidates = []
    for k in k_candidates:
        assignments, centroids = _kmeans(normalized, int(k))
        candidates.append((
            _silhouette(normalized, assignments), int(k), assignments, centroids
        ))
    silhouette, k, assignments, centroids = max(
        candidates, key=lambda item: (item[0], -item[1])
    )
    cluster_relations: dict[str, str] = {}
    cluster_profiles = []
    for cluster in range(k):
        members = [group for group, value in zip(groups, assignments) if value == cluster]
        relations = [relation for group in members for relation in group["relations"]]
        lower = relations.count("lower_afterstate_better")
        higher = relations.count("higher_afterstate_better")
        relation = (
            "lower_afterstate_better" if lower > higher else "higher_afterstate_better"
        )
        cluster_relations[str(cluster)] = relation
        cluster_profiles.append({
            "cluster": cluster,
            "source_states": len(members),
            "directional_rows": len(relations),
            "lower_afterstate_better": lower,
            "higher_afterstate_better": higher,
            "frozen_relation": relation,
        })
    minimum_cluster_states = max(2, math.ceil(0.10 * len(groups)))
    regime_structure_supported = all(
        profile["source_states"] >= minimum_cluster_states
        for profile in cluster_profiles
    )
    directional = _eligible(rows)
    return {
        "schema_version": 1,
        "status": "prospective_evaluation_only",
        "target": METRIC,
        "label_family": LABEL_FAMILY,
        "source_run_id": str(manifest["source_run_id"]),
        "feature_contract": "label_blind_source_candidate_physical_response_v1",
        "feature_names": list(FEATURE_NAMES),
        "root_step_used_as_feature": False,
        "selected_regime_count": k,
        "selection_contract": "maximum training-only silhouette over k=2,3; ties prefer smaller k",
        "training_silhouette": silhouette,
        "minimum_source_states_per_regime": minimum_cluster_states,
        "regime_structure_supported": regime_structure_supported,
        "normalization": {"means": means.tolist(), "scales": scales.tolist()},
        "centroids": centroids.tolist(),
        "cluster_relations": cluster_relations,
        "training_cluster_profiles": cluster_profiles,
        "training_source_states": len(groups),
        "training_directional_rows": len(directional),
        "training_teacher_signatures": sorted(teacher_signature(row) for row in directional),
        "promotion_contract": (
            "different physical run; zero teacher-signature overlap; at least 20 directional "
            "rows; every training regime has at least max(2, 10% of source states); "
            "frozen sensitivity regime strictly beats immediate score"
        ),
    }


def _assign(policy: dict[str, Any], features: list[float]) -> int:
    means = np.asarray(policy["normalization"]["means"], dtype=float)
    scales = np.asarray(policy["normalization"]["scales"], dtype=float)
    value = (np.asarray(features, dtype=float) - means) / scales
    centroids = np.asarray(policy["centroids"], dtype=float)
    return int(np.argmin(np.sum((centroids - value) ** 2, axis=1)))


def evaluate_sensitivity_regimes(
    policy: dict[str, Any], manifest: dict[str, Any], rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if policy.get("status") != "prospective_evaluation_only":
        raise ValueError("policy is not prospective")
    target_run_id = str(manifest["source_run_id"])
    if target_run_id == str(policy["source_run_id"]):
        raise ValueError("prospective evaluation requires a different physical run")
    groups = aggregate_source_sensitivities(rows)
    group_clusters = {
        group["source_key"]: _assign(policy, group["features"]) for group in groups
    }
    directional = _eligible(rows)
    target_signatures = {teacher_signature(row) for row in directional}
    overlap = target_signatures & set(policy["training_teacher_signatures"])
    correct = immediate_correct = 0
    profiles: dict[int, dict[str, Any]] = {}
    for group in groups:
        cluster = group_clusters[group["source_key"]]
        profile = profiles.setdefault(cluster, {
            "cluster": cluster, "source_states": 0, "directional_rows": 0,
            "lower_afterstate_better": 0, "higher_afterstate_better": 0,
            "root_steps_telemetry_only": defaultdict(int),
        })
        profile["source_states"] += 1
        profile["directional_rows"] += group["directional_rows"]
        profile["root_steps_telemetry_only"][str(group["root_step_telemetry_only"])] += 1
        predicted = policy["cluster_relations"][str(cluster)]
        for relation in group["relations"]:
            profile[relation] += 1
            correct += int(predicted == relation)
            immediate_correct += int(relation == "higher_afterstate_better")
    serial_profiles = []
    for cluster in range(int(policy["selected_regime_count"])):
        profile = profiles.get(cluster, {
            "cluster": cluster, "source_states": 0, "directional_rows": 0,
            "lower_afterstate_better": 0, "higher_afterstate_better": 0,
            "root_steps_telemetry_only": {},
        })
        profile["root_steps_telemetry_only"] = dict(profile["root_steps_telemetry_only"])
        profile["frozen_relation"] = policy["cluster_relations"][str(cluster)]
        serial_profiles.append(profile)
    passed = (
        bool(policy["regime_structure_supported"])
        and len(directional) >= 20
        and not overlap
        and correct > immediate_correct
    )
    return {
        "schema_version": 1,
        "protocol": "label_blind_regimes_frozen_on_previous_run_whole_stream_holdout",
        "training_run_id": str(policy["source_run_id"]),
        "target_run_id": target_run_id,
        "directional_rows": len(directional),
        "source_states": len(groups),
        "teacher_signature_overlap": len(overlap),
        "selected_regime_count": int(policy["selected_regime_count"]),
        "training_silhouette": policy["training_silhouette"],
        "minimum_source_states_per_regime": policy[
            "minimum_source_states_per_regime"
        ],
        "regime_structure_supported": policy["regime_structure_supported"],
        "models": {
            "immediate_score": {"correct": immediate_correct, "total": len(directional)},
            "sensitivity_regime": {"correct": correct, "total": len(directional)},
        },
        "training_cluster_profiles": policy["training_cluster_profiles"],
        "target_cluster_profiles": serial_profiles,
        "promotion_gate": {
            "passed": passed,
            "decision": "license_regime_shadow" if passed else "do_not_connect_regime_model",
        },
    }


def _load_teacher_dir(path: pathlib.Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    rows = (
        _read_jsonl(path / "distributional_discovery.jsonl")
        + _read_jsonl(path / "distributional_late_holdout.jsonl")
    )
    return manifest, rows


def render_markdown(report: dict[str, Any]) -> str:
    immediate = report["models"]["immediate_score"]
    regime = report["models"]["sensitivity_regime"]
    lines = [
        "# Counterfactual sensitivity regimes", "",
        f"Training / target run: **{report['training_run_id']} / {report['target_run_id']}**",
        f"Frozen regimes / training silhouette: **{report['selected_regime_count']} / "
        f"{report['training_silhouette']:.3f}**",
        f"Training regime support gate: **"
        f"{'PASS' if report['regime_structure_supported'] else 'FAIL'}** "
        f"(minimum {report['minimum_source_states_per_regime']} source states each).",
        f"Target source states / directional rows / signature overlap: "
        f"**{report['source_states']} / {report['directional_rows']} / "
        f"{report['teacher_signature_overlap']}**.", "",
        "| Model | Correct |", "|---|---:|",
        f"| immediate_score | {immediate['correct']}/{immediate['total']} |",
        f"| sensitivity_regime | {regime['correct']}/{regime['total']} |", "",
        "| Regime | Training states | Training lower / higher | Frozen direction |",
        "|---:|---:|---:|---|",
    ]
    for profile in report["training_cluster_profiles"]:
        lines.append(
            f"| {profile['cluster']} | {profile['source_states']} | "
            f"{profile['lower_afterstate_better']} / "
            f"{profile['higher_afterstate_better']} | "
            f"{profile['frozen_relation']} |"
        )
    lines.extend([
        "",
        "| Regime | Frozen direction | Target states | Target lower / higher | Root steps (telemetry only) |",
        "|---:|---|---:|---:|---|",
    ])
    for profile in report["target_cluster_profiles"]:
        lines.append(
            f"| {profile['cluster']} | {profile['frozen_relation']} | "
            f"{profile['source_states']} | {profile['lower_afterstate_better']} / "
            f"{profile['higher_afterstate_better']} | "
            f"{json.dumps(profile['root_steps_telemetry_only'], sort_keys=True)} |"
        )
    gate = report["promotion_gate"]
    lines.extend(["", f"Promotion gate: **{'PASS' if gate['passed'] else 'FAIL'}** "
                  f"({gate['decision']}).", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-dir", type=pathlib.Path, required=True)
    parser.add_argument("--target-dir", type=pathlib.Path, required=True)
    parser.add_argument("--policy-output", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    training_manifest, training_rows = _load_teacher_dir(args.training_dir)
    policy = fit_sensitivity_regimes(training_manifest, training_rows)
    target_manifest, target_rows = _load_teacher_dir(args.target_dir)
    report = evaluate_sensitivity_regimes(policy, target_manifest, target_rows)
    for path in (args.policy_output, args.json_output, args.markdown_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.policy_output.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
