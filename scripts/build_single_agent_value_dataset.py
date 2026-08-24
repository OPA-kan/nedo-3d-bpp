"""Build single-agent played-state suffix-V rows from Phase-3A manifests.

The committed Phase-3A manifests do not retain the pre-action snapshot file,
but every physically measured selected action retains its exact post-action
set tensor.  That tensor is the next record's played state.  Consequently we
can recover steps 1..T-1 without replaying physics; step 0 is explicitly
omitted rather than approximated.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.single_agent_packing import BEHAVIOR_CONTRACT


FORBIDDEN_KEYS = {"score", "immediate_score", "rank", "prior", "selection"}
VALUE_SEMANTICS = "V^pi_behavior_observed_suffix_not_V_star"


def _forbidden_key_hits(value: Any, prefix: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if key in FORBIDDEN_KEYS:
                hits.append(path)
            hits.extend(_forbidden_key_hits(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_forbidden_key_hits(child, f"{prefix}[{index}]"))
    return hits


def _selected_leaf_state(record: dict[str, Any]) -> dict[str, Any]:
    selected = str(record["selected_candidate_id"])
    matches = [
        sample for sample in record.get("measurement_samples") or []
        if str(sample.get("root_candidate_id")) == selected
        and sample.get("physical_safe")
        and isinstance(sample.get("leaf_state"), dict)
    ]
    if not matches:
        raise ValueError(f"selected candidate {selected} has no safe leaf state")
    canonical = json.dumps(matches[0]["leaf_state"], sort_keys=True)
    if any(json.dumps(row["leaf_state"], sort_keys=True) != canonical for row in matches[1:]):
        raise ValueError(f"selected candidate {selected} has inconsistent world states")
    return dict(matches[0]["leaf_state"])


def build_rows(root: pathlib.Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    groups: set[str] = set()
    manifests = sorted(root.rglob("manifest.json"))
    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("behavior_contract") != BEHAVIOR_CONTRACT:
            continue
        for episode_index, episode in enumerate(manifest.get("episodes") or []):
            if episode.get("behavior_contract") != BEHAVIOR_CONTRACT:
                raise ValueError(f"{manifest_path}: mixed behavior contract")
            group = f"{manifest_path.parent.name}:episode-{episode_index:03d}"
            groups.add(group)
            records = sorted(episode.get("records") or [], key=lambda row: int(row["step"]))
            targets = {
                int(row["step"]): row for row in episode.get("value_targets") or []
            }
            previous_state = None
            for record in records:
                step = int(record["step"])
                target = targets.get(step)
                if target is None:
                    raise ValueError(f"{manifest_path}: missing value target at step {step}")
                if previous_state is not None and target.get("value_target_eligible"):
                    if target.get("value_target_semantics") != VALUE_SEMANTICS:
                        raise ValueError(f"{manifest_path}: invalid value semantics")
                    row = {
                        "schema_version": 1,
                        "behavior_contract": BEHAVIOR_CONTRACT,
                        "trajectory_group": group,
                        "split_group": group,
                        "case_id": manifest.get("case_id"),
                        "environment_seed": manifest.get("environment_seed"),
                        "step": step,
                        "state": previous_state,
                        "value_target_eligible": True,
                        "value_target_semantics": VALUE_SEMANTICS,
                        "value_heads": dict(target.get("value_heads") or {}),
                    }
                    hits = _forbidden_key_hits(row)
                    if hits:
                        raise ValueError("forbidden heuristic leakage: " + ", ".join(hits))
                    rows.append(row)
                previous_state = _selected_leaf_state(record)
    if not rows:
        raise ValueError(f"no eligible single-agent suffix states below {root}")
    eligible_heads: dict[str, int] = {}
    for row in rows:
        for name, head in row["value_heads"].items():
            if head.get("target_eligible"):
                eligible_heads[name] = eligible_heads.get(name, 0) + 1
    return rows, {
        "schema_version": 1,
        "contract": "single_agent_played_state_suffix_value_v1",
        "behavior_contract": BEHAVIOR_CONTRACT,
        "value_target_semantics": VALUE_SEMANTICS,
        "manifests": len(manifests),
        "trajectory_groups": len(groups),
        "rows": len(rows),
        "initial_states_omitted": len(groups),
        "eligible_value_heads": dict(sorted(eligible_heads.items())),
        "forbidden_heuristic_key_hits": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--summary", type=pathlib.Path, required=True)
    args = parser.parse_args()
    rows, summary = build_rows(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    args.summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
