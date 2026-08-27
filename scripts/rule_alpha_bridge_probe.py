"""Does the official environment accept a bridge?

``agent.py`` refuses a placement whose *single largest* contact patch covers
less than ``MIN_SUPPORT_RATIO`` of the footprint.  Nothing in the simulator
asks for that.  The official acceptance path is

    check_inclusion -> check_transport_path -> place_item

and ``place_item`` warps the item to the target, runs ``settle_wait_step`` of
physics, and accepts it unless it moved more than ``displacement_threshold``
(0.30 m) or rotated more than ``angle_displacement_threshold`` (45 deg).

So the real question for a bridge is not "does one support cover 60 %" but
"does it stay put".  This drives the environment directly with a hand-built
stream: two piers with a gap, then a deck spanning them, at a series of gap
widths.  The deck's single largest contact is deliberately far below 0.6 while
the union of its two contacts is well above it.

    python3 -m scripts.rule_alpha_bridge_probe
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from rule_alpha.physics import _load_env_module, scenario_to_config  # noqa: E402
from rule_alpha.scenarios import scenario_by_name  # noqa: E402


PIER_DX, PIER_DY, PIER_DZ = 0.30, 0.50, 0.30
DECK_DY, DECK_DZ = 0.45, 0.22


def _config(deck_dx: float) -> dict:
    """Two piers and a deck, as an official config."""
    base = scenario_to_config(scenario_by_name("12-large-hard-only"))
    base["item_stream"]["item_list"] = [
        {"index": 0, "length": PIER_DX, "width": PIER_DY, "height": PIER_DZ,
         "mass": 12.0, "is_soft": False, "is_prioritized": False},
        {"index": 1, "length": PIER_DX, "width": PIER_DY, "height": PIER_DZ,
         "mass": 12.0, "is_soft": False, "is_prioritized": False},
        {"index": 2, "length": deck_dx, "width": DECK_DY, "height": DECK_DZ,
         "mass": 8.0, "is_soft": False, "is_prioritized": False},
    ]
    base["item_stream"]["look_ahead"] = 3
    base["item_stream"]["max_space"] = 3
    base["agent"]["optimize"] = False
    return base


def probe(deck_dx: float, gap: float) -> dict:
    """Place two piers ``gap`` apart, then a deck of ``deck_dx`` across them."""
    env_cls = _load_env_module()
    config = _config(deck_dx)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        env = env_cls(config=config, verbose=False, render_mode=None)
        # the boot order EvaluationApp.run uses; reset() alone leaves the
        # container list empty
        env.reset_settings()
        env.set_item_order([0, 1, 2])
        env.reset_item_stream()
        observation, _info = env.reset(seed=42)

        spec = config["containers"]["container_list"][0]
        thickness = float(spec["thickness"])
        buffer = float(spec.get("buffer", 0.0))
        floor_z = thickness + buffer
        offset_x = float(
            observation["container_list"][0].get("center", (0.0, 0.0, 0.0))[0]
        )

        span = gap + PIER_DX          # centre-to-centre of the two piers
        pier_z = floor_z + PIER_DZ / 2.0 + 0.02
        deck_z = floor_z + PIER_DZ + DECK_DZ / 2.0 + 0.02

        actions = [
            (0, (-span / 2.0, 0.15, pier_z)),
            (1, (+span / 2.0, 0.15, pier_z)),
            (2, (0.0, 0.15, deck_z)),
        ]
        results = []
        for item_idx, (x, y, z) in actions:
            obs_action = {
                "item_idx": 0,          # always the head of the visible pool
                "container_idx": 0,
                "place_pos": (x + offset_x, y, z),
                "orientation": 0,
            }
            _obs, _r, _term, _trunc, info = env.step(obs_action)
            results.append(info["status"])
        env.close()

    # geometry of the deck's contacts, for the record
    overlap = max(0.0, min(deck_dx / 2.0, span / 2.0 + PIER_DX / 2.0)
                  - max(-deck_dx / 2.0, span / 2.0 - PIER_DX / 2.0))
    single = overlap * min(DECK_DY, PIER_DY) / (deck_dx * DECK_DY)
    return {
        "gap": gap,
        "deck_dx": deck_dx,
        "single_contact_ratio": round(single, 3),
        "union_contact_ratio": round(min(1.0, 2.0 * single), 3),
        "piers_ok": all(r["is_placed_safe"] for r in results[:2]),
        "deck": results[2],
    }


def cantilever(overhang_fraction: float, deck_dx: float = 0.70) -> dict:
    """One pier, one deck on top overhanging by a fraction of its own width.

    This is the shape the wedge staircase makes, and the number rule-alpha
    guessed (``wedge_overhang_fraction``) was derived from a support-ratio rule
    the simulator does not have.  So ask the simulator instead.
    """
    env_cls = _load_env_module()
    config = _config(deck_dx)
    config["item_stream"]["item_list"] = config["item_stream"]["item_list"][1:]
    for position, item in enumerate(config["item_stream"]["item_list"]):
        item["index"] = position
    config["item_stream"]["look_ahead"] = 2
    config["item_stream"]["max_space"] = 2

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        env = env_cls(config=config, verbose=False, render_mode=None)
        env.reset_settings()
        env.set_item_order([0, 1])
        env.reset_item_stream()
        observation, _info = env.reset(seed=42)
        spec = config["containers"]["container_list"][0]
        floor_z = float(spec["thickness"]) + float(spec.get("buffer", 0.0))
        offset_x = float(
            observation["container_list"][0].get("center", (0.0, 0.0, 0.0))[0]
        )
        pier_z = floor_z + PIER_DZ / 2.0 + 0.02
        deck_z = floor_z + PIER_DZ + DECK_DZ / 2.0 + 0.02
        # deck's left edge hangs `overhang_fraction * deck_dx` past the pier's
        overhang = overhang_fraction * deck_dx
        deck_x = -PIER_DX / 2.0 - overhang + deck_dx / 2.0
        results = []
        commanded = []
        for x, z in ((0.0, pier_z), (deck_x, deck_z)):
            commanded.append((x + offset_x, 0.15, z))
            observation, _r, _t, _tr, info = env.step({
                "item_idx": 0, "container_idx": 0,
                "place_pos": (x + offset_x, 0.15, z), "orientation": 0,
            })
            results.append(info["status"])
        # where did the deck actually end up?  "safe" only means it moved less
        # than displacement_threshold, not that it stayed where it was put.
        settled = None
        for packed in observation["container_list"][0].get("packed_items", []):
            if int(packed.get("index", -1)) == 1:
                settled = packed.get("pos")
        env.close()
    drift = None
    if settled is not None:
        want = commanded[1]
        drift = {
            "dx": round(float(settled[0]) - want[0], 3),
            "dy": round(float(settled[1]) - want[1], 3),
            "dz": round(float(settled[2]) - want[2], 3),
        }
        drift["total"] = round(
            (drift["dx"] ** 2 + drift["dy"] ** 2 + drift["dz"] ** 2) ** 0.5, 3
        )
    return {
        "overhang_fraction": overhang_fraction,
        "pier_ok": results[0]["is_placed_safe"],
        "deck": results[1],
        "drift": drift,
    }


def main() -> int:
    print(f"pier {PIER_DX} x {PIER_DY} x {PIER_DZ},  deck dy={DECK_DY} dz={DECK_DZ}")
    print(f"{'gap':>6}{'deck dx':>9}{'single':>8}{'union':>7}{'piers':>7}"
          f"{'incl':>6}{'path':>6}{'safe':>6}")
    for gap, deck_dx in ((0.20, 0.80), (0.35, 0.95), (0.50, 1.10), (0.65, 1.25)):
        try:
            out = probe(deck_dx, gap)
        except Exception as exc:  # noqa: BLE001 - probe, report and continue
            print(f"{gap:>6.2f}{deck_dx:>9.2f}   failed: {exc}")
            continue
        d = out["deck"]
        print(f"{out['gap']:>6.2f}{out['deck_dx']:>9.2f}"
              f"{out['single_contact_ratio']:>8.2f}{out['union_contact_ratio']:>7.2f}"
              f"{str(out['piers_ok']):>7}{str(d['is_included']):>6}"
              f"{str(d['is_valid']):>6}{str(d['is_placed_safe']):>6}")

    print(f"\ncantilever: deck {0.70} wide on a {PIER_DX} pier, overhanging")
    print(f"{'o/w':>6}{'support':>9}{'pier':>7}{'safe':>6}{'drift m':>9}"
          f"{'  where it actually landed (dx, dy, dz)':<40}")
    for fraction in (0.25, 0.40, 0.50, 0.60, 0.70, 0.80):
        try:
            out = cantilever(fraction)
        except Exception as exc:  # noqa: BLE001
            print(f"{fraction:>6.2f}   failed: {exc}")
            continue
        d = out["deck"]
        drift = out["drift"]
        total = f"{drift['total']:.3f}" if drift else "—"
        where = (f"  ({drift['dx']:+.3f}, {drift['dy']:+.3f}, {drift['dz']:+.3f})"
                 if drift else "  (removed)")
        print(f"{fraction:>6.2f}{1.0 - fraction:>9.2f}{str(out['pier_ok']):>7}"
              f"{str(d['is_placed_safe']):>6}{total:>9}{where:<40}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
