"""Why the local soft proxy reads ~98 while the official score reads ~20.

The published rule is one line (`docs/COMPETITION_RULES.md`): "soft手荷物
の上への通常荷物配置による破損リスク" -- the breakage risk of placing an
ordinary item ON TOP OF a soft one. Both the bundled diagnostic
(`calculate_attribute_placement` via `_covers_from_above`) and the
agent's own `candidate_attribute_violations` implement that as DIRECT
CONTACT: the upper item's bottom must sit within `CONTACT_TOLERANCE`
(2 cm) of the soft item's top.

That reading is almost never violated in a real pile, and the numbers
say so. This script recomputes soft coverage on recorded terminal states
under a family of rule readings, so the choice can be argued from
measurement rather than from how the sentence sounds.

Inputs are `pose_snapshot` trace events (NEDO_POSE_SNAPSHOT=1), which
carry every packed item's pose, dimensions and attribute flags, plus the
episode config for the number of soft items in the whole stream. No new
physics is spent.

The variants differ on two independent axes:

* **predicate** -- `contact` (upper bottom within CONTACT_TOLERANCE of
  the soft top, the current reading) versus `above` (upper bottom at or
  above the soft top, i.e. anything resting anywhere over it, load
  carried through a stack included).
* **denominator** -- soft items PLACED, versus every soft item in the
  stream with the unplaced ones charged as lost.

and on whether a soft item under three ordinary items counts once or
three times (`pairs`).

None of this identifies the official rule; the official normalization
and scene set are both unpublished. What it does is bound the gap and
locate which structural choice carries it.
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


def aabb(pos, orn, dims):
    """Axis-aligned bounds of an oriented box, from the recorded pose."""
    x, y, z, w = orn
    rot = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    half = [d / 2 for d in dims]
    ext = [
        sum(abs(rot[i][j]) * half[j] for j in range(3)) for i in range(3)
    ]
    return (
        [pos[i] - ext[i] for i in range(3)],
        [pos[i] + ext[i] for i in range(3)],
    )


def footprint_overlap(a, b) -> float:
    dx = min(a[1][0], b[1][0]) - max(a[0][0], b[0][0])
    dy = min(a[1][1], b[1][1]) - max(a[0][1], b[0][1])
    return max(0.0, dx) * max(0.0, dy)


def count_violations(items, predicate: str) -> tuple[int, int]:
    """(soft items violated, violating (soft, ordinary) pairs)."""
    violated = 0
    pairs = 0
    for lower in items:
        if not lower["soft"]:
            continue
        hit = False
        for upper in items:
            if upper is lower or upper["soft"]:
                continue
            if footprint_overlap(lower["bb"], upper["bb"]) <= FOOTPRINT_EPSILON:
                continue
            gap = upper["bb"][0][2] - lower["bb"][1][2]
            covered = (
                -CONTACT_TOLERANCE <= gap <= CONTACT_TOLERANCE
                if predicate == "contact"
                else gap >= -CONTACT_TOLERANCE
            )
            if covered:
                pairs += 1
                hit = True
        violated += int(hit)
    return violated, pairs


def load_episodes(trace_globs, config_globs) -> list[dict[str, Any]]:
    stream_soft: dict[str, int] = {}
    for pattern in config_globs:
        for path in sorted(glob.glob(pattern)):
            for case, cfg in json.loads(
                pathlib.Path(path).read_text(encoding="utf-8")
            ).items():
                stream_soft[case] = sum(
                    1
                    for item in cfg["item_stream"]["item_list"]
                    if item.get("is_soft")
                )

    episodes = []
    for pattern in trace_globs:
        for trace in sorted(glob.glob(pattern)):
            snapshots = []
            for line in open(trace, encoding="utf-8"):
                if '"pose_snapshot"' not in line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("event") == "pose_snapshot":
                    snapshots.append(event)
            if not snapshots:
                continue
            items = []
            for container in snapshots[-1]["containers"]:
                for item in container["packed_items"]:
                    items.append(
                        {
                            "bb": aabb(
                                item["pos"], item["orn"], item["dims"]
                            ),
                            "soft": bool(item["is_soft"]),
                        }
                    )
            label = os.path.basename(os.path.dirname(trace))
            case = label.rsplit("-", 2)[0]
            if case not in stream_soft:
                continue
            episodes.append(
                {
                    "label": label,
                    "case_id": case,
                    "items": items,
                    "placed_soft": sum(1 for i in items if i["soft"]),
                    "stream_soft": stream_soft[case],
                }
            )
    return episodes


VARIANTS = (
    ("V0_contact_over_placed", "contact", "placed", False),
    ("V1_above_over_placed", "above", "placed", False),
    ("V2_contact_over_stream", "contact", "stream", False),
    ("V3_above_over_stream", "above", "stream", False),
    ("V4_above_pairs_over_placed", "above", "placed", True),
    ("V5_above_pairs_over_stream", "above", "stream", True),
)


def clean_ratio(violations: int, total: int) -> float | None:
    if total == 0:
        return None
    return max(0.0, (total - violations) / total)


def analyze(episodes, official_soft: float) -> dict[str, Any]:
    counts = {
        e["label"]: {
            "contact": count_violations(e["items"], "contact"),
            "above": count_violations(e["items"], "above"),
        }
        for e in episodes
    }
    variants = {}
    for name, predicate, denominator, use_pairs in VARIANTS:
        values = []
        for episode in episodes:
            violated, pairs = counts[episode["label"]][predicate]
            charged = pairs if use_pairs else violated
            if denominator == "placed":
                ratio = clean_ratio(charged, episode["placed_soft"])
            else:
                unplaced = episode["stream_soft"] - episode["placed_soft"]
                ratio = clean_ratio(
                    charged + unplaced, episode["stream_soft"]
                )
            if ratio is not None:
                values.append(ratio)
        mean = statistics.fmean(values) if values else None
        variants[name] = {
            "predicate": predicate,
            "denominator": denominator,
            "pairs": use_pairs,
            "mean_clean_ratio": mean,
            "scaled_to_100": None if mean is None else mean * 100,
            "gap_to_official": (
                None if mean is None else abs(mean * 100 - official_soft)
            ),
            "episodes": len(values),
        }
    return {
        "episodes": len(episodes),
        "official_soft_item_score": official_soft,
        "mean_placed_soft": statistics.fmean(
            e["placed_soft"] for e in episodes
        ),
        "mean_stream_soft": statistics.fmean(
            e["stream_soft"] for e in episodes
        ),
        "mean_violated_soft_items": {
            "contact": statistics.fmean(
                counts[e["label"]]["contact"][0] for e in episodes
            ),
            "above": statistics.fmean(
                counts[e["label"]]["above"][0] for e in episodes
            ),
        },
        "mean_violating_pairs": {
            "contact": statistics.fmean(
                counts[e["label"]]["contact"][1] for e in episodes
            ),
            "above": statistics.fmean(
                counts[e["label"]]["above"][1] for e in episodes
            ),
        },
        "episodes_with_zero_violations": {
            "contact": sum(
                1 for e in episodes if counts[e["label"]]["contact"][0] == 0
            ),
            "above": sum(
                1 for e in episodes if counts[e["label"]]["above"][0] == 0
            ),
        },
        "variants": variants,
    }


def render_markdown(result: dict) -> str:
    zero = result["episodes_with_zero_violations"]
    total = result["episodes"]
    lines = [
        "# The soft rule gap: our proxy reads ~98, the official score ~20",
        "",
        "Generated by `scripts/analyze_soft_rule_gap.py` from recorded "
        "`pose_snapshot` traces. No new physics.",
        "",
        f"- episodes: {total}",
        f"- official `soft_item_score` (latest submission): "
        f"{result['official_soft_item_score']}",
        f"- mean soft items placed: {result['mean_placed_soft']:.2f} of "
        f"{result['mean_stream_soft']:.2f} in the stream",
        "",
        "## Rule readings",
        "",
        "`contact` is the current reading in both the bundled diagnostic "
        "and the agent: an ordinary item violates a soft item only if its "
        "bottom sits within 2 cm of the soft item's top. `above` charges "
        "any ordinary item resting anywhere over the soft one, load "
        "carried through a stack included.",
        "",
        "| variant | predicate | denominator | pairs | x100 | gap to official |",
        "|---|---|---|---|---:|---:|",
    ]
    for name, stats in result["variants"].items():
        lines.append(
            f"| `{name}` | {stats['predicate']} | {stats['denominator']} | "
            f"{'yes' if stats['pairs'] else 'no'} | "
            f"{stats['scaled_to_100']:.2f} | "
            f"{stats['gap_to_official']:.2f} |"
        )
    lines += [
        "",
        "## The operative number",
        "",
        f"- soft items violated per episode: "
        f"**{result['mean_violated_soft_items']['contact']:.2f}** under "
        f"`contact`, "
        f"**{result['mean_violated_soft_items']['above']:.2f}** under "
        f"`above`",
        f"- violating pairs per episode: "
        f"{result['mean_violating_pairs']['contact']:.2f} under `contact`, "
        f"{result['mean_violating_pairs']['above']:.2f} under `above`",
        f"- episodes with ZERO violations: "
        f"**{zero['contact']}/{total}** under `contact`, "
        f"{zero['above']}/{total} under `above`",
        "",
        "The agent optimizes the `contact` reading "
        "(`candidate_attribute_violations`, agent/agent.py, the "
        "`abs(bottom - lower.top) > CONTACT_TOLERANCE: continue` guard). "
        "On most episodes that predicate is identically zero, so the soft "
        "axis carries no gradient at all: there is nothing for a filter, a "
        "guard or a ranking term to act on. That is the mechanical reason "
        "the preregistered attribute filter came back inert.",
        "",
        "## What this does and does not establish",
        "",
        "- It does NOT identify the official rule. The official "
        "normalization and scene set are unpublished, and the closest "
        "variant here is still several points away on development "
        "configs.",
        "- It DOES bound the gap and locate it. The proxy is roughly five "
        "times optimistic, and the single structural choice carrying most "
        "of that is direct-contact versus stack-aware.",
        "- It does NOT license a hard attribute gate. That was measured "
        "and closed for placed cost (`release attribute hard reject`); a "
        "stricter predicate would cost more, not less.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traces", action="append", required=True)
    parser.add_argument("--configs", action="append", required=True)
    parser.add_argument("--official-soft", type=float, default=19.65)
    parser.add_argument("--output-json", type=pathlib.Path, required=True)
    parser.add_argument("--output-md", type=pathlib.Path)
    args = parser.parse_args()

    episodes = load_episodes(args.traces, args.configs)
    if not episodes:
        raise SystemExit("no episodes with pose_snapshot traces matched")
    result = analyze(episodes, args.official_soft)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(args.output_json)
    if args.output_md:
        args.output_md.write_text(
            render_markdown(result), encoding="utf-8"
        )
        print(args.output_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
