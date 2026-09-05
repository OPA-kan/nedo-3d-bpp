"""Bridge to the geometry utilities that already exist in ``agent/agent.py``.

rule-alpha is an independent prototype: it must not change the production
policy.  It *may* reuse the geometry / transport / physics helpers that the
production agent already carries, and doing so is strictly better than copying
them, because a divergence between the two models of the official validator is
exactly the kind of bug this prototype cannot afford.

``agent/agent.py`` is a single flat module (there is no ``agent`` package), so
it is loaded by path.  Nothing here writes to it.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_AGENT_PATH = _REPO_ROOT / "agent" / "agent.py"
_MODULE_NAME = "_rule_alpha_production_geometry"


def _load() -> types.ModuleType:
    cached = sys.modules.get(_MODULE_NAME)
    if cached is not None:
        return cached
    if not _AGENT_PATH.exists():
        raise RuntimeError(
            f"rule-alpha needs the shared geometry helpers in {_AGENT_PATH}, "
            "which is missing from this checkout."
        )
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _AGENT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {_AGENT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


_production = _load()

# --- data types -------------------------------------------------------------
AABB = _production.AABB

# --- orientation ------------------------------------------------------------
get_rotated_dimensions = _production.get_rotated_dimensions
unique_orientations = _production.unique_orientations

# --- container / packed item accessors --------------------------------------
container_offset_x = _production.container_offset_x
container_requires_shelf = _production.container_requires_shelf
local_to_world = _production.local_to_world
world_to_local = _production.world_to_local
packed_position_world = _production.packed_position_world
packed_dimensions = _production.packed_dimensions
_packed_aabbs_local_uncached = _production.packed_aabbs_local
shelf_aabbs = _production.shelf_aabbs

# ``packed_aabbs_local`` re-parses every packed item's dict on every call and
# a single decision calls it thousands of times on the same, unchanged
# container.  The result is a list of (frozen AABB, bool, bool) tuples, so it
# can be shared.  Keyed on the identity of the container dict *and* of every
# packed-item dict in it: ``Board.apply`` appends a new dict, an observation
# builds new dicts, and neither mutates one in place.
_PACKED_CACHE: dict = {}
_PACKED_CACHE_LIMIT = 32


def packed_aabbs_local(container):
    packed = container.get("packed_items", [])
    key = (id(container), len(packed), tuple(id(p) for p in packed))
    hit = _PACKED_CACHE.get(key)
    if hit is not None:
        return hit
    value = _packed_aabbs_local_uncached(container)
    if len(_PACKED_CACHE) >= _PACKED_CACHE_LIMIT:
        _PACKED_CACHE.pop(next(iter(_PACKED_CACHE)))
    _PACKED_CACHE[key] = value
    return value
support_surfaces = _production.support_surfaces

# --- overlap / clearance ----------------------------------------------------
xy_overlap_area = _production.xy_overlap_area
penetrates_with_lateral_clearance = _production.penetrates_with_lateral_clearance
within_euclidean_clearance = _production.within_euclidean_clearance

# --- transport model (mirror of PlacementValidator.check_transport_path) -----
transport_samples = _production.transport_samples
transport_sweeps = _production.transport_sweeps
simulator_action_center = _production.simulator_action_center

# --- validity ---------------------------------------------------------------
Geometry = _production.Geometry

# --- clearance constants ----------------------------------------------------
INCLUSION_CLEARANCE = _production.INCLUSION_CLEARANCE
TRANSPORT_CLEARANCE = _production.TRANSPORT_CLEARANCE
SETTLED_ITEM_CLEARANCE = _production.SETTLED_ITEM_CLEARANCE
SIMULATOR_DROP_HEIGHT = _production.SIMULATOR_DROP_HEIGHT
SIMULATOR_START_MARGIN = _production.SIMULATOR_START_MARGIN
SHELF_ACTION_LIFT = _production.SHELF_ACTION_LIFT
CONTACT_TOLERANCE = _production.CONTACT_TOLERANCE
EPS = _production.EPS

__all__ = [
    "AABB",
    "CONTACT_TOLERANCE",
    "EPS",
    "Geometry",
    "INCLUSION_CLEARANCE",
    "SETTLED_ITEM_CLEARANCE",
    "SHELF_ACTION_LIFT",
    "SIMULATOR_DROP_HEIGHT",
    "SIMULATOR_START_MARGIN",
    "TRANSPORT_CLEARANCE",
    "container_offset_x",
    "container_requires_shelf",
    "get_rotated_dimensions",
    "local_to_world",
    "packed_aabbs_local",
    "packed_dimensions",
    "packed_position_world",
    "penetrates_with_lateral_clearance",
    "shelf_aabbs",
    "simulator_action_center",
    "support_surfaces",
    "transport_samples",
    "transport_sweeps",
    "unique_orientations",
    "within_euclidean_clearance",
    "world_to_local",
    "xy_overlap_area",
]
