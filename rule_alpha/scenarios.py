"""Scenario definitions for looking at rule-alpha Layer 1 boards.

Item sizes follow the official ``sample_config.json`` envelope
(L 0.45-0.75, W 0.30-0.56, H 0.20-0.40, mass 5-18) unless a scenario exists
precisely to leave it, which the elongated and awkward streams do.  Every
stream is generated from a fixed seed so a picture can be reproduced.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from .geometry import make_container_dict


# Official ULD used by sample_config 000 / 001.
ULD = dict(length=2.0, width=1.45, height=1.61, thickness=0.04, cut_x=0.44, cut_y=0.40)
ULD_SHELF = dict(length=2.0, width=1.52, height=1.62, thickness=0.04, cut_x=0.43, cut_y=0.40)


@dataclass
class Scenario:
    name: str
    description: str
    containers: list
    items: list
    look_ahead: int = 1
    notes: str = ""


def _item(index, length, width, height, mass=8.0, soft=False, priority=False) -> dict:
    return {
        "index": index,
        "length": round(length, 3),
        "width": round(width, 3),
        "height": round(height, 3),
        "mass": mass,
        "is_soft": soft,
        "is_prioritized": priority,
    }


def _typical(rng: random.Random, index: int, soft=False, priority=False) -> dict:
    return _item(
        index,
        rng.uniform(0.45, 0.75),
        rng.uniform(0.30, 0.56),
        rng.uniform(0.20, 0.40),
        mass=round(rng.uniform(5, 18), 1),
        soft=soft,
        priority=priority,
    )


def _stream(seed: int, count: int, soft_ratio=0.0, priority_ratio=0.0,
            sp_ratio=0.0, builder=None) -> list[dict]:
    rng = random.Random(seed)
    items = []
    for index in range(count):
        roll = rng.random()
        soft = priority = False
        if roll < sp_ratio:
            soft = priority = True
        elif roll < sp_ratio + soft_ratio:
            soft = True
        elif roll < sp_ratio + soft_ratio + priority_ratio:
            priority = True
        if builder is not None:
            items.append(builder(rng, index, soft, priority))
        else:
            items.append(_typical(rng, index, soft, priority))
    return items


def _normal_container(index=0, offset_x=0.0, shelf=False, prioritized=False) -> dict:
    spec = ULD_SHELF if shelf else ULD
    return make_container_dict(
        index=index,
        require_shelf=shelf,
        is_prioritized=prioritized,
        offset_x=offset_x,
        **spec,
    )


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
def build_scenarios() -> list[Scenario]:
    scenarios: list[Scenario] = []

    # 1. plain container, no shelf, mostly hard cargo
    scenarios.append(
        Scenario(
            name="01-normal-no-shelf",
            description="Single ULD without a shelf, mostly plain hard cargo. "
                        "The reference picture for the rectangular floor rule.",
            containers=[_normal_container()],
            items=_stream(1001, 26, soft_ratio=0.15, priority_ratio=0.08),
        )
    )

    # 2. same stream, shelf container
    scenarios.append(
        Scenario(
            name="02-normal-with-shelf",
            description="Same cargo mix in a shelf ULD: shows where the soft "
                        "items go once a shelf exists, and what the shelf does "
                        "to the back half of the floor.",
            containers=[_normal_container(shelf=True)],
            items=_stream(1001, 26, soft_ratio=0.15, priority_ratio=0.08),
        )
    )

    # 3. priority container plus a normal one
    scenarios.append(
        Scenario(
            name="03-priority-plus-normal",
            description="Priority ULD (index 0) next to a normal ULD. Tests the "
                        "routing rules: soft-only never enters the priority "
                        "container, plain hard may but only inside its budget.",
            containers=[
                _normal_container(index=0, offset_x=0.0, shelf=True, prioritized=True),
                _normal_container(index=1, offset_x=2.5, shelf=False),
            ],
            items=_stream(1002, 40, soft_ratio=0.22, priority_ratio=0.20, sp_ratio=0.08),
        )
    )

    # 4. soft heavy
    scenarios.append(
        Scenario(
            name="04-soft-heavy",
            description="Soft-dominated stream into a shelf ULD: shelf saturates "
                        "early, the rest must cluster on the left soft strip.",
            containers=[_normal_container(shelf=True)],
            items=_stream(1003, 26, soft_ratio=0.72),
        )
    )

    # 5. priority heavy, no priority container
    scenarios.append(
        Scenario(
            name="05-priority-heavy-no-priority-uld",
            description="Priority-dominated stream with no priority ULD: the "
                        "priority edge zone on the right is the only home.",
            containers=[_normal_container()],
            items=_stream(1004, 26, priority_ratio=0.70),
        )
    )

    # 6. soft+priority heavy with a priority shelf container
    scenarios.append(
        Scenario(
            name="06-soft-priority-heavy",
            description="Soft+priority dominated stream with a priority shelf "
                        "ULD present: SP should prefer the priority shelf, then "
                        "cluster.",
            containers=[
                _normal_container(index=0, offset_x=0.0, shelf=True, prioritized=True),
                _normal_container(index=1, offset_x=2.5, shelf=False),
            ],
            items=_stream(1005, 34, sp_ratio=0.55, soft_ratio=0.15),
        )
    )

    # 7. elongated heavy
    def elongated_builder(rng, index, soft, priority):
        long_side = rng.uniform(0.85, 1.30)
        mid = rng.uniform(0.22, 0.36)
        short = rng.uniform(0.14, mid)
        dims = [long_side, mid, short]
        rng.shuffle(dims)
        return _item(index, dims[0], dims[1], dims[2],
                     mass=round(rng.uniform(6, 16), 1), soft=soft, priority=priority)

    scenarios.append(
        Scenario(
            name="07-elongated-heavy",
            description="Long thin cargo (rho 2.5-6): the structural exception "
                        "path. Watch where the wall / corner preference sends "
                        "them and which poses the tipping bands refuse.",
            containers=[_normal_container()],
            items=_stream(1006, 22, soft_ratio=0.10, builder=elongated_builder),
        )
    )

    # 8. slope / cut corner exploitation
    def low_flat_builder(rng, index, soft, priority):
        return _item(
            index,
            rng.uniform(0.30, 0.55),
            rng.uniform(0.26, 0.45),
            rng.uniform(0.16, 0.30),
            mass=round(rng.uniform(5, 12), 1),
            soft=soft,
            priority=priority,
        )

    scenarios.append(
        Scenario(
            name="08-slope-exploitation",
            description="Small low boxes that would fit the chamfer wedge if it "
                        "were reachable. This scenario exists to show whether "
                        "the slope pocket is usable at all from a floor layer.",
            containers=[_normal_container()],
            items=_stream(1007, 30, builder=low_flat_builder),
        )
    )

    # 9. mixed random
    scenarios.append(
        Scenario(
            name="09-mixed-random",
            description="Realistic mixed stream matching the official sample "
                        "config class ratios.",
            containers=[_normal_container(shelf=True)],
            items=_stream(1008, 34, soft_ratio=0.28, priority_ratio=0.10, sp_ratio=0.03),
        )
    )

    # 10. awkward sizes designed to create holes
    def awkward_builder(rng, index, soft, priority):
        # widths that tile the 1.47 m usable length badly on purpose
        length = rng.choice([0.62, 0.66, 0.71, 0.74])
        width = rng.choice([0.33, 0.37, 0.52, 0.55])
        height = rng.choice([0.21, 0.27, 0.34, 0.39])
        return _item(index, length, width, height,
                     mass=round(rng.uniform(5, 18), 1), soft=soft, priority=priority)

    scenarios.append(
        Scenario(
            name="10-awkward-holes",
            description="Deliberately badly tiling sizes: the hole diagnostics "
                        "scenario. Interior holes here are the point, not a bug.",
            containers=[_normal_container()],
            items=_stream(1009, 26, soft_ratio=0.12, builder=awkward_builder),
        )
    )

    # 11. official sample-config-like stream, lookahead 3
    scenarios.append(
        Scenario(
            name="11-lookahead-3",
            description="Same mix as 09 but with look_ahead=3, to see whether "
                        "the pool ordering rule changes the board shape.",
            containers=[_normal_container(shelf=True)],
            items=_stream(1008, 34, soft_ratio=0.28, priority_ratio=0.10, sp_ratio=0.03),
            look_ahead=3,
        )
    )

    # 12. big hard only, the cleanest possible floor
    def big_builder(rng, index, soft, priority):
        return _item(index, rng.uniform(0.68, 0.75), rng.uniform(0.44, 0.56),
                     rng.uniform(0.22, 0.32), mass=round(rng.uniform(10, 18), 1))

    scenarios.append(
        Scenario(
            name="12-large-hard-only",
            description="Only large plain hard cargo: the best case for the "
                        "rectangular floor rule, and the flatness reference.",
            containers=[_normal_container()],
            items=_stream(1010, 20, builder=big_builder),
        )
    )

    # ------------------------------------------------------------------
    # 13: the adversarial order for "large sets the frontier"
    # ------------------------------------------------------------------
    def small_then_large(rng, index, soft, priority):
        """Twelve small hard boxes, then eight large ones.

        The failure this is built to catch: with only the next item visible,
        a run of small cargo arrives first, spreads itself over the floor, and
        leaves nothing but slivers for the large cargo behind it.  Nothing in
        the stream is unusual on its own -- the *order* is the attack.
        """
        if index < 12:
            return _item(index, rng.uniform(0.30, 0.40), rng.uniform(0.24, 0.34),
                         rng.uniform(0.18, 0.28), mass=round(rng.uniform(4, 9), 1))
        return _item(index, rng.uniform(0.70, 0.78), rng.uniform(0.50, 0.60),
                     rng.uniform(0.26, 0.36), mass=round(rng.uniform(12, 20), 1))

    scenarios.append(
        Scenario(
            name="13-small-first-then-large",
            description="Small hard cargo first, large hard cargo after: does "
                        "the follower rule stop the small boxes from carving "
                        "up the bays the large ones still need?",
            containers=[_normal_container()],
            items=_stream(1300, 20, builder=small_then_large),
        )
    )

    return scenarios


def scenario_by_name(name: str) -> Scenario:
    for scenario in build_scenarios():
        if scenario.name == name:
            return scenario
    raise KeyError(name)
