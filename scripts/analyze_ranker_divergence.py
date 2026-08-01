"""
Explain the first action divergence between two trajectories.

The report keeps the immediate ranker additive instead of collapsing it:

    Q_old = 12V + 2R + D - 0.12|x| - 0.18*z*m + B_route
    Q_live = Q_old - lambda_rot*P_rot - lambda_slide*P_slide

Candidates can come from a replay JSONL or from a complete, unlimited oracle
enumeration of a saved pre-action snapshot.  Optional left/right search JSONL
files (or a fresh timed current-policy search) identify candidates reached by
one search but not the other.

``next_valid_candidate_count`` is deliberately a *static survival proxy*: put
the candidate into a deep-copied observation using the same settled proxy as
the online lookahead, then revalidate the already-enumerated candidates for
the remaining items.  It does not generate new anchors and it is not a
PyBullet counterfactual.  The limitation is repeated in every output.
"""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import pathlib
import sys
import time
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measure_anchor_recall import (
    candidate_key,
    enumerate_dual_settled_oracle,
    enumerate_oracle_candidates,
    extract_anytime_candidates,
    load_agent_module,
    policy_indexed_items,
    unique_candidates,
)


DEFAULT_OUTPUT = ROOT / "reports" / "ranker-divergence"
ACTION_TOLERANCE = 1e-4
NEXT_COUNT_CONTRACT = (
    "Static surviving-current-candidate proxy after apply_placement_decision; "
    "does not generate new anchors and does not run PyBullet settle."
)


@dataclass(frozen=True)
class SimpleCandidate:
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    name: str = "candidate"


@dataclass(frozen=True)
class SearchMembership:
    """Candidate reachability evidence from one search.

    ``observed_ids`` is the set for which the source can prove either reached
    or not reached.  A complete timed audit observes the whole candidate
    population, while a stratified replay JSONL only observes its sampled
    rows.  This distinction prevents an absent sample row from being reported
    as absent from the search.
    """

    reached_ids: frozenset[str]
    observed_ids: frozenset[str] | None
    source: str
    forced_selected_ids: frozenset[str] = frozenset()

    def verdict(self, candidate: str) -> bool | None:
        if candidate in self.reached_ids:
            return True
        if self.observed_ids is None or candidate in self.observed_ids:
            return False
        return None

    def with_selected(self, candidate: str | None) -> SearchMembership:
        if candidate is None:
            return self
        observed = (
            None
            if self.observed_ids is None
            else frozenset((*self.observed_ids, candidate))
        )
        return SearchMembership(
            reached_ids=frozenset((*self.reached_ids, candidate)),
            observed_ids=observed,
            source=self.source,
            forced_selected_ids=frozenset((*self.forced_selected_ids, candidate)),
        )


def add_selected_evidence(
    membership: SearchMembership | None,
    selected_id: str | None,
    side: str,
) -> SearchMembership | None:
    """A historically selected action proves that its candidate was reached."""
    if selected_id is None:
        return membership
    if membership is None:
        return SearchMembership(
            reached_ids=frozenset({selected_id}),
            observed_ids=frozenset({selected_id}),
            source=f"{side} selected-action evidence only",
            forced_selected_ids=frozenset({selected_id}),
        )
    return membership.with_selected(selected_id)


def _action_from_step(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": int(step.get("step", -1)),
        "item_index": int(step.get("selected_item_index", -1)),
        "pool_index": int(step.get("selected_pool_index", -1)),
        "container_index": int(step.get("container_index", -1)),
        "orientation": int(step.get("orientation", -1)),
        "place_pos": [float(value) for value in step.get("place_pos", [])],
    }


def _same_action(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in ("item_index", "container_index", "orientation"):
        if int(left.get(key, -1)) != int(right.get(key, -1)):
            return False
    left_pos = left.get("place_pos", [])
    right_pos = right.get("place_pos", [])
    if len(left_pos) != len(right_pos):
        return False
    return all(
        abs(float(a) - float(b)) <= ACTION_TOLERANCE
        for a, b in zip(left_pos, right_pos)
    )


def first_action_divergence(
    left_steps: list[dict[str, Any]],
    right_steps: list[dict[str, Any]],
) -> dict[str, Any]:
    left_by_step = {int(row.get("step", index)): row for index, row in enumerate(left_steps)}
    right_by_step = {
        int(row.get("step", index)): row for index, row in enumerate(right_steps)
    }
    shared = sorted(set(left_by_step) & set(right_by_step))
    for step in shared:
        left = _action_from_step(left_by_step[step])
        right = _action_from_step(right_by_step[step])
        if not _same_action(left, right):
            return {"step": step, "left": left, "right": right}
    if set(left_by_step) != set(right_by_step):
        first_missing = min(set(left_by_step) ^ set(right_by_step))
        return {
            "step": first_missing,
            "left": (
                _action_from_step(left_by_step[first_missing])
                if first_missing in left_by_step
                else None
            ),
            "right": (
                _action_from_step(right_by_step[first_missing])
                if first_missing in right_by_step
                else None
            ),
        }
    raise ValueError("the trajectories have no action divergence")


def load_case_steps(path: pathlib.Path, case_id: str) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    case = payload.get(case_id)
    if not isinstance(case, dict):
        raise ValueError(f"case {case_id!r} is absent from {path}")
    evaluation = case.get("evaluation") or {}
    steps = evaluation.get("step_metrics") or []
    if not isinstance(steps, list):
        raise ValueError(f"step_metrics is not a list in {path}")
    return steps


def record_candidate(agent_module, record: dict[str, Any]):
    return agent_module.AABB(
        tuple(float(value) for value in record["center"]),
        tuple(float(value) for value in record["size"]),
        str(record.get("kind", "candidate")),
    )


def candidate_id(record: dict[str, Any]) -> str:
    if record.get("candidate_id"):
        return str(record["candidate_id"])
    return "|".join(str(part) for part in candidate_key(record))


def decompose_score(
    agent_module,
    candidate,
    item: dict[str, Any],
    container: dict[str, Any],
    *,
    orientation: int,
    has_priority_container: bool,
    rotation_lambda: float,
    slide_lambda: float,
) -> dict[str, float | None]:
    support = float(agent_module.Geometry.support_ratio(candidate, container))
    volume = float(math.prod(candidate.size))
    mass = float(item.get("mass", 1.0))
    x, y, z = (float(value) for value in candidate.center)
    is_priority_item = bool(item.get("is_prioritized", False))
    is_priority_container = bool(container.get("is_prioritized", False))
    depth = -0.55 * y if is_priority_item else 0.35 * y
    route = 0.0
    if has_priority_container:
        if is_priority_item and is_priority_container:
            route = 8.0
        elif not is_priority_item and is_priority_container:
            route = -2.5

    terms = {
        "term_12v": 12.0 * volume,
        "term_2r": 2.0 * support,
        "term_depth": depth,
        "term_x": -0.12 * abs(x),
        "term_z_mass": -0.18 * z * mass,
        "term_route": route,
    }
    q_old = float(sum(terms.values()))
    p_rot = None
    p_slide = None
    q_active = q_old
    if candidate.name == "release_candidate":
        p_rot = float(
            agent_module.release_rotation_risk_probability_mech(
                x,
                y,
                z,
                tuple(float(value) for value in candidate.size),
                container,
            )
        )
        p_slide = float(
            agent_module.release_large_slide_probability(
                candidate,
                item,
                container,
                int(orientation),
            )
        )
        q_active -= float(rotation_lambda) * p_rot
        q_active -= float(slide_lambda) * p_slide
    return {
        **terms,
        "p_rot": p_rot,
        "p_slide": p_slide,
        "q_old": q_old,
        "q_active": float(q_active),
    }


def build_rows(
    agent_module,
    observation: dict[str, Any],
    records: Iterable[dict[str, Any]],
    *,
    rotation_lambda: float,
    slide_lambda: float,
) -> list[dict[str, Any]]:
    pool = observation.get("pool_list", [])
    containers = observation.get("container_list", [])
    has_priority_container = any(
        bool(container.get("is_prioritized", False)) for container in containers
    )
    rows = []
    for source in records:
        record = dict(source)
        pool_index = int(record["pool_index"])
        container_index = int(record["container_index"])
        if not (0 <= pool_index < len(pool)):
            continue
        if not (0 <= container_index < len(containers)):
            continue
        candidate = record_candidate(agent_module, record)
        row = {
            "candidate_id": candidate_id(record),
            "pool_index": pool_index,
            "item_index": int(record.get("item_index", pool_index)),
            "container_index": container_index,
            "orientation": int(record["orientation"]),
            "kind": str(record.get("kind", "candidate")),
            "center": [float(value) for value in record["center"]],
            "size": [float(value) for value in record["size"]],
            "action_center": [
                float(value)
                for value in record.get("action_center", record["center"])
            ],
            "found_by_anytime": record.get("found_by_anytime"),
            "next_valid_candidate_count": None,
        }
        row.update(
            decompose_score(
                agent_module,
                candidate,
                pool[pool_index],
                containers[container_index],
                orientation=int(record["orientation"]),
                has_priority_container=has_priority_container,
                rotation_lambda=rotation_lambda,
                slide_lambda=slide_lambda,
            )
        )
        rows.append(row)
    return rows


def _selected_score(rows: list[dict[str, Any]], selected_id: str | None):
    if selected_id is None:
        return None
    return next(
        (float(row["q_active"]) for row in rows if row["candidate_id"] == selected_id),
        None,
    )


def annotate_ranks_and_membership(
    rows: list[dict[str, Any]],
    *,
    left_membership: SearchMembership | None,
    right_membership: SearchMembership | None,
    left_selected_id: str | None,
    right_selected_id: str | None,
) -> None:
    by_item: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        by_item.setdefault(int(row["item_index"]), []).append(row)

    def assign_ranks(score_key: str, prefix: str) -> None:
        ordered = sorted(
            rows, key=lambda row: (-float(row[score_key]), row["candidate_id"])
        )
        for rank, row in enumerate(ordered, start=1):
            row[f"{prefix}across_candidate_rank"] = rank
        for item_rows in by_item.values():
            ordered_within = sorted(
                item_rows,
                key=lambda row: (-float(row[score_key]), row["candidate_id"]),
            )
            for rank, row in enumerate(ordered_within, start=1):
                row[f"{prefix}within_item_rank"] = rank
        ordered_items = sorted(
            by_item,
            key=lambda item_index: (
                -max(float(row[score_key]) for row in by_item[item_index]),
                item_index,
            ),
        )
        item_ranks = {
            item_index: rank for rank, item_index in enumerate(ordered_items, 1)
        }
        for row in rows:
            row[f"{prefix}item_rank"] = item_ranks[int(row["item_index"])]

    assign_ranks("q_old", "old_")
    assign_ranks("q_active", "")
    left_score = _selected_score(rows, left_selected_id)
    right_score = _selected_score(rows, right_selected_id)
    for row in rows:
        cid = row["candidate_id"]
        left_reached = (
            None if left_membership is None else left_membership.verdict(cid)
        )
        right_reached = (
            None if right_membership is None else right_membership.verdict(cid)
        )
        row["left_search_reached"] = left_reached
        row["right_search_reached"] = right_reached
        row["new_search_only"] = (
            True
            if right_reached is True and left_reached is False
            else False
            if right_reached is False or left_reached is True
            else None
        )
        row["left_selected"] = cid == left_selected_id
        row["right_selected"] = cid == right_selected_id
        row["margin_to_left_selected"] = (
            None if left_score is None else left_score - float(row["q_active"])
        )
        row["margin_to_right_selected"] = (
            None if right_score is None else right_score - float(row["q_active"])
        )


def match_action(
    rows: list[dict[str, Any]], action: dict[str, Any] | None
) -> str | None:
    if action is None:
        return None
    matches = []
    for row in rows:
        if int(row["item_index"]) != int(action["item_index"]):
            continue
        if int(row["container_index"]) != int(action["container_index"]):
            continue
        if int(row["orientation"]) != int(action["orientation"]):
            continue
        if len(row["action_center"]) != len(action["place_pos"]):
            continue
        distance = max(
            abs(float(a) - float(b))
            for a, b in zip(row["action_center"], action["place_pos"])
        )
        if distance <= ACTION_TOLERANCE:
            matches.append((distance, row["candidate_id"]))
    return min(matches)[1] if matches else None


def load_candidate_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def load_search_membership(
    path: pathlib.Path | None,
    *,
    complete: bool = False,
) -> SearchMembership | None:
    if path is None:
        return None
    rows = load_candidate_jsonl(path)
    has_flag = any("found_by_anytime" in row for row in rows)
    all_ids = frozenset(candidate_id(row) for row in rows)
    reached = frozenset(
        candidate_id(row)
        for row in rows
        if not has_flag or bool(row.get("found_by_anytime"))
    )
    return SearchMembership(
        reached_ids=reached,
        observed_ids=None if complete else all_ids,
        source=path.as_posix(),
    )


def enumerate_population(agent_module, observation: dict[str, Any]):
    indexed_items = policy_indexed_items(agent_module, observation)
    settled, settled_complete, settled_stats = enumerate_dual_settled_oracle(
        agent_module, observation, indexed_items=indexed_items
    )
    release, release_complete, release_stats = enumerate_oracle_candidates(
        agent_module,
        observation,
        attempt_kind="release",
        indexed_items=indexed_items,
    )
    return (
        unique_candidates([*settled, *release]),
        {
            "settled_complete": bool(settled_complete),
            "release_complete": bool(release_complete),
            "settled": settled_stats,
            "release": release_stats,
        },
    )


def collect_current_search_ids(
    agent_module,
    observation: dict[str, Any],
    seconds: float,
) -> SearchMembership:
    diagnostics = {"_class_aware_first_pass": True}
    indexed_items = policy_indexed_items(agent_module, observation)
    original = agent_module.CANDIDATE_AUDIT_ENABLED
    agent_module.CANDIDATE_AUDIT_ENABLED = True
    try:
        agent_module.PlacementCore.top_candidates(
            observation,
            indexed_items,
            max(1, int(agent_module.LOOKAHEAD_TOP_K)),
            deadline=time.perf_counter() + max(0.01, float(seconds)),
            diagnostics=diagnostics,
            risk_lambda=(
                agent_module.RELEASE_RISK_RERANK_LAMBDA
                if agent_module.RELEASE_RISK_LIVE_RERANK
                else None
            ),
        )
    finally:
        agent_module.CANDIDATE_AUDIT_ENABLED = original
    records = [
        *extract_anytime_candidates(diagnostics, candidate_kind="settled"),
        *extract_anytime_candidates(diagnostics, candidate_kind="release"),
    ]
    return SearchMembership(
        reached_ids=frozenset(candidate_id(record) for record in records),
        observed_ids=None,
        source=f"fresh current-policy timed audit ({seconds:.3f}s)",
    )


def next_surviving_valid_count(
    agent_module,
    observation: dict[str, Any],
    row: dict[str, Any],
    universe: list[dict[str, Any]],
) -> int:
    pool = observation.get("pool_list", [])
    containers = copy.deepcopy(observation.get("container_list", []))
    pool_index = int(row["pool_index"])
    candidate = record_candidate(agent_module, row)
    decision = agent_module.PlacementDecision(
        action={
            "item_idx": pool_index,
            "container_idx": int(row["container_index"]),
            "place_pos": np.asarray(row["action_center"], dtype=np.float32),
            "orientation": int(row["orientation"]),
        },
        candidate=candidate,
        score=float(row["q_active"]),
    )
    agent_module.apply_placement_decision(pool[pool_index], decision, containers)
    count = 0
    for other in universe:
        if int(other["item_index"]) == int(row["item_index"]):
            continue
        container_index = int(other["container_index"])
        other_candidate = record_candidate(agent_module, other)
        if agent_module.Geometry.valid(other_candidate, containers[container_index]):
            count += 1
    return count


def select_next_count_rows(
    rows: list[dict[str, Any]], mode: str, frontier: int
) -> list[dict[str, Any]]:
    if mode == "none":
        return []
    if mode == "all":
        return list(rows)
    selected = [
        row for row in rows if row.get("left_selected") or row.get("right_selected")
    ]
    if mode == "selected":
        return selected
    ordered = sorted(rows, key=lambda row: int(row["across_candidate_rank"]))
    ids = {row["candidate_id"] for row in selected}
    result = list(selected)
    for row in ordered[: max(0, int(frontier))]:
        if row["candidate_id"] not in ids:
            ids.add(row["candidate_id"])
            result.append(row)
    for row in rows:
        if row.get("new_search_only") and row["candidate_id"] not in ids:
            ids.add(row["candidate_id"])
            result.append(row)
    return result


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(report: dict[str, Any], limit: int) -> str:
    divergence = report["divergence"]
    rows = sorted(
        report["candidates"], key=lambda row: int(row["across_candidate_rank"])
    )
    important = [
        row
        for row in rows
        if row.get("left_selected")
        or row.get("right_selected")
        or row.get("new_search_only")
    ]
    seen = {row["candidate_id"] for row in important}
    shown = list(important)
    for row in rows:
        if len(shown) >= limit:
            break
        if row["candidate_id"] not in seen:
            seen.add(row["candidate_id"])
            shown.append(row)
    shown.sort(key=lambda row: int(row["across_candidate_rank"]))

    lines = [
        "# Ranker first-divergence decomposition",
        "",
        f"- case: `{report['case_id']}`; first divergent step: "
        f"`{divergence['step']}`",
        f"- candidates: {len(rows)} ({report['population_scope']})",
        f"- active score: `Q_old - {report['rotation_lambda']} P_rot "
        f"- {report['slide_lambda']} P_slide`",
        f"- next-count contract: {NEXT_COUNT_CONTRACT}",
        "- search-only is three-valued: `yes`, `no`, or `-` (unknown when "
        "a stratified source did not observe that candidate).",
        "",
        "## Divergent actions",
        "",
        "```json",
        json.dumps(
            {"left": divergence.get("left"), "right": divergence.get("right")},
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "## Selected-candidate comparison",
        "",
        "| side | item | kind | old all/item/in-item | live all/item/in-item | "
        "Q_old | P_rot | P_slide | Q_live | next valid proxy |",
        "|---|---:|---|---|---|---:|---:|---:|---:|---:|",
    ]
    selected_rows = [
        ("left", next((row for row in rows if row.get("left_selected")), None)),
        ("right", next((row for row in rows if row.get("right_selected")), None)),
    ]
    for side, row in selected_rows:
        if row is None:
            lines.append(f"| {side} | - | unmatched | - | - | - | - | - | - | - |")
            continue
        lines.append(
            f"| {side} | {row['item_index']} | {row['kind']} | "
            f"{row['old_across_candidate_rank']}/{row['old_item_rank']}/"
            f"{row['old_within_item_rank']} | "
            f"{row['across_candidate_rank']}/{row['item_rank']}/"
            f"{row['within_item_rank']} | {_fmt(row['q_old'])} | "
            f"{_fmt(row['p_rot'])} | {_fmt(row['p_slide'])} | "
            f"{_fmt(row['q_active'])} | "
            f"{_fmt(row['next_valid_candidate_count'], 0)} |"
        )
    lines.extend(
        [
            "",
            "## Candidate ranking",
            "",
            "The Markdown view is a frontier excerpt; `candidates.csv` and "
            "`report.json` contain every candidate.",
            "",
            "| old/live all | old/live item | old/live in-item | kind | "
            "pool/item | pose | center | 12V | 2R | D | x | zm | route | "
            "P_rot | P_slide | Q_old | Q_live | new-only | d(left) | "
            "d(right) | next valid |",
            "|---:|---:|---:|---|---|---:|---|---:|---:|---:|---:|---:|"
            "---:|---:|---:|---:|---:|---|---:|---:|---:|",
        ]
    )
    for row in shown:
        marker = "L" if row.get("left_selected") else "R" if row.get("right_selected") else ""
        center = ",".join(f"{float(value):.3f}" for value in row["center"])
        lines.append(
            f"| {row['old_across_candidate_rank']}/{row['across_candidate_rank']}"
            f"{marker} | {row['old_item_rank']}/{row['item_rank']} | "
            f"{row['old_within_item_rank']}/{row['within_item_rank']} | {row['kind']} | "
            f"{row['pool_index']}/{row['item_index']} | {row['orientation']} | "
            f"{center} | {_fmt(row['term_12v'])} | {_fmt(row['term_2r'])} | "
            f"{_fmt(row['term_depth'])} | {_fmt(row['term_x'])} | "
            f"{_fmt(row['term_z_mass'])} | {_fmt(row['term_route'])} | "
            f"{_fmt(row['p_rot'])} | {_fmt(row['p_slide'])} | "
            f"{_fmt(row['q_old'])} | {_fmt(row['q_active'])} | "
            f"{_fmt(row['new_search_only'])} | "
            f"{_fmt(row['margin_to_left_selected'])} | "
            f"{_fmt(row['margin_to_right_selected'])} | "
            f"{_fmt(row['next_valid_candidate_count'], 0)} |"
        )
    lines.extend(
        [
            "",
            "`d(left/right)` is selected score minus candidate score. A "
            "negative value means the candidate outranks the action that was "
            "actually selected under the reconstructed active score.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], output_dir: pathlib.Path, markdown_limit: int):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = report["candidates"]
    fields = [
        "candidate_id",
        "old_across_candidate_rank",
        "across_candidate_rank",
        "old_item_rank",
        "item_rank",
        "old_within_item_rank",
        "within_item_rank",
        "pool_index",
        "item_index",
        "container_index",
        "orientation",
        "kind",
        "center",
        "size",
        "term_12v",
        "term_2r",
        "term_depth",
        "term_x",
        "term_z_mass",
        "term_route",
        "p_rot",
        "p_slide",
        "q_old",
        "q_active",
        "left_search_reached",
        "right_search_reached",
        "new_search_only",
        "left_selected",
        "right_selected",
        "margin_to_left_selected",
        "margin_to_right_selected",
        "next_valid_candidate_count",
    ]
    with (output_dir / "candidates.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in sorted(rows, key=lambda value: value["across_candidate_rank"]):
            payload = dict(row)
            payload["center"] = json.dumps(payload["center"])
            payload["size"] = json.dumps(payload["size"])
            writer.writerow(payload)
    (output_dir / "report.md").write_text(
        render_markdown(report, markdown_limit), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--left-evaluation", type=pathlib.Path, required=True)
    parser.add_argument("--right-evaluation", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--candidate-jsonl", type=pathlib.Path)
    parser.add_argument("--left-search-jsonl", type=pathlib.Path)
    parser.add_argument("--right-search-jsonl", type=pathlib.Path)
    parser.add_argument(
        "--left-search-complete",
        action="store_true",
        help="treat absence from left search JSONL as proven not reached",
    )
    parser.add_argument(
        "--right-search-complete",
        action="store_true",
        help="treat absence from right search JSONL as proven not reached",
    )
    parser.add_argument("--collect-current-search-seconds", type=float)
    parser.add_argument("--rotation-lambda", type=float, default=1.0)
    parser.add_argument("--slide-lambda", type=float, default=0.5)
    parser.add_argument(
        "--next-count", choices=("none", "selected", "frontier", "all"), default="selected"
    )
    parser.add_argument("--frontier", type=int, default=20)
    parser.add_argument("--markdown-limit", type=int, default=100)
    parser.add_argument("--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    left_steps = load_case_steps(args.left_evaluation, args.case)
    right_steps = load_case_steps(args.right_evaluation, args.case)
    divergence = first_action_divergence(left_steps, right_steps)
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    if int(snapshot.get("step", -1)) != int(divergence["step"]):
        raise SystemExit(
            f"snapshot step {snapshot.get('step')} does not match first "
            f"divergence step {divergence['step']}"
        )
    observation = snapshot["observation"]
    agent_module = load_agent_module()

    enumeration = None
    if args.candidate_jsonl is not None:
        records = load_candidate_jsonl(args.candidate_jsonl)
        population_scope = f"JSONL rows from {args.candidate_jsonl.as_posix()}"
    else:
        records, enumeration = enumerate_population(agent_module, observation)
        population_scope = "complete policy-item oracle enumeration"
    rows = build_rows(
        agent_module,
        observation,
        records,
        rotation_lambda=args.rotation_lambda,
        slide_lambda=args.slide_lambda,
    )
    left_selected_id = match_action(rows, divergence.get("left"))
    right_selected_id = match_action(rows, divergence.get("right"))
    left_membership = load_search_membership(
        args.left_search_jsonl, complete=args.left_search_complete
    )
    right_membership = load_search_membership(
        args.right_search_jsonl, complete=args.right_search_complete
    )
    if args.collect_current_search_seconds is not None:
        if right_membership is not None:
            raise SystemExit(
                "use either --right-search-jsonl or "
                "--collect-current-search-seconds, not both"
            )
        right_membership = collect_current_search_ids(
            agent_module, observation, args.collect_current_search_seconds
        )
    left_membership = add_selected_evidence(
        left_membership, left_selected_id, "left"
    )
    right_membership = add_selected_evidence(
        right_membership, right_selected_id, "right"
    )
    annotate_ranks_and_membership(
        rows,
        left_membership=left_membership,
        right_membership=right_membership,
        left_selected_id=left_selected_id,
        right_selected_id=right_selected_id,
    )

    targets = select_next_count_rows(rows, args.next_count, args.frontier)
    for index, row in enumerate(targets, start=1):
        row["next_valid_candidate_count"] = next_surviving_valid_count(
            agent_module, observation, row, rows
        )
        print(
            f"next-count {index}/{len(targets)}: rank "
            f"{row['across_candidate_rank']} -> "
            f"{row['next_valid_candidate_count']}",
            flush=True,
        )

    report = {
        "schema_version": 2,
        "case_id": args.case,
        "snapshot": args.snapshot.as_posix(),
        "population_scope": population_scope,
        "rotation_lambda": float(args.rotation_lambda),
        "slide_lambda": float(args.slide_lambda),
        "next_count_contract": NEXT_COUNT_CONTRACT,
        "next_count_mode": args.next_count,
        "divergence": {
            **divergence,
            "left_selected_candidate_id": left_selected_id,
            "right_selected_candidate_id": right_selected_id,
        },
        "search_membership": {
            "left": (
                None
                if left_membership is None
                else {
                    "source": left_membership.source,
                    "reached": len(left_membership.reached_ids),
                    "absence_is_known": left_membership.observed_ids is None,
                    "observed": (
                        None
                        if left_membership.observed_ids is None
                        else len(left_membership.observed_ids)
                    ),
                    "forced_selected_ids": sorted(
                        left_membership.forced_selected_ids
                    ),
                }
            ),
            "right": (
                None
                if right_membership is None
                else {
                    "source": right_membership.source,
                    "reached": len(right_membership.reached_ids),
                    "absence_is_known": right_membership.observed_ids is None,
                    "observed": (
                        None
                        if right_membership.observed_ids is None
                        else len(right_membership.observed_ids)
                    ),
                    "forced_selected_ids": sorted(
                        right_membership.forced_selected_ids
                    ),
                }
            ),
        },
        "enumeration": enumeration,
        "candidates": rows,
    }
    write_outputs(report, args.output_dir, args.markdown_limit)
    print(args.output_dir / "report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
