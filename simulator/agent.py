import copy
import heapq
import math
import os
import random
import time
from dataclasses import dataclass

import numpy as np

# Geometry contract
# -----------------
# - Actions use container-local coordinates.
# - Packed item positions and container planes use world coordinates.
# - The simulator only offsets containers on the world X axis.
# - Boundary clearance includes official, physics-settle, and float32 guards.
# - Transport clearance includes the official 15 mm plus a float32 guard.
# - Candidate poses represent final support contact.
# - The inclusion check applies to the transmitted action pose, so contact
#   poses on inclusion planes (the container floor) are lifted before the
#   inclusion test, exactly as the emitted action is.
# - Shelf actions are lifted 5.1 cm to avoid the validator's direct-rest path.
# - Floor actions are lifted 2 cm: enough to clear the official 5 mm
#   floor-plane inclusion margin plus guards, small enough to stay inside
#   the validator's 5 cm direct-rest window (no extra drop dynamics).
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
# The validator samples the transport path every 1 cm; the distance to any
# fixed box is 1-Lipschitz in the moving pose, so with our sample step s the
# continuous minimum is at least (SETTLED_ITEM_CLEARANCE - s/2). With
# s = 0.02 that lower bound is 16 mm > the official 15 mm margin.
TRANSPORT_SAMPLE_STEP = 0.02
SIMULATOR_DROP_HEIGHT = 0.08
SIMULATOR_START_MARGIN = 0.01
SIMULATOR_CEILING_MARGIN = 0.018
SIMULATOR_CEILING_CLIP_EPS = 0.0005
SHELF_ACTION_LIFT = 0.051
FLOOR_ACTION_LIFT = 0.02
CONTACT_TOLERANCE = 0.006
MIN_SUPPORT_RATIO = 0.55
# Side-by-side placement gap: settled clearance plus 1 mm slack so both the
# final-pose lateral guard and the transport clearance pass without sitting
# exactly on the rejection threshold.
ADJACENCY_GAP = SETTLED_ITEM_CLEARANCE + 0.001
# When the strict search finds nothing, retry once with relaxed support
# before emitting any blind fallback: a partially supported settle is far
# more survivable than a transport collision, which ends the episode.
RELAXED_MIN_SUPPORT_RATIO = 0.30
RELAXED_FALLBACK_RESERVE_SECONDS = 1.2
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
LOOKAHEAD_TIME_RESERVE_SECONDS = float(
    os.environ.get("LOOKAHEAD_TIME_RESERVE_SECONDS", "1.5")
)
LOOKAHEAD_INNER_ITEMS = int(os.environ.get("LOOKAHEAD_INNER_ITEMS", "3"))
# --- DPOR (dynamic partial-order reduction) for pair-block ordering ---
DPOR_MAX_ALTERNATE_ATTEMPTS = int(
    os.environ.get("DPOR_MAX_ALTERNATE_ATTEMPTS", "16")
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


def transport_start_and_z(candidate, container, geo=None):
    """
    Mirror of the validator's start-pose computation: clamped start X, the
    entry Y just outside the opening, and the transport height including the
    direct-rest and ceiling-clip rules, all derived from the transmitted
    action pose (with any shelf/floor lift applied).
    """
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
    action_center = simulator_action_center(candidate, container, geo)
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
    return start_x, entry_y, transport_z, target_x, target_y


def transport_sweeps(candidate, container, geo=None):
    start_x, entry_y, transport_z, target_x, target_y = transport_start_and_z(
        candidate, container, geo
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


def transport_sample_centers(
    candidate, container, geo=None, step: float = TRANSPORT_SAMPLE_STEP
):
    """Sample centers along the Y-then-X transport path as an (n, 3) array."""
    start_x, entry_y, transport_z, target_x, target_y = transport_start_and_z(
        candidate, container, geo
    )
    steps_y = max(int(math.ceil(abs(target_y - entry_y) / step)), 1)
    ys = np.linspace(entry_y, target_y, steps_y + 1)
    steps_x = max(int(math.ceil(abs(target_x - start_x) / step)), 1)
    xs = np.linspace(start_x, target_x, steps_x + 1)

    centers = np.empty((len(ys) + len(xs), 3), dtype=np.float64)
    centers[: len(ys), 0] = start_x
    centers[: len(ys), 1] = ys
    centers[len(ys):, 0] = xs
    centers[len(ys):, 1] = target_y
    centers[:, 2] = transport_z
    return centers


def transport_samples(candidate, container, step: float = TRANSPORT_SAMPLE_STEP):
    centers = transport_sample_centers(candidate, container, step=step)
    return [
        AABB(tuple(center), candidate.size, "transport_sample")
        for center in centers
    ]


def simulator_action_center(candidate, container, geo=None):
    action_center = np.asarray(candidate.center, dtype=np.float64).copy()
    bottom = float(candidate.minimum[2])
    shelves = geo.shelves if geo is not None else shelf_aabbs(container)
    for shelf in shelves:
        if (
            abs(bottom - shelf.top) <= CONTACT_TOLERANCE
            and xy_overlap_area(candidate, shelf) > EPS
        ):
            action_center[2] += SHELF_ACTION_LIFT
            return action_center
    floor_top = float(container["thickness"]) + float(
        container.get("buffer", 0.0)
    )
    if abs(bottom - floor_top) <= CONTACT_TOLERANCE:
        action_center[2] += FLOOR_ACTION_LIFT
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


class ContainerGeometry:
    """
    Precomputed geometry for one container observation state. Shelf boxes,
    packed AABBs, boundary planes, and support surfaces are static for the
    duration of a placement search, so computing them once per container
    per search (instead of per candidate) removes the dominant cost of
    candidate generation.
    """

    def __init__(self, container):
        self.container = container
        self.offset_x = container_offset_x(container)
        self.floor_top = float(container["thickness"]) + float(
            container.get("buffer", 0.0)
        )
        self.shelves = shelf_aabbs(container)
        self.packed = packed_aabbs_local(container)

        self.support = [
            AABB(
                center=(0.0, 0.0, self.floor_top),
                size=(
                    float(container["length"]),
                    float(container["width"]),
                    0.0,
                ),
                name="floor",
            )
        ]
        self.support.extend(self.shelves)
        self.support.extend(
            box
            for box, is_soft, is_prioritized in self.packed
            if not is_soft and not is_prioritized
        )
        self.support_min = np.array([s.minimum for s in self.support])
        self.support_max = np.array([s.maximum for s in self.support])
        self.support_top = np.array([s.top for s in self.support])

        obstacles = list(self.shelves) + [box for box, _s, _p in self.packed]
        if obstacles:
            self.obstacle_min = np.array([b.minimum for b in obstacles])
            self.obstacle_max = np.array([b.maximum for b in obstacles])
        else:
            self.obstacle_min = None
            self.obstacle_max = None

        points = container.get("points")
        normals = container.get("n_vecs")
        if points is not None and normals is not None:
            self.plane_points = np.asarray(points, dtype=np.float64)
            self.plane_normals = np.asarray(normals, dtype=np.float64)
        else:
            self.plane_points = None
            self.plane_normals = None


class Geometry:
    @staticmethod
    def inside_container(candidate, container, geo=None):
        if geo is not None:
            points = geo.plane_points
            normals = geo.plane_normals
        else:
            points = container.get("points")
            normals = container.get("n_vecs")
            if points is not None:
                points = np.asarray(points, dtype=np.float64)
            if normals is not None:
                normals = np.asarray(normals, dtype=np.float64)
        if points is None or normals is None:
            return True

        center_world = local_to_world(candidate.center, container)
        half_size = np.asarray(candidate.size, dtype=np.float64) / 2.0
        signed_extents = (
            np.sum(normals * (center_world - points), axis=1)
            + np.abs(normals) @ half_size
        )
        return bool(np.all(signed_extents <= -INCLUSION_CLEARANCE + EPS))

    @staticmethod
    def clears_static_geometry(candidate, container, geo=None):
        if geo is None:
            geo = ContainerGeometry(container)
        if geo.obstacle_min is None:
            return True
        cmin = np.asarray(candidate.minimum)
        cmax = np.asarray(candidate.maximum)
        vertical_gap = np.maximum(
            geo.obstacle_min[:, 2] - cmax[2],
            cmin[2] - geo.obstacle_max[:, 2],
        )
        x_gap = np.maximum(
            geo.obstacle_min[:, 0] - cmax[0],
            cmin[0] - geo.obstacle_max[:, 0],
        )
        y_gap = np.maximum(
            geo.obstacle_min[:, 1] - cmax[1],
            cmin[1] - geo.obstacle_max[:, 1],
        )
        penetrates = (
            (vertical_gap < -CONTACT_TOLERANCE)
            & (x_gap < SETTLED_ITEM_CLEARANCE - EPS)
            & (y_gap < SETTLED_ITEM_CLEARANCE - EPS)
        )
        return not bool(penetrates.any())

    @staticmethod
    def support_ratio(candidate, container, geo=None):
        item_area = float(candidate.size[0] * candidate.size[1])
        if item_area <= EPS:
            return 0.0
        if geo is None:
            geo = ContainerGeometry(container)

        bottom = float(candidate.minimum[2])
        matching = np.abs(bottom - geo.support_top) <= CONTACT_TOLERANCE
        if not matching.any():
            return 0.0
        cmin = np.asarray(candidate.minimum[:2])
        cmax = np.asarray(candidate.maximum[:2])
        overlap_min = np.maximum(cmin, geo.support_min[matching, :2])
        overlap_max = np.minimum(cmax, geo.support_max[matching, :2])
        span = np.maximum(0.0, overlap_max - overlap_min)
        supported_area = float((span[:, 0] * span[:, 1]).max())
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
        max_area = 0.0
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
            max_area = max(max_area, area)
            signed_margin = min(
                float(center_xy[0] - overlap_min[0]),
                float(overlap_max[0] - center_xy[0]),
                float(center_xy[1] - overlap_min[1]),
                float(overlap_max[1] - center_xy[1]),
            )
            margins.append(max(-1.0, min(1.0, signed_margin / normalizer)))
            mass_weighted += area * mass_ratio
            area_weight += area

        ratio = min(1.0, max_area / item_area)
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
    def has_stable_support(candidate, container, geo=None, min_support=None):
        threshold = MIN_SUPPORT_RATIO if min_support is None else min_support
        return Geometry.support_ratio(candidate, container, geo) >= threshold

    @staticmethod
    def transport_path_clear(candidate, container, geo=None):
        if geo is None:
            geo = ContainerGeometry(container)
        if geo.obstacle_min is None:
            return True
        centers = transport_sample_centers(candidate, container, geo)
        half = np.asarray(candidate.size, dtype=np.float64) / 2.0
        sample_min = centers - half
        sample_max = centers + half
        gaps = np.maximum(
            0.0,
            np.maximum(
                geo.obstacle_min[None, :, :] - sample_max[:, None, :],
                sample_min[:, None, :] - geo.obstacle_max[None, :, :],
            ),
        )
        squared = (gaps * gaps).sum(axis=2)
        threshold = SETTLED_ITEM_CLEARANCE - EPS
        return not bool((squared < threshold * threshold).any())

    @classmethod
    def valid(cls, candidate, container, geo=None, min_support=None):
        if geo is None:
            geo = ContainerGeometry(container)
        # The inclusion contract applies to the transmitted action pose,
        # which carries the shelf/floor lift; the raw contact pose may rest
        # exactly on the floor inclusion plane and would wrongly fail.
        action_pose = AABB(
            center=tuple(
                float(value)
                for value in simulator_action_center(candidate, container, geo)
            ),
            size=candidate.size,
            name="action_pose",
        )
        return (
            cls.inside_container(action_pose, container, geo)
            and cls.clears_static_geometry(candidate, container, geo)
            and cls.has_stable_support(candidate, container, geo, min_support)
            and cls.transport_path_clear(candidate, container, geo)
        )


class CandidateGenerator:
    @staticmethod
    def generate(
        observation,
        item,
        container_idx,
        orientation,
        limit=400,
        geo=None,
        min_support=None,
    ):
        container = observation["container_list"][container_idx]
        if geo is None:
            geo = ContainerGeometry(container)
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

        xs = {x_low, 0.0, x_high}
        ys = {y_low, 0.0, y_high}
        zs = set()

        if cut_x > 0.0:
            xs.add(
                -length / 2.0
                + thickness
                + cut_x
                + dx / 2.0
                + ADJACENCY_GAP
            )

        for surface in geo.support:
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

        for packed, _is_soft, _is_prioritized in geo.packed:
            xs.update(
                (
                    packed.minimum[0] - dx / 2.0 - ADJACENCY_GAP,
                    packed.maximum[0] + dx / 2.0 + ADJACENCY_GAP,
                )
            )
            ys.update(
                (
                    packed.minimum[1] - dy / 2.0 - ADJACENCY_GAP,
                    packed.maximum[1] + dy / 2.0 + ADJACENCY_GAP,
                )
            )

        # Grid in the historical iteration order: y descending outer,
        # x sorted by |x| inner; each z-layer is culled with vectorized
        # inclusion / static-clearance / support tests, and only the
        # survivors pay for the per-candidate transport-path check.
        xs_sorted = np.asarray(sorted(xs, key=abs), dtype=np.float64)
        ys_sorted = np.asarray(sorted(ys, reverse=True), dtype=np.float64)
        grid_x = np.tile(xs_sorted, len(ys_sorted))
        grid_y = np.repeat(ys_sorted, len(xs_sorted))
        half = np.asarray(dims, dtype=np.float64) / 2.0
        threshold = MIN_SUPPORT_RATIO if min_support is None else min_support
        item_area = float(dx * dy)
        if item_area <= EPS:
            return []

        candidates = []
        seen = set()
        for z in sorted(zs):
            bottom = float(z) - half[2]
            top = float(z) + half[2]

            matching = np.abs(bottom - geo.support_top) <= CONTACT_TOLERANCE
            if not matching.any():
                continue

            lifts = np.zeros(len(grid_x), dtype=np.float64)
            shelf_contact = np.zeros(len(grid_x), dtype=bool)
            for shelf in geo.shelves:
                if abs(bottom - shelf.top) <= CONTACT_TOLERANCE:
                    overlap_x = np.minimum(
                        grid_x + half[0], shelf.maximum[0]
                    ) - np.maximum(grid_x - half[0], shelf.minimum[0])
                    overlap_y = np.minimum(
                        grid_y + half[1], shelf.maximum[1]
                    ) - np.maximum(grid_y - half[1], shelf.minimum[1])
                    shelf_contact |= (
                        np.maximum(0.0, overlap_x) * np.maximum(0.0, overlap_y)
                        > EPS
                    )
            lifts[shelf_contact] = SHELF_ACTION_LIFT
            if abs(bottom - geo.floor_top) <= CONTACT_TOLERANCE:
                lifts[~shelf_contact] = FLOOR_ACTION_LIFT

            mask = np.ones(len(grid_x), dtype=bool)

            if geo.plane_points is not None:
                centers_world = np.stack(
                    (
                        grid_x + geo.offset_x,
                        grid_y,
                        np.full(len(grid_x), float(z)) + lifts,
                    ),
                    axis=1,
                )
                extents = (
                    (centers_world[:, None, :] - geo.plane_points[None, :, :])
                    * geo.plane_normals[None, :, :]
                ).sum(axis=2) + (np.abs(geo.plane_normals) @ half)[None, :]
                mask &= (extents <= -INCLUSION_CLEARANCE + EPS).all(axis=1)
                if not mask.any():
                    continue

            if geo.obstacle_min is not None:
                vertical_gap = np.maximum(
                    geo.obstacle_min[None, :, 2] - top,
                    bottom - geo.obstacle_max[None, :, 2],
                )
                x_gap = np.maximum(
                    geo.obstacle_min[None, :, 0]
                    - (grid_x[:, None] + half[0]),
                    (grid_x[:, None] - half[0])
                    - geo.obstacle_max[None, :, 0],
                )
                y_gap = np.maximum(
                    geo.obstacle_min[None, :, 1]
                    - (grid_y[:, None] + half[1]),
                    (grid_y[:, None] - half[1])
                    - geo.obstacle_max[None, :, 1],
                )
                penetrates = (
                    (vertical_gap < -CONTACT_TOLERANCE)
                    & (x_gap < SETTLED_ITEM_CLEARANCE - EPS)
                    & (y_gap < SETTLED_ITEM_CLEARANCE - EPS)
                )
                mask &= ~penetrates.any(axis=1)
                if not mask.any():
                    continue

            support_min = geo.support_min[matching, :2]
            support_max = geo.support_max[matching, :2]
            overlap_x = np.minimum(
                grid_x[:, None] + half[0], support_max[None, :, 0]
            ) - np.maximum(grid_x[:, None] - half[0], support_min[None, :, 0])
            overlap_y = np.minimum(
                grid_y[:, None] + half[1], support_max[None, :, 1]
            ) - np.maximum(grid_y[:, None] - half[1], support_min[None, :, 1])
            areas = np.maximum(0.0, overlap_x) * np.maximum(0.0, overlap_y)
            ratios = areas.max(axis=1) / item_area
            mask &= ratios >= threshold

            for index in np.flatnonzero(mask):
                position = (
                    float(grid_x[index]),
                    float(grid_y[index]),
                    float(z),
                )
                key = tuple(round(value, 4) for value in position)
                if key in seen:
                    continue
                seen.add(key)
                candidate = AABB(position, dims, "candidate")
                if Geometry.transport_path_clear(candidate, container, geo):
                    candidates.append(candidate)
                    if len(candidates) >= limit:
                        return candidates
        return candidates


class Ranker:
    @staticmethod
    def score(candidate, item, container, has_priority_container, geo=None):
        support = Geometry.support_ratio(candidate, container, geo)
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


class PlacementCore:
    """Single source of truth used by online policy and offline dry-runs."""

    @staticmethod
    def choose(observation, indexed_items, deadline=None, min_support=None):
        containers = observation.get("container_list", [])
        if not containers:
            return None

        has_priority_container = any(
            bool(container.get("is_prioritized", False))
            for container in containers
        )
        geos = {}
        best = None
        best_score = -float("inf")

        for item_idx, item in indexed_items:
            for container_idx in eligible_container_indices(item, containers):
                container = containers[container_idx]
                geo = geos.get(container_idx)
                if geo is None:
                    geo = ContainerGeometry(container)
                    geos[container_idx] = geo
                for orientation in unique_orientations(item):
                    if deadline is not None and time.perf_counter() >= deadline:
                        return best
                    for candidate in CandidateGenerator.generate(
                        observation,
                        item,
                        container_idx,
                        orientation,
                        geo=geo,
                        min_support=min_support,
                    ):
                        score = Ranker.score(
                            candidate,
                            item,
                            container,
                            has_priority_container,
                            geo,
                        )
                        if score > best_score:
                            best_score = score
                            best = PlacementDecision(
                                action={
                                    "item_idx": int(item_idx),
                                    "container_idx": int(container_idx),
                                    "place_pos": np.asarray(
                                        simulator_action_center(
                                            candidate, container, geo
                                        ),
                                        dtype=np.float32,
                                    ),
                                    "orientation": int(orientation),
                                },
                                candidate=candidate,
                                score=float(score),
                            )
        return best

    @staticmethod
    def top_candidates(observation, indexed_items, k, deadline=None):
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
        geos = {}
        heap = []
        counter = 0

        for item_idx, item in indexed_items:
            for container_idx in eligible_container_indices(item, containers):
                container = containers[container_idx]
                geo = geos.get(container_idx)
                if geo is None:
                    geo = ContainerGeometry(container)
                    geos[container_idx] = geo
                for orientation in unique_orientations(item):
                    if deadline is not None and time.perf_counter() >= deadline:
                        return [
                            decision
                            for _, _, decision in sorted(
                                heap, key=lambda entry: entry[0], reverse=True
                            )
                        ]
                    for candidate in CandidateGenerator.generate(
                        observation,
                        item,
                        container_idx,
                        orientation,
                        geo=geo,
                    ):
                        score = Ranker.score(
                            candidate,
                            item,
                            container,
                            has_priority_container,
                            geo,
                        )
                        decision = PlacementDecision(
                            action={
                                "item_idx": int(item_idx),
                                "container_idx": int(container_idx),
                                "place_pos": np.asarray(
                                    simulator_action_center(
                                        candidate, container, geo
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
                        if len(heap) < k:
                            heapq.heappush(heap, entry)
                        elif score > heap[0][0]:
                            heapq.heapreplace(heap, entry)
        return [
            decision
            for _, _, decision in sorted(
                heap, key=lambda entry: entry[0], reverse=True
            )
        ]


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
    metrics = Geometry.support_metrics(decision.candidate, container, item)

    packed = copy.deepcopy(item)
    packed["pos"] = local_to_world(
        decision.candidate.center, container
    ).tolist()
    packed["orientation"] = int(action["orientation"])
    packed["belongs_to"] = container_idx
    container.setdefault("packed_items", []).append(packed)

    return PlacementTrace(
        item_index=int(item["index"]),
        container_idx=container_idx,
        orientation=int(action["orientation"]),
        candidate=decision.candidate,
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

    def get_init_states(self, init_states: dict):
        containers = init_states.get("container_list", [])
        self._container_templates = [
            normalize_container(container) for container in containers
        ]
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
        used for every other decision, then score it by its own immediate
        score plus a discounted best-next-placement score for the items
        still in the pool. This reacts to what is genuinely still placeable
        after each candidate rather than only the single myopic best.
        """
        if not ordered_items:
            return None

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
        )
        if not top:
            return None
        if (
            len(top) == 1
            or len(ordered_items) <= 1
            or time.perf_counter() >= lookahead_deadline
        ):
            return top[0]

        inner_pool = ordered_items[:LOOKAHEAD_INNER_ITEMS]
        best_decision = top[0]
        best_total = -float("inf")
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
            future_score = 0.0
            if remaining:
                sim_observation = {
                    "pool_list": pool_list,
                    "container_list": sim_containers,
                }
                next_decision = PlacementCore.choose(
                    sim_observation, remaining, deadline=deadline - 0.2
                )
                if next_decision is not None:
                    future_score = next_decision.score
            total = decision.score + LOOKAHEAD_DISCOUNT * future_score
            if total > best_total:
                best_total = total
                best_decision = decision
        return best_decision

    def policy(self, observation: dict):
        deadline = time.perf_counter() + POLICY_BUDGET_SECONDS
        primary_deadline = deadline - RELAXED_FALLBACK_RESERVE_SECONDS
        pool_list = observation.get("pool_list", [])
        containers = observation.get("container_list", [])
        ordered_items = online_item_order(pool_list)[
            :MAX_POOL_ITEMS_EVALUATED
        ]

        decision = self._closed_loop_choice(
            observation, pool_list, ordered_items, primary_deadline
        )
        if decision is None:
            decision = PlacementCore.choose(
                observation,
                ordered_items,
                deadline=primary_deadline,
            )
        if decision is None:
            # A failed step ends the whole episode, so before emitting any
            # blind pose, retry with relaxed support: a partially supported
            # settle usually survives, a transport collision never does.
            decision = PlacementCore.choose(
                observation,
                ordered_items,
                deadline=deadline,
                min_support=RELAXED_MIN_SUPPORT_RATIO,
            )
        if decision is not None:
            return decision.action

        # Last resort: a floor pose just inside the opening. The packing
        # heuristics fill the container from the far wall (+y) first, so
        # the door-side floor strip is the least likely region to collide.
        fallback_container = 0
        if pool_list and containers:
            eligible = eligible_container_indices(pool_list[0], containers)
            if eligible:
                fallback_container = eligible[0]
        place_pos = np.array([0.0, 0.0, 0.25], dtype=np.float32)
        if pool_list and containers:
            item = pool_list[0]
            container = containers[fallback_container]
            dims = get_rotated_dimensions(
                item["length"], item["width"], item["height"], 0
            )
            thickness = float(container["thickness"])
            buffer = float(container.get("buffer", 0.0))
            width = float(container["width"])
            place_pos = np.array(
                [
                    0.0,
                    -width / 2.0
                    + thickness
                    + dims[1] / 2.0
                    + INCLUSION_CLEARANCE,
                    thickness + buffer + dims[2] / 2.0 + FLOOR_ACTION_LIFT,
                ],
                dtype=np.float32,
            )
        return {
            "item_idx": 0,
            "container_idx": fallback_container,
            "place_pos": place_pos,
            "orientation": 0,
        }
