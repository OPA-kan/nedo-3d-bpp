"""
Does a placement CREATE support, or spend it?

The section drawings read as towers rather than spread, with roofed voids
under them, and the reachability census says why that matters: at
termination three of four containers have zero columns where anything would
stand. Support exhaustion, not floor space, is what these boards run out of.

So the quantity a placement should be judged on is not the volume it fills
but the connected support surface it leaves behind:

    dA_support(z) = A_after(z) - A_before(z)

per height band. Raising a tower by one course adds volume and almost no new
surface. Bridging two towers adds a void underneath and a large surface on
top. Under that reading a void is not automatically bad -- the question is
whether it bought a surface.

Two facts make the sign non-obvious, and both are the agent's own rules:

  * `support_surfaces()` admits only PLAIN packed items. A soft or priority
    item placed on a plain top does not add a surface -- it REMOVES the one
    it covers. dA is negative by construction for protected cargo.
  * components are grouped by `support_plane_components` with the shipped
    16 mm adjacency, so two tops at the same height a centimetre apart are
    one surface and a big item can span them.

This scores candidates from an anchor-recall oracle dump, which enumerates
from the agent's own contract, and reports where the pose the agent actually
took sits in the dA distribution. Nothing is adopted here: it tests whether
dA separates the chosen pose from its alternatives at all, before any knob
is built on it.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "simulator"))

from scripts.measure_anchor_recall import load_agent_module  # noqa: E402

BAND = 0.25


def component_areas(agent_module, surfaces):
    """(top, union area) per connected component, shipped grouping."""
    out = []
    for component in agent_module.support_plane_components(surfaces):
        rectangles = [
            (
                float(s.minimum[0]),
                float(s.maximum[0]),
                float(s.minimum[1]),
                float(s.maximum[1]),
            )
            for s in component.surfaces
        ]
        out.append(
            (float(component.top), float(agent_module.rectangle_union_area(rectangles)))
        )
    return out


def support_profile(agent_module, container, extra=None):
    """
    Connected support area by height band, and the largest single component.

    The largest component matters separately from the total: ten scattered
    tops of 0.1 m2 do not hold a 0.55 x 0.40 suitcase, and one connected
    1.0 m2 does.
    """
    surfaces = list(agent_module.support_surfaces(container))
    if extra is not None:
        surfaces.append(extra)
    bands = collections.defaultdict(float)
    largest = 0.0
    for top, area in component_areas(agent_module, surfaces):
        bands[round(top / BAND) * BAND] += area
        largest = max(largest, area)
    return dict(bands), largest, sum(bands.values())


def candidate_surface(agent_module, container, centre, size, item):
    """
    The support surface a candidate would contribute, or None.

    None for soft or priority cargo -- `support_surfaces` does not admit
    those tops, so such a placement adds nothing and covers whatever it
    lands on.
    """
    if bool(item.get("is_soft")) or bool(item.get("is_prioritized")):
        return None
    rest = agent_module.release_rest_height(centre[0], centre[1], size, container)
    return agent_module.AABB(
        center=(centre[0], centre[1], rest + size[2] / 2.0),
        size=tuple(size),
        name="packed_item",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=pathlib.Path, required=True)
    parser.add_argument("--candidates", type=pathlib.Path, required=True)
    parser.add_argument("--chosen", nargs=3, type=float)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    agent_module = load_agent_module()
    state = json.loads(args.state.read_text(encoding="utf-8"))
    observation = state["observation"]
    rows = [
        json.loads(line)
        for line in args.candidates.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        print("no candidates", file=sys.stderr)
        return 1
    container = observation["container_list"][int(rows[0].get("container_index", 0))]
    item = observation["pool_list"][int(rows[0]["pool_index"])]

    before_bands, before_largest, before_total = support_profile(
        agent_module, container
    )
    print(
        f'item {item["length"]:.2f}x{item["width"]:.2f}x{item["height"]:.2f}  '
        f'soft={bool(item.get("is_soft"))} priority={bool(item.get("is_prioritized"))}'
    )
    print(
        f"before: total support area {before_total:.3f} m2, "
        f"largest component {before_largest:.3f} m2"
    )
    print("        by height band: " + ", ".join(
        f"{z:.2f}:{a:.2f}" for z, a in sorted(before_bands.items())
    ))

    deltas = []
    for row in rows:
        centre = [float(v) for v in row["center"]]
        size = [float(v) for v in row["size"]]
        extra = candidate_surface(agent_module, container, centre, size, item)
        _bands, largest, total = support_profile(agent_module, container, extra)
        deltas.append(
            {
                "center": centre,
                "d_total": total - before_total,
                "d_largest": largest - before_largest,
                "found_by_anytime": bool(row.get("found_by_anytime")),
            }
        )

    values = sorted(d["d_total"] for d in deltas)
    print(
        f"\ndA_total over {len(values)} candidates: "
        f"min {values[0]:+.3f}  median {statistics.median(values):+.3f}  "
        f"max {values[-1]:+.3f}"
    )
    largest_values = sorted(d["d_largest"] for d in deltas)
    print(
        f"dA_largest: min {largest_values[0]:+.3f}  "
        f"median {statistics.median(largest_values):+.3f}  "
        f"max {largest_values[-1]:+.3f}"
    )
    positive = sum(1 for v in values if v > 1e-6)
    print(
        f"candidates that ADD connected support area: {positive} of "
        f"{len(values)} ({100 * positive / len(values):.1f}%)"
    )

    if args.chosen:
        cx, cy, cz = args.chosen
        near = min(
            deltas,
            key=lambda d: (d["center"][0] - cx) ** 2
            + (d["center"][1] - cy) ** 2
            + (d["center"][2] - cz) ** 2,
        )
        rank = sum(1 for v in values if v > near["d_total"])
        print(
            f'\nnearest enumerated pose to the chosen one: '
            f'{[round(v, 3) for v in near["center"]]}'
        )
        print(
            f'  dA_total {near["d_total"]:+.4f}  '
            f'({rank} of {len(values)} candidates create more)'
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "before_total": before_total,
                    "before_largest": before_largest,
                    "before_bands": {str(k): v for k, v in before_bands.items()},
                    "candidates": deltas,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
