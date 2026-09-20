"""The transport sweep, mirrored from the production agent with the
simulator's two height rules read *conservatively*.

The simulator lifts an item by ``start_z`` (0.08 m) before carrying it in,
except when the item's bottom is within 0.05 m above a resting surface
(the floor, or the shelf level at mid height -- checked in every
container) where it slides in at its own height, and except near a
ceiling surface where the lift is clipped.  Both rules are step functions
of the pose height, and the simulator evaluates them in float32 on the
commanded pose: a planned bottom exactly at the shelf level (0.86 m)
came out as 0.859999 here and 0.860000 there, so this model lifted the
item and the simulator did not -- and the item, carried at its own
height, touched its support on the way in (v6 with the replay fix: eight
of 48 episodes ended that way, every one at bottom 0.86).  So each rule
is applied whenever the pose is within ``EDGE`` of triggering it, and the
sweep is then checked at the *lower* of the two lifts.
"""

from __future__ import annotations

import math

from . import _reuse

AABB = _reuse.AABB
_prod = _reuse._production
EDGE = 0.003


def transport_lifts(candidate, container) -> list[float]:
    """The lifts (m) the simulator may apply to this pose: the nominal
    one, and the reduced ones of any rule the pose is within ``EDGE`` of."""
    height = float(container["height"])
    thickness = float(container["thickness"])
    buffer = float(container.get("buffer", 0.0))
    action_center = _prod.simulator_action_center(candidate, container)
    half_z = float(candidate.size[2]) / 2.0
    bottom_z = float(action_center[2]) - half_z
    top_z = float(action_center[2]) + half_z
    lifts = {float(_prod.SIMULATOR_DROP_HEIGHT)}
    for resting_z in (thickness, height / 2.0 + thickness + buffer):
        if -EDGE <= bottom_z - resting_z <= 0.05 + EDGE:
            lifts.add(0.0)
    margin = float(_prod.SIMULATOR_CEILING_MARGIN)
    clip_eps = float(_prod.SIMULATOR_CEILING_CLIP_EPS)
    for ceiling_z in (height / 2.0 + buffer, height + buffer - thickness):
        clearance = ceiling_z - top_z
        if -EDGE <= clearance < float(_prod.SIMULATOR_DROP_HEIGHT) + margin + EDGE:
            lifts.add(max(0.0, clearance - margin - clip_eps))
    return sorted(lifts)


def transport_samples(candidate, container, step: float | None = None) -> list:
    """Sample poses of the sweep, at the lowest lift the simulator may use."""
    step = float(_prod.TRANSPORT_SAMPLE_STEP) if step is None else float(step)
    length = float(container["length"])
    width = float(container["width"])
    thickness = float(container["thickness"])
    cut_x = float(container.get("cut_x", 0.0))
    height = float(container["height"])
    buffer = float(container.get("buffer", 0.0))
    half_x = float(candidate.size[0]) / 2.0
    half_z = float(candidate.size[2]) / 2.0
    margin = float(_prod.SIMULATOR_START_MARGIN)
    x_min = -length / 2.0 + thickness + cut_x + half_x + margin
    x_max = length / 2.0 - thickness - half_x - margin
    target_x = float(candidate.center[0])
    target_y = float(candidate.center[1])
    start_x = min(max(target_x, x_min), x_max)
    entry_y = -width / 2.0
    action_center = _prod.simulator_action_center(candidate, container)
    lift = transport_lifts(candidate, container)[0]
    maximum_start_z = height + buffer - thickness - half_z - margin
    transport_z = min(maximum_start_z, float(action_center[2]) + lift)

    samples = []
    dist_y = abs(target_y - entry_y)
    steps_y = max(int(math.ceil(dist_y / step)), 1)
    for i in range(steps_y + 1):
        frac = i / steps_y
        y = entry_y + (target_y - entry_y) * frac
        samples.append(AABB((start_x, y, transport_z), candidate.size, "transport_sample_y"))
    dist_x = abs(target_x - start_x)
    steps_x = max(int(math.ceil(dist_x / step)), 1)
    for i in range(steps_x + 1):
        frac = i / steps_x
        x = start_x + (target_x - start_x) * frac
        samples.append(AABB((x, target_y, transport_z), candidate.size, "transport_sample_x"))
    return samples
