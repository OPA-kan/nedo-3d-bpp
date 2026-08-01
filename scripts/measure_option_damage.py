"""
Does a placement destroy the remaining option space, or convert it?

The viability framing needs two claims to be true that have not been
measured, and one of them is very likely false as stated:

    s not in K  =>  T_a(s) not in K          (irreversibility)
    soft dominates rigid on the option family (soft as a dominating operator)

Free volume is monotone under placement, but a typed option count is not
obviously so: a placement also creates flat support, levels heights, and can
open an anchor for a class that had none. So this measures the typed delta
across a *real* placement rather than assuming its sign:

    Delta kappa_type = kappa_type(T_a(s)) - kappa_type(s)

and reports how often each type goes **up**. One increase is a
counterexample to unconditional irreversibility; a type that never increases
is a candidate for the `K_irreversible` component of a split viability set.

Types follow the option family rather than the item table: options are
grouped by the attribute that decides which future baggage can use them -
`priority`, `soft`, and `rigid` - so `Delta` can be read per type instead of
as one scalar. The soft-versus-rigid question is then not "which is bigger"
but which components move in which direction, which is the shape a
type-converting operator would leave.

Successor states are the **realised** ones: the item at `x_plus`, the pose
the official validator actually observed. For a question about what a
placement did to the container, the proxy pose would be answering a
different question.

Corridor is tracked separately from option count, because the two are
claimed to have different reversibility. `corridor_blocked` counts anchors
the transport check rejected; `has_option` is whether any option survived at
all.
"""
from __future__ import annotations

import argparse
import copy
import json
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
)

SCHEMA_VERSION = 1
DEFAULT_STRIDE = 16
DEFAULT_ACCEPT_CAP = 32
DIMS_ROUND = 4
TYPES = ("priority", "soft", "rigid")


def option_type(item: dict[str, Any]) -> str:
    """
    Which future baggage a surviving option serves.

    Priority is checked before soft: a prioritised soft item is routed by
    its priority, so counting it as `soft` would put it in a type whose
    options cannot serve it.
    """
    if bool(item.get("is_prioritized", False)):
        return "priority"
    if bool(item.get("is_soft", False)):
        return "soft"
    return "rigid"


def typed_classes(
    item_list: list[dict[str, Any]],
    packed_indices: set[int],
) -> list[dict[str, Any]]:
    """Remaining classes, keyed by dims *and* the attributes that type them."""
    classes: dict[tuple, dict[str, Any]] = {}
    for item in item_list:
        if int(item["index"]) in packed_indices:
            continue
        signature = (
            tuple(
                round(float(item[key]), DIMS_ROUND)
                for key in ("length", "width", "height")
            ),
            bool(item.get("is_soft", False)),
            bool(item.get("is_prioritized", False)),
        )
        entry = classes.get(signature)
        if entry is None:
            classes[signature] = {
                "signature": signature,
                "type": option_type(item),
                "representative": dict(item),
                "count": 1,
                "volume": float(
                    item["length"] * item["width"] * item["height"]
                ),
            }
        else:
            entry["count"] += 1
    return sorted(classes.values(), key=lambda e: -e["volume"])


def typed_capacity(
    agent,
    observation: dict[str, Any],
    item_list: list[dict[str, Any]],
    *,
    stride: int,
    accept_cap: int,
) -> dict[str, Any]:
    packed = {
        int(entry["index"])
        for container in observation.get("container_list", [])
        for entry in container.get("packed_items", [])
    }
    clearance = float(agent.SETTLED_ITEM_CLEARANCE)
    per_type = {
        name: {
            "kappa": 0,
            "classes": 0,
            "corridor_blocked": 0,
            "attempted": 0,
        }
        for name in TYPES
    }
    for entry in typed_classes(item_list, packed):
        diagnostics: dict[str, Any] = {}
        accepted = []
        for kind in ("settled", "release"):
            for orientation in agent.unique_orientations(
                entry["representative"]
            ):
                produced = 0
                stream = agent.CandidateGenerator.iter_cartesian_attempts(
                    observation,
                    entry["representative"],
                    0,
                    orientation,
                    limit=accept_cap,
                    attempt_kind=kind,
                    diagnostics=diagnostics,
                    item_idx=int(entry["representative"]["index"]),
                    stride=stride,
                )
                for candidate in stream:
                    if candidate is None:
                        continue
                    accepted.append(candidate)
                    produced += 1
                    if produced >= accept_cap:
                        break
        chosen: list[Any] = []
        for candidate in accepted:
            if len(chosen) >= entry["count"]:
                break
            if any(
                anchors_conflict(candidate, taken, clearance)
                for taken in chosen
            ):
                continue
            chosen.append(candidate)
        corridor = 0
        attempted = 0
        for counters in _walk_counters(diagnostics):
            attempted += int(counters.get("attempted", 0))
            corridor += int(
                (counters.get("rejected") or {}).get("corridor", 0)
            )
        slot = per_type[entry["type"]]
        slot["kappa"] += len(chosen)
        slot["classes"] += 1
        slot["corridor_blocked"] += corridor
        slot["attempted"] += attempted
    for name in TYPES:
        slot = per_type[name]
        slot["has_option"] = int(slot["kappa"] > 0)
        slot["corridor_block_rate"] = (
            round(slot["corridor_blocked"] / slot["attempted"], 4)
            if slot["attempted"]
            else None
        )
    return per_type


def _walk_counters(diagnostics: Any):
    """Yield every per-item counter dict the generator recorded."""
    if isinstance(diagnostics, dict):
        if "attempted" in diagnostics and "rejected" in diagnostics:
            yield diagnostics
            return
        for value in diagnostics.values():
            yield from _walk_counters(value)
    elif isinstance(diagnostics, list):
        for value in diagnostics:
            yield from _walk_counters(value)


def realised_successor(observation, row):
    """The container as the official validator actually left it."""
    x_plus = (row.get("physical") or {}).get("x_plus") or {}
    if not x_plus.get("position") or not x_plus.get("quaternion"):
        return None
    successor = copy.deepcopy(observation)
    container = successor["container_list"][int(row["container_index"])]
    item = copy.deepcopy(successor["pool_list"][int(row["pool_index"])])
    item["pos"] = [float(v) for v in x_plus["position"]]
    item["orn"] = [float(v) for v in x_plus["quaternion"]]
    item["belongs_to"] = int(row["container_index"])
    container.setdefault("packed_items", []).append(item)
    return successor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=pathlib.Path,
        default=ROOT / "reports" / "replay-dataset",
    )
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    parser.add_argument("--accept-cap", type=int, default=DEFAULT_ACCEPT_CAP)
    parser.add_argument("--per-state", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--include-final-holdout",
        action="store_true",
        help="RELEASE_RISK_PROTOCOL 3.1: off unless deliberately opened",
    )
    args = parser.parse_args()

    agent = load_agent_module()
    states = []
    skipped: list[str] = []
    for manifest_path in sorted(args.dataset_root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("split") == "final_holdout"
            and not args.include_final_holdout
        ):
            skipped.append(manifest_path.parent.name)
            continue
        case = manifest.get("case") or {}
        for step in case.get("steps", []):
            if step.get("status") != "ok":
                continue
            state_path = manifest_path.parent / (
                step.get("snapshot_path") or ""
            )
            rows_path = manifest_path.parent / (step.get("dataset_path") or "")
            if state_path.exists() and rows_path.exists():
                states.append(
                    {
                        "case_id": case.get("case_id"),
                        "step": int(step["step"]),
                        "state_path": state_path,
                        "rows_path": rows_path,
                    }
                )
    if args.limit > 0:
        states = states[: args.limit]
    if not states:
        raise SystemExit("no labelled states found")

    transitions = []
    for index, state in enumerate(states, start=1):
        snapshot = json.loads(state["state_path"].read_text(encoding="utf-8"))
        observation = snapshot["observation"]
        item_list, _count = rebuild_case_items(state["case_id"])
        before = typed_capacity(
            agent,
            observation,
            item_list,
            stride=args.stride,
            accept_cap=args.accept_cap,
        )
        rows = [
            json.loads(line)
            for line in state["rows_path"].read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]
        labelled = [
            row for row in rows
            if (row.get("physical") or {}).get("x_plus")
        ]
        # Prefer the action the policy actually took, then the highest
        # scoring alternatives, so every transition measured is one the
        # agent could plausibly have issued.
        labelled.sort(
            key=lambda row: (
                not bool(row.get("selected")),
                -float(row["score_immediate"]),
                row["candidate_id"],
            )
        )
        for row in labelled[: max(1, args.per_state)]:
            successor = realised_successor(observation, row)
            if successor is None:
                continue
            after = typed_capacity(
                agent,
                successor,
                item_list,
                stride=args.stride,
                accept_cap=args.accept_cap,
            )
            item = observation["pool_list"][int(row["pool_index"])]
            transitions.append(
                {
                    "case_id": state["case_id"],
                    "step": state["step"],
                    "candidate_id": row["candidate_id"],
                    "selected": bool(row.get("selected")),
                    "placed_type": option_type(item),
                    "placed_is_soft": bool(item.get("is_soft", False)),
                    "kind": row["kind"],
                    "survived": bool(row["physical"]["is_placed_safe"]),
                    "before": before,
                    "after": after,
                    "delta": {
                        name: {
                            "kappa": after[name]["kappa"]
                            - before[name]["kappa"],
                            "has_option": after[name]["has_option"]
                            - before[name]["has_option"],
                        }
                        for name in TYPES
                    },
                }
            )
        print(
            f"[{index}/{len(states)}] {state['case_id']} step {state['step']}",
            file=sys.stderr,
            flush=True,
        )

    summary: dict[str, Any] = {"transitions": len(transitions), "types": {}}
    for name in TYPES:
        deltas = [t["delta"][name]["kappa"] for t in transitions]
        present = [
            t for t in transitions if t["before"][name]["classes"] > 0
        ]
        gains = [t for t in present if t["delta"][name]["kappa"] > 0]
        restored = [
            t for t in present
            if t["before"][name]["has_option"] == 0
            and t["after"][name]["has_option"] == 1
        ]
        summary["types"][name] = {
            "observed_transitions": len(present),
            "mean_delta": (
                round(statistics.fmean(deltas), 4) if deltas else None
            ),
            "increases": len(gains),
            "increase_rate": (
                round(len(gains) / len(present), 4) if present else None
            ),
            "decreases": sum(
                1 for t in present if t["delta"][name]["kappa"] < 0
            ),
            "unchanged": sum(
                1 for t in present if t["delta"][name]["kappa"] == 0
            ),
            "option_type_restored": len(restored),
            "option_type_lost": sum(
                1 for t in present
                if t["before"][name]["has_option"] == 1
                and t["after"][name]["has_option"] == 0
            ),
        }

    soft = [t for t in transitions if t["placed_is_soft"]]
    rigid = [t for t in transitions if not t["placed_is_soft"]]
    summary["soft_versus_rigid"] = {
        "soft_transitions": len(soft),
        "rigid_transitions": len(rigid),
        "mean_delta_by_type": {
            name: {
                "soft": (
                    round(
                        statistics.fmean(
                            t["delta"][name]["kappa"] for t in soft
                        ),
                        4,
                    )
                    if soft
                    else None
                ),
                "rigid": (
                    round(
                        statistics.fmean(
                            t["delta"][name]["kappa"] for t in rigid
                        ),
                        4,
                    )
                    if rigid
                    else None
                ),
            }
            for name in TYPES
        },
    }

    report = {
        "schema_version": SCHEMA_VERSION,
        "settings": {
            "stride": args.stride,
            "accept_cap": args.accept_cap,
            "per_state": args.per_state,
            "successor": "realised (official x_plus pose)",
        },
        "claims_under_test": {
            "irreversibility": (
                "s not in K => T_a(s) not in K. Any type with a nonzero "
                "increase rate, or any option_type_restored, is a "
                "counterexample for that type."
            ),
            "soft_dominates_rigid": (
                "compare mean_delta_by_type across soft and rigid "
                "placements per type; a dominating operator would move "
                "every type the same way, a converting one would not."
            ),
        },
        "skipped_final_holdout_datasets": skipped,
        "summary": summary,
        "transitions": transitions,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
