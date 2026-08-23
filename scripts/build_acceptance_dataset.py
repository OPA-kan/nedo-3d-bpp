"""Build the acceptance dataset A(s, a) = P(a in search-Pareto frontier).

The strategic teacher the beta contract reserves for search: labels come
from vector-MCTS runs (`run_vector_mcts.py`), never from rank-0
continuation. Only physically safe root candidates are labeled; rows use
the feasibility-row format so the binary-head trainer is reused with
``--semantics acceptance_p_search_pareto_v1``.
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
    mcts_path: pathlib.Path, episode_dir: pathlib.Path, *, cell_id: str,
) -> list[dict[str, Any]]:
    payload = json.loads(mcts_path.read_text(encoding="utf-8"))
    if payload.get("contract") != "vector_mcts_search_pareto_v1":
        raise ValueError(f"{mcts_path} is not a vector-MCTS label file")
    rows = []
    for root in payload.get("roots") or []:
        snapshot_path = root.get("snapshot_path")
        if not snapshot_path:
            continue
        snapshot = json.loads(
            (episode_dir / snapshot_path).read_text(encoding="utf-8")
        )
        state = state_tensor_from_snapshot(snapshot)
        visible = list(state["visible_item_indices"])
        for candidate in root.get("root_candidates") or []:
            if not candidate.get("safe"):
                continue
            command = candidate.get("command_action")
            stable_item = candidate.get("stable_item_index")
            if command is None or stable_item not in visible:
                continue
            rows.append({
                "schema_version": 1,
                "contract": "acceptance_row_v1",
                "cell_id": cell_id,
                "root_id": root["root_id"],
                "step": int(root["step"]),
                "root_candidate_id": candidate["root_candidate_id"],
                "features": {
                    "state": state,
                    "action": [
                        float(command["container_idx"]),
                        float(command["orientation"]),
                        float(command["place_pos"][0]),
                        float(command["place_pos"][1]),
                        float(command["place_pos"][2]),
                    ],
                    "acting_item": [
                        float(v)
                        for v in state["visible_item_values"][
                            visible.index(stable_item)
                        ]
                    ],
                },
                "physical_safe": bool(candidate["in_search_pareto"]),
                "audit_only": {
                    "label_semantics": "in_search_pareto_from_vector_mcts",
                    "provenance": candidate.get("provenance"),
                },
            })
    if not rows:
        raise ValueError(f"{mcts_path} produced no acceptance rows")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run", action="append", required=True,
        metavar="CELL=MCTS_JSON:EPISODE_DIR",
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    rows: list[dict[str, Any]] = []
    for spec in args.run:
        cell, _, rest = spec.partition("=")
        mcts_path, _, episode_dir = rest.partition(":")
        rows.extend(build_rows(
            pathlib.Path(mcts_path), pathlib.Path(episode_dir),
            cell_id=cell,
        ))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    positives = sum(row["physical_safe"] for row in rows)
    print(
        f"rows={len(rows)} on_frontier={positives} "
        f"off_frontier={len(rows) - positives}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
