"""Build the feasibility dataset F(s, a) = P(safe) from v3 manifests.

Every measurement attempt of the single-agent runner — safe and unsafe
alike — becomes one supervised row: root state set tensors, the
commanded action, the acting item's features, and the physical verdict.
Provider rank/score never enters; provenance rides along audit-only per
the beta contract.
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

from scripts.counterfactual_graph import state_tensor_from_snapshot  # noqa: E402


def build_rows(
    run_dir: pathlib.Path, *, cell_id: str,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    manifest = json.loads(
        (run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("behavior_contract") != "single_agent_v1":
        raise ValueError(f"{run_dir} is not a single-agent v1 run")
    rows: list[dict[str, Any]] = []
    skipped = {"missing_action": 0, "missing_item": 0}
    for episode_index, episode in enumerate(manifest.get("episodes") or []):
        episode_dir = run_dir / f"episode-{episode_index:03d}"
        for record in episode.get("records") or []:
            snapshot = json.loads(
                (episode_dir / record["snapshot_path"]).read_text(
                    encoding="utf-8"
                )
            )
            state = state_tensor_from_snapshot(snapshot)
            visible_indices = list(state["visible_item_indices"])
            for sample in record.get("measurement_samples") or []:
                command = sample.get("command_action")
                if command is None:
                    skipped["missing_action"] += 1
                    continue
                stable_item = sample.get("stable_item_index")
                if stable_item not in visible_indices:
                    skipped["missing_item"] += 1
                    continue
                item_features = [
                    float(v)
                    for v in state["visible_item_values"][
                        visible_indices.index(stable_item)
                    ]
                ]
                rows.append({
                    "schema_version": 1,
                    "contract": "feasibility_row_v1",
                    "cell_id": cell_id,
                    "root_id": sample["root_id"],
                    "step": int(record["step"]),
                    "root_candidate_id": sample["root_candidate_id"],
                    "features": {
                        "state": state,
                        "action": [
                            float(command["container_idx"]),
                            float(command["orientation"]),
                            float(command["place_pos"][0]),
                            float(command["place_pos"][1]),
                            float(command["place_pos"][2]),
                        ],
                        "acting_item": item_features,
                    },
                    "physical_safe": bool(sample["physical_safe"]),
                    "audit_only": {
                        "provenance": sample.get("root_candidate_provenance"),
                        "status": sample.get("status"),
                    },
                })
    if not rows:
        raise ValueError(f"{run_dir} produced no feasibility rows")
    return rows, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="append", required=True, metavar="CELL_ID=RUN_DIR",
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    skipped_total = {"missing_action": 0, "missing_item": 0}
    for spec in args.run:
        cell_id, _, run_dir = spec.partition("=")
        if not run_dir:
            raise SystemExit(f"expected CELL_ID=RUN_DIR, got: {spec}")
        cell_rows, skipped = build_rows(
            pathlib.Path(run_dir), cell_id=cell_id
        )
        rows.extend(cell_rows)
        for key in skipped_total:
            skipped_total[key] += skipped[key]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    safe = sum(row["physical_safe"] for row in rows)
    print(
        f"rows={len(rows)} safe={safe} unsafe={len(rows) - safe} "
        f"cells={len(args.run)} skipped={skipped_total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
