"""
Score recorded decisions offline: risk percentile, and the weight that flips.

Reads what `record_decisions.py` wrote from an unperturbed replay and, for
each step, rebuilds the board and enumerates the alternatives the agent
could have taken. Because the replay is already finished, nothing here can
change it -- which is the whole reason the two passes are separate. The
previous single-pass version scored alternatives between the policy call and
the step, and that alone moved c000-k1 from 21 placements and no topple to
16 and a topple.

Two quantities per step:

  percentile   share of legal alternatives with strictly lower P_rot than
               the pose actually chosen. 0 means the safest available pose
               was taken, 1 the riskiest.

  lambda flip  smallest lambda_rot at which some strictly safer pose would
               have outranked the chosen one under the shipped score,
               Q - lambda_rot*P_rot - lambda_slide*P_slide. There is no
               solution when every safer pose loses on Q by more than the
               risk range can recover, and that is reported rather than
               smoothed away.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "simulator"))

from scripts.measure_anchor_recall import load_agent_module  # noqa: E402


def scored_alternatives(agent_module, container, item, containers, stride):
    from scripts.fast_afterstate_env import AfterstateBoard

    has_priority = any(bool(c.get("is_prioritized")) for c in containers)
    board = AfterstateBoard(agent_module, container)
    rows = []
    x = board.x0 + stride / 2.0
    while x < -board.x0:
        y = board.y0 + stride / 2.0
        while y < -board.y0:
            for orientation in agent_module.unique_orientations(item):
                dx, dy, dz = agent_module.get_rotated_dimensions(
                    item["length"], item["width"], item["height"], orientation
                )
                bottom = board.drop_height(x, y, dx, dy)
                candidate = agent_module.AABB(
                    center=(x, y, bottom + dz / 2.0),
                    size=(dx, dy, dz),
                    name="release_candidate",
                )
                if (
                    agent_module.Geometry.release_rejection_reason(
                        candidate, container
                    )
                    is not None
                ):
                    continue
                rows.append(
                    {
                        "q": float(
                            agent_module.Ranker.score(
                                candidate, item, container, has_priority
                            )
                        ),
                        "p_rot": float(
                            agent_module.release_rotation_risk_probability_mech(
                                float(candidate.center[0]),
                                float(candidate.center[1]),
                                float(candidate.center[2]),
                                tuple(float(v) for v in candidate.size),
                                container,
                            )
                        ),
                        "p_slide": float(
                            agent_module.release_large_slide_probability(
                                candidate, item, container, int(orientation)
                            )
                        ),
                        "support": float(
                            agent_module.Geometry.support_ratio(
                                candidate, container
                            )
                        ),
                    }
                )
            y += stride
        x += stride
    return rows


def describe_chosen(agent_module, entry):
    container = entry["containers"][entry["container_index"]]
    item = entry["item"]
    orientation = int(entry["orientation"])
    dims = agent_module.get_rotated_dimensions(
        item["length"], item["width"], item["height"], orientation
    )
    cx, cy, cz = (float(v) for v in entry["place_pos"])
    box = agent_module.AABB(
        center=(cx, cy, cz),
        size=tuple(float(v) for v in dims),
        name="release_candidate",
    )
    has_priority = any(
        bool(c.get("is_prioritized")) for c in entry["containers"]
    )
    return {
        "q": float(
            agent_module.Ranker.score(box, item, container, has_priority)
        ),
        "p_rot": float(
            agent_module.release_rotation_risk_probability_mech(
                cx, cy, cz, tuple(float(v) for v in dims), container
            )
        ),
        "p_slide": float(
            agent_module.release_large_slide_probability(
                box, item, container, orientation
            )
        ),
        "support": float(agent_module.Geometry.support_ratio(box, container)),
    }


def lambda_to_flip(rows, chosen, slide_lambda):
    base = chosen["q"] - slide_lambda * chosen["p_slide"]
    best = None
    for row in rows:
        gap = chosen["p_rot"] - row["p_rot"]
        if gap <= 1e-9:
            continue
        need = max((base - (row["q"] - slide_lambda * row["p_slide"])) / gap, 0.0)
        if best is None or need < best[0]:
            best = (need, row)
    return best


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", type=pathlib.Path, required=True)
    parser.add_argument("--stride", type=float, default=0.05)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    agent_module = load_agent_module()
    record = json.loads(args.record.read_text(encoding="utf-8"))
    slide_lambda = float(agent_module.RELEASE_RISK_SLIDE_LAMBDA)
    live_lambda = float(agent_module.RELEASE_RISK_RERANK_LAMBDA)

    print(f'{record["case"]}: {record["placed"]} placed, {record["outcome"]}')
    print(f"shipped lambda_rot {live_lambda}, lambda_slide {slide_lambda}\n")
    print(
        f'{"step":>4s} {"P_rot":>7s} {"median":>7s} {"alts":>5s} '
        f'{"pct":>6s} {"lam_flip":>9s} {"support":>8s}  flags'
    )

    out = []
    for entry in record["steps"]:
        container = entry["containers"][entry["container_index"]]
        chosen = describe_chosen(agent_module, entry)
        rows = scored_alternatives(
            agent_module, container, entry["item"], entry["containers"],
            args.stride,
        )
        p = np.array([r["p_rot"] for r in rows]) if rows else np.array([])
        percentile = float((p < chosen["p_rot"]).mean()) if p.size else None
        best = lambda_to_flip(rows, chosen, slide_lambda) if rows else None
        kind = entry.get("candidate_kind")
        flags = []
        if kind and kind != "release_candidate":
            flags.append(kind)
        if entry["item"].get("is_soft"):
            flags.append("soft")
        if entry["item"].get("is_prioritized"):
            flags.append("prio")
        if not entry["safe"]:
            flags.append("FATAL")
        print(
            f'{entry["step"]:4d} {chosen["p_rot"]:7.4f} '
            f'{("-" if not p.size else f"{float(np.median(p)):.4f}"):>7s} '
            f'{p.size:5d} '
            f'{("-" if percentile is None else f"{percentile:.3f}"):>6s} '
            f'{("-" if best is None else f"{best[0]:.2f}"):>9s} '
            f'{chosen["support"]:8.3f}  {" ".join(flags)}'
        )
        out.append(
            {
                "step": entry["step"],
                "chosen": chosen,
                "alternatives": int(p.size),
                "median_p_rot": float(np.median(p)) if p.size else None,
                "percentile": percentile,
                "lambda_needed": None if best is None else float(best[0]),
                "safe": entry["safe"],
                "source": entry["source"],
                "candidate_kind": kind,
            }
        )

    percentiles = [r["percentile"] for r in out if r["percentile"] is not None]
    if percentiles:
        print(
            f"\npercentile of the chosen pose: median "
            f"{statistics.median(percentiles):.3f} over {len(percentiles)} "
            f"scored steps"
        )
    needed = [
        r["lambda_needed"] for r in out if r["lambda_needed"] is not None
    ]
    if needed:
        print(
            f"lambda_rot that would promote a safer pose: median "
            f"{statistics.median(needed):.2f}, min {min(needed):.2f}, "
            f"max {max(needed):.2f} (shipped {live_lambda})"
        )
    unscored = sum(1 for r in out if r["percentile"] is None)
    if unscored:
        print(
            f"{unscored} step(s) had no release alternatives in the grid and "
            f"could not be scored -- the agent also places settled "
            f"candidates, which this enumeration does not generate."
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {"case": record["case"], "outcome": record["outcome"],
                 "placed": record["placed"], "steps": out},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
