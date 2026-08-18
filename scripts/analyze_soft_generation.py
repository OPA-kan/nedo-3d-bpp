"""Is the soft-clean placement generated, or only unretained?

Protocol: `reports/hazard/soft-generation-protocol.md`, whose three
measurements and reading thresholds were fixed before the wave ran.

`stack-aware-soft-tiebreak-has-no-reach-in-selection` established that
on 64 of 273 decisions the agent places something over a soft item while
every RETAINED alternative does the same. That leaves two readings with
different consequences: soft-clean candidates are produced and then
dropped by a score-ordered top-K (a bounded retention change), or they
are never produced (the generator, a much larger undertaking). This
script separates them from data two existing diagnostics already emit.

Inputs, per episode:

* `NEDO_CANDIDATE_AUDIT=1` -- `candidate_diagnostics.candidate_audit`
  on each decision, carrying every ACCEPTED candidate's `item_index`,
  `orientation`, `center` and `size` before retention.
* `NEDO_POSE_SNAPSHOT=1` -- the packed items' poses, dimensions and
  attribute flags at that same step.

The violation counts are computed here rather than in the agent on
purpose: doing it inside the candidate loop would perturb the
deadline-bound trajectory it measures.

The audit does not carry a candidate's score, so this answers EXISTENCE
only. What a soft-clean candidate costs in score is a separate question
and is deliberately not estimated here.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import statistics
from typing import Any

CONTACT_TOLERANCE = 0.02  # simulator/src/ground_handling/diagnostics.py
FOOTPRINT_EPSILON = 1e-6

G2_RETENTION_THRESHOLD = 0.5
G2_GENERATOR_THRESHOLD = 0.1


def aabb_from_pose(pos, orn, dims):
    x, y, z, w = orn
    rot = (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )
    half = [d / 2 for d in dims]
    ext = [
        sum(abs(rot[i][j]) * half[j] for j in range(3)) for i in range(3)
    ]
    return (
        [pos[i] - ext[i] for i in range(3)],
        [pos[i] + ext[i] for i in range(3)],
    )


def aabb_from_center_size(center, size):
    half = [s / 2 for s in size]
    return (
        [center[i] - half[i] for i in range(3)],
        [center[i] + half[i] for i in range(3)],
    )


def footprint_overlap(a, b) -> float:
    dx = min(a[1][0], b[1][0]) - max(a[0][0], b[0][0])
    dy = min(a[1][1], b[1][1]) - max(a[0][1], b[0][1])
    return max(0.0, dx) * max(0.0, dy)


def stack_soft_violations(candidate_bb, packed, mover_is_soft: bool) -> int:
    """Soft items the mover would cover, stack-aware.

    Same predicate as candidate_attribute_violations(stack_aware=True):
    footprint overlap, and the mover's bottom at or above the protected
    top by CONTACT_TOLERANCE. Same-attribute stacking is allowed,
    mirroring the official definition.
    """
    if mover_is_soft:
        return 0
    bottom = candidate_bb[0][2]
    violations = 0
    for item in packed:
        if not item["soft"]:
            continue
        if bottom < item["bb"][1][2] - CONTACT_TOLERANCE:
            continue
        if footprint_overlap(candidate_bb, item["bb"]) <= FOOTPRINT_EPSILON:
            continue
        violations += 1
    return violations


def load_steps(trace_path: str) -> list[dict[str, Any]]:
    """Join each decision's audit with the pose snapshot of its step."""
    snapshots: dict[int, list[dict]] = {}
    decisions: list[dict] = []
    for line in open(trace_path, encoding="utf-8"):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = event.get("event")
        if kind == "pose_snapshot":
            packed = []
            for container in event.get("containers", []):
                for item in container.get("packed_items", []):
                    packed.append(
                        {
                            "bb": aabb_from_pose(
                                item["pos"], item["orn"], item["dims"]
                            ),
                            "soft": bool(item["is_soft"]),
                        }
                    )
            snapshots[event.get("step")] = packed
        elif kind == "decision":
            decisions.append(event)

    steps = []
    for decision in decisions:
        step = decision.get("step")
        packed = snapshots.get(step)
        if packed is None:
            continue
        audit = (decision.get("candidate_diagnostics") or {}).get(
            "candidate_audit"
        )
        if not audit:
            continue
        accepted = []
        for search in audit:
            accepted.extend(search.get("accepted_settled", []))
            accepted.extend(search.get("accepted_release", []))
        if not accepted:
            continue
        steps.append(
            {
                "step": step,
                "packed": packed,
                "accepted": accepted,
                "chosen_item_index": decision.get("selected_item_index"),
                "action_command": decision.get("action_command"),
            }
        )
    return steps


def analyze_episode(trace_path: str, soft_item_indices: set[int]) -> list[dict]:
    rows = []
    for step in load_steps(trace_path):
        packed = step["packed"]
        if not any(item["soft"] for item in packed):
            continue
        chosen_index = step["chosen_item_index"]
        best_by_item: dict[int, int] = {}
        chosen_violations = None
        for record in step["accepted"]:
            item_index = record.get("item_index")
            mover_is_soft = item_index in soft_item_indices
            bb = aabb_from_center_size(record["center"], record["size"])
            violations = stack_soft_violations(bb, packed, mover_is_soft)
            previous = best_by_item.get(item_index)
            if previous is None or violations < previous:
                best_by_item[item_index] = violations
        # The chosen placement's own violation count, from the audit
        # record that matches the played command where one exists.
        command = step["action_command"] or {}
        for record in step["accepted"]:
            if record.get("item_index") != chosen_index:
                continue
            if record.get("orientation") != command.get("orientation"):
                continue
            bb = aabb_from_center_size(record["center"], record["size"])
            violations = stack_soft_violations(
                bb, packed, chosen_index in soft_item_indices
            )
            if chosen_violations is None or violations < chosen_violations:
                chosen_violations = violations
        if chosen_violations is None:
            chosen_violations = best_by_item.get(chosen_index)
        if chosen_violations is None or chosen_violations == 0:
            continue

        same_item_best = best_by_item.get(chosen_index)
        other_best = min(
            (
                value
                for key, value in best_by_item.items()
                if key != chosen_index
            ),
            default=None,
        )
        overall_best = min(best_by_item.values())
        rows.append(
            {
                "trace": pathlib.Path(trace_path).parent.name,
                "step": step["step"],
                "accepted": len(step["accepted"]),
                "chosen_violations": chosen_violations,
                "best_any": overall_best,
                "best_same_item": same_item_best,
                "best_other_item": other_best,
            }
        )
    return rows


def summarize(rows: list[dict]) -> dict[str, Any]:
    total = len(rows)
    g1 = sum(1 for r in rows if r["best_any"] < r["chosen_violations"])
    g2 = sum(1 for r in rows if r["best_any"] == 0)
    clean_same = sum(
        1 for r in rows if r["best_same_item"] == 0
    )
    clean_other = sum(
        1
        for r in rows
        if r["best_other_item"] is not None and r["best_other_item"] == 0
    )
    fraction_g2 = (g2 / total) if total else 0.0
    if fraction_g2 >= G2_RETENTION_THRESHOLD:
        reading = "retention"
    elif fraction_g2 < G2_GENERATOR_THRESHOLD:
        reading = "generation"
    else:
        reading = "ambiguous"
    return {
        "decisions_with_a_violating_choice": total,
        "G1_some_accepted_candidate_is_better": {
            "hits": g1,
            "fraction": (g1 / total) if total else 0.0,
        },
        "G2_some_accepted_candidate_is_clean": {
            "hits": g2,
            "fraction": fraction_g2,
        },
        "G3_split": {
            "clean_available_for_the_same_item": clean_same,
            "clean_available_for_another_item": clean_other,
        },
        "mean_accepted_candidates": (
            statistics.fmean(r["accepted"] for r in rows) if rows else None
        ),
        "thresholds": {
            "retention_at_or_above": G2_RETENTION_THRESHOLD,
            "generation_below": G2_GENERATOR_THRESHOLD,
        },
        "reading": reading,
    }


def render_markdown(result: dict, rows: list[dict]) -> str:
    g1 = result["G1_some_accepted_candidate_is_better"]
    g2 = result["G2_some_accepted_candidate_is_clean"]
    split = result["G3_split"]
    total = result["decisions_with_a_violating_choice"]
    lines = [
        "# Is the soft-clean placement generated, or only unretained?",
        "",
        "Protocol: `reports/hazard/soft-generation-protocol.md`. "
        "Measurements and reading thresholds fixed before the wave. "
        "Computed offline from `NEDO_CANDIDATE_AUDIT` and "
        "`NEDO_POSE_SNAPSHOT`; no agent change and no hot-path work.",
        "",
        f"- decisions where the played placement covers a soft item: "
        f"**{total}**",
        f"- accepted candidates per such decision (mean): "
        f"{result['mean_accepted_candidates']:.0f}"
        if result["mean_accepted_candidates"]
        else "- accepted candidates per such decision: -",
        "",
        "| measurement | hits | fraction |",
        "|---|---:|---:|",
        f"| G1 some accepted candidate covers fewer | {g1['hits']}/{total} "
        f"| {g1['fraction']:.1%} |",
        f"| **G2 some accepted candidate covers none** | "
        f"{g2['hits']}/{total} | **{g2['fraction']:.1%}** |",
        "",
        "| G3 split | decisions |",
        "|---|---:|",
        f"| a clean candidate exists for the SAME item | "
        f"{split['clean_available_for_the_same_item']} |",
        f"| a clean candidate exists for ANOTHER item | "
        f"{split['clean_available_for_another_item']} |",
        "",
        f"## Reading: **{result['reading']}**",
        "",
    ]
    if result["reading"] == "retention":
        lines += [
            "The placements exist and are being dropped. The lever is "
            "retention diversity and its size is bounded by G1/G2. A "
            "retention arm becomes preregisterable, and per the protocol "
            "it must be a diversity constraint at FIXED K -- widening K "
            "is what the item-cap experiments did, and they failed fresh "
            "permutations twice.",
        ]
    elif result["reading"] == "generation":
        lines += [
            "The generator does not produce soft-clean placements in "
            "these states, so retention diversity is empty. Say so and "
            "stop: this result alone does not license opening the "
            "generator.",
        ]
    else:
        lines += [
            "Ambiguous by the preregistered thresholds. No arm is "
            "licensed; the numbers and the G3 split are the finding.",
        ]
    lines += [
        "",
        "## What this does not answer",
        "",
        "The audit carries no score, so this is existence only. What a "
        "soft-clean candidate gives up in score -- and therefore whether "
        "a retention change could take one without losing placed -- is a "
        "separate question, deliberately not estimated here.",
        "",
        "The audit's own recording cost changes the trajectory, so these "
        "episodes' placed and fill are not comparable with another "
        "wave's.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", action="append", required=True)
    parser.add_argument("--configs", action="append", required=True)
    parser.add_argument("--output-json", type=pathlib.Path, required=True)
    parser.add_argument("--output-md", type=pathlib.Path)
    args = parser.parse_args()

    soft_by_case: dict[str, set[int]] = {}
    for pattern in args.configs:
        for path in sorted(glob.glob(pattern)):
            for case, cfg in json.loads(
                pathlib.Path(path).read_text(encoding="utf-8")
            ).items():
                soft_by_case[case] = {
                    int(item["index"])
                    for item in cfg["item_stream"]["item_list"]
                    if item.get("is_soft")
                }

    rows: list[dict] = []
    for pattern in args.traces:
        for trace in sorted(glob.glob(pattern)):
            case = os.path.basename(os.path.dirname(trace)).rsplit("-", 2)[0]
            soft_indices = soft_by_case.get(case)
            if soft_indices is None:
                continue
            rows.extend(analyze_episode(trace, soft_indices))
    if not rows:
        raise SystemExit(
            "no decisions with a violating played placement were found; "
            "was the wave run with --candidate-audit?"
        )

    result = summarize(rows)
    result["rows"] = rows
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(args.output_json)
    if args.output_md:
        args.output_md.write_text(
            render_markdown(result, rows), encoding="utf-8"
        )
        print(args.output_md)
    print(
        json.dumps(
            {
                "decisions": result["decisions_with_a_violating_choice"],
                "G2": result["G2_some_accepted_candidate_is_clean"][
                    "fraction"
                ],
                "reading": result["reading"],
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
