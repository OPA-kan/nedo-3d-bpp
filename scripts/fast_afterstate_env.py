"""
Physics-free afterstate environment: the speed step RL needs first.

The Tetris result this borrows from is not a network change. It is that the
environment got about 53x faster by representing the board as bits and
scoring AFTERSTATES -- the board a placement leaves behind -- instead of
learning through a long sequence of key presses. The same split applies
here, and more cleanly, because our candidate generator already enumerates
legal placements: the search proposes, and a value function only has to
rank what it proposed.

What is slow here is PyBullet. One episode costs one to two minutes because
every placement is settled. That is fine for a final check and hopeless as
a training loop, so this module drops a candidate onto a heightmap and
accepts it under the RELEASE contract -- containment, static clearance,
corridor -- which is the contract the shipped release candidates already
pass. It deliberately does NOT decide safety; `is_safe` is what physics
answers, and the fidelity of this approximation is a measured question, not
an assumption (see scripts/measure_afterstate_fidelity.py).

Generality constraint, and it is the reason this is not a fixed grid.
Container geometry VARIES across the official cases: one or two containers,
shelf or not, a chamfer, pre-loaded stock. A representation indexed by
absolute coordinates would learn one container. So every feature here is
relative to the container's own envelope, and occupancy is tested against
the container's half-spaces rather than a box formula -- the same fix that
was worth +52% when the anchor envelope stopped assuming a box.
"""
from __future__ import annotations

import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CELL = 0.05

# keyed by container geometry; the mask is pure geometry so it is reusable
_INSIDE_MASK_CACHE: dict = {}


class AfterstateBoard:
    """A container as a heightmap plus its real half-spaces."""

    def __init__(self, agent_module, container):
        self.agent = agent_module
        self.container = container
        self.length = float(container["length"])
        self.width = float(container["width"])
        self.height = float(container["height"])
        self.thickness = float(container["thickness"])
        self.nx = max(1, int(round(self.length / CELL)))
        self.ny = max(1, int(round(self.width / CELL)))
        self.x0 = -self.length / 2.0
        self.y0 = -self.width / 2.0
        # The floor half-space sits AT z = thickness, and containment
        # demands INCLUSION_CLEARANCE from every plane, so a pose resting
        # exactly on the floor is rejected -- correctly, because a release
        # candidate is the pose sent BEFORE settle, not where the item ends
        # up. The effective drop floor is therefore lifted by that
        # clearance; physics lowers it the rest of the way.
        self.floor = self.thickness + float(
            getattr(agent_module, "INCLUSION_CLEARANCE", 0.016)
        )
        self.heights = np.full((self.nx, self.ny), self.floor, dtype=np.float64)
        # Cells outside the real envelope are not floor and must never be
        # counted as usable space; a box assumption here is the defect the
        # envelope fix removed.
        # The mask costs nx*ny containment probes and depends only on the
        # container's geometry, so self-play over many episodes on the same
        # container must not pay for it repeatedly.
        key = (
            self.length, self.width, self.height, self.thickness,
            container.get("cut_x"), container.get("cut_y"),
            None if container.get("points") is None
            else len(container["points"]),
        )
        cached = _INSIDE_MASK_CACHE.get(key)
        if cached is None:
            cached = self._inside_mask()
            _INSIDE_MASK_CACHE[key] = cached
        self.inside = cached
        self.placed = 0
        for packed, _soft, _prioritized in agent_module.packed_aabbs_local(container):
            cx, cy, cz = packed.center
            sx, sy, sz = packed.size
            self.paint(float(cx), float(cy), float(sx), float(sy), float(cz) + float(sz) / 2.0)
            self.placed += 1

    def _inside_mask(self) -> np.ndarray:
        """
        Which floor cells the container actually admits.

        The probe has to clear INCLUSION_CLEARANCE (16 mm) from every plane
        including the floor -- a probe resting exactly on the floor is
        rejected by all of them, which reads as a container with no inside
        at all. It also sits low on purpose: these shapes have a chamfer,
        so the usable footprint is narrowest near the floor and a probe
        placed mid-height would call cells usable that nothing can rest on.
        """
        mask = np.zeros((self.nx, self.ny), dtype=bool)
        probe = 0.01
        clearance = float(getattr(self.agent, "INCLUSION_CLEARANCE", 0.016))
        z = self.thickness + clearance + probe / 2.0
        # (same lift as the drop floor, for the same reason)
        for i in range(self.nx):
            for j in range(self.ny):
                x = self.x0 + (i + 0.5) * CELL
                y = self.y0 + (j + 0.5) * CELL
                candidate = self.agent.AABB(
                    center=(x, y, z), size=(CELL, CELL, probe), name="probe"
                )
                mask[i, j] = self.agent.Geometry.inside_container(
                    candidate, self.container
                )
        return mask

    def _span(self, cx, cy, dx, dy):
        lo_i = max(0, int((cx - dx / 2.0 - self.x0) / CELL))
        hi_i = min(self.nx - 1, int((cx + dx / 2.0 - self.x0) / CELL))
        lo_j = max(0, int((cy - dy / 2.0 - self.y0) / CELL))
        hi_j = min(self.ny - 1, int((cy + dy / 2.0 - self.y0) / CELL))
        return lo_i, hi_i, lo_j, hi_j

    def drop_height(self, cx, cy, dx, dy) -> float:
        lo_i, hi_i, lo_j, hi_j = self._span(cx, cy, dx, dy)
        return float(self.heights[lo_i : hi_i + 1, lo_j : hi_j + 1].max())

    def paint(self, cx, cy, dx, dy, top) -> None:
        lo_i, hi_i, lo_j, hi_j = self._span(cx, cy, dx, dy)
        window = self.heights[lo_i : hi_i + 1, lo_j : hi_j + 1]
        np.maximum(window, top, out=window)

    def afterstate(self, item, orientation, cx, cy):
        """
        The board this placement would leave, or None if it is not legal.

        Legality is the shipped release contract, not a reimplementation:
        the same call the agent's own release candidates pass.
        """
        dx, dy, dz = self.agent.get_rotated_dimensions(
            item["length"], item["width"], item["height"], orientation
        )
        bottom = self.drop_height(cx, cy, dx, dy)
        candidate = self.agent.AABB(
            center=(cx, cy, bottom + dz / 2.0), size=(dx, dy, dz), name="release_candidate"
        )
        if (
            self.agent.Geometry.release_rejection_reason(candidate, self.container)
            is not None
        ):
            return None
        child = self.__class__.__new__(self.__class__)
        child.__dict__.update(self.__dict__)
        child.heights = self.heights.copy()
        child.paint(cx, cy, dx, dy, bottom + dz)
        child.placed = self.placed + 1
        return child, candidate

    def features(self) -> dict:
        """
        Container-relative descriptors. Every one is a ratio or a
        normalised quantity, so the same vector means the same thing on a
        different container -- which is what makes a learned ranker
        transferable across the case mix rather than fitted to one shape.
        """
        usable = self.heights[self.inside]
        if usable.size == 0:
            return {}
        interior = max(self.height - self.floor, 1e-9)
        rel = (usable - self.floor) / interior
        # roughness along each axis, over inside cells only
        h = np.where(self.inside, self.heights, np.nan)
        dx_diff = np.abs(np.diff(h, axis=0))
        dy_diff = np.abs(np.diff(h, axis=1))
        roughness = float(
            np.nanmean(np.concatenate([dx_diff.ravel(), dy_diff.ravel()]))
        ) / interior
        return {
            "occupancy_mean": float(rel.mean()),
            "occupancy_max": float(rel.max()),
            "occupancy_std": float(rel.std()),
            "roughness": roughness,
            # Wasted headroom under the tallest column: the analogue of a
            # Tetris hole, expressed as a fraction of the interior.
            "headroom_deficit": float((rel.max() - rel).mean()),
            "floor_fraction_free": float((rel < 1e-6).mean()),
            "placed": float(self.placed),
        }


SLOT_CELL = 0.25


def board_grid(board, gx=16, gy=12):
    """Max-pooled relative-height grid: the raw learnable substrate.

    The six scalar descriptors collapsed onto the fullness axis and the
    hand-built receptivity scan costs 1.2 s per call, which prices it out
    of per-row self-play labelling. This is the alternative: hand the
    model the height field itself (0.6 ms) and let it learn what
    receptivity looks like. Max pooling, not mean: a single tall column
    inside a cell blocks a landing exactly like a full cell does.
    """
    h = np.where(board.inside, board.heights, board.floor)
    interior = max(board.height - board.floor, 1e-9)
    rel = (h - board.floor) / interior
    nx, ny = rel.shape
    grid = []
    for i in range(gx):
        lo_x = int(i * nx / gx)
        hi_x = max(int((i + 1) * nx / gx), lo_x + 1)
        row = []
        for j in range(gy):
            lo_y = int(j * ny / gy)
            hi_y = max(int((j + 1) * ny / gy), lo_y + 1)
            row.append(float(rel[lo_x:hi_x, lo_y:hi_y].max()))
        grid.append(row)
    return grid


def largest_free_span(board):
    """Widest run of floor-level cells along x, as a length fraction.

    The original inline version iterated heightmap ROWS, which are runs
    along y, and then normalised by container LENGTH — an axis mismatch
    that reported 0.7 for an empty container. Fixed here: runs along x
    (the container's long axis, where big items need room), normalised
    by length, so an empty container reads ~1 minus the wall clearance.
    """
    floor_cells = board.inside & (board.heights <= board.floor + 1e-9)
    best_run = 0
    for column in floor_cells.T:
        run = 0
        for cell in column:
            run = run + 1 if cell else 0
            best_run = max(best_run, run)
    return float(best_run) * CELL / board.length


def fullness_orthogonal_features(agent_module, board, *, stride=0.15):
    """
    Board quality at CONSTANT fullness.

    The six descriptors on AfterstateBoard turned out to be one axis:
    occupancy_mean alone scores AUC 0.944 against 0.809 for a model fitted
    on all six, and two of them are that same number inverted. Nothing in
    the set distinguishes a half-full board that is clean from a half-full
    board that is ruined, so nothing learned on it can either.

    These are the quantities that vary when fullness does not:

    R_c   per published type, how many INDEPENDENT places it can still go.
          Independent means separated by a coarse slot, because two drops a
          few centimetres apart are one escape route and counting them as
          two is how a raw candidate count measures the generator's stride
          instead of the board (docs/theory/TASK_C_BOARD_VALUE.md 0.1).
          Counted from geometry here, never from generated candidates, so
          that contamination cannot recur.

    covered_void  free space with material directly above it, as a
          fraction of the interior. Voxelised, NOT read off the heightmap:
          the first version of this was `mean(max_height - height)`, which
          is `headroom_deficit` to machine precision, because a heightmap
          cannot tell a low column beside a tall one from a pocket under an
          overhang. See `sealed_void_fraction`.

    largest_free_span  the widest run of cells at the floor level, which is
          what decides whether a big item still has anywhere to go.

    Cost is the reason for the coarse stride: this runs per afterstate.
    """
    from scripts.measure_board_value import BAGGAGE_TYPES, type_representative

    features = {}
    total_slots = set()
    for index, entry in enumerate(BAGGAGE_TYPES):
        item = type_representative(entry, index)
        slots = set()
        for orientation in agent_module.unique_orientations(item):
            dx, dy, dz = agent_module.get_rotated_dimensions(
                item["length"], item["width"], item["height"], orientation
            )
            x = board.x0 + stride / 2.0
            while x < -board.x0:
                y = board.y0 + stride / 2.0
                while y < -board.y0:
                    bottom = board.drop_height(x, y, dx, dy)
                    candidate = agent_module.AABB(
                        center=(x, y, bottom + dz / 2.0),
                        size=(dx, dy, dz),
                        name="release_candidate",
                    )
                    if (
                        agent_module.Geometry.release_rejection_reason(
                            candidate, board.container
                        )
                        is None
                    ):
                        slots.add(
                            (
                                int(round(x / SLOT_CELL)),
                                int(round(y / SLOT_CELL)),
                                int(round(bottom / 0.10)),
                            )
                        )
                    y += stride
                x += stride
        features[f"R_{entry['name']}"] = float(len(slots))
        total_slots |= slots

    features["R_total_slots"] = float(len(total_slots))
    features["R_min_type"] = float(
        min(v for k, v in features.items() if k.startswith("R_") and k != "R_total_slots")
    )
    features["R_extinct_types"] = float(
        sum(
            1
            for k, v in features.items()
            if k.startswith("R_") and k not in ("R_total_slots", "R_min_type") and v == 0
        )
    )
    total, by_items = sealed_void_fraction(agent_module, board)
    features["covered_void"] = total
    features["covered_void_by_items"] = by_items
    features["largest_free_span"] = largest_free_span(board)
    return features


def sealed_void_fraction(agent_module, board, *, cell=0.05):
    """
    Free volume that has material directly above it, as a fraction of the
    interior.

    This was originally computed from the heightmap as
    ``mean(max_height - height)`` -- which is exactly the existing
    ``headroom_deficit``, to machine precision, so the "new" feature was a
    rename. The duplication was not a naming slip: a heightmap CANNOT
    express this quantity. It records one number per column, so a low column
    beside a tall one (still open from above) and a pocket under an overhang
    (sealed) look identical to it.

    The distinction is the whole point -- the section drawings put 21.4% of
    the envelope in sealed void overall and 30% in the shelf containers --
    so this voxelises the settled AABBs instead, which is the cheapest
    representation that can see an overhang at all.

    Returns TWO fractions, because the first version conflated them and the
    conflation is load-bearing: on an EMPTY shelf container the total is
    already 0.268, all of it the volume the main shelf seals off. That part
    is a property of the container -- useful to L3 when choosing between
    containers, useless as a description of what the packing did. So:

      total      everything sealed, shelves included
      by_items   sealed with only settled items acting as the ceiling,
                 which is the part the policy created and can avoid
    """
    length = board.length
    width = board.width
    height = board.height
    xs = np.arange(-length / 2.0 + cell / 2.0, length / 2.0, cell)
    ys = np.arange(-width / 2.0 + cell / 2.0, width / 2.0, cell)
    zs = np.arange(board.floor + cell / 2.0, height, cell)
    if xs.size == 0 or ys.size == 0 or zs.size == 0:
        return 0.0
    gx, gy, gz = np.meshgrid(xs, ys, zs, indexing="ij")
    points = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)

    container = board.container
    planes = container.get("points")
    normals = container.get("n_vecs")
    if planes is None or normals is None:
        inside = np.ones(len(points), dtype=bool)
    else:
        offset = float(agent_module.container_offset_x(container))
        plane_points = np.asarray(planes, dtype=np.float64).copy()
        plane_points[:, 0] -= offset
        plane_normals = np.asarray(normals, dtype=np.float64)
        inside = np.ones(len(points), dtype=bool)
        for point, normal in zip(plane_points, plane_normals):
            inside &= (points - point) @ normal <= 0.0

    items = np.zeros(len(points), dtype=bool)
    for packed, _soft, _prioritized in agent_module.packed_aabbs_local(container):
        centre = np.asarray(packed.center, dtype=np.float64)
        half = np.asarray(packed.size, dtype=np.float64) / 2.0
        items |= np.all(np.abs(points - centre) <= half, axis=1)
    plates = np.zeros(len(points), dtype=bool)
    for plate in agent_module.shelf_aabbs(container):
        plates |= np.all(
            (points >= np.asarray(plate.minimum))
            & (points <= np.asarray(plate.maximum)),
            axis=1,
        )

    shape = gx.shape
    inside3 = inside.reshape(shape)
    interior_cells = int(inside3.sum())
    if interior_cells == 0:
        return 0.0, 0.0

    def sealed(ceiling, solid):
        above = np.cumsum(ceiling[:, :, ::-1], axis=2)[:, :, ::-1] > 0
        return float((inside3 & ~solid & above).sum()) / interior_cells

    solid3 = (items | plates).reshape(shape)
    items3 = items.reshape(shape)
    return sealed(solid3, solid3), sealed(items3, solid3)


def enumerate_afterstates(agent_module, container, item, *, stride=CELL):
    """Every legal drop of one item, with the board each one leaves."""
    board = AfterstateBoard(agent_module, container)
    out = []
    xs = np.arange(board.x0 + stride / 2.0, -board.x0, stride)
    ys = np.arange(board.y0 + stride / 2.0, -board.y0, stride)
    for orientation in agent_module.unique_orientations(item):
        for cx in xs:
            for cy in ys:
                result = board.afterstate(item, orientation, float(cx), float(cy))
                if result is None:
                    continue
                child, candidate = result
                out.append(
                    {
                        "orientation": int(orientation),
                        "center": tuple(float(v) for v in candidate.center),
                        "size": tuple(float(v) for v in candidate.size),
                        "features": child.features(),
                    }
                )
    return board, out


def main() -> int:
    import argparse
    import json
    import time

    from scripts.measure_anchor_recall import load_agent_module, policy_observation

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--stride", type=float, default=CELL)
    args = parser.parse_args()

    agent_module = load_agent_module()
    sys.path.insert(0, str(ROOT / "simulator"))
    from src.ground_handling.env import GroundHandlingEnv

    config = json.loads(args.config.read_text(encoding="utf-8"))
    # Config files hold one case keyed by its id; the env wants the case.
    case = config.get(args.case) or next(iter(config.values()))
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = agent_module.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)
    observation = policy_observation(env, raw)
    item = observation["pool_list"][0]
    container = observation["container_list"][0]

    started = time.perf_counter()
    board, states = enumerate_afterstates(
        agent_module, container, item, stride=args.stride
    )
    elapsed = time.perf_counter() - started
    print(f"grid {board.nx}x{board.ny}, inside cells {int(board.inside.sum())}")
    print(f"legal afterstates: {len(states)} in {elapsed:.3f}s")
    if states:
        rate = len(states) / max(elapsed, 1e-9)
        print(f"rate: {rate:,.0f} afterstates/s")
        print("example features:", json.dumps(states[0]["features"], indent=1))
    env.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
