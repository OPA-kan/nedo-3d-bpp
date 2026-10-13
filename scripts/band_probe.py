"""The simulator's two height rules at the shelf level, measured in the
official simulator (``config.band_lift``).

The validator carries a box in at its own height, no 8 cm lift, when its
bottom is within 5 cm above the shelf level (``height/2 + thickness``,
tested in every container, shelf or not), and clips the lift under the
level's underside (``height/2``, a ceiling surface in every container) to
the clearance less the 1.8 cm ceiling margin.  A box resting on a packed
item in either band touches its support on the way in and is refused
(``is_valid`` False, the episode ends).  Both rules are step functions
evaluated in float32 on the commanded pose, so a bottom or top exactly on
the level is inside the band there and outside in float64.

This probe stacks a column in the 1.61 m ULD (no shelf: level 0.845, its
underside 0.805) and places one more box with its bottom, or its top, at a
chosen height, unlifted and then commanded the way ``band_lift`` commands
it: the bottom 5.3 cm above the level, or the top 3 mm over the underside.

    .venv312/bin/python -m scripts.band_probe

Needs the simulator extras (see docs/rule_alpha/README.md).
"""

from __future__ import annotations

import contextlib
import io
import sys

import numpy as np

from rule_alpha.penetration import _config
from rule_alpha.physics import _load_env_module

FOOT = (0.60, 0.45)
HEIGHT = 1.61
LEVEL = HEIGHT / 2.0 + 0.04
MID = HEIGHT / 2.0


def place(heights: list[float], top_h: float, command_z) -> tuple[dict, str]:
    """Stack ``heights`` on the floor at one spot, then place a ``top_h``
    box there at the centre height ``command_z(bottom)``."""
    items = [{"index": i, "length": FOOT[0], "width": FOOT[1], "height": h,
              "mass": 8, "is_soft": False, "is_prioritized": False}
             for i, h in enumerate(list(heights) + [top_h])]
    Env = _load_env_module()
    sink = io.StringIO()
    result: dict = {}
    with contextlib.redirect_stdout(sink):
        env = Env(config=_config(items, -0.005), verbose=False, render_mode=None)
        try:
            env.reset_settings()
            env.reset_item_stream()
            obs, _ = env.reset(seed=1)
            x, y = 0.30, 0.20
            bottom = 0.04
            for level, h in enumerate(heights):
                z = bottom + (0.02 if level == 0 else 0.0) + h / 2.0
                obs, _r, _t, _tr, info = env.step({"item_idx": 0, "container_idx": 0,
                                                   "place_pos": np.array([x, y, z], dtype=np.float32),
                                                   "orientation": 0})
                status = (info or {}).get("status", {})
                if not status.get("is_placed_safe"):
                    return {"base_failed_at": level, **{k: bool(v) for k, v in status.items()}}, sink.getvalue()
                bottom += h
            z = command_z(bottom)
            obs, _r, _t, _tr, info = env.step({"item_idx": 0, "container_idx": 0,
                                               "place_pos": np.array([x, y, z], dtype=np.float32),
                                               "orientation": 0})
            status = (info or {}).get("status", {})
            packed = obs["container_list"][0]["packed_items"] if obs else []
            settled = [p for p in packed if int(p["index"]) == len(heights)]
            result = {"bottom": round(bottom, 4), "top": round(bottom + top_h, 4),
                      "commanded_bottom": round(z - top_h / 2.0, 4),
                      **{k: bool(v) for k, v in status.items()},
                      "settled_z": round(float(settled[0]["pos"][2]), 4) if settled else None}
        finally:
            with contextlib.suppress(Exception):
                env.close()
    return result, sink.getvalue()


def main() -> int:
    top_h = 0.30
    bottom_band = {
        "bottom = level + 0.005": (0.27, 0.30, 0.24),
        "bottom = level + 0.025": (0.41, 0.42),
        "bottom = level + 0.05 ": (0.43, 0.425),
        "bottom = level       ": (0.40, 0.405),
        "bottom = level - 0.01": (0.40, 0.395),
        "bottom = level + 0.06": (0.45, 0.415),
    }
    print("# the zero-lift band above the level (0.845): unlifted, then bottom at level + 0.053")
    for name, heights in bottom_band.items():
        for lifted in (False, True):
            cmd = (lambda b: LEVEL + 0.053 + top_h / 2.0) if lifted else (lambda b: b + top_h / 2.0)
            res, log = place(list(heights), top_h, cmd)
            hit = [l for l in log.splitlines() if "collision" in l]
            print(f"{name} {'lifted  ' if lifted else 'unlifted'}: {res}" + (f"  [{hit[-1]}]" if hit else ""))
    top_band = {
        "top = mid       ": (0.235, 0.23),
        "top = mid - 0.02": (0.225, 0.22),
        "top = mid - 0.03": (0.22, 0.215),
        "top = mid - 0.05": (0.21, 0.205),
        "top = mid + 0.01": (0.24, 0.235),
    }
    print("# the ceiling rule under the level's underside (0.805): unlifted, then top at mid + 0.003")
    for name, heights in top_band.items():
        for lifted in (False, True):
            cmd = (lambda b: MID + 0.003 - top_h / 2.0) if lifted else (lambda b: b + top_h / 2.0)
            res, log = place(list(heights), top_h, cmd)
            hit = [l for l in log.splitlines() if "collision" in l]
            print(f"{name} {'lifted  ' if lifted else 'unlifted'}: {res}" + (f"  [{hit[-1]}]" if hit else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
