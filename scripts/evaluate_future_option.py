"""Paired saved-snapshot evaluation of the future-option tie-break.

This is a geometry-only policy replay.  It restores the same serialized
observation for every arm/repeat, but it does not restore PyBullet and does
not claim to reproduce the historical action that created the snapshot.
The report is therefore evidence about admission, fixed-work cost, and the
immediate decision -- not about the resulting physical episode trajectory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib
import statistics
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.measure_anchor_recall import load_agent_module  # noqa: E402


DEFAULT_OUTPUT = ROOT / "reports" / "future-option"


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def normalized_action(action: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_idx": int(action["item_idx"]),
        "container_idx": int(action["container_idx"]),
        "orientation": int(action["orientation"]),
        "place_pos": [round(float(value), 6) for value in action["place_pos"]],
    }


def action_hash(action: dict[str, Any]) -> str:
    payload = json.dumps(
        normalized_action(action), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def run_policy_once(
    agent_module: Any,
    observation: dict[str, Any],
    *,
    enabled: bool,
    repeat: int,
) -> dict[str, Any]:
    agent_module.FUTURE_OPTION_TIEBREAK_ENABLED = bool(enabled)
    agent_module._PACKED_AABBS_CACHE.clear()
    solver = agent_module.Agent("")
    solver.get_init_states(copy.deepcopy(observation))
    started = time.perf_counter()
    action = solver.policy(copy.deepcopy(observation))
    elapsed = time.perf_counter() - started
    normalized = normalized_action(action)
    pool_index = normalized["item_idx"]
    pool = observation.get("pool_list", [])
    item_index = (
        int(pool[pool_index].get("index", pool_index))
        if 0 <= pool_index < len(pool)
        else None
    )
    diagnostics = solver.last_candidate_diagnostics or {}
    return {
        "arm": "future-option" if enabled else "off",
        "repeat": int(repeat),
        "elapsed_seconds": float(elapsed),
        "action": normalized,
        "action_hash": action_hash(action),
        "selected_item_index": item_index,
        "action_source": solver.last_action_source,
        "candidate_kind": solver.last_candidate_kind,
        "top_candidate_items": list(solver.last_top_candidate_item_indices),
        "future_probe_items": list(solver.last_future_probe_item_indices),
        "future_option": json_safe(diagnostics.get("future_option_tiebreak")),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for arm in ("off", "future-option"):
        arm_rows = [row for row in rows if row["arm"] == arm]
        elapsed = [float(row["elapsed_seconds"]) for row in arm_rows]
        result[arm] = {
            "runs": len(arm_rows),
            "elapsed_mean": statistics.fmean(elapsed) if elapsed else None,
            "elapsed_min": min(elapsed) if elapsed else None,
            "elapsed_max": max(elapsed) if elapsed else None,
            "action_hashes": sorted({row["action_hash"] for row in arm_rows}),
            "selected_items": [row["selected_item_index"] for row in arm_rows],
        }
    return result


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Future-option saved-snapshot evaluation",
        "",
        "> Geometry-only replay from the same serialized observation. It does "
        "not restore PyBullet and does not claim to reproduce the historical "
        "action or the downstream physical trajectory.",
        "",
        f"- snapshot: `{report['snapshot']}`",
        f"- case / step: `{report['case_id']}` / {report['step']}",
        f"- repeats: {report['repeats']}",
        f"- item top-K: {report['configuration']['item_top_k']}",
        f"- Q-live band: {report['configuration']['q_band']}",
        f"- validation budget per hypothetical: "
        f"{report['configuration']['validation_budget']}",
        "",
        "## Summary",
        "",
        "| arm | selected items | elapsed mean | range | unique actions |",
        "|---|---|---:|---:|---:|",
    ]
    for arm in ("off", "future-option"):
        row = report["summary"][arm]
        lines.append(
            f"| {arm} | {row['selected_items']} | "
            f"{row['elapsed_mean']:.3f}s | {row['elapsed_min']:.3f}-"
            f"{row['elapsed_max']:.3f}s | {len(row['action_hashes'])} |"
        )
    lines.extend(
        [
            "",
            "## Per run",
            "",
            "| arm | repeat | item | elapsed | action hash | future changed | "
            "aborted |",
            "|---|---:|---:|---:|---|---|---|",
        ]
    )
    for row in report["rows"]:
        future = row.get("future_option") or {}
        lines.append(
            f"| {row['arm']} | {row['repeat']} | "
            f"{row['selected_item_index']} | {row['elapsed_seconds']:.3f}s | "
            f"`{row['action_hash']}` | "
            f"{future.get('changed_from_q_best', '')} | "
            f"{future.get('aborted_for_deadline', '')} |"
        )
    lines.extend(
        [
            "",
            "The JSON preserves every evaluated item's `Q_live`, Q gap, the "
            "four live future-option components, and the shadow quotient / "
            "static-conflict capacity descriptors. Only the four live "
            "components participate in selection. `valid_candidates` is a "
            "count inside the sampled probe budget, not a full anchor "
            "population count.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=pathlib.Path, required=True)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.repeats < 1:
        raise SystemExit("--repeats must be positive")

    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    observation = snapshot["observation"]
    agent_module = load_agent_module()
    rows = []
    # Alternate arms so machine-load drift does not always favor one arm.
    for repeat in range(args.repeats):
        for enabled in (False, True):
            row = run_policy_once(
                agent_module,
                observation,
                enabled=enabled,
                repeat=repeat,
            )
            rows.append(row)
            print(
                f"{row['arm']} r{repeat}: item "
                f"{row['selected_item_index']} in "
                f"{row['elapsed_seconds']:.3f}s",
                flush=True,
            )

    report = {
        "schema_version": 1,
        "snapshot": args.snapshot.as_posix(),
        "case_id": snapshot.get("case_id"),
        "step": snapshot.get("step"),
        "repeats": int(args.repeats),
        "configuration": {
            "item_top_k": int(agent_module.FUTURE_OPTION_ITEM_TOP_K),
            "q_band": float(agent_module.FUTURE_OPTION_Q_BAND),
            "validation_budget": int(
                agent_module.FUTURE_OPTION_VALIDATION_BUDGET
            ),
            "probes_per_signature": int(
                agent_module.FUTURE_OPTION_PROBES_PER_SIGNATURE
            ),
        },
        "summary": summarize(rows),
        "rows": rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "report.md").write_text(
        render_markdown(report), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
