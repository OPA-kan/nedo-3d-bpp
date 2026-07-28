import copy
import heapq
import json
import math
import os
import random
import time
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

# Geometry contract
# -----------------
# - Actions use container-local coordinates.
# - Packed item positions and container planes use world coordinates.
# - The simulator only offsets containers on the world X axis.
# - Boundary clearance includes official, physics-settle, and float32 guards.
# - Transport clearance includes the official 15 mm plus a float32 guard.
# - Settled candidates represent final support contact.
# - Release candidates represent the pose sent to the simulator before settle.
# - Shelf actions are lifted 5.1 cm to avoid the validator's direct-rest path.
OFFICIAL_INCLUSION_CLEARANCE = 0.005
PHYSICS_BOUNDARY_GUARD = 0.010
FLOAT32_CLEARANCE_GUARD = 0.001
INCLUSION_CLEARANCE = (
    OFFICIAL_INCLUSION_CLEARANCE
    + PHYSICS_BOUNDARY_GUARD
    + FLOAT32_CLEARANCE_GUARD
)
OFFICIAL_TRANSPORT_CLEARANCE = 0.015
TRANSPORT_CLEARANCE = (
    OFFICIAL_TRANSPORT_CLEARANCE + FLOAT32_CLEARANCE_GUARD
)
PHYSICS_LATERAL_GUARD = 0.010
SETTLED_ITEM_CLEARANCE = TRANSPORT_CLEARANCE + PHYSICS_LATERAL_GUARD
TRANSPORT_SAMPLE_STEP = 0.03
SIMULATOR_DROP_HEIGHT = 0.08
SIMULATOR_START_MARGIN = 0.01
SIMULATOR_CEILING_MARGIN = 0.018
SIMULATOR_CEILING_CLIP_EPS = 0.0005
SHELF_ACTION_LIFT = 0.051
RELEASE_TARGET_LIFT = 0.052
RELEASE_BOUNDARY_MARGIN = 0.002
CONTACT_TOLERANCE = 0.006
MIN_SUPPORT_RATIO = 0.55
POLICY_BUDGET_SECONDS = 6.5
MAX_POOL_ITEMS_EVALUATED = 10
OFFLINE_SEARCH_BUDGET_SECONDS = float(
    os.environ.get("OFFLINE_SEARCH_BUDGET_SECONDS", "150.0")
)
OFFLINE_MAX_EVALUATIONS = int(
    os.environ.get("OFFLINE_MAX_EVALUATIONS", "1000")
)
OFFLINE_RANDOM_SEED = 20260723
OFFLINE_FILL_WEIGHT = float(
    os.environ.get("OFFLINE_FILL_WEIGHT", "0.65")
)
OFFLINE_STABILITY_WEIGHT = float(
    os.environ.get("OFFLINE_STABILITY_WEIGHT", "0.35")
)
# --- Closed-loop lookahead (online policy) ---
LOOKAHEAD_TOP_K = int(os.environ.get("LOOKAHEAD_TOP_K", "3"))
LOOKAHEAD_DISCOUNT = float(os.environ.get("LOOKAHEAD_DISCOUNT", "0.5"))
LOOKAHEAD_SELECTION_MODE = os.environ.get(
    "LOOKAHEAD_SELECTION_MODE", "weighted"
).strip().lower()
LOOKAHEAD_SELECTION_MODES = frozenset(
    {"weighted", "depth2", "pool_resilience"}
)
LOOKAHEAD_TIME_RESERVE_SECONDS = float(
    os.environ.get("LOOKAHEAD_TIME_RESERVE_SECONDS", "1.5")
)
LOOKAHEAD_INNER_ITEMS = int(os.environ.get("LOOKAHEAD_INNER_ITEMS", "3"))
# --- DPOR (dynamic partial-order reduction) for pair-block ordering ---
DPOR_MAX_ALTERNATE_ATTEMPTS = int(
    os.environ.get("DPOR_MAX_ALTERNATE_ATTEMPTS", "16")
)
# Candidate search is breadth-first across prioritized
# (item, orientation, container) units.  The first pass prevents one
# infeasible unit from consuming the whole policy budget; later passes keep
# improving the best validated incumbent.
ANCHOR_FIRST_PASS_ATTEMPTS = int(
    os.environ.get("ANCHOR_FIRST_PASS_ATTEMPTS", "64")
)
ANCHOR_DEEP_PASS_ATTEMPTS = int(
    os.environ.get("ANCHOR_DEEP_PASS_ATTEMPTS", "256")
)
ANCHOR_GENERATOR_MODES = frozenset({"cartesian", "support_plane"})
ANCHOR_GENERATOR_MODE = os.environ.get(
    "ANCHOR_GENERATOR_MODE", "support_plane"
).strip().lower()
SUPPORT_PLANE_ADJACENCY = float(
    os.environ.get("SUPPORT_PLANE_ADJACENCY", "0.016")
)
SUPPORT_PLANE_ROUND_ATTEMPTS = int(
    os.environ.get("SUPPORT_PLANE_ROUND_ATTEMPTS", "8")
)
CANDIDATE_AUDIT_ENABLED = (
    os.environ.get("NEDO_CANDIDATE_AUDIT", "0").strip().lower()
    in {"1", "true", "yes", "on"}
)
EPS = 1e-6


def get_rotated_dimensions(length, width, height, orientation):
    dimensions = (
        (length, width, height),
        (length, height, width),
        (height, width, length),
        (width, length, height),
        (width, height, length),
        (height, length, width),
    )
    if orientation not in range(6):
        raise ValueError("orientation must be between 0 and 5")
    return tuple(float(value) for value in dimensions[orientation])


def unique_orientations(item):
    seen = set()
    result = []
    for orientation in range(6):
        dims = get_rotated_dimensions(
            item["length"], item["width"], item["height"], orientation
        )
        key = tuple(round(value, 6) for value in dims)
        if key not in seen:
            seen.add(key)
            result.append(orientation)
    return result


def container_offset_x(container):
    center = container.get("center")
    return 0.0 if center is None else float(center[0])


def container_requires_shelf(container):
    return bool(container.get("shelf", container.get("require_shelf", False)))


def normalize_container(container):
    normalized = copy.deepcopy(container)
    normalized["require_shelf"] = container_requires_shelf(normalized)
    normalized.setdefault("buffer", 0.0)
    normalized.setdefault("cut_x", 0.0)
    normalized.setdefault("cut_y", 0.0)
    normalized.setdefault("is_prioritized", False)
    normalized["packed_items"] = []
    return normalized


def local_to_world(local_pos, container):
    x, y, z = (float(value) for value in local_pos)
    return np.array(
        [x + container_offset_x(container), y, z], dtype=np.float64
    )


def world_to_local(world_pos, container):
    x, y, z = (float(value) for value in world_pos)
    return np.array(
        [x - container_offset_x(container), y, z], dtype=np.float64
    )


@lru_cache(maxsize=65536)
def _cached_container_z_interval(
    x,
    y,
    dims,
    offset_x,
    points,
    normals,
):
    half_size = np.asarray(dims, dtype=np.float64) / 2.0
    center_x = float(x) + float(offset_x)
    lower = -float("inf")
    upper = float("inf")
    limit = -INCLUSION_CLEARANCE + EPS

    for point_values, normal_values in zip(points, normals):
        point = np.asarray(point_values, dtype=np.float64)
        normal = np.asarray(normal_values, dtype=np.float64)
        constant = (
            normal[0] * (center_x - point[0])
            + normal[1] * (float(y) - point[1])
            - normal[2] * point[2]
            + float(np.abs(normal) @ half_size)
        )
        coefficient = float(normal[2])
        if abs(coefficient) <= EPS:
            if constant > limit:
                return None
            continue
        boundary = (limit - constant) / coefficient
        if coefficient > 0.0:
            upper = min(upper, boundary)
        else:
            lower = max(lower, boundary)

    if lower > upper + EPS:
        return None
    return (float(lower), float(upper))


def container_z_interval(x, y, dims, container):
    """Exact AABB z interval allowed by the static container half-spaces."""
    points = container.get("points")
    normals = container.get("n_vecs")
    if points is None or normals is None:
        return (-float("inf"), float("inf"))
    point_key = tuple(
        tuple(float(value) for value in point) for point in points
    )
    normal_key = tuple(
        tuple(float(value) for value in normal) for normal in normals
    )
    return _cached_container_z_interval(
        float(x),
        float(y),
        tuple(float(value) for value in dims),
        container_offset_x(container),
        point_key,
        normal_key,
    )


def packed_position_world(packed):
    for key in ("pos", "place_pos", "position", "center"):
        value = packed.get(key)
        if value is not None:
            return np.asarray(value, dtype=np.float64)
    raise KeyError("packed item has no position")


def packed_dimensions(packed):
    if packed.get("dims") is not None:
        return tuple(float(value) for value in packed["dims"])
    settled_orn = packed.get("orn")
    if settled_orn is not None and len(settled_orn) == 4:
        x, y, z, w = (float(value) for value in settled_orn)
        norm = math.sqrt(x * x + y * y + z * z + w * w)
        if norm > EPS:
            x, y, z, w = (value / norm for value in (x, y, z, w))
        rotation = np.array(
            [
                [
                    1.0 - 2.0 * (y * y + z * z),
                    2.0 * (x * y - z * w),
                    2.0 * (x * z + y * w),
                ],
                [
                    2.0 * (x * y + z * w),
                    1.0 - 2.0 * (x * x + z * z),
                    2.0 * (y * z - x * w),
                ],
                [
                    2.0 * (x * z - y * w),
                    2.0 * (y * z + x * w),
                    1.0 - 2.0 * (x * x + y * y),
                ],
            ],
            dtype=np.float64,
        )
        base_dimensions = np.array(
            [
                packed["length"],
                packed["width"],
                packed["height"],
            ],
            dtype=np.float64,
        )
        settled_aabb = np.abs(rotation) @ base_dimensions
        return tuple(float(value) for value in settled_aabb)
    orientation = int(packed.get("orientation", 0))
    return get_rotated_dimensions(
        packed["length"], packed["width"], packed["height"], orientation
    )


@dataclass(frozen=True)
class AABB:
    center: tuple
    size: tuple
    name: str = ""

    @property
    def minimum(self):
        return np.asarray(self.center) - np.asarray(self.size) / 2.0

    @property
    def maximum(self):
        return np.asarray(self.center) + np.asarray(self.size) / 2.0

    @property
    def top(self):
        return float(self.maximum[2])


@dataclass(frozen=True)
class SupportPlaneComponent:
    surfaces: tuple

    @property
    def top(self):
        return max(float(surface.top) for surface in self.surfaces)

    @property
    def minimum_xy(self):
        return np.min(
            np.asarray(
                [surface.minimum[:2] for surface in self.surfaces],
                dtype=np.float64,
            ),
            axis=0,
        )

    @property
    def maximum_xy(self):
        return np.max(
            np.asarray(
                [surface.maximum[:2] for surface in self.surfaces],
                dtype=np.float64,
            ),
            axis=0,
        )

    @property
    def area(self):
        rectangles = [
            (
                float(surface.minimum[0]),
                float(surface.maximum[0]),
                float(surface.minimum[1]),
                float(surface.maximum[1]),
            )
            for surface in self.surfaces
        ]
        return rectangle_union_area(rectangles)

    @property
    def contains_floor(self):
        return any(surface.name == "floor" for surface in self.surfaces)


@dataclass(frozen=True)
class SupportMetrics:
    ratio: float
    center_margin: float
    contact_count: int
    mass_support_ratio: float


@dataclass(frozen=True)
class PlacementDecision:
    action: dict
    candidate: AABB
    score: float


@dataclass(frozen=True)
class VisiblePoolFeasibility:
    feasible_items: int
    evaluated_items: int
    best_score: float


@dataclass(frozen=True)
class LookaheadEvaluation:
    decision: PlacementDecision
    feasible_next_items: int
    total_next_items: int
    best_next_score: float


@dataclass(frozen=True)
class PlacementTrace:
    item_index: int
    container_idx: int
    orientation: int
    candidate: AABB
    support: SupportMetrics
    mass: float


@dataclass(frozen=True)
class BlockSignature:
    fill_ratio: float
    top_profile: tuple
    min_support_ratio: float
    total_mass: float
    center_of_mass: tuple


@dataclass(frozen=True)
class BlockTemplate:
    item_indices: tuple
    internal_order: tuple
    relative_placements: tuple
    dimensions: tuple
    signature: BlockSignature


@dataclass(frozen=True)
class DryRunResult:
    placed_count: int
    failed_index: object
    placed_volume: float
    fill_ratio: float
    stability_proxy: float
    center_of_mass_z: float
    normalized_center_of_mass_z: float
    mean_support_ratio: float
    min_support_ratio: float
    min_support_margin: float
    mean_support_count: float
    runtime_seconds: float

    def rank_key(self):
        return (
            int(self.placed_count),
            float(self.placed_volume),
            float(self.fill_ratio),
            float(self.stability_proxy),
            -float(self.normalized_center_of_mass_z),
        )

    def weighted_score(
        self,
        fill_weight=OFFLINE_FILL_WEIGHT,
        stability_weight=OFFLINE_STABILITY_WEIGHT,
    ):
        return (
            float(fill_weight) * float(self.fill_ratio)
            + float(stability_weight) * float(self.stability_proxy)
        )


def shelf_aabbs(container):
    length = float(container["length"])
    width = float(container["width"])
    height = float(container["height"])
    thickness = float(container["thickness"])
    buffer = float(container.get("buffer", 0.0))
    cut_x = float(container.get("cut_x", 0.0))
    shelf_z = height / 2.0 + thickness / 2.0 + buffer

    shelves = []
    if cut_x > 0.0:
        shelves.append(
            AABB(
                center=(
                    -length / 2.0 + cut_x / 2.0 + thickness,
                    0.0,
                    shelf_z,
                ),
                size=(cut_x, width - 2.0 * thickness, thickness),
                name="small_shelf",
            )
        )

    if container_requires_shelf(container):
        shelves.append(
            AABB(
                center=(0.0, width / 4.0, shelf_z),
                size=(
                    length - thickness,
                    width / 2.0 - 2.0 * thickness,
                    thickness,
                ),
                name="main_shelf",
            )
        )
    return shelves


def packed_aabbs_local(container):
    boxes = []
    for packed in container.get("packed_items", []):
        try:
            center = world_to_local(packed_position_world(packed), container)
            dims = packed_dimensions(packed)
        except (KeyError, TypeError, ValueError):
            continue
        boxes.append(
            (
                AABB(tuple(center), dims, "packed_item"),
                bool(packed.get("is_soft", False)),
                bool(packed.get("is_prioritized", False)),
            )
        )
    return boxes


def xy_overlap_area(first, second):
    overlap = np.maximum(
        0.0,
        np.minimum(first.maximum[:2], second.maximum[:2])
        - np.maximum(first.minimum[:2], second.minimum[:2]),
    )
    return float(overlap[0] * overlap[1])


def rectangle_union_area(rectangles):
    """Exact union area for a small collection of axis-aligned rectangles."""
    normalized = [
        (float(x0), float(x1), float(y0), float(y1))
        for x0, x1, y0, y1 in rectangles
        if float(x1) > float(x0) + EPS and float(y1) > float(y0) + EPS
    ]
    if not normalized:
        return 0.0
    xs = sorted({value for rect in normalized for value in rect[:2]})
    area = 0.0
    for x0, x1 in zip(xs, xs[1:]):
        if x1 <= x0 + EPS:
            continue
        intervals = sorted(
            (y0, y1)
            for rx0, rx1, y0, y1 in normalized
            if rx0 < x1 - EPS and rx1 > x0 + EPS
        )
        if not intervals:
            continue
        covered = 0.0
        current_start, current_end = intervals[0]
        for start, end in intervals[1:]:
            if start <= current_end + EPS:
                current_end = max(current_end, end)
            else:
                covered += current_end - current_start
                current_start, current_end = start, end
        covered += current_end - current_start
        area += (x1 - x0) * covered
    return float(area)


def _axis_gap(first_min, first_max, second_min, second_max):
    return max(
        0.0,
        float(second_min) - float(first_max),
        float(first_min) - float(second_max),
    )


def _axis_overlap(first_min, first_max, second_min, second_max):
    return min(float(first_max), float(second_max)) - max(
        float(first_min), float(second_min)
    )


def support_surfaces_are_adjacent(
    first,
    second,
    adjacency=SUPPORT_PLANE_ADJACENCY,
):
    if abs(float(first.top) - float(second.top)) > CONTACT_TOLERANCE:
        return False
    x_gap = _axis_gap(
        first.minimum[0],
        first.maximum[0],
        second.minimum[0],
        second.maximum[0],
    )
    y_gap = _axis_gap(
        first.minimum[1],
        first.maximum[1],
        second.minimum[1],
        second.maximum[1],
    )
    x_overlap = _axis_overlap(
        first.minimum[0],
        first.maximum[0],
        second.minimum[0],
        second.maximum[0],
    )
    y_overlap = _axis_overlap(
        first.minimum[1],
        first.maximum[1],
        second.minimum[1],
        second.maximum[1],
    )
    return bool(
        (x_gap <= adjacency + EPS and y_overlap > EPS)
        or (y_gap <= adjacency + EPS and x_overlap > EPS)
    )


def support_plane_components(
    surfaces,
    adjacency=SUPPORT_PLANE_ADJACENCY,
):
    surfaces = list(surfaces)
    parents = list(range(len(surfaces)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first_index, second_index):
        first_root = find(first_index)
        second_root = find(second_index)
        if first_root != second_root:
            parents[second_root] = first_root

    for first_index, first in enumerate(surfaces):
        for second_index in range(first_index + 1, len(surfaces)):
            if support_surfaces_are_adjacent(
                first,
                surfaces[second_index],
                adjacency=adjacency,
            ):
                union(first_index, second_index)

    groups = {}
    for index, surface in enumerate(surfaces):
        groups.setdefault(find(index), []).append(surface)
    return [
        SupportPlaneComponent(tuple(group))
        for group in groups.values()
    ]


def order_support_plane_components(components):
    """Floor, area, depth, then low height preserve future accessibility."""
    return sorted(
        components,
        key=lambda component: (
            0 if component.contains_floor else 1,
            -float(component.area),
            -float(component.maximum_xy[1]),
            float(component.top),
            float(component.minimum_xy[0]),
            float(component.minimum_xy[1]),
        ),
    )


def support_component_overlap_area(candidate, component):
    rectangles = []
    for surface in component.surfaces:
        overlap_min = np.maximum(
            candidate.minimum[:2], surface.minimum[:2]
        )
        overlap_max = np.minimum(
            candidate.maximum[:2], surface.maximum[:2]
        )
        rectangles.append(
            (
                float(overlap_min[0]),
                float(overlap_max[0]),
                float(overlap_min[1]),
                float(overlap_max[1]),
            )
        )
    return rectangle_union_area(rectangles)


def penetrates_with_lateral_clearance(candidate, obstacle, clearance):
    vertical_gap = max(
        obstacle.minimum[2] - candidate.maximum[2],
        candidate.minimum[2] - obstacle.maximum[2],
    )
    if vertical_gap >= -CONTACT_TOLERANCE:
        return False

    x_gap = max(
        obstacle.minimum[0] - candidate.maximum[0],
        candidate.minimum[0] - obstacle.maximum[0],
    )
    y_gap = max(
        obstacle.minimum[1] - candidate.maximum[1],
        candidate.minimum[1] - obstacle.maximum[1],
    )
    return x_gap < clearance - EPS and y_gap < clearance - EPS


def within_euclidean_clearance(candidate, obstacle, clearance):
    gaps = np.maximum(
        0.0,
        np.maximum(
            obstacle.minimum - candidate.maximum,
            candidate.minimum - obstacle.maximum,
        ),
    )
    return float(np.linalg.norm(gaps)) < float(clearance) - EPS


def transport_sweeps(candidate, container):
    length = float(container["length"])
    width = float(container["width"])
    thickness = float(container["thickness"])
    cut_x = float(container.get("cut_x", 0.0))
    half_x = float(candidate.size[0]) / 2.0
    x_min = (
        -length / 2.0
        + thickness
        + cut_x
        + half_x
        + SIMULATOR_START_MARGIN
    )
    x_max = (
        length / 2.0
        - thickness
        - half_x
        - SIMULATOR_START_MARGIN
    )
    target_x = float(candidate.center[0])
    target_y = float(candidate.center[1])
    start_x = min(max(target_x, x_min), x_max)
    entry_y = -width / 2.0
    action_center = simulator_action_center(candidate, container)
    height = float(container["height"])
    buffer = float(container.get("buffer", 0.0))
    half_z = float(candidate.size[2]) / 2.0
    effective_start_z = SIMULATOR_DROP_HEIGHT
    bottom_z = float(action_center[2]) - half_z
    resting_surfaces = (
        thickness,
        height / 2.0 + thickness + buffer,
    )
    for resting_z in resting_surfaces:
        if 0.0 <= bottom_z - resting_z <= 0.05:
            effective_start_z = 0.0
            break

    top_z = float(action_center[2]) + half_z
    if effective_start_z > 0.0:
        ceiling_surfaces = (
            height / 2.0 + buffer,
            height + buffer - thickness,
        )
        for ceiling_z in ceiling_surfaces:
            clearance = ceiling_z - top_z
            if (
                0.0
                <= clearance
                < effective_start_z + SIMULATOR_CEILING_MARGIN
            ):
                effective_start_z = max(
                    0.0,
                    clearance
                    - SIMULATOR_CEILING_MARGIN
                    - SIMULATOR_CEILING_CLIP_EPS,
                )
                break

    maximum_start_z = (
        height
        + buffer
        - thickness
        - half_z
        - SIMULATOR_START_MARGIN
    )
    transport_z = min(
        maximum_start_z,
        float(action_center[2]) + effective_start_z,
    )
    y_leg = AABB(
        center=(start_x, (entry_y + target_y) / 2.0, transport_z),
        size=(
            float(candidate.size[0]),
            abs(target_y - entry_y) + float(candidate.size[1]),
            float(candidate.size[2]),
        ),
        name="transport_y_sweep",
    )
    x_leg = AABB(
        center=((start_x + target_x) / 2.0, target_y, transport_z),
        size=(
            abs(target_x - start_x) + float(candidate.size[0]),
            float(candidate.size[1]),
            float(candidate.size[2]),
        ),
        name="transport_x_sweep",
    )
    return (y_leg, x_leg)


def transport_sweep(candidate, container):
    sweeps = transport_sweeps(candidate, container)
    minimum = np.minimum(sweeps[0].minimum, sweeps[1].minimum)
    maximum = np.maximum(sweeps[0].maximum, sweeps[1].maximum)
    return AABB(
        center=tuple(float(value) for value in (minimum + maximum) / 2.0),
        size=tuple(float(value) for value in maximum - minimum),
        name="transport_sweep",
    )


def transport_samples(candidate, container, step: float = TRANSPORT_SAMPLE_STEP):
    length = float(container["length"])
    width = float(container["width"])
    thickness = float(container["thickness"])
    cut_x = float(container.get("cut_x", 0.0))
    half_x = float(candidate.size[0]) / 2.0
    x_min = (
        -length / 2.0
        + thickness
        + cut_x
        + half_x
        + SIMULATOR_START_MARGIN
    )
    x_max = (
        length / 2.0
        - thickness
        - half_x
        - SIMULATOR_START_MARGIN
    )
    target_x = float(candidate.center[0])
    target_y = float(candidate.center[1])
    start_x = min(max(target_x, x_min), x_max)
    entry_y = -width / 2.0
    action_center = simulator_action_center(candidate, container)
    height = float(container["height"])
    buffer = float(container.get("buffer", 0.0))
    half_z = float(candidate.size[2]) / 2.0
    effective_start_z = SIMULATOR_DROP_HEIGHT
    bottom_z = float(action_center[2]) - half_z
    resting_surfaces = (
        thickness,
        height / 2.0 + thickness + buffer,
    )
    for resting_z in resting_surfaces:
        if 0.0 <= bottom_z - resting_z <= 0.05:
            effective_start_z = 0.0
            break

    top_z = float(action_center[2]) + half_z
    if effective_start_z > 0.0:
        ceiling_surfaces = (
            height / 2.0 + buffer,
            height + buffer - thickness,
        )
        for ceiling_z in ceiling_surfaces:
            clearance = ceiling_z - top_z
            if (
                0.0
                <= clearance
                < effective_start_z + SIMULATOR_CEILING_MARGIN
            ):
                effective_start_z = max(
                    0.0,
                    clearance
                    - SIMULATOR_CEILING_MARGIN
                    - SIMULATOR_CEILING_CLIP_EPS,
                )
                break

    maximum_start_z = (
        height
        + buffer
        - thickness
        - half_z
        - SIMULATOR_START_MARGIN
    )
    transport_z = min(
        maximum_start_z,
        float(action_center[2]) + effective_start_z,
    )

    samples = []
    dist_y = abs(target_y - entry_y)
    steps_y = max(int(math.ceil(dist_y / step)), 1)
    for i in range(steps_y + 1):
        frac = i / steps_y
        y = entry_y + (target_y - entry_y) * frac
        samples.append(
            AABB((start_x, y, transport_z), candidate.size, "transport_sample_y")
        )

    dist_x = abs(target_x - start_x)
    steps_x = max(int(math.ceil(dist_x / step)), 1)
    for i in range(steps_x + 1):
        frac = i / steps_x
        x = start_x + (target_x - start_x) * frac
        samples.append(
            AABB((x, target_y, transport_z), candidate.size, "transport_sample_x")
        )

    return samples


def simulator_action_center(candidate, container):
    action_center = np.asarray(candidate.center, dtype=np.float64).copy()
    if candidate.name == "release_candidate":
        return action_center
    for shelf in shelf_aabbs(container):
        if (
            abs(float(candidate.minimum[2]) - shelf.top)
            <= CONTACT_TOLERANCE
            and xy_overlap_area(candidate, shelf) > EPS
        ):
            action_center[2] += SHELF_ACTION_LIFT
            break
    return action_center


def support_surfaces(container):
    thickness = float(container["thickness"])
    buffer = float(container.get("buffer", 0.0))
    length = float(container["length"])
    width = float(container["width"])

    surfaces = [
        AABB(
            center=(0.0, 0.0, thickness + buffer),
            size=(length, width, 0.0),
            name="floor",
        )
    ]
    surfaces.extend(shelf_aabbs(container))
    for box, is_soft, is_prioritized in packed_aabbs_local(container):
        if not is_soft and not is_prioritized:
            surfaces.append(box)
    return surfaces


class Geometry:
    @staticmethod
    def inside_container(candidate, container):
        points = container.get("points")
        normals = container.get("n_vecs")
        if points is None or normals is None:
            return True

        center_world = local_to_world(candidate.center, container)
        half_size = np.asarray(candidate.size, dtype=np.float64) / 2.0
        points = np.asarray(points, dtype=np.float64)
        normals = np.asarray(normals, dtype=np.float64)
        signed_extents = (
            np.sum(normals * (center_world - points), axis=1)
            + np.abs(normals) @ half_size
        )
        return bool(np.all(signed_extents <= -INCLUSION_CLEARANCE + EPS))

    @staticmethod
    def clears_static_geometry(candidate, container):
        for shelf in shelf_aabbs(container):
            if penetrates_with_lateral_clearance(
                candidate, shelf, SETTLED_ITEM_CLEARANCE
            ):
                return False
        for packed, _is_soft, _is_prioritized in packed_aabbs_local(container):
            if penetrates_with_lateral_clearance(
                candidate, packed, SETTLED_ITEM_CLEARANCE
            ):
                return False
        return True

    @staticmethod
    def support_ratio(candidate, container):
        item_area = float(candidate.size[0] * candidate.size[1])
        if item_area <= EPS:
            return 0.0

        bottom = float(candidate.minimum[2])
        contact_surfaces = [
            surface
            for surface in support_surfaces(container)
            if abs(bottom - surface.top) <= CONTACT_TOLERANCE
            and xy_overlap_area(candidate, surface) > EPS
        ]
        supported_area = max(
            (
                support_component_overlap_area(candidate, component)
                for component in support_plane_components(contact_surfaces)
            ),
            default=0.0,
        )
        return min(1.0, supported_area / item_area)

    @staticmethod
    def support_metrics(candidate, container, item=None):
        item_area = float(candidate.size[0] * candidate.size[1])
        if item_area <= EPS:
            return SupportMetrics(0.0, -1.0, 0, 0.0)

        contacts = []
        thickness = float(container["thickness"])
        buffer = float(container.get("buffer", 0.0))
        static_surfaces = [
            AABB(
                center=(0.0, 0.0, thickness + buffer),
                size=(
                    float(container["length"]),
                    float(container["width"]),
                    0.0,
                ),
                name="floor",
            )
        ]
        static_surfaces.extend(shelf_aabbs(container))
        for surface in static_surfaces:
            contacts.append((surface, 1.0))

        item_mass = max(EPS, float((item or {}).get("mass", 1.0)))
        for packed in container.get("packed_items", []):
            if bool(packed.get("is_soft", False)):
                continue
            if bool(packed.get("is_prioritized", False)):
                continue
            try:
                box = AABB(
                    tuple(
                        world_to_local(
                            packed_position_world(packed), container
                        )
                    ),
                    packed_dimensions(packed),
                    "packed_item",
                )
            except (KeyError, TypeError, ValueError):
                continue
            support_mass = max(EPS, float(packed.get("mass", 1.0)))
            contacts.append((box, min(1.0, support_mass / item_mass)))

        bottom = float(candidate.minimum[2])
        margins = []
        mass_weighted = 0.0
        area_weight = 0.0
        contact_count = 0
        center_xy = np.asarray(candidate.center[:2], dtype=np.float64)
        normalizer = max(
            EPS, 0.5 * min(float(candidate.size[0]), float(candidate.size[1]))
        )

        for surface, mass_ratio in contacts:
            if abs(bottom - surface.top) > CONTACT_TOLERANCE:
                continue
            overlap_min = np.maximum(
                candidate.minimum[:2], surface.minimum[:2]
            )
            overlap_max = np.minimum(
                candidate.maximum[:2], surface.maximum[:2]
            )
            span = np.maximum(0.0, overlap_max - overlap_min)
            area = float(span[0] * span[1])
            if area <= EPS:
                continue

            contact_count += 1
            signed_margin = min(
                float(center_xy[0] - overlap_min[0]),
                float(overlap_max[0] - center_xy[0]),
                float(center_xy[1] - overlap_min[1]),
                float(overlap_max[1] - center_xy[1]),
            )
            margins.append(max(-1.0, min(1.0, signed_margin / normalizer)))
            mass_weighted += area * mass_ratio
            area_weight += area

        ratio = Geometry.support_ratio(candidate, container)
        center_margin = max(margins) if margins else -1.0
        mass_support = (
            min(1.0, mass_weighted / area_weight)
            if area_weight > EPS
            else 0.0
        )
        return SupportMetrics(
            ratio=ratio,
            center_margin=center_margin,
            contact_count=contact_count,
            mass_support_ratio=mass_support,
        )

    @staticmethod
    def has_stable_support(candidate, container):
        return Geometry.support_ratio(candidate, container) >= MIN_SUPPORT_RATIO

    @staticmethod
    def transport_path_clear(candidate, container):
        for sample in transport_samples(candidate, container):
            for obstacle in shelf_aabbs(container):
                if within_euclidean_clearance(
                    sample, obstacle, SETTLED_ITEM_CLEARANCE
                ):
                    return False
            for obstacle, _is_soft, _is_prioritized in packed_aabbs_local(
                container
            ):
                if within_euclidean_clearance(
                    sample, obstacle, SETTLED_ITEM_CLEARANCE
                ):
                    return False
        return True

    @classmethod
    def rejection_reason(cls, candidate, container):
        if not cls.inside_container(candidate, container):
            return "containment"
        if not cls.clears_static_geometry(candidate, container):
            return "static_geometry"
        if not cls.has_stable_support(candidate, container):
            return "support"
        if not cls.transport_path_clear(candidate, container):
            return "corridor"
        return None

    @classmethod
    def release_rejection_reason(cls, candidate, container):
        if not cls.inside_container(candidate, container):
            return "containment"
        if not cls.clears_static_geometry(candidate, container):
            return "static_geometry"
        if not cls.transport_path_clear(candidate, container):
            return "corridor"
        return None

    @classmethod
    def valid(cls, candidate, container):
        if candidate.name == "release_candidate":
            return cls.release_rejection_reason(candidate, container) is None
        return cls.rejection_reason(candidate, container) is None


REJECTION_REASONS = (
    "containment",
    "headroom",
    "static_geometry",
    "support",
    "corridor",
)


def _new_candidate_counter():
    return {
        "attempted": 0,
        "accepted": 0,
        "envelope_pruned": 0,
        "rejected": {reason: 0 for reason in REJECTION_REASONS},
    }


def _diagnostic_counters(diagnostics, item_idx, kind):
    total = diagnostics.setdefault("total", _new_candidate_counter())
    by_item = diagnostics.setdefault("by_item", {})
    item_counter = by_item.setdefault(str(item_idx), _new_candidate_counter())
    by_kind = diagnostics.setdefault("by_kind", {})
    kind_counter = by_kind.setdefault(str(kind), _new_candidate_counter())
    return total, item_counter, kind_counter


def _record_candidate_diagnostic(
    diagnostics,
    item_idx,
    reason,
    kind="settled",
):
    if diagnostics is None:
        return
    for counter in _diagnostic_counters(diagnostics, item_idx, kind):
        counter["attempted"] += 1
        if reason is None:
            counter["accepted"] += 1
        else:
            counter["rejected"][reason] += 1


def _record_envelope_prune(diagnostics, item_idx, kind="settled"):
    if diagnostics is None:
        return
    for counter in _diagnostic_counters(diagnostics, item_idx, kind):
        counter["envelope_pruned"] += 1


def release_rest_height(x, y, dims, container):
    footprint = AABB(
        center=(float(x), float(y), 0.0),
        size=(float(dims[0]), float(dims[1]), 0.0),
        name="release_footprint",
    )
    height = float(container["thickness"]) + float(
        container.get("buffer", 0.0)
    )
    obstacles = list(shelf_aabbs(container))
    obstacles.extend(
        box for box, _is_soft, _is_priority in packed_aabbs_local(container)
    )
    for obstacle in obstacles:
        if xy_overlap_area(footprint, obstacle) > EPS:
            height = max(height, obstacle.top)
    return height


def settled_proxy_candidate(candidate, container):
    if candidate.name != "release_candidate":
        return candidate
    interval = container_z_interval(
        candidate.center[0],
        candidate.center[1],
        candidate.size,
        container,
    )
    if interval is None:
        return candidate
    rest_height = release_rest_height(
        candidate.center[0],
        candidate.center[1],
        candidate.size,
        container,
    )
    proxy_z = max(
        interval[0],
        rest_height + float(candidate.size[2]) / 2.0,
    )
    return AABB(
        center=(
            float(candidate.center[0]),
            float(candidate.center[1]),
            float(proxy_z),
        ),
        size=candidate.size,
        name="release_settled_proxy",
    )


def rectangular_container_anchor_bounds(dims, container):
    dx, dy, _dz = dims
    length = float(container["length"])
    width = float(container["width"])
    thickness = float(container["thickness"])
    return (
        -length / 2.0 + thickness + dx / 2.0 + INCLUSION_CLEARANCE,
        length / 2.0 - thickness - dx / 2.0 - INCLUSION_CLEARANCE,
        -width / 2.0 + thickness + dy / 2.0 + INCLUSION_CLEARANCE,
        width / 2.0 - thickness - dy / 2.0 - INCLUSION_CLEARANCE,
    )


def _component_near_obstacle(component, obstacle, dims):
    dx, dy, _dz = dims
    x_gap = _axis_gap(
        component.minimum_xy[0],
        component.maximum_xy[0],
        obstacle.minimum[0],
        obstacle.maximum[0],
    )
    y_gap = _axis_gap(
        component.minimum_xy[1],
        component.maximum_xy[1],
        obstacle.minimum[1],
        obstacle.maximum[1],
    )
    return bool(
        x_gap <= dx + SETTLED_ITEM_CLEARANCE + EPS
        and y_gap <= dy + SETTLED_ITEM_CLEARANCE + EPS
    )


def support_plane_anchor_positions(component, dims, container):
    """Generate anchors coupled to one connected horizontal support plane."""
    dx, dy, dz = dims
    x_low, x_high, y_low, y_high = rectangular_container_anchor_bounds(
        dims, container
    )
    if x_low > x_high + EPS or y_low > y_high + EPS:
        return []

    xs = {
        float(x_low),
        0.0,
        float(x_high),
        float((component.minimum_xy[0] + component.maximum_xy[0]) / 2.0),
        float(component.minimum_xy[0] + dx / 2.0),
        float(component.maximum_xy[0] - dx / 2.0),
    }
    ys = {
        float(y_low),
        0.0,
        float(y_high),
        float((component.minimum_xy[1] + component.maximum_xy[1]) / 2.0),
        float(component.minimum_xy[1] + dy / 2.0),
        float(component.maximum_xy[1] - dy / 2.0),
    }
    for surface in component.surfaces:
        xs.update(
            (
                float(surface.center[0]),
                float(surface.minimum[0] + dx / 2.0),
                float(surface.maximum[0] - dx / 2.0),
            )
        )
        ys.update(
            (
                float(surface.center[1]),
                float(surface.minimum[1] + dy / 2.0),
                float(surface.maximum[1] - dy / 2.0),
            )
        )

    candidate_bottom = float(component.top)
    candidate_top = candidate_bottom + float(dz)
    obstacles = list(shelf_aabbs(container))
    obstacles.extend(
        box for box, _is_soft, _is_priority in packed_aabbs_local(container)
    )
    for obstacle in obstacles:
        vertical_gap = max(
            float(obstacle.minimum[2]) - candidate_top,
            candidate_bottom - float(obstacle.maximum[2]),
        )
        if (
            vertical_gap >= -CONTACT_TOLERANCE
            or not _component_near_obstacle(component, obstacle, dims)
        ):
            continue
        xs.update(
            (
                float(
                    obstacle.minimum[0]
                    - dx / 2.0
                    - TRANSPORT_CLEARANCE
                ),
                float(
                    obstacle.maximum[0]
                    + dx / 2.0
                    + TRANSPORT_CLEARANCE
                ),
            )
        )
        ys.update(
            (
                float(
                    obstacle.minimum[1]
                    - dy / 2.0
                    - TRANSPORT_CLEARANCE
                ),
                float(
                    obstacle.maximum[1]
                    + dy / 2.0
                    + TRANSPORT_CLEARANCE
                ),
            )
        )

    xs = sorted(
        (
            value
            for value in xs
            if x_low - EPS <= value <= x_high + EPS
        ),
        key=abs,
    )
    ys = sorted(
        (
            value
            for value in ys
            if y_low - EPS <= value <= y_high + EPS
        ),
        reverse=True,
    )
    z = float(component.top + dz / 2.0)
    return [
        (float(x), float(y), z)
        for y in ys
        for x in xs
    ]


def support_plane_anchor_count(components, dims, container):
    return len(
        {
            tuple(round(value, 6) for value in position)
            for component in components
            for position in support_plane_anchor_positions(
                component, dims, container
            )
        }
    )


class CandidateGenerator:
    @staticmethod
    def iter_cartesian_attempts(
        observation,
        item,
        container_idx,
        orientation,
        limit=400,
        deadline=None,
        diagnostics=None,
        item_idx=None,
        attempt_kind="both",
    ):
        """
        Yield every validated candidate attempt lazily.

        A rejected or envelope-pruned anchor yields ``None`` so the caller
        can time-slice work by attempted anchors rather than by accepted
        candidates.  This is important late in an episode, where a unit may
        inspect tens of thousands of invalid anchors before finding nothing.
        """
        if attempt_kind not in {"both", "settled", "release"}:
            raise ValueError(
                "attempt_kind must be 'both', 'settled', or 'release'"
            )
        container = observation["container_list"][container_idx]
        if item_idx is None:
            item_idx = item.get("index", -1)
        dims = get_rotated_dimensions(
            item["length"], item["width"], item["height"], orientation
        )
        dx, dy, dz = dims
        length = float(container["length"])
        width = float(container["width"])
        thickness = float(container["thickness"])
        cut_x = float(container.get("cut_x", 0.0))

        x_low = (
            -length / 2.0
            + thickness
            + dx / 2.0
            + INCLUSION_CLEARANCE
        )
        x_high = (
            length / 2.0
            - thickness
            - dx / 2.0
            - INCLUSION_CLEARANCE
        )
        y_low = (
            -width / 2.0
            + thickness
            + dy / 2.0
            + INCLUSION_CLEARANCE
        )
        y_high = (
            width / 2.0
            - thickness
            - dy / 2.0
            - INCLUSION_CLEARANCE
        )
        if x_low > x_high + EPS or y_low > y_high + EPS:
            _record_envelope_prune(diagnostics, item_idx)
            yield None
            return

        xs = {x_low, 0.0, x_high}
        ys = {y_low, 0.0, y_high}
        zs = set()

        if cut_x > 0.0:
            xs.add(
                -length / 2.0
                + thickness
                + cut_x
                + dx / 2.0
                + TRANSPORT_CLEARANCE
            )

        for surface in support_surfaces(container):
            zs.add(surface.top + dz / 2.0)
            xs.update(
                (
                    surface.minimum[0] + dx / 2.0,
                    surface.maximum[0] - dx / 2.0,
                )
            )
            ys.update(
                (
                    surface.minimum[1] + dy / 2.0,
                    surface.maximum[1] - dy / 2.0,
                )
            )

        for packed, _is_soft, _is_prioritized in packed_aabbs_local(container):
            xs.update(
                (
                    packed.minimum[0] - dx / 2.0 - TRANSPORT_CLEARANCE,
                    packed.maximum[0] + dx / 2.0 + TRANSPORT_CLEARANCE,
                )
            )
            ys.update(
                (
                    packed.minimum[1] - dy / 2.0 - TRANSPORT_CLEARANCE,
                    packed.maximum[1] + dy / 2.0 + TRANSPORT_CLEARANCE,
                )
            )

        accepted = 0
        seen = set()
        intervals = {}

        def interval_at(x, y):
            key = (float(x), float(y))
            if key not in intervals:
                intervals[key] = container_z_interval(
                    x,
                    y,
                    dims,
                    container,
                )
            return intervals[key]

        if attempt_kind in {"both", "settled"}:
            for z in sorted(zs):
                for y in sorted(ys, reverse=True):
                    for x in sorted(xs, key=abs):
                        if (
                            deadline is not None
                            and time.perf_counter() >= deadline
                        ):
                            return
                        position = (float(x), float(y), float(z))
                        key = tuple(round(value, 4) for value in position)
                        if key in seen:
                            continue
                        seen.add(key)
                        interval = interval_at(x, y)
                        if (
                            interval is None
                            or float(z) < interval[0] - EPS
                            or float(z) > interval[1] + EPS
                        ):
                            _record_envelope_prune(
                                diagnostics,
                                item_idx,
                            )
                            yield None
                            continue
                        candidate = AABB(position, dims, "candidate")
                        reason = Geometry.rejection_reason(
                            candidate,
                            container,
                        )
                        _record_candidate_diagnostic(
                            diagnostics,
                            item_idx,
                            reason,
                        )
                        if reason is None:
                            accepted += 1
                            yield candidate
                            if accepted >= limit:
                                return
                        else:
                            yield None
        if accepted and attempt_kind == "both":
            return

        if attempt_kind in {"both", "release"}:
            for y in sorted(ys, reverse=True):
                for x in sorted(xs, key=abs):
                    if (
                        deadline is not None
                        and time.perf_counter() >= deadline
                    ):
                        return
                    interval = interval_at(x, y)
                    if interval is None:
                        _record_envelope_prune(
                            diagnostics,
                            item_idx,
                            kind="release",
                        )
                        yield None
                        continue
                    rest_height = release_rest_height(
                        x,
                        y,
                        dims,
                        container,
                    )
                    z = max(
                        interval[0] + RELEASE_BOUNDARY_MARGIN,
                        rest_height + dz / 2.0 + RELEASE_TARGET_LIFT,
                    )
                    if z > interval[1] + EPS:
                        _record_envelope_prune(
                            diagnostics,
                            item_idx,
                            kind="release",
                        )
                        yield None
                        continue
                    position = (float(x), float(y), float(z))
                    key = tuple(round(value, 4) for value in position)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidate = AABB(
                        position,
                        dims,
                        "release_candidate",
                    )
                    reason = Geometry.release_rejection_reason(
                        candidate,
                        container,
                    )
                    _record_candidate_diagnostic(
                        diagnostics,
                        item_idx,
                        reason,
                        kind="release",
                    )
                    if reason is None:
                        accepted += 1
                        yield candidate
                        if accepted >= limit:
                            return
                    else:
                        yield None

    @staticmethod
    def iter_support_plane_attempts(
        observation,
        item,
        container_idx,
        orientation,
        limit=400,
        deadline=None,
        diagnostics=None,
        item_idx=None,
        attempt_kind="both",
    ):
        if attempt_kind not in {"both", "settled", "release"}:
            raise ValueError(
                "attempt_kind must be 'both', 'settled', or 'release'"
            )
        if attempt_kind == "release":
            yield from CandidateGenerator.iter_cartesian_attempts(
                observation,
                item,
                container_idx,
                orientation,
                limit=limit,
                deadline=deadline,
                diagnostics=diagnostics,
                item_idx=item_idx,
                attempt_kind="release",
            )
            return

        container = observation["container_list"][container_idx]
        if item_idx is None:
            item_idx = item.get("index", -1)
        dims = get_rotated_dimensions(
            item["length"], item["width"], item["height"], orientation
        )
        x_low, x_high, y_low, y_high = rectangular_container_anchor_bounds(
            dims, container
        )
        if x_low > x_high + EPS or y_low > y_high + EPS:
            _record_envelope_prune(diagnostics, item_idx)
            yield None
            return

        surfaces = support_surfaces(container)
        components = order_support_plane_components(
            support_plane_components(surfaces)
        )
        position_groups = [
            (
                component,
                support_plane_anchor_positions(component, dims, container),
            )
            for component in components
        ]
        if diagnostics is not None:
            connected_keys = {
                tuple(round(value, 6) for value in position)
                for _component, positions in position_groups
                for position in positions
            }
            separate_components = [
                SupportPlaneComponent((surface,)) for surface in surfaces
            ]
            diagnostics.setdefault("support_plane_searches", []).append(
                {
                    "item_index": int(item_idx),
                    "container_index": int(container_idx),
                    "orientation": int(orientation),
                    "adjacency_threshold": float(
                        SUPPORT_PLANE_ADJACENCY
                    ),
                    "surface_count": len(surfaces),
                    "component_count": len(components),
                    "connected_anchor_count": len(connected_keys),
                    "unconnected_anchor_count": (
                        support_plane_anchor_count(
                            separate_components,
                            dims,
                            container,
                        )
                    ),
                    "round_attempts": max(
                        1, SUPPORT_PLANE_ROUND_ATTEMPTS
                    ),
                    "component_order": [
                        {
                            "contains_floor": component.contains_floor,
                            "area": float(component.area),
                            "depth": float(component.maximum_xy[1]),
                            "top": float(component.top),
                            "surface_count": len(component.surfaces),
                        }
                        for component in components
                    ],
                }
            )

        states = [
            {
                "iterator": iter(positions),
            }
            for _component, positions in position_groups
            if positions
        ]
        accepted = 0
        seen = set()
        attempts_per_plane = max(1, SUPPORT_PLANE_ROUND_ATTEMPTS)
        while states:
            next_states = []
            for state in states:
                exhausted = False
                for _ in range(attempts_per_plane):
                    if (
                        deadline is not None
                        and time.perf_counter() >= deadline
                    ):
                        return
                    try:
                        position = next(state["iterator"])
                    except StopIteration:
                        exhausted = True
                        break
                    key = tuple(round(value, 4) for value in position)
                    if key in seen:
                        continue
                    seen.add(key)
                    interval = container_z_interval(
                        position[0],
                        position[1],
                        dims,
                        container,
                    )
                    if (
                        interval is None
                        or position[2] < interval[0] - EPS
                        or position[2] > interval[1] + EPS
                    ):
                        _record_envelope_prune(
                            diagnostics,
                            item_idx,
                        )
                        yield None
                        continue
                    candidate = AABB(position, dims, "candidate")
                    reason = Geometry.rejection_reason(
                        candidate,
                        container,
                    )
                    _record_candidate_diagnostic(
                        diagnostics,
                        item_idx,
                        reason,
                    )
                    if reason is None:
                        accepted += 1
                        yield candidate
                        if accepted >= limit:
                            return
                    else:
                        yield None
                if not exhausted:
                    next_states.append(state)
            states = next_states

        if accepted or attempt_kind == "settled":
            return
        yield from CandidateGenerator.iter_cartesian_attempts(
            observation,
            item,
            container_idx,
            orientation,
            limit=limit,
            deadline=deadline,
            diagnostics=diagnostics,
            item_idx=item_idx,
            attempt_kind="release",
        )

    @staticmethod
    def iter_attempts(
        observation,
        item,
        container_idx,
        orientation,
        limit=400,
        deadline=None,
        diagnostics=None,
        item_idx=None,
        attempt_kind="both",
        generator_mode=None,
    ):
        mode = (
            ANCHOR_GENERATOR_MODE
            if generator_mode is None
            else str(generator_mode).strip().lower()
        )
        if mode not in ANCHOR_GENERATOR_MODES:
            available = ", ".join(sorted(ANCHOR_GENERATOR_MODES))
            raise ValueError(
                f"unknown anchor generator mode '{mode}'; "
                f"available: {available}"
            )
        iterator = (
            CandidateGenerator.iter_cartesian_attempts
            if mode == "cartesian"
            else CandidateGenerator.iter_support_plane_attempts
        )
        yield from iterator(
            observation,
            item,
            container_idx,
            orientation,
            limit=limit,
            deadline=deadline,
            diagnostics=diagnostics,
            item_idx=item_idx,
            attempt_kind=attempt_kind,
        )

    @staticmethod
    def generate(
        observation,
        item,
        container_idx,
        orientation,
        limit=400,
        deadline=None,
        diagnostics=None,
        item_idx=None,
        generator_mode=None,
    ):
        """Compatibility wrapper returning only accepted candidates."""
        return [
            candidate
            for candidate in CandidateGenerator.iter_attempts(
                observation,
                item,
                container_idx,
                orientation,
                limit=limit,
                deadline=deadline,
                diagnostics=diagnostics,
                item_idx=item_idx,
                generator_mode=generator_mode,
            )
            if candidate is not None
        ]


class Ranker:
    @staticmethod
    def score(candidate, item, container, has_priority_container):
        support = Geometry.support_ratio(candidate, container)
        volume = math.prod(candidate.size)
        mass = float(item.get("mass", 1.0))
        x, y, z = candidate.center
        is_priority_item = bool(item.get("is_prioritized", False))
        is_priority_container = bool(container.get("is_prioritized", False))
        if is_priority_item:
            depth_score = -0.55 * y
        else:
            depth_score = 0.35 * y

        routing_score = 0.0
        if has_priority_container:
            if is_priority_item and is_priority_container:
                routing_score = 8.0
            elif not is_priority_item and is_priority_container:
                routing_score = -2.5

        return (
            12.0 * volume
            + 2.0 * support
            + depth_score
            - 0.12 * abs(x)
            - 0.18 * z * mass
            + routing_score
        )


def eligible_container_indices(item, containers):
    indices = list(range(len(containers)))
    if not bool(item.get("is_prioritized", False)):
        return indices
    priority_indices = [
        index
        for index, container in enumerate(containers)
        if bool(container.get("is_prioritized", False))
    ]
    return priority_indices or indices


def online_item_order(pool_list):
    def key(index_and_item):
        index, item = index_and_item
        volume = (
            float(item["length"])
            * float(item["width"])
            * float(item["height"])
        )
        if bool(item.get("is_prioritized", False)):
            group = 2
        elif bool(item.get("is_soft", False)):
            group = 1
        else:
            group = 0
        return (
            group,
            -float(item.get("mass", 1.0)),
            -volume,
            index,
        )

    return sorted(enumerate(pool_list), key=key)


def item_group(item):
    if bool(item.get("is_prioritized", False)):
        return 2
    if bool(item.get("is_soft", False)):
        return 1
    return 0


def constructive_order(item_list):
    if not item_list:
        return []

    volumes = [
        float(item["length"])
        * float(item["width"])
        * float(item["height"])
        for item in item_list
    ]
    base_areas = [
        max(
            float(item["length"]) * float(item["width"]),
            float(item["length"]) * float(item["height"]),
            float(item["width"]) * float(item["height"]),
        )
        for item in item_list
    ]
    masses = [float(item.get("mass", 1.0)) for item in item_list]
    volume_scale = max(max(volumes), EPS)
    area_scale = max(max(base_areas), EPS)
    mass_scale = max(max(masses), EPS)

    scored = []
    for stable_position, item in enumerate(item_list):
        length = float(item["length"])
        width = float(item["width"])
        height = float(item["height"])
        volume = length * width * height
        base_area = max(length * width, length * height, width * height)
        mass = float(item.get("mass", 1.0))
        cutout_filler = (
            min(length, width, height) <= 0.30
            and sorted((length, width, height))[1] <= 0.44
            and mass <= 10.0
        )
        composite = (
            0.45 * volume / volume_scale
            + 0.30 * base_area / area_scale
            + 0.25 * mass / mass_scale
            - (0.05 if cutout_filler else 0.0)
        )
        scored.append(
            (
                item_group(item),
                -composite,
                -mass,
                -volume,
                stable_position,
                item,
            )
        )
    scored.sort(key=lambda row: row[:-1])
    return [row[-1] for row in scored]


def estimated_remaining_container_volume(container):
    remaining = effective_container_volume(container)
    for packed in container.get("packed_items", []):
        try:
            remaining -= math.prod(packed_dimensions(packed))
        except (KeyError, TypeError, ValueError):
            continue
    return max(0.0, float(remaining))


def prioritized_search_units(observation, indexed_items):
    """
    Build a deterministic item -> stable-pose -> roomy-container order.

    ``indexed_items`` already carries the strategy order (hard normal,
    soft, then priority for the online policy).  Within an item, poses with
    a larger base are visited first, followed by eligible containers with
    more estimated remaining volume.
    """
    containers = observation.get("container_list", [])
    units = []
    for item_rank, (item_idx, item) in enumerate(indexed_items):
        orientations = sorted(
            unique_orientations(item),
            key=lambda orientation: (
                -math.prod(
                    get_rotated_dimensions(
                        item["length"],
                        item["width"],
                        item["height"],
                        orientation,
                    )[:2]
                ),
                orientation,
            ),
        )
        container_indices = sorted(
            eligible_container_indices(item, containers),
            key=lambda container_idx: (
                -estimated_remaining_container_volume(
                    containers[container_idx]
                ),
                container_idx,
            ),
        )
        for pose_rank, orientation in enumerate(orientations):
            for container_rank, container_idx in enumerate(container_indices):
                for kind_rank, attempt_kind in enumerate(
                    ("settled", "release")
                ):
                    units.append(
                        (
                            item_rank,
                            pose_rank,
                            container_rank,
                            kind_rank,
                            int(item_idx),
                            item,
                            int(container_idx),
                            int(orientation),
                            attempt_kind,
                        )
                    )
    units.sort(key=lambda unit: unit[:4])
    return units


def candidate_audit_record(
    item_idx,
    item,
    container_idx,
    orientation,
    candidate,
    container,
    elapsed_seconds=None,
):
    action_center = simulator_action_center(candidate, container)
    record = {
        "pool_index": int(item_idx),
        "item_index": int(item.get("index", item_idx)),
        "container_index": int(container_idx),
        "orientation": int(orientation),
        "kind": candidate.name or "candidate",
        "center": [float(value) for value in candidate.center],
        "size": [float(value) for value in candidate.size],
        "action_center": [float(value) for value in action_center],
    }
    if elapsed_seconds is not None:
        record["elapsed_seconds"] = float(elapsed_seconds)
    return record


def iter_prioritized_candidates(
    observation,
    indexed_items,
    deadline=None,
    diagnostics=None,
):
    """
    Time-sliced candidate stream.

    Every prioritized (item, pose, container) unit receives a shallow first
    pass before any unit is deeply expanded.  Subsequent rounds continue in
    the same priority order, so the caller can retain and improve a safe
    incumbent without starving later items or poses.
    """
    units = prioritized_search_units(observation, indexed_items)
    search_started = time.perf_counter()
    audit = None
    if diagnostics is not None and CANDIDATE_AUDIT_ENABLED:
        searches = diagnostics.setdefault("candidate_audit", [])
        audit = {
            "search_index": len(searches),
            "accepted_settled": [],
        }
        searches.append(audit)
    states = [
        {
            "unit": unit,
            "iterator": None,
        }
        for unit in units
    ]
    search_stats = None
    if diagnostics is not None:
        search_stats = diagnostics.setdefault(
            "search",
            {
                "units_total": len(units),
                "units_started": 0,
                "units_completed": 0,
                "rounds_started": 0,
                "deadline_reached": False,
                "incumbent_updates": 0,
            },
        )

    attempts_per_unit = max(1, ANCHOR_FIRST_PASS_ATTEMPTS)
    while states:
        if search_stats is not None:
            search_stats["rounds_started"] += 1
        next_states = []
        for state in states:
            if (
                deadline is not None
                and time.perf_counter() >= deadline
            ):
                if search_stats is not None:
                    search_stats["deadline_reached"] = True
                return

            (
                _item_rank,
                _pose_rank,
                _container_rank,
                _kind_rank,
                item_idx,
                item,
                container_idx,
                orientation,
                attempt_kind,
            ) = state["unit"]
            if state["iterator"] is None:
                state["iterator"] = CandidateGenerator.iter_attempts(
                    observation,
                    item,
                    container_idx,
                    orientation,
                    deadline=deadline,
                    diagnostics=diagnostics,
                    item_idx=item_idx,
                    attempt_kind=attempt_kind,
                )
                if search_stats is not None:
                    search_stats["units_started"] += 1

            exhausted = False
            for _ in range(attempts_per_unit):
                if (
                    deadline is not None
                    and time.perf_counter() >= deadline
                ):
                    if search_stats is not None:
                        search_stats["deadline_reached"] = True
                    return
                try:
                    candidate = next(state["iterator"])
                except StopIteration:
                    exhausted = True
                    if search_stats is not None:
                        search_stats["units_completed"] += 1
                    break
                if candidate is not None:
                    if (
                        audit is not None
                        and candidate.name != "release_candidate"
                    ):
                        audit["accepted_settled"].append(
                            candidate_audit_record(
                                item_idx,
                                item,
                                container_idx,
                                orientation,
                                candidate,
                                observation["container_list"][
                                    container_idx
                                ],
                                elapsed_seconds=(
                                    time.perf_counter() - search_started
                                ),
                            )
                        )
                    yield (
                        item_idx,
                        item,
                        container_idx,
                        orientation,
                        candidate,
                    )
            if not exhausted:
                next_states.append(state)
        states = next_states
        attempts_per_unit = max(1, ANCHOR_DEEP_PASS_ATTEMPTS)


class PlacementCore:
    """Single source of truth used by online policy and offline dry-runs."""

    @staticmethod
    def choose(
        observation,
        indexed_items,
        deadline=None,
        diagnostics=None,
    ):
        containers = observation.get("container_list", [])
        if not containers:
            return None

        has_priority_container = any(
            bool(container.get("is_prioritized", False))
            for container in containers
        )
        best_settled = None
        best_settled_score = -float("inf")
        best_release = None
        best_release_score = -float("inf")

        for (
            item_idx,
            item,
            container_idx,
            orientation,
            candidate,
        ) in iter_prioritized_candidates(
            observation,
            indexed_items,
            deadline=deadline,
            diagnostics=diagnostics,
        ):
            container = containers[container_idx]
            score = Ranker.score(
                candidate,
                item,
                container,
                has_priority_container,
            )
            decision = PlacementDecision(
                action={
                    "item_idx": int(item_idx),
                    "container_idx": int(container_idx),
                    "place_pos": np.asarray(
                        simulator_action_center(
                            candidate, container
                        ),
                        dtype=np.float32,
                    ),
                    "orientation": int(orientation),
                },
                candidate=candidate,
                score=float(score),
            )
            updated = False
            if candidate.name == "release_candidate":
                if score > best_release_score:
                    best_release_score = score
                    best_release = decision
                    updated = True
            elif score > best_settled_score:
                best_settled_score = score
                best_settled = decision
                updated = True
            if updated and diagnostics is not None:
                diagnostics["search"]["incumbent_updates"] += 1
        return best_settled or best_release

    @staticmethod
    def top_candidates(
        observation,
        indexed_items,
        k,
        deadline=None,
        diagnostics=None,
    ):
        """
        Same search as choose(), but keeps the best k decisions (a bounded
        min-heap) instead of only the single best. Used by the closed-loop
        lookahead in Agent.policy() to consider more than one immediate
        action before committing.
        """
        containers = observation.get("container_list", [])
        if not containers or k <= 0:
            return []

        has_priority_container = any(
            bool(container.get("is_prioritized", False))
            for container in containers
        )
        settled_heap = []
        release_heap = []
        counter = 0

        for (
            item_idx,
            item,
            container_idx,
            orientation,
            candidate,
        ) in iter_prioritized_candidates(
            observation,
            indexed_items,
            deadline=deadline,
            diagnostics=diagnostics,
        ):
            container = containers[container_idx]
            score = Ranker.score(
                candidate,
                item,
                container,
                has_priority_container,
            )
            decision = PlacementDecision(
                action={
                    "item_idx": int(item_idx),
                    "container_idx": int(container_idx),
                    "place_pos": np.asarray(
                        simulator_action_center(
                            candidate, container
                        ),
                        dtype=np.float32,
                    ),
                    "orientation": int(orientation),
                },
                candidate=candidate,
                score=float(score),
            )
            counter += 1
            entry = (score, counter, decision)
            heap = (
                release_heap
                if candidate.name == "release_candidate"
                else settled_heap
            )
            updated = False
            if len(heap) < k:
                heapq.heappush(heap, entry)
                updated = True
            elif score > heap[0][0]:
                heapq.heapreplace(heap, entry)
                updated = True
            if updated and diagnostics is not None:
                diagnostics["search"]["incumbent_updates"] += 1
        return [
            decision
            for _, _, decision in sorted(
                settled_heap or release_heap,
                key=lambda entry: entry[0],
                reverse=True,
            )
        ]


def normalized_lookahead_mode(mode):
    normalized = str(mode).strip().lower()
    if normalized not in LOOKAHEAD_SELECTION_MODES:
        available = ", ".join(sorted(LOOKAHEAD_SELECTION_MODES))
        raise ValueError(
            f"unknown lookahead selection mode '{mode}'; available: {available}"
        )
    return normalized


def lookahead_rank_key(
    evaluation,
    mode=LOOKAHEAD_SELECTION_MODE,
    discount=LOOKAHEAD_DISCOUNT,
):
    mode = normalized_lookahead_mode(mode)
    immediate_score = float(evaluation.decision.score)
    best_next_score = float(evaluation.best_next_score)
    has_feasible_next = (
        evaluation.total_next_items == 0
        or evaluation.feasible_next_items > 0
    )

    if mode == "weighted":
        return (immediate_score + float(discount) * best_next_score,)
    if mode == "depth2":
        return (
            int(has_feasible_next),
            best_next_score,
            immediate_score,
        )
    return (
        int(evaluation.feasible_next_items),
        best_next_score,
        immediate_score,
    )


def evaluate_visible_pool_feasibility(
    observation,
    indexed_items,
    deadline=None,
):
    feasible_items = 0
    best_score = -float("inf")
    evaluated_items = 0
    for indexed_item in indexed_items:
        if deadline is not None and time.perf_counter() >= deadline:
            return None
        next_decision = PlacementCore.choose(
            observation,
            [indexed_item],
            deadline=deadline,
        )
        evaluated_items += 1
        if next_decision is None:
            continue
        feasible_items += 1
        best_score = max(best_score, float(next_decision.score))

    if feasible_items == 0:
        best_score = 0.0
    return VisiblePoolFeasibility(
        feasible_items=feasible_items,
        evaluated_items=evaluated_items,
        best_score=best_score,
    )


def effective_container_volume(container):
    if container.get("volume") is not None:
        return max(EPS, float(container["volume"]))

    length = float(container["length"])
    width = float(container["width"])
    height = float(container["height"])
    thickness = float(container["thickness"])
    buffer = float(container.get("buffer", 0.0))
    cut_x = float(container.get("cut_x", 0.0))
    cut_y = float(container.get("cut_y", 0.0))
    inner_length = length - 2.0 * thickness
    inner_width = width - 2.0 * thickness
    inner_height = height - thickness - buffer
    base_volume = inner_length * inner_width * inner_height
    cut_volume = (
        0.5
        * max(0.0, cut_x - thickness)
        * max(0.0, cut_y - thickness)
        * inner_width
    )
    small_shelf_volume = cut_x * thickness * inner_width
    shelf_volume = 0.0
    if container_requires_shelf(container):
        shelf_width = width / 2.0 - 2.0 * thickness
        shelf_volume = inner_length * thickness * max(0.0, shelf_width)
    return max(
        EPS,
        base_volume - cut_volume - small_shelf_volume - shelf_volume,
    )


def apply_placement_decision(item, decision, containers):
    action = decision.action
    container_idx = int(action["container_idx"])
    container = containers[container_idx]
    predicted_settled = settled_proxy_candidate(
        decision.candidate,
        container,
    )
    metrics = Geometry.support_metrics(predicted_settled, container, item)

    packed = copy.deepcopy(item)
    packed["pos"] = local_to_world(
        predicted_settled.center, container
    ).tolist()
    packed["orientation"] = int(action["orientation"])
    packed["belongs_to"] = container_idx
    container.setdefault("packed_items", []).append(packed)

    return PlacementTrace(
        item_index=int(item["index"]),
        container_idx=container_idx,
        orientation=int(action["orientation"]),
        candidate=predicted_settled,
        support=metrics,
        mass=max(EPS, float(item.get("mass", 1.0))),
    )


def replay_placement_trace(ordered_items, container_templates, deadline=None):
    containers = [
        normalize_container(container) for container in container_templates
    ]
    trace = []
    for item in ordered_items:
        if deadline is not None and time.perf_counter() >= deadline:
            break
        observation = {
            "pool_list": [item],
            "container_list": containers,
        }
        decision = PlacementCore.choose(
            observation,
            [(0, item)],
            deadline=deadline,
        )
        if decision is None:
            break
        trace.append(apply_placement_decision(item, decision, containers))
    return trace


def _pair_template_from_records(first, second, first_item, second_item):
    """
    Shared math for turning two adjacent PlacementTrace records (in the
    order they were actually executed) into a BlockTemplate. Used both for
    the trace's natural order and for a DPOR-generated alternate order.
    """
    boxes = (first.candidate, second.candidate)
    minimum = np.minimum(boxes[0].minimum, boxes[1].minimum)
    maximum = np.maximum(boxes[0].maximum, boxes[1].maximum)
    dimensions = tuple(float(value) for value in maximum - minimum)
    envelope_volume = max(EPS, math.prod(dimensions))
    item_volume = sum(
        float(item["length"])
        * float(item["width"])
        * float(item["height"])
        for item in (first_item, second_item)
    )
    total_mass = first.mass + second.mass
    center_of_mass = (
        first.mass * np.asarray(first.candidate.center, dtype=np.float64)
        + second.mass
        * np.asarray(second.candidate.center, dtype=np.float64)
    ) / max(EPS, total_mass)

    relative_placements = tuple(
        (
            record.item_index,
            record.container_idx,
            tuple(
                float(value)
                for value in (
                    np.asarray(record.candidate.center)
                    - minimum
                )
            ),
            record.orientation,
        )
        for record in (first, second)
    )
    top_profile = tuple(
        (
            float(box.minimum[0] - minimum[0]),
            float(box.maximum[0] - minimum[0]),
            float(box.minimum[1] - minimum[1]),
            float(box.maximum[1] - minimum[1]),
            float(box.top - minimum[2]),
        )
        for box in boxes
    )
    signature = BlockSignature(
        fill_ratio=min(1.0, item_volume / envelope_volume),
        top_profile=top_profile,
        min_support_ratio=min(
            first.support.ratio, second.support.ratio
        ),
        total_mass=total_mass,
        center_of_mass=tuple(
            float(value) for value in center_of_mass - minimum
        ),
    )
    return BlockTemplate(
        item_indices=(first.item_index, second.item_index),
        internal_order=(first.item_index, second.item_index),
        relative_placements=relative_placements,
        dimensions=dimensions,
        signature=signature,
    )


def records_are_support_independent(first, second):
    """
    Sufficient (not necessary) DPOR condition: neither placed box rests on
    top of the other. If that holds, neither placement used the other as a
    support surface, so swapping which one was placed first cannot remove a
    support relationship either order depends on -- the two actions
    commute in the sense of dynamic partial-order reduction (Flanagan &
    Godefroid). When it does NOT hold (one is stacked on the other), the
    original execution order is kept as the only candidate, since trying
    the reverse would place the top item into empty space with no support.
    """
    first_box = first.candidate
    second_box = second.candidate
    second_rests_on_first = (
        abs(float(second_box.minimum[2]) - first_box.top) <= CONTACT_TOLERANCE
    )
    first_rests_on_second = (
        abs(float(first_box.minimum[2]) - second_box.top) <= CONTACT_TOLERANCE
    )
    return not second_rests_on_first and not first_rests_on_second


def containers_after_prefix(container_templates, trace_prefix, items_by_index):
    """
    Cheaply reconstruct container state after replaying a known prefix of a
    trace, without re-running PlacementCore (positions are already known).
    """
    containers = [
        normalize_container(container) for container in container_templates
    ]
    for record in trace_prefix:
        item = items_by_index.get(record.item_index)
        if item is None:
            continue
        container = containers[record.container_idx]
        packed = copy.deepcopy(item)
        packed["pos"] = local_to_world(
            record.candidate.center, container
        ).tolist()
        packed["orientation"] = int(record.orientation)
        packed["belongs_to"] = record.container_idx
        container.setdefault("packed_items", []).append(packed)
    return containers


def alternate_order_records(
    items_by_index,
    container_templates,
    trace,
    index,
    deadline=None,
):
    """
    DPOR pricing step: actually replay the reverse order (second_item then
    first_item) from the true pre-pair state, using the same PlacementCore
    used everywhere else, instead of guessing at swapped coordinates. Returns
    None if either placement is infeasible in the reversed order.
    """
    first = trace[index]
    second = trace[index + 1]
    first_item = items_by_index.get(first.item_index)
    second_item = items_by_index.get(second.item_index)
    if first_item is None or second_item is None:
        return None

    containers = containers_after_prefix(
        container_templates, trace[:index], items_by_index
    )

    observation_1 = {"pool_list": [second_item], "container_list": containers}
    decision_1 = PlacementCore.choose(
        observation_1, [(0, second_item)], deadline=deadline
    )
    if decision_1 is None:
        return None
    record_1 = apply_placement_decision(second_item, decision_1, containers)

    observation_2 = {"pool_list": [first_item], "container_list": containers}
    decision_2 = PlacementCore.choose(
        observation_2, [(0, first_item)], deadline=deadline
    )
    if decision_2 is None:
        return None
    record_2 = apply_placement_decision(first_item, decision_2, containers)

    return record_1, record_2


def block_templates_from_trace(
    ordered_items,
    trace,
    container_templates=None,
    max_templates=8,
    deadline=None,
):
    items_by_index = {
        int(item["index"]): item for item in ordered_items
    }
    templates = []
    dpor_attempts = 0
    for index, (first, second) in enumerate(zip(trace, trace[1:])):
        if first.container_idx != second.container_idx:
            continue
        first_item = items_by_index.get(first.item_index)
        second_item = items_by_index.get(second.item_index)
        if first_item is None or second_item is None:
            continue
        if item_group(first_item) != item_group(second_item):
            continue

        templates.append(
            _pair_template_from_records(first, second, first_item, second_item)
        )

        # DPOR: only pay for an alternate-order dry run when the pair is
        # provably order-independent, and only while there is search budget
        # and an attempt allowance left. Dependent pairs (one physically
        # supports the other) keep the single witnessed order, matching the
        # theory's "static sufficient condition, else keep fixed order".
        if (
            container_templates is not None
            and dpor_attempts < DPOR_MAX_ALTERNATE_ATTEMPTS
            and (deadline is None or time.perf_counter() < deadline)
            and records_are_support_independent(first, second)
        ):
            dpor_attempts += 1
            alternate = alternate_order_records(
                items_by_index,
                container_templates,
                trace,
                index,
                deadline=deadline,
            )
            if alternate is not None:
                alt_first, alt_second = alternate
                templates.append(
                    _pair_template_from_records(
                        alt_first, alt_second, second_item, first_item
                    )
                )

    templates.sort(
        key=lambda template: (
            template.signature.min_support_ratio,
            template.signature.fill_ratio,
            -template.dimensions[2],
            tuple(-index for index in template.item_indices),
        ),
        reverse=True,
    )
    return templates[:max(0, int(max_templates))]


def generate_pair_block_templates(
    ordered_items,
    container_templates,
    max_templates=8,
    deadline=None,
):
    trace = replay_placement_trace(
        ordered_items,
        container_templates,
        deadline=deadline,
    )
    return block_templates_from_trace(
        ordered_items,
        trace,
        container_templates=container_templates,
        max_templates=max_templates,
        deadline=deadline,
    )


def apply_block_template_neighbor(items, template, target_position):
    positions = {
        int(item["index"]): position
        for position, item in enumerate(items)
    }
    if any(index not in positions for index in template.internal_order):
        return list(items)

    target_position = max(0, min(int(target_position), len(items)))
    selected = set(template.item_indices)
    removed_before_target = sum(
        1
        for index in selected
        if positions.get(index, len(items)) < target_position
    )
    insertion = max(
        0,
        min(
            target_position - removed_before_target,
            len(items) - len(selected),
        ),
    )
    remaining = [
        item for item in items if int(item["index"]) not in selected
    ]
    by_index = {int(item["index"]): item for item in items}
    block_items = [
        by_index[index] for index in template.internal_order
    ]
    return remaining[:insertion] + block_items + remaining[insertion:]


class DryRunEvaluator:
    """Evaluate an offline order by replaying the online placement core."""

    def __init__(self, container_templates):
        self.container_templates = [
            normalize_container(container) for container in container_templates
        ]
        self._cache = {}
        self.cache_hits = 0
        self.evaluations = 0
        self.last_trace = []

    def evaluate(self, ordered_items, deadline=None):
        key = tuple(int(item["index"]) for item in ordered_items)
        cached = self._cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            self.last_trace = []
            return cached

        started = time.perf_counter()
        containers = copy.deepcopy(self.container_templates)
        total_capacity = sum(
            effective_container_volume(container) for container in containers
        )
        placed_volume = 0.0
        weighted_z = 0.0
        weighted_normalized_z = 0.0
        total_mass = 0.0
        support_ratios = []
        support_margins = []
        support_counts = []
        mass_support_ratios = []
        failed_index = None
        timed_out = False
        trace = []

        for item in ordered_items:
            if deadline is not None and time.perf_counter() >= deadline:
                failed_index = int(item["index"])
                timed_out = True
                break

            observation = {
                "pool_list": [item],
                "container_list": containers,
            }
            decision = PlacementCore.choose(
                observation,
                [(0, item)],
                deadline=deadline,
            )
            if decision is None:
                failed_index = int(item["index"])
                timed_out = (
                    deadline is not None
                    and time.perf_counter() >= deadline
                )
                break

            record = apply_placement_decision(
                item, decision, containers
            )
            trace.append(record)
            container = containers[record.container_idx]
            support_ratios.append(record.support.ratio)
            support_margins.append(record.support.center_margin)
            support_counts.append(float(record.support.contact_count))
            mass_support_ratios.append(
                record.support.mass_support_ratio
            )

            item_volume = (
                float(item["length"])
                * float(item["width"])
                * float(item["height"])
            )
            mass = record.mass
            z = float(record.candidate.center[2])
            height = max(EPS, float(container["height"]))
            placed_volume += item_volume
            weighted_z += mass * z
            weighted_normalized_z += mass * (z / height)
            total_mass += mass

        placed_count = len(support_ratios)
        mean_support = (
            float(np.mean(support_ratios)) if support_ratios else 0.0
        )
        min_support = min(support_ratios) if support_ratios else 0.0
        min_margin = min(support_margins) if support_margins else -1.0
        mean_margin = (
            float(np.mean(support_margins)) if support_margins else -1.0
        )
        mean_count = (
            float(np.mean(support_counts)) if support_counts else 0.0
        )
        mean_mass_support = (
            float(np.mean(mass_support_ratios))
            if mass_support_ratios
            else 0.0
        )
        stability = (
            0.45 * mean_support
            + 0.20 * min_support
            + 0.20 * ((mean_margin + 1.0) / 2.0)
            + 0.10 * mean_mass_support
            + 0.05 * min(1.0, mean_count / 2.0)
        )
        result = DryRunResult(
            placed_count=placed_count,
            failed_index=failed_index,
            placed_volume=placed_volume,
            fill_ratio=min(1.0, placed_volume / total_capacity),
            stability_proxy=max(0.0, min(1.0, stability)),
            center_of_mass_z=(
                weighted_z / total_mass if total_mass > EPS else 0.0
            ),
            normalized_center_of_mass_z=(
                weighted_normalized_z / total_mass
                if total_mass > EPS
                else 0.0
            ),
            mean_support_ratio=mean_support,
            min_support_ratio=min_support,
            min_support_margin=min_margin,
            mean_support_count=mean_count,
            runtime_seconds=time.perf_counter() - started,
        )
        self.evaluations += 1
        self.last_trace = trace
        if not timed_out:
            self._cache[key] = result
        return result


class Agent:
    def __init__(self, module_path: str):
        self.module_path = module_path
        self._container_templates = []
        self._offline_search_budget_seconds = OFFLINE_SEARCH_BUDGET_SECONDS
        self._offline_max_evaluations = OFFLINE_MAX_EVALUATIONS
        self.last_offline_result = None
        self.last_offline_evaluations = 0
        self.last_offline_cache_hits = 0
        self.last_pair_macro_candidates = 0
        self.last_pair_macro_adoptions = 0
        self.last_lookahead_evaluation = None
        self.last_top_candidate_count = 0
        self.last_candidate_diagnostics = {}
        self._policy_step = 0
        self._optimize_enabled = False
        self._lookahead_k = 0
        self._policy_trace_path = os.environ.get("NEDO_POLICY_TRACE_PATH")

    def _append_policy_trace(self, payload):
        if not self._policy_trace_path:
            return
        trace_dir = os.path.dirname(self._policy_trace_path)
        if trace_dir:
            os.makedirs(trace_dir, exist_ok=True)
        with open(self._policy_trace_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def get_init_states(self, init_states: dict):
        containers = init_states.get("container_list", [])
        self._container_templates = [
            normalize_container(container) for container in containers
        ]
        self._policy_step = 0
        self._optimize_enabled = bool(init_states.get("optimize", False))
        self._lookahead_k = int(init_states.get("lookahead_k", 0))
        self._append_policy_trace(
            {
                "event": "init",
                "optimize": self._optimize_enabled,
                "lookahead_k": self._lookahead_k,
            }
        )
        return True

    def optimize(self, item_list: list):
        initial = constructive_order(item_list)
        initial_indices = [int(item["index"]) for item in initial]
        if len(initial) < 2 or not self._container_templates:
            return initial_indices

        evaluator = DryRunEvaluator(self._container_templates)
        started = time.perf_counter()
        deadline = started + max(0.0, self._offline_search_budget_seconds)
        best_items = list(initial)
        best_result = evaluator.evaluate(best_items, deadline=deadline)
        self.last_offline_result = best_result
        pair_macros = block_templates_from_trace(
            initial,
            evaluator.last_trace,
            container_templates=self._container_templates,
            deadline=deadline,
        )
        self.last_pair_macro_candidates = len(pair_macros)
        self.last_pair_macro_adoptions = 0

        if self._offline_search_budget_seconds <= 0.0:
            self.last_offline_evaluations = evaluator.evaluations
            return initial_indices

        seed = OFFLINE_RANDOM_SEED
        for position, item in enumerate(initial):
            seed = (
                seed * 1000003
                + (position + 1) * int(item["index"] + 1)
            ) & 0xFFFFFFFF
        rng = random.Random(seed)
        current_items = list(best_items)
        moving_runtime = max(0.001, best_result.runtime_seconds)

        for iteration in range(max(0, self._offline_max_evaluations - 1)):
            remaining = deadline - time.perf_counter()
            if remaining <= max(0.01, 1.5 * moving_runtime):
                break

            group_positions = {}
            for position, item in enumerate(current_items):
                group_positions.setdefault(item_group(item), []).append(position)
            movable_groups = [
                group
                for group, positions in sorted(group_positions.items())
                if len(positions) >= 2
            ]
            if not movable_groups:
                break

            used_pair_macro = False
            if pair_macros and iteration % 3 == 0:
                template = pair_macros[
                    iteration % len(pair_macros)
                ]
                first_item = next(
                    (
                        item
                        for item in current_items
                        if int(item["index"])
                        == template.item_indices[0]
                    ),
                    None,
                )
                if first_item is not None:
                    group = item_group(first_item)
                    target_positions = list(
                        group_positions.get(group, [])
                    )
                    if target_positions:
                        target_positions.append(
                            target_positions[-1] + 1
                        )
                        target = rng.choice(target_positions)
                        neighbor = apply_block_template_neighbor(
                            current_items,
                            template,
                            target,
                        )
                        used_pair_macro = neighbor != current_items
                    else:
                        neighbor = list(current_items)
                else:
                    neighbor = list(current_items)
            else:
                neighbor = list(current_items)

            if not used_pair_macro:
                group = movable_groups[iteration % len(movable_groups)]
                positions = group_positions[group]
                first, second = rng.sample(positions, 2)
                neighbor = list(current_items)
                if iteration % 2 == 0:
                    neighbor[first], neighbor[second] = (
                        neighbor[second],
                        neighbor[first],
                    )
                else:
                    moved = neighbor.pop(first)
                    neighbor.insert(second, moved)

            result = evaluator.evaluate(neighbor, deadline=deadline)
            moving_runtime = (
                0.8 * moving_runtime
                + 0.2 * max(0.001, result.runtime_seconds)
            )
            if result.rank_key() > best_result.rank_key():
                best_result = result
                best_items = list(neighbor)
            current_items = list(neighbor)
            if used_pair_macro:
                self.last_pair_macro_adoptions += 1

        self.last_offline_result = best_result
        self.last_offline_evaluations = evaluator.evaluations
        self.last_offline_cache_hits = evaluator.cache_hits
        return [int(item["index"]) for item in best_items]

    def _closed_loop_choice(self, observation, pool_list, ordered_items, deadline):
        """
        Closed-loop 1-ply lookahead. Keep the top-K immediate candidates
        (not just the single best), hypothetically settle each one against
        a deep-copied container state using the exact same PlacementCore
        used for every other decision, then rank the resulting pool-aware
        evaluation with the configured selection mode.

        weighted preserves the original discounted sum. depth2 avoids mixing
        immediate and future scales by comparing next-step feasibility,
        best-next score, and immediate score lexicographically.
        pool_resilience first preserves the number of visible items that
        remain individually placeable.
        """
        if not ordered_items:
            self.last_lookahead_evaluation = None
            self.last_top_candidate_count = 0
            return None

        selection_mode = normalized_lookahead_mode(
            LOOKAHEAD_SELECTION_MODE
        )
        lookahead_deadline = deadline - LOOKAHEAD_TIME_RESERVE_SECONDS
        search_deadline = (
            lookahead_deadline
            if lookahead_deadline > time.perf_counter()
            else deadline
        )
        top = PlacementCore.top_candidates(
            observation,
            ordered_items,
            LOOKAHEAD_TOP_K,
            deadline=search_deadline,
            diagnostics=self.last_candidate_diagnostics,
        )
        self.last_top_candidate_count = len(top)
        if not top:
            self.last_lookahead_evaluation = None
            return None
        if (
            len(top) == 1
            or len(ordered_items) <= 1
            or time.perf_counter() >= lookahead_deadline
        ):
            self.last_lookahead_evaluation = LookaheadEvaluation(
                decision=top[0],
                feasible_next_items=0,
                total_next_items=0,
                best_next_score=0.0,
            )
            return top[0]

        inner_pool = ordered_items[:LOOKAHEAD_INNER_ITEMS]
        best_decision = top[0]
        best_key = None
        best_evaluation = None
        for decision in top:
            if time.perf_counter() >= deadline - 0.2:
                break
            item_idx = decision.action["item_idx"]
            placed_item = pool_list[item_idx]
            sim_containers = copy.deepcopy(
                observation.get("container_list", [])
            )
            apply_placement_decision(placed_item, decision, sim_containers)
            remaining = [
                (idx, item) for idx, item in inner_pool if idx != item_idx
            ]
            pool_feasibility = VisiblePoolFeasibility(
                feasible_items=0,
                evaluated_items=0,
                best_score=0.0,
            )
            if remaining:
                sim_observation = {
                    "pool_list": pool_list,
                    "container_list": sim_containers,
                }
                pool_feasibility = evaluate_visible_pool_feasibility(
                    sim_observation,
                    remaining,
                    deadline=deadline - 0.2,
                )
                if pool_feasibility is None:
                    break
            evaluation = LookaheadEvaluation(
                decision=decision,
                feasible_next_items=pool_feasibility.feasible_items,
                total_next_items=len(remaining),
                best_next_score=pool_feasibility.best_score,
            )
            rank_key = lookahead_rank_key(
                evaluation,
                mode=selection_mode,
            )
            if best_key is None or rank_key > best_key:
                best_key = rank_key
                best_decision = decision
                best_evaluation = evaluation
        if best_evaluation is None:
            best_evaluation = LookaheadEvaluation(
                decision=best_decision,
                feasible_next_items=0,
                total_next_items=0,
                best_next_score=0.0,
            )
        self.last_lookahead_evaluation = best_evaluation
        return best_decision

    def policy(self, observation: dict):
        deadline = time.perf_counter() + POLICY_BUDGET_SECONDS
        self.last_candidate_diagnostics = {}
        pool_list = observation.get("pool_list", [])
        containers = observation.get("container_list", [])
        ordered_items = online_item_order(pool_list)[
            :MAX_POOL_ITEMS_EVALUATED
        ]

        decision = self._closed_loop_choice(
            observation, pool_list, ordered_items, deadline
        )
        if decision is None:
            decision = PlacementCore.choose(
                observation,
                ordered_items,
                deadline=deadline,
                diagnostics=self.last_candidate_diagnostics,
            )
        if decision is not None:
            evaluation = self.last_lookahead_evaluation
            if evaluation is None or evaluation.decision is not decision:
                evaluation = LookaheadEvaluation(
                    decision=decision,
                    feasible_next_items=0,
                    total_next_items=0,
                    best_next_score=0.0,
                )
            selected_pool_index = int(decision.action["item_idx"])
            selected_item_index = None
            if 0 <= selected_pool_index < len(pool_list):
                selected_item_index = int(
                    pool_list[selected_pool_index]["index"]
                )
            feasible_ratio = (
                evaluation.feasible_next_items / evaluation.total_next_items
                if evaluation.total_next_items > 0
                else None
            )
            self._append_policy_trace(
                {
                    "event": "decision",
                    "step": self._policy_step,
                    "mode": LOOKAHEAD_SELECTION_MODE,
                    "optimize": self._optimize_enabled,
                    "lookahead_k": self._lookahead_k,
                    "pool_size": len(pool_list),
                    "selected_pool_index": selected_pool_index,
                    "selected_item_index": selected_item_index,
                    "top_candidate_count": self.last_top_candidate_count,
                    "immediate_score": float(decision.score),
                    "evaluated_remaining_items": (
                        evaluation.total_next_items
                    ),
                    "feasible_remaining_items": (
                        evaluation.feasible_next_items
                    ),
                    "feasible_remaining_ratio": feasible_ratio,
                    "best_next_score": float(
                        evaluation.best_next_score
                    ),
                    "action_source": "placement_core",
                    "candidate_kind": (
                        decision.candidate.name or "candidate"
                    ),
                    "candidate_diagnostics": self.last_candidate_diagnostics,
                }
            )
            self._policy_step += 1
            return decision.action

        fallback_container = 0
        if pool_list and containers:
            eligible = eligible_container_indices(pool_list[0], containers)
            if eligible:
                fallback_container = eligible[0]
        selected_item_index = (
            int(pool_list[0]["index"]) if pool_list else None
        )
        self._append_policy_trace(
            {
                "event": "decision",
                "step": self._policy_step,
                "mode": LOOKAHEAD_SELECTION_MODE,
                "optimize": self._optimize_enabled,
                "lookahead_k": self._lookahead_k,
                "pool_size": len(pool_list),
                "selected_pool_index": 0 if pool_list else None,
                "selected_item_index": selected_item_index,
                "top_candidate_count": self.last_top_candidate_count,
                "immediate_score": None,
                "evaluated_remaining_items": 0,
                "feasible_remaining_items": 0,
                "feasible_remaining_ratio": None,
                "best_next_score": 0.0,
                "action_source": "fixed_fallback",
                "candidate_kind": "fixed_fallback",
                "candidate_diagnostics": self.last_candidate_diagnostics,
            }
        )
        self._policy_step += 1
        return {
            "item_idx": 0,
            "container_idx": fallback_container,
            "place_pos": np.array([0.0, 0.0, 0.25], dtype=np.float32),
            "orientation": 0,
        }
