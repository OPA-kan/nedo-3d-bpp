"""
Stage A', cheap diagnostic: was raw kappa's failure caused by ignoring physics?

`stage-a-calibrated-negative` measured that geometric acceptance capacity
does not explain placed-to-go, and showed why in its own table: release
capacity was the constant 0.113 on all 24 snapshots, release anchors stayed
in the thousands at to-go 0, and settled-zero states still placed five more
items. Capacity does not run out. Episodes end by release topple.

So this redefines an option from *geometrically placeable* to *placeable and
likely to survive settle*:

    kappa_c^safe(s) = sum over independent options j of class c  of  w_j

with w_j a survival weight from the two calibrated release models. This is
not a feature addition on top of raw kappa; it changes what an option is.

`sum(w_j)` is an **expected count of safe options**. It is not an episode
survival probability and must not be read as one.

The two risk models are separate, so P_fail does not exist yet. Rather than
inventing one, three combination rules are emitted side by side:

    w_sum     = max(0, 1 - P_rot - P_slide)   union-bound, conservative
    w_max     = 1 - max(P_rot, P_slide)       one instability, two observations
    w_product = (1 - P_rot)(1 - P_slide)      conditional independence

Agreement across all three is robustness. If exactly one moves the result,
that combination rule is itself a new hypothesis and has to be stated as one.
Settled options carry weight 1.0: both models are release-specific, so
`safe` and `raw` differ only where release options dominate - which is
exactly the saturated descriptor Stage A reported.

Labels are the physical-failure channel, not placed-to-go:

    Y_h(s) = 1[the episode reaches a settle failure within h steps of s]

A fixed horizon is used precisely because it is not censored: an episode that
ended safe contributes Y_h = 0 at every step, and an episode that toppled at
step N contributes Y_h = 1[N - t <= h]. `T_physical` is also emitted, with an
explicit censor flag, because it is only defined on the failing episodes.

Judgement is deliberately not a single number. The reported quantities are
per-class saturation, raw-vs-safe on the *same* snapshot, and rank agreement
with the physical label - in that order.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measure_residual_capacity import (  # noqa: E402
    anchors_conflict,
    load_agent_module,
    rebuild_case_items,
    remaining_classes,
)

SCHEMA_VERSION = 1
DEFAULT_STRIDE = 16
DEFAULT_ACCEPT_CAP = 64
WEIGHTINGS = ("raw", "sum", "max", "product")


def survival_weights(agent, candidate, item, container, orientation):
    """
    Per-option survival weights under the three combination rules.

    Settled options get 1.0 under every rule: both calibrated models are
    release-specific, so pretending otherwise would invent a number.
    """
    if candidate.name != "release_candidate":
        return {rule: 1.0 for rule in WEIGHTINGS[1:]} | {
            "p_rot": 0.0,
            "p_slide": 0.0,
            "modelled": False,
        }
    p_rot = float(
        agent.release_rotation_risk_probability_mech(
            float(candidate.center[0]),
            float(candidate.center[1]),
            float(candidate.center[2]),
            tuple(float(v) for v in candidate.size),
            container,
        )
    )
    p_slide = float(
        agent.release_large_slide_probability(
            candidate, item, container, int(orientation)
        )
    )
    return {
        "sum": max(0.0, 1.0 - p_rot - p_slide),
        "max": 1.0 - max(p_rot, p_slide),
        "product": (1.0 - p_rot) * (1.0 - p_slide),
        "p_rot": p_rot,
        "p_slide": p_slide,
        "modelled": True,
    }


def class_options(
    agent,
    observation: dict[str, Any],
    representative: dict[str, Any],
    *,
    stride: int,
    phase: int,
    accept_cap: int,
) -> list[dict[str, Any]]:
    """
    Sampled reachable options for one class, keeping the orientation.

    The orientation is dropped by the Stage A helper but the slide model
    needs it, so this re-derives the anchor list rather than reusing it.
    """
    container = observation["container_list"][0]
    options: list[dict[str, Any]] = []
    for kind in ("settled", "release"):
        for orientation in agent.unique_orientations(representative):
            produced = 0
            stream = agent.CandidateGenerator.iter_cartesian_attempts(
                observation,
                representative,
                0,
                orientation,
                limit=accept_cap,
                attempt_kind=kind,
                stride=stride,
                stride_offset=phase,
            )
            for candidate in stream:
                if candidate is None:
                    continue
                weights = survival_weights(
                    agent,
                    candidate,
                    representative,
                    container,
                    orientation,
                )
                options.append(
                    {
                        "candidate": candidate,
                        "kind": kind,
                        "orientation": int(orientation),
                        "weights": weights,
                    }
                )
                produced += 1
                if produced >= accept_cap:
                    break
    return options


def independent_options(agent, options: list[dict[str, Any]], count: int):
    """
    Greedy independent set inside one class, capped by its multiplicity.

    Same conflict rule and deterministic order as the Stage A bound, so a
    raw-vs-safe comparison is about the weights and nothing else.
    """
    clearance = float(agent.SETTLED_ITEM_CLEARANCE)
    chosen: list[dict[str, Any]] = []
    for option in options:
        if len(chosen) >= count:
            break
        if any(
            anchors_conflict(
                option["candidate"], taken["candidate"], clearance
            )
            for taken in chosen
        ):
            continue
        chosen.append(option)
    return chosen


def snapshot_capacity(
    agent,
    observation: dict[str, Any],
    item_list: list[dict[str, Any]],
    *,
    stride: int,
    phase: int,
    accept_cap: int,
) -> dict[str, Any]:
    packed = {
        int(entry["index"])
        for container in observation.get("container_list", [])
        for entry in container.get("packed_items", [])
    }
    classes = remaining_classes(item_list, packed)
    per_class = []
    totals = {rule: 0.0 for rule in WEIGHTINGS}
    release_share = []
    for entry in classes:
        options = class_options(
            agent,
            observation,
            entry["representative"],
            stride=stride,
            phase=phase,
            accept_cap=accept_cap,
        )
        chosen = independent_options(agent, options, entry["count"])
        row = {
            "signature": list(entry["signature"]),
            "multiplicity": int(entry["count"]),
            "volume": float(entry["volume"]),
            "sampled_options": len(options),
            "independent_options": len(chosen),
            "release_fraction": (
                round(
                    sum(1 for o in chosen if o["kind"] == "release")
                    / len(chosen),
                    4,
                )
                if chosen
                else None
            ),
        }
        row["kappa_raw"] = float(len(chosen))
        for rule in WEIGHTINGS[1:]:
            row[f"kappa_{rule}"] = round(
                sum(float(o["weights"][rule]) for o in chosen), 6
            )
        modelled = [o for o in chosen if o["weights"]["modelled"]]
        row["mean_p_rot"] = (
            round(statistics.fmean(o["weights"]["p_rot"] for o in modelled), 6)
            if modelled
            else None
        )
        row["mean_p_slide"] = (
            round(
                statistics.fmean(o["weights"]["p_slide"] for o in modelled), 6
            )
            if modelled
            else None
        )
        for rule in WEIGHTINGS:
            totals[rule] += row[f"kappa_{rule}"] if rule != "raw" else row[
                "kappa_raw"
            ]
        if row["release_fraction"] is not None:
            release_share.append(row["release_fraction"])
        per_class.append(row)
    return {
        "class_count": len(classes),
        "totals": {rule: round(totals[rule], 6) for rule in WEIGHTINGS},
        "mean_release_fraction": (
            round(statistics.fmean(release_share), 4)
            if release_share
            else None
        ),
        "per_class": per_class,
    }


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation with average ranks for ties."""
    n = len(xs)
    if n < 3:
        return None

    def ranks(values):
        order = sorted(range(n), key=lambda i: values[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            average = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = average
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(
        sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)
    )
    return round(num / den, 4) if den else None


def auc(scores: list[float], labels: list[int]) -> float | None:
    """Rank AUC with tie correction; None when a class is absent."""
    positives = [s for s, y in zip(scores, labels) if y == 1]
    negatives = [s for s, y in zip(scores, labels) if y == 0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for p in positives:
        for q in negatives:
            wins += 1.0 if p > q else 0.5 if p == q else 0.0
    return round(wins / (len(positives) * len(negatives)), 4)


def collect_snapshots(
    dataset_root: pathlib.Path,
    *,
    include_final_holdout: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    One row per saved state, carrying its episode's terminal channel.

    `Y_h` is exact for every row: an episode that ended safe never had a
    physical failure, and one that toppled did so at its last step.

    `final_holdout` datasets are skipped by default, matching the Stage A
    instrument and RELEASE_RISK_PROTOCOL 3.1. Skipped datasets are returned
    rather than silently dropped, so a run states its own coverage.
    """
    rows = []
    skipped: list[str] = []
    for manifest_path in sorted(dataset_root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("split") == "final_holdout"
            and not include_final_holdout
        ):
            skipped.append(manifest_path.parent.name)
            continue
        case = manifest.get("case") or {}
        final = case.get("final_status") or {}
        executed = case.get("episode_steps_executed")
        if executed is None:
            continue
        physical_failure = final.get("is_placed_safe") is False
        fallback_failure = final.get("is_valid") is False
        for step in case.get("steps", []):
            if step.get("status") != "ok" or not step.get("snapshot_path"):
                continue
            path = manifest_path.parent / step["snapshot_path"]
            if not path.exists():
                continue
            to_end = int(executed) - int(step["step"])
            rows.append(
                {
                    "snapshot": path.as_posix(),
                    "case_id": case.get("case_id"),
                    "step": int(step["step"]),
                    "steps_to_episode_end": to_end,
                    "terminal_channel": (
                        "physical"
                        if physical_failure
                        else "fallback"
                        if fallback_failure
                        else "terminal"
                    ),
                    "t_physical": to_end if physical_failure else None,
                    "t_physical_censored": not physical_failure,
                }
            )
    return rows, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=pathlib.Path,
        default=ROOT / "reports" / "replay-dataset",
    )
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    parser.add_argument("--phase", type=int, default=0)
    parser.add_argument("--accept-cap", type=int, default=DEFAULT_ACCEPT_CAP)
    parser.add_argument(
        "--horizon", type=int, action="append", default=[]
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--include-final-holdout",
        action="store_true",
        help="RELEASE_RISK_PROTOCOL 3.1: off unless deliberately opened",
    )
    args = parser.parse_args()

    horizons = sorted(set(args.horizon or [1, 3]))
    agent = load_agent_module()
    rows, skipped_holdout = collect_snapshots(
        args.dataset_root,
        include_final_holdout=args.include_final_holdout,
    )
    if args.limit > 0:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("no labelled snapshots found")

    for index, row in enumerate(rows, start=1):
        snapshot = json.loads(
            pathlib.Path(row["snapshot"]).read_text(encoding="utf-8")
        )
        observation = snapshot["observation"]
        item_list, _count = rebuild_case_items(row["case_id"])
        row["capacity"] = snapshot_capacity(
            agent,
            observation,
            item_list,
            stride=args.stride,
            phase=args.phase,
            accept_cap=args.accept_cap,
        )
        for h in horizons:
            row[f"y_{h}"] = int(
                row["terminal_channel"] == "physical"
                and row["steps_to_episode_end"] <= h
            )
        print(
            f"[{index}/{len(rows)}] {row['case_id']} step {row['step']} "
            f"kappa_raw={row['capacity']['totals']['raw']}",
            file=sys.stderr,
            flush=True,
        )

    analysis: dict[str, Any] = {"weightings": list(WEIGHTINGS), "rules": {}}
    for rule in WEIGHTINGS:
        scores = [float(r["capacity"]["totals"][rule]) for r in rows]
        entry: dict[str, Any] = {
            "mean": round(statistics.fmean(scores), 4),
            "stdev": round(statistics.pstdev(scores), 4),
            "constant": len(set(round(s, 6) for s in scores)) == 1,
            "distinct_values": len(set(round(s, 6) for s in scores)),
        }
        uncensored = [
            (float(r["capacity"]["totals"][rule]), int(r["t_physical"]))
            for r in rows
            if not r["t_physical_censored"]
        ]
        entry["n_uncensored"] = len(uncensored)
        entry["spearman_vs_t_physical"] = (
            spearman([a for a, _ in uncensored], [b for _, b in uncensored])
            if len(uncensored) >= 3
            else None
        )
        for h in horizons:
            entry[f"auc_vs_y_{h}"] = auc(
                scores, [int(r[f"y_{h}"]) for r in rows]
            )
        analysis["rules"][rule] = entry

    # Per-class saturation: a descriptor that is constant across snapshots
    # carries no information, which is how raw kappa failed in Stage A.
    by_signature: dict[str, dict[str, list[float]]] = {}
    for row in rows:
        for cls in row["capacity"]["per_class"]:
            key = "x".join(f"{v:.3f}" for v in cls["signature"])
            slot = by_signature.setdefault(
                key, {rule: [] for rule in WEIGHTINGS}
            )
            for rule in WEIGHTINGS:
                slot[rule].append(
                    float(
                        cls["kappa_raw"] if rule == "raw"
                        else cls[f"kappa_{rule}"]
                    )
                )
    saturation = {}
    for key, slot in by_signature.items():
        saturation[key] = {
            "observations": len(slot["raw"]),
            **{
                rule: {
                    "distinct": len(set(round(v, 6) for v in values)),
                    "constant": len(set(round(v, 6) for v in values)) == 1,
                    "stdev": round(statistics.pstdev(values), 4),
                }
                for rule, values in slot.items()
            },
        }
    analysis["per_class_saturation"] = saturation
    analysis["constant_class_fraction"] = {
        rule: round(
            sum(1 for s in saturation.values() if s[rule]["constant"])
            / len(saturation),
            4,
        )
        for rule in WEIGHTINGS
    } if saturation else {}

    report = {
        "schema_version": SCHEMA_VERSION,
        "settings": {
            "stride": args.stride,
            "phase": args.phase,
            "accept_cap": args.accept_cap,
            "horizons": horizons,
            "generator": "cartesian (Stage A instrument, kept for parity)",
        },
        "label_contract": {
            "y_h": "1 if the episode reaches a settle failure within h steps",
            "t_physical": "steps to settle failure; None when censored",
            "channels": "physical | fallback | terminal",
            "note": (
                "sum(w_j) is an expected count of safe options, not an "
                "episode survival probability."
            ),
        },
        "skipped_final_holdout_datasets": skipped_holdout,
        "label_counts": {
            "snapshots": len(rows),
            "by_channel": {
                channel: sum(
                    1 for r in rows if r["terminal_channel"] == channel
                )
                for channel in ("physical", "fallback", "terminal")
            },
            **{
                f"y_{h}_positive": sum(int(r[f"y_{h}"]) for r in rows)
                for h in horizons
            },
        },
        "analysis": analysis,
        "rows": rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        {
            "label_counts": report["label_counts"],
            "rules": analysis["rules"],
            "constant_class_fraction": analysis["constant_class_fraction"],
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
