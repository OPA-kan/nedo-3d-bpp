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
        self.inside = self._inside_mask()
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
