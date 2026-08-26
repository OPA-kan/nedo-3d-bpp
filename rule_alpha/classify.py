"""Item classification and orientation policy (steps A and B of the spec).

Classification is deliberately shallow: it only reads ``is_soft`` /
``is_prioritized`` and the raw dimensions.  Nothing here looks at the board, so
a class is a stable property of an item and can be logged once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ._reuse import get_rotated_dimensions, unique_orientations


# --- cargo classes -----------------------------------------------------------
NORMAL_HARD = "normal-hard"
SOFT = "soft"
PRIORITY = "priority"
SOFT_PRIORITY = "soft-priority"

# --- structural roles (orthogonal to the cargo class) ------------------------
ROLE_NONE = "none"
ROLE_ELONGATED = "elongated"
ROLE_WALL_FRONT = "wall-front"
ROLE_SLOPE_INFILL = "slope-infill"
ROLE_TALL_PERIMETER = "tall-perimeter"

# --- tipping bands -----------------------------------------------------------
TIP_NORMAL = "normal"
TIP_WALL_PREFERRED = "wall-preferred"
TIP_WALL_STRONG = "wall-strong"
TIP_NEEDS_BACKING = "needs-backing"


@dataclass(frozen=True)
class Orientation:
    """One admissible orientation of one item."""

    index: int
    dx: float
    dy: float
    dz: float

    @property
    def footprint(self) -> float:
        return self.dx * self.dy

    @property
    def tipping_ratio(self) -> float:
        """R = dz / min(dx, dy) — the spec's tip-over risk proxy."""
        return self.dz / max(1e-9, min(self.dx, self.dy))

    def tipping_band(self, config) -> str:
        r = self.tipping_ratio
        if r < config.tipping_normal:
            return TIP_NORMAL
        if r < config.tipping_wall_preferred:
            return TIP_WALL_PREFERRED
        if r < config.tipping_wall_strong:
            return TIP_WALL_STRONG
        return TIP_NEEDS_BACKING

    def as_dict(self) -> dict:
        return {
            "orientation": self.index,
            "dx": round(self.dx, 4),
            "dy": round(self.dy, 4),
            "dz": round(self.dz, 4),
            "footprint": round(self.footprint, 4),
            "tipping_ratio": round(self.tipping_ratio, 3),
        }


@dataclass
class ItemProfile:
    """Everything rule-alpha decides about an item before looking at the board."""

    index: int
    item: dict
    cargo_class: str
    is_soft: bool
    is_prioritized: bool
    elongation: float
    is_elongated: bool
    orientations: list[Orientation] = field(default_factory=list)
    volume: float = 0.0
    mass: float = 1.0

    @property
    def max_footprint(self) -> float:
        return max((o.footprint for o in self.orientations), default=0.0)

    @property
    def max_height(self) -> float:
        return max((o.dz for o in self.orientations), default=0.0)

    def summary(self) -> dict:
        return {
            "item_index": self.index,
            "class": self.cargo_class,
            "is_soft": self.is_soft,
            "is_prioritized": self.is_prioritized,
            "elongation_rho": round(self.elongation, 3),
            "is_elongated": self.is_elongated,
            "dims": [
                round(float(self.item["length"]), 4),
                round(float(self.item["width"]), 4),
                round(float(self.item["height"]), 4),
            ],
            "mass": self.mass,
            "volume": round(self.volume, 5),
        }


def elongation_ratio(length: float, width: float, height: float) -> float:
    """rho = max / median of the three raw dimensions."""
    a, b, _c = sorted((length, width, height), reverse=True)
    return a / max(1e-9, b)


def classify_item(index: int, item: dict, config) -> ItemProfile:
    soft = bool(item.get("is_soft", False))
    priority = bool(item.get("is_prioritized", False))
    if soft and priority:
        cargo_class = SOFT_PRIORITY
    elif soft:
        cargo_class = SOFT
    elif priority:
        cargo_class = PRIORITY
    else:
        cargo_class = NORMAL_HARD

    length = float(item["length"])
    width = float(item["width"])
    height = float(item["height"])
    rho = elongation_ratio(length, width, height)

    orientations = [
        Orientation(o, *get_rotated_dimensions(length, width, height, o))
        for o in unique_orientations(item)
    ]

    return ItemProfile(
        index=index,
        item=item,
        cargo_class=cargo_class,
        is_soft=soft,
        is_prioritized=priority,
        elongation=rho,
        is_elongated=rho >= config.elongation_tau,
        orientations=orientations,
        volume=length * width * height,
        mass=float(item.get("mass", 1.0)),
    )


# ---------------------------------------------------------------------------
# Orientation policy
# ---------------------------------------------------------------------------
def floor_orientation_order(profile: ItemProfile, config) -> list[Orientation]:
    """Normal floor rule: maximise footprint, break ties by the lower box."""
    return sorted(
        profile.orientations,
        key=lambda o: (-round(o.footprint, 6), round(o.dz, 6), o.index),
    )


def shelf_orientation_order(profile: ItemProfile, config) -> list[Orientation]:
    """Shelf rule: minimise footprint, but refuse to stand a box on a spike.

    The shelf is the scarce surface, so one soft item must not eat it.  The
    ``max_shelf_tipping_ratio`` cap is what stops "minimise footprint" from
    degenerating into "stand everything on end".
    """
    usable = [
        o for o in profile.orientations
        if o.tipping_ratio <= config.max_shelf_tipping_ratio
    ]
    if not usable:
        usable = sorted(profile.orientations, key=lambda o: o.tipping_ratio)[:1]
    return sorted(
        usable,
        key=lambda o: (round(o.footprint, 6), round(o.tipping_ratio, 6), o.index),
    )


def structural_orientation_order(profile: ItemProfile, config) -> list[Orientation]:
    """Elongated / wall-front rule: buy height, but stay inside the tip bands.

    Orientations that would be free-standing spikes are kept but pushed to the
    back of the list; the placement stage is what refuses them when no wall or
    backing item is available.
    """
    return sorted(
        profile.orientations,
        key=lambda o: (
            -round(o.dz, 6),
            round(o.tipping_ratio, 6),
            -round(o.footprint, 6),
            o.index,
        ),
    )


def orientation_order(profile: ItemProfile, surface: str, role: str, config):
    """Dispatch to the orientation rule that matches surface and role."""
    if surface == "shelf":
        return shelf_orientation_order(profile, config)
    if role in (ROLE_WALL_FRONT, ROLE_ELONGATED, ROLE_TALL_PERIMETER) and not profile.is_soft:
        # The structural exception is for hard cargo only: a soft item cannot be
        # a structural member, so a long soft bag still lies down.
        return structural_orientation_order(profile, config)
    return floor_orientation_order(profile, config)
