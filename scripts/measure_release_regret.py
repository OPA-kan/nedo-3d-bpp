"""
Did the search miss better poses, or decline them?

The dominated-choice measurement said the agent takes a pose worse on its own
objective than an available alternative -- but the alternatives came from a
5 cm grid with a heightmap drop, and the agent generates from support-plane
anchors. A pose that grid finds might be outside the agent's candidate model
entirely, which would make the finding an L1 generator gap rather than an L2
ranking failure. That caveat is why this exists.

`measure_anchor_recall.py` settles it, because its release oracle enumerates
from the agent's OWN contract and marks each candidate `found_by_anytime`.
So the comparison is inside one candidate model:

  best score among poses the search accepted    (what it could choose)
  best score among poses the oracle enumerated  (what existed)

regret = the gap. Large regret means better poses existed in the model and
the deadline did not reach them -- the same class as the true-envelope fix
(+52% official) and the direct-release fix (deadline acceptances 0 -> 151).
Zero regret means the search reached the best pose and the ranker passed on
it, which is a different repair entirely.

Scores are the agent's, risk-adjusted the way the shipped policy ranks:
Q - lambda_rot*P_rot - lambda_slide*P_slide. The oracle stores the raw Q, so
the risk terms are recomputed here from the stored geometry rather than
assumed to be already included.
"""
from __future__ import annotations

import argparse
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "simulator"))

from scripts.measure_anchor_recall import load_agent_module  # noqa: E402


def adjusted(agent_module, record, container):
    """Q - lambda_rot*P_rot - lambda_slide*P_slide for one oracle record."""
    centre = [float(v) for v in record["center"]]
    size = tuple(float(v) for v in record["size"])
    q = float(record["score"])
    p_rot = float(
        agent_module.release_rotation_risk_probability_mech(
            centre[0], centre[1], centre[2], size, container
        )
    )
    candidate = agent_module.AABB(
        center=tuple(centre), size=size, name="release_candidate"
    )
    p_slide = float(
        agent_module.release_large_slide_probability(
            candidate, {}, container, int(record["orientation"])
        )
    )
    return (
        q
        - float(agent_module.RELEASE_RISK_RERANK_LAMBDA) * p_rot
        - float(agent_module.RELEASE_RISK_SLIDE_LAMBDA) * p_slide,
        q,
        p_rot,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oracle-dir", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    agent_module = load_agent_module()
    rows = []
    for candidates_path in sorted(
        glob.glob(f"{args.oracle_dir}/**/step-*-release-candidates.jsonl",
                  recursive=True)
    ):
        state_path = pathlib.Path(
            candidates_path.replace("-release-candidates.jsonl", "-state.json")
        )
        if not state_path.exists():
            continue
        state = json.loads(state_path.read_text(encoding="utf-8"))
        containers = (
            state.get("containers")
            or state.get("container_list")
            or (state.get("observation") or {}).get("container_list")
        )
        if not containers:
            print(f"no container in {state_path.name}", file=sys.stderr)
            continue

        best_found = None
        best_any = None
        found = 0
        total = 0
        for line in pathlib.Path(candidates_path).read_text(
            encoding="utf-8"
        ).splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            container = containers[int(record.get("container_index", 0))]
            value, q, p_rot = adjusted(agent_module, record, container)
            total += 1
            entry = (value, q, p_rot, record)
            if best_any is None or value > best_any[0]:
                best_any = entry
            if record.get("found_by_anytime"):
                found += 1
                if best_found is None or value > best_found[0]:
                    best_found = entry

        step = int(pathlib.Path(candidates_path).name.split("-")[1])
        if best_any is None:
            continue
        regret = (
            None if best_found is None
            else float(best_any[0] - best_found[0])
        )
        rows.append(
            {
                "step": step,
                "oracle_candidates": total,
                "found_by_anytime": found,
                "recall": found / max(total, 1),
                "best_oracle_adjusted": float(best_any[0]),
                "best_found_adjusted": (
                    None if best_found is None else float(best_found[0])
                ),
                "regret": regret,
                "best_oracle_p_rot": float(best_any[2]),
                "best_found_p_rot": (
                    None if best_found is None else float(best_found[2])
                ),
            }
        )

    rows.sort(key=lambda r: r["step"])
    print(
        f'{"step":>5s} {"oracle":>7s} {"found":>6s} {"recall":>7s} '
        f'{"best found":>11s} {"best oracle":>12s} {"regret":>8s}'
    )
    for row in rows:
        found_text = (
            "-" if row["best_found_adjusted"] is None
            else f'{row["best_found_adjusted"]:+.4f}'
        )
        regret_text = "-" if row["regret"] is None else f'{row["regret"]:+.4f}'
        print(
            f'{row["step"]:5d} {row["oracle_candidates"]:7d} '
            f'{row["found_by_anytime"]:6d} {row["recall"]:7.3f} '
            f'{found_text:>11s} {row["best_oracle_adjusted"]:+12.4f} '
            f'{regret_text:>8s}'
        )
    print(
        "\nregret > 0 means a better-scoring pose existed in the agent's own "
        "candidate model and the deadline did not reach it -- reachability, "
        "not ranking. regret 0 means the search had the best pose in hand."
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
