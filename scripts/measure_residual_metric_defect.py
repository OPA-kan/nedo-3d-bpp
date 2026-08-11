"""
The residual metric compares two coordinate frames. Measure what that cost.

`state-NNN.json` states the contract plainly: `candidate_positions` are
container-local and `packed_item_positions` are world. The replayed `x_plus`
position is world too. So `residual_proxy_distance` is applied to
container-local coordinates in the overdraw stage and to world coordinates in
the final observed stage, and on a two-container board those frames differ by
the container spacing -- measured here at 2.5 m, against item extents of tens
of centimetres.

Three consequences, none of them intended:

* a cross-container pair is near-maximally distant in the observed metric
  whatever the items actually did, because the 2.5 m offset saturates the
  normalised position term;
* container membership is then counted twice, once through that offset and
  again through the `container_index` categorical field;
* the command proxy does the opposite -- two candidates at the same local
  spot in different containers look almost identical to it.

The swap optimizer maximises the observed metric, so on a two-container board
"more diverse" partly means "one from each container", which is not what the
metric was meant to say.

This script does not change any of that. It measures it, on the retained
corpus, so the fix has a basis and the existing ledger entries can be read
correctly. The question it answers is the one that matters for those entries:
**does the optimizer still beat its paired control once both arms are scored
in a single frame?**
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.residual_diversity import (  # noqa: E402
    component_mean_nn,
    container_frame_offsets,
    nearest_neighbor_distances,
    proxy_feature_vector,
    scale_vector,
    settled_proxy_record,
)

POSITIVE = "positive_transition"
CONTROL = "positive_transition_random_control"


def mean_nn(records: list[dict[str, Any]], reference) -> float | None:
    if len(records) < 2:
        return None
    scales = scale_vector([proxy_feature_vector(r) for r in reference])
    nearest = nearest_neighbor_distances(
        [proxy_feature_vector(r) for r in records], scales=scales
    )
    return sum(nearest) / len(nearest) if nearest else None


def load_board(path: pathlib.Path) -> dict[str, Any] | None:
    """One board's positive and control arms, in both frames.

    Both descriptors come from `settled_proxy_record`, the same function the
    dataset builder calls -- the corrected arm just gets the container
    offsets. Rebuilding the shift here would let the measurement and the
    shipped path drift apart, which is exactly the failure being measured.
    """
    step = path.name.split("-")[1]
    snapshot_path = path.parent / f"step-{step}-state.json"
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    containers = (snapshot.get("observation") or {}).get("container_list")
    offsets = container_frame_offsets(containers)

    arms: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    local: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for suffix, role in (
        ("candidates", POSITIVE),
        ("random-control", CONTROL),
    ):
        rows_path = path.parent / f"step-{step}-{suffix}.jsonl"
        if not rows_path.exists():
            continue
        with rows_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                physical = row.get("physical")
                settled = settled_proxy_record(row, physical)
                shifted = settled_proxy_record(
                    row, physical, container_offsets=offsets
                )
                if settled is not None and shifted is not None:
                    arms[role].append(settled)
                    local[role].append(shifted)
    if len(arms[POSITIVE]) < 2 or len(arms[CONTROL]) < 2:
        return None
    return {
        "case_id": path.parent.name,
        "step": int(step),
        "containers": len(offsets),
        "arms": dict(arms),
        "local_arms": dict(local),
    }


def score(board: dict[str, Any]) -> dict[str, Any]:
    """The guard's delta, as reported and after collapsing to one frame."""
    positive = board["arms"][POSITIVE]
    control = board["arms"][CONTROL]
    reference = control + positive

    local_positive = board["local_arms"][POSITIVE]
    local_control = board["local_arms"][CONTROL]
    local_reference = local_control + local_positive

    as_reported = mean_nn(positive, reference)
    control_reported = mean_nn(control, reference)
    as_local = mean_nn(local_positive, local_reference)
    control_local = mean_nn(local_control, local_reference)

    def delta(a, b):
        return None if a is None or b is None else a - b

    return {
        "case_id": board["case_id"],
        "step": board["step"],
        "containers": board["containers"],
        "positive_rows": len(positive),
        "control_rows": len(control),
        "delta_as_reported": delta(as_reported, control_reported),
        "delta_single_frame": delta(as_local, control_local),
        # The two components the single sum was averaging together, each in
        # the corrected frame.
        "delta_occupancy": delta(
            component_mean_nn(local_positive, local_reference, "occupancy"),
            component_mean_nn(local_control, local_reference, "occupancy"),
        ),
        "delta_consumption": delta(
            component_mean_nn(local_positive, local_reference, "consumption"),
            component_mean_nn(local_control, local_reference, "consumption"),
        ),
    }


def measure(root: pathlib.Path) -> dict[str, Any]:
    boards = [
        scored
        for path in sorted(root.glob("*/dataset/*/step-*-candidates.jsonl"))
        if (board := load_board(path)) is not None
        and (scored := score(board))["delta_as_reported"] is not None
        and scored["delta_single_frame"] is not None
    ]
    if not boards:
        return {"verdict": "no_scorable_boards"}

    def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
        def column(name: str) -> list[float]:
            return [
                row[name] for row in rows if row.get(name) is not None
            ]

        summary = {
            "boards": len(rows),
            "mean_delta_as_reported": sum(column("delta_as_reported"))
            / len(rows),
            "mean_delta_single_frame": sum(column("delta_single_frame"))
            / len(rows),
            "boards_positive_as_reported": sum(
                v > 0 for v in column("delta_as_reported")
            ),
            "boards_positive_single_frame": sum(
                v > 0 for v in column("delta_single_frame")
            ),
        }
        for name in ("delta_occupancy", "delta_consumption"):
            values = column(name)
            summary[f"mean_{name}"] = (
                sum(values) / len(values) if values else None
            )
            summary[f"boards_positive_{name}"] = sum(v > 0 for v in values)
            # Ties are not losses. On the consumption axis both arms often
            # draw the same item set, and reading "positive" against "scored"
            # would count those boards against the optimizer.
            summary[f"boards_tied_{name}"] = sum(v == 0 for v in values)
            summary[f"boards_negative_{name}"] = sum(v < 0 for v in values)
            summary[f"boards_scored_{name}"] = len(values)
        return summary

    multi = [row for row in boards if row["containers"] > 1]
    single = [row for row in boards if row["containers"] <= 1]
    report = {
        "schema_version": 1,
        "all_boards": summarise(boards),
        "multi_container_boards": summarise(multi) if multi else None,
        "single_container_boards": summarise(single) if single else None,
        "boards": boards,
        "contract": (
            "delta_as_reported is the acceptance guard's own number: mean "
            "nearest-neighbour distance of the positive arm minus the paired "
            "control, over settled x_plus in WORLD coordinates. "
            "delta_single_frame is the same quantity with settled positions "
            "shifted back into their own container's frame, so container "
            "membership is carried once, by container_index, instead of "
            "also by a 2.5 m offset in the position term. Single-container "
            "boards are unaffected by construction and are reported "
            "separately as the control on this control."
        ),
    }
    survives = (
        report["all_boards"]["mean_delta_single_frame"] > 0.0
        and (
            multi is None
            or not multi
            or report["multi_container_boards"]["mean_delta_single_frame"]
            > 0.0
        )
    )
    report["verdict"] = (
        "optimizer_gain_survives_one_frame"
        if survives
        else "optimizer_gain_was_the_frame"
    )
    return report


def markdown(report: dict[str, Any]) -> str:
    if "all_boards" not in report:
        return (
            "# Residual metric frame\n\n"
            f"- Verdict: **{report['verdict']}**\n"
        )
    lines = [
        "# Residual metric: the two coordinate frames, and what they cost",
        "",
        f"- Verdict: **{report['verdict']}**",
        "",
        "| board set | boards | mean delta as reported | "
        "mean delta in one frame | boards > 0 reported | "
        "boards > 0 one frame |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, key in (
        ("all", "all_boards"),
        ("multi-container", "multi_container_boards"),
        ("single-container (control)", "single_container_boards"),
    ):
        block = report.get(key)
        if not block:
            continue
        lines.append(
            f"| {name} | {block['boards']} | "
            f"{block['mean_delta_as_reported']:+.6f} | "
            f"{block['mean_delta_single_frame']:+.6f} | "
            f"{block['boards_positive_as_reported']} | "
            f"{block['boards_positive_single_frame']} |"
        )
    lines.extend(
        [
            "",
            "## the two components the sum was averaging together",
            "",
            "Occupancy is where the item landed and in which container; "
            "consumption is which item was taken out of the pool. A single "
            "Gower sum averages them, and cannot say which one moved.",
            "",
            "| board set | mean Δ occupancy | win/tie/loss | "
            "mean Δ consumption | win/tie/loss |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for name, key in (
        ("all", "all_boards"),
        ("multi-container", "multi_container_boards"),
        ("single-container", "single_container_boards"),
    ):
        block = report.get(key)
        if not block:
            continue

        def cell(component: str) -> str:
            mean = block.get(f"mean_{component}")
            record = "/".join(
                str(block.get(f"boards_{outcome}_{component}", 0))
                for outcome in ("positive", "tied", "negative")
            )
            shown = "—" if mean is None else f"{mean:+.6f}"
            return f"{shown} | {record}"

        lines.append(
            f"| {name} | {cell('delta_occupancy')} | "
            f"{cell('delta_consumption')} |"
        )
    lines.extend(["", report["contract"], ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    report = measure(args.root)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=float) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
