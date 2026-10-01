"""A private pybullet world that mirrors the official simulator's placement
test, so a pose can be tried before it is committed.

The official simulator (``ground_handling``) accepts a placement in three
steps: an inclusion test on the target pose, a transport sweep that moves
the box from the opening to the target with ``getClosestPoints`` against the
packed items and the shelves within ``safety_margin``, and a settle: the box
is warped to the target and the world stepped ``settle_wait_step`` times,
after which a displacement over ``displacement_threshold`` or a rotation
over ``angle_displacement_threshold`` ends the episode.  Rule-alpha's
analytic mirror models the first two with axis-aligned boxes and does not
model the settle at all; on the physics bench 2-4 episodes of 48 end on
a settle or transport rejection the mirror did not see, and the poses the
item search adds on the analytic board settle outside what the evaluator
counts.

``ShadowSim`` builds the same world from the observation (the container
meshes the simulator writes, the shelves, the packed items at their
settled poses with their dynamics), and ``check`` runs the same sweep and
the same settle for one candidate pose, returning the verdicts and where
the box came to rest.  The world is rebuilt from the observation at every
call, so it never drifts from what the simulator reports.  The mesh
writers are the simulator's own (``ground_handling.utils``), copied here
so the agent does not import the simulator package at play time.
"""

from __future__ import annotations

import math
import os
import tempfile

import numpy as np

try:  # pybullet is what the official simulator runs on, so it is present
    import pybullet as p
    from pybullet_utils.bullet_client import BulletClient
except Exception:  # pragma: no cover - the check is simply unavailable
    p = None
    BulletClient = None

# --- the simulator's orientation table and half extents ---------------------
ORNS = [
    [0, 0, 0],
    [math.pi / 2, 0, 0],
    [0, math.pi / 2, 0],
    [0, 0, math.pi / 2],
    [0, math.pi / 2, math.pi / 2],
    [math.pi / 2, 0, math.pi / 2],
]


def get_half_ext(original_lwh, orn_idx: int):
    l, w, h = (float(v) / 2.0 for v in original_lwh)
    return {0: [l, w, h], 1: [l, h, w], 2: [h, w, l], 3: [w, l, h], 4: [w, h, l], 5: [h, l, w]}.get(orn_idx, [l, w, h])


# --- the simulator's container mesh writers (ground_handling.utils) ----------
def _center_xy(poly, cx, cy):
    return [[x - cx, y - cy] for x, y in poly]


def _line_intersection_2d(p1, d1, p2, d2):
    cross = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(cross) < 1e-12:
        raise ValueError("offset failed: parallel lines")
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    t = (dx * d2[1] - dy * d2[0]) / cross
    return [p1[0] + t * d1[0], p1[1] + t * d1[1]]


def _offset_convex_polygon_ccw(poly, offset):
    lines = []
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        ex = b[0] - a[0]
        ey = b[1] - a[1]
        length = math.hypot(ex, ey)
        if length < 1e-12:
            raise ValueError("invalid polygon")
        nx = -ey / length
        ny = ex / length
        lines.append(([a[0] + nx * offset, a[1] + ny * offset], [ex, ey]))
    inner = []
    for i in range(n):
        p1, d1 = lines[i - 1]
        p2, d2 = lines[i]
        inner.append(_line_intersection_2d(p1, d1, p2, d2))
    return inner


def _triangulate_fan(indices, reverse=False):
    tris = []
    for i in range(1, len(indices) - 1):
        if reverse:
            tris.append([indices[0], indices[i + 1], indices[i]])
        else:
            tris.append([indices[0], indices[i], indices[i + 1]])
    return tris


def write_open_cut_corner_cup_obj(file_path, width, height, cut_x, cut_y, depth, wall, bottom):
    outer2d = [[cut_x, 0.0], [width, 0.0], [width, height], [0.0, height], [0.0, cut_y]]
    inner2d = _offset_convex_polygon_ccw(outer2d, wall)
    cx, cy = width / 2.0, height / 2.0
    outer2d = _center_xy(outer2d, cx, cy)
    inner2d = _center_xy(inner2d, cx, cy)
    z0, z1 = -depth / 2.0, depth / 2.0
    zi = z0 + bottom
    vertices = []
    for x, y in outer2d:
        vertices.append([x, y, z0])
    for x, y in outer2d:
        vertices.append([x, y, z1])
    for x, y in inner2d:
        vertices.append([x, y, zi])
    for x, y in inner2d:
        vertices.append([x, y, z1])
    n = 5
    ob = list(range(0, n))
    ot = list(range(n, 2 * n))
    ib = list(range(2 * n, 3 * n))
    it = list(range(3 * n, 4 * n))
    faces = []
    faces += _triangulate_fan(ob, reverse=True)
    for i in range(n):
        j = (i + 1) % n
        faces.append([ob[i], ob[j], ot[j]])
        faces.append([ob[i], ot[j], ot[i]])
    faces += _triangulate_fan(ib, reverse=False)
    for i in range(n):
        j = (i + 1) % n
        faces.append([ib[i], it[j], ib[j]])
        faces.append([ib[i], it[i], it[j]])
    for i in range(n):
        j = (i + 1) % n
        faces.append([ot[i], ot[j], it[j]])
        faces.append([ot[i], it[j], it[i]])
    with open(file_path, "w", encoding="utf-8") as f:
        for v in vertices:
            f.write(f"v {v[0]:.8f} {v[1]:.8f} {v[2]:.8f}\n")
        for tri in faces:
            a, b, c = [idx + 1 for idx in tri]
            f.write(f"f {a} {b} {c}\n")


def write_corner_lid_obj(file_path, width, height, cut_x, cut_y, depth, lid_thickness):
    outer2d = [[cut_x, 0.0], [cut_x, height], [0.0, height], [0.0, cut_y]]
    outer2d = _center_xy(outer2d, width / 2.0, height / 2.0)
    z0 = depth / 2.0
    z1 = z0 + lid_thickness
    vertices = [[outer2d[i][0], outer2d[i][1], z0] for i in range(4)] + [[outer2d[i][0], outer2d[i][1], z1] for i in range(4)]
    faces = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
             [0, 1, 4], [4, 1, 5], [1, 2, 6], [1, 6, 5], [2, 3, 7], [7, 6, 2], [3, 0, 4], [4, 7, 3]]
    with open(file_path, "w", encoding="utf-8") as f:
        for v in vertices:
            f.write(f"v {v[0]:.8f} {v[1]:.8f} {v[2]:.8f}\n")
        for tri in faces:
            a, b, c = [i + 1 for i in tri]
            f.write(f"f {a} {b} {c}\n")


# --- the item dynamics the simulator applies (ground_handling.items.Item) ---
_ITEM_DEFAULTS = {
    "lateralFriction": 0.8, "rollingFriction": 0.01, "spinningFriction": 0.01,
    "restitution": 0.0, "angularDamping": 0.8,
}
_SOFT_DEFAULTS = {"contactStiffness": 5000, "contactDamping": 500, "linearDamping": 0.8}


def _dynamics(item: dict) -> dict:
    out = {k: float(item.get(k, v)) for k, v in _ITEM_DEFAULTS.items()}
    if bool(item.get("is_soft", False)):
        out.update({k: float(item.get(k, v)) for k, v in _SOFT_DEFAULTS.items()})
    return out


def _orientation_quaternion(item: dict):
    orn = item.get("orn")
    if orn is not None and len(orn) == 4:
        return tuple(float(v) for v in orn)
    idx = item.get("orientation")
    if idx is not None and p is not None:
        return p.getQuaternionFromEuler(ORNS[int(idx)])
    return (0.0, 0.0, 0.0, 1.0)


def available() -> bool:
    return p is not None


class ShadowSim:
    """The simulator's placement test in a private world.

    ``settle_steps``, ``safety_margin``, ``start_z``, ``start_margin``,
    ``ceiling_margin``, ``displacement_threshold`` and
    ``angle_threshold_deg`` are the simulator's validator settings
    (``simulator/configs/sample_config.json``)."""

    def __init__(self, settle_steps: int = 300, safety_margin: float = 0.015, start_z: float = 0.08,
                 start_margin: float = 0.01, ceiling_margin: float = 0.018,
                 displacement_threshold: float = 0.3, angle_threshold_deg: float = 45.0, step_len: float = 0.01,
                 rest_steps: int = 20, rest_velocity: float = 1e-3):
        if p is None:
            raise RuntimeError("pybullet is not available")
        self.client = BulletClient(connection_mode=p.DIRECT)
        try:
            import pybullet_data

            self.client.setAdditionalSearchPath(pybullet_data.getDataPath())
        except Exception:
            pass
        self.settle_steps = int(settle_steps)
        self.safety_margin = float(safety_margin)
        self.start_z = float(start_z)
        self.start_margin = float(start_margin)
        self.ceiling_margin = float(ceiling_margin)
        self.displacement_threshold = float(displacement_threshold)
        self.angle_threshold = math.radians(float(angle_threshold_deg))
        self.step_len = float(step_len)
        # the settle stops early once the box has been at rest (linear
        # velocity under rest_velocity, angular under ten times it) for
        # rest_steps consecutive steps: the pose then agrees with the full
        # 300 steps' within 0.8 mm and 0.04 deg on 168 probed placements
        # (B and C scenes), at half the time (median 74-78 steps).  A box
        # that falls never rests, so a settle failure runs its full course.
        # 0 turns it off.
        self.rest_steps = int(rest_steps)
        self.rest_velocity = float(rest_velocity)
        # the shake (check(..., shake=True)): the bench's proxy settings
        self.shake_tilt = 0.3
        self.shake_steps = 60
        self.shake_settle_steps = 120
        self.shake_max_shift = 0.10
        self.shake_max_angle = 30.0
        self.settle_steps_used = 0
        self._key = None
        self._containers: list[dict] = []   # per container: geometry and body ids
        self._item_ids: list[int] = []
        self.checks = 0
        self.seconds = 0.0

    # -- world -------------------------------------------------------------
    @staticmethod
    def _geometry_key(containers: list) -> tuple:
        key = []
        for c in containers:
            key.append((round(float(c["length"]), 6), round(float(c["width"]), 6), round(float(c["height"]), 6),
                        round(float(c["thickness"]), 6), round(float(c.get("buffer", 0.0)), 6),
                        round(float(c.get("cut_x", 0.3)), 6), round(float(c.get("cut_y", 0.3)), 6),
                        bool(c.get("shelf", c.get("require_shelf", False))),
                        tuple(round(float(v), 6) for v in c.get("center", (0.0, 0.0, 0.0)))))
        return tuple(key)

    def _build_world(self, containers: list) -> None:
        client = self.client
        client.resetSimulation()
        client.setPhysicsEngineParameter(deterministicOverlappingPairs=1)
        client.setGravity(0, 0, -9.8)
        try:
            client.loadURDF("plane.urdf")
        except Exception:
            pass
        self._containers = []
        self._item_ids = []
        for c in containers:
            length, width, height = float(c["length"]), float(c["width"]), float(c["height"])
            thickness = float(c["thickness"])
            cut_x, cut_y = float(c.get("cut_x", 0.3)), float(c.get("cut_y", 0.3))
            shelf = bool(c.get("shelf", c.get("require_shelf", False)))
            # the observation carries no buffer, but the centre's z is
            # height / 2 + buffer, so it is there to read
            center = c.get("center")
            if center is not None:
                center = tuple(float(v) for v in center)
                buffer = float(c.get("buffer", center[2] - height / 2.0))
            else:
                buffer = float(c.get("buffer", 0.0))
                center = (0.0, 0.0, height / 2.0 + buffer)
            offset_x = float(center[0])
            orn = p.getQuaternionFromEuler([math.pi / 2, 0, 0])
            with tempfile.TemporaryDirectory() as tmp:
                fname = os.path.join(tmp, "container.obj")
                write_open_cut_corner_cup_obj(fname, width=length, height=height, cut_x=cut_x, cut_y=cut_y,
                                              depth=width, wall=thickness, bottom=thickness)
                body = self._mesh_body(fname, center, orn)
                top = os.path.join(tmp, "top.obj")
                write_corner_lid_obj(top, width=length, height=height, cut_x=cut_x, cut_y=cut_y,
                                     depth=width, lid_thickness=thickness)
                self._mesh_body(top, center, orn)
            entry = {"offset_x": offset_x, "length": length, "width": width, "height": height,
                     "thickness": thickness, "buffer": buffer, "cut_x": cut_x, "shelf": shelf,
                     "body": body, "shelf_id": None, "small_shelf_id": None, "item_ids": []}
            shelf_z = height / 2.0 + thickness / 2.0 + buffer
            if shelf:
                entry["shelf_id"] = self._box_body(
                    (offset_x + 0.0, width / 4.0, shelf_z), orn,
                    [length / 2.0 - thickness / 2.0, thickness / 2.0, width / 4.0 - thickness])
            entry["small_shelf_id"] = self._box_body(
                (offset_x - length / 2.0 + cut_x / 2.0 + thickness, 0.0, shelf_z), orn,
                [cut_x / 2.0, thickness / 2.0, width / 2.0 - thickness])
            self._containers.append(entry)

    def _mesh_body(self, fname: str, pos, orn) -> int:
        client = self.client
        col = client.createCollisionShape(shapeType=p.GEOM_MESH, fileName=fname, meshScale=[1, 1, 1],
                                          flags=p.GEOM_FORCE_CONCAVE_TRIMESH)
        body = client.createMultiBody(baseMass=0, baseCollisionShapeIndex=col, basePosition=pos, baseOrientation=orn)
        client.changeDynamics(body, -1, lateralFriction=0.8, rollingFriction=0.01, spinningFriction=0.01)
        return body

    def _box_body(self, pos, orn, half_ext, mass: float = 0.0) -> int:
        client = self.client
        col = client.createCollisionShape(shapeType=p.GEOM_BOX, halfExtents=half_ext)
        return client.createMultiBody(baseMass=mass, baseCollisionShapeIndex=col, basePosition=pos, baseOrientation=orn)

    def sync(self, containers: list) -> None:
        """Make the world the observation's: the containers once, the packed
        items at their reported poses every time."""
        key = self._geometry_key(containers)
        if key != self._key:
            self._build_world(containers)
            self._key = key
        client = self.client
        for body in self._item_ids:
            client.removeBody(body)
        self._item_ids = []
        for ci, c in enumerate(containers):
            self._containers[ci]["item_ids"] = []
            for item in c.get("packed_items", []):
                pos = item.get("pos")
                if pos is None:
                    continue
                pos = tuple(float(v) for v in pos)
                # rule-alpha's own boards keep the pose in the container's
                # frame with the offset added; the simulator's are world
                # poses already: both put x in the world frame
                half = [float(item["length"]) / 2.0, float(item["width"]) / 2.0, float(item["height"]) / 2.0]
                orn = _orientation_quaternion(item)
                col = client.createCollisionShape(p.GEOM_BOX, halfExtents=half)
                body = client.createMultiBody(baseMass=float(item.get("mass", 1.0)), baseCollisionShapeIndex=col,
                                              basePosition=pos, baseOrientation=orn)
                client.changeDynamics(body, -1, **_dynamics(item))
                self._item_ids.append(body)
                self._containers[ci]["item_ids"].append(body)
        # let the contacts form as the simulator's world has them
        client.stepSimulation()

    # -- the placement test --------------------------------------------------
    def check(self, container_idx: int, item: dict, local_pos, orientation_idx: int,
              transport: bool = True, settle: bool = True, shake: bool = False) -> dict:
        """The simulator's transport sweep and settle for ``item`` (a pool
        item dict) at ``local_pos`` (the container's frame) with the
        orientation index.  Returns a dict: ``transport_ok``, ``settle_ok``,
        ``displacement``, ``angle_deg``, ``settled_local`` (the pose after
        the settle, container frame), ``drift`` (its distance from the
        target)."""
        import time as _time

        t0 = _time.perf_counter()
        client = self.client
        entry = self._containers[container_idx]
        offset_x = entry["offset_x"]
        lwh = [float(item["length"]), float(item["width"]), float(item["height"])]
        half = get_half_ext(lwh, int(orientation_idx))
        target = (float(local_pos[0]) + offset_x, float(local_pos[1]), float(local_pos[2]))
        orn = p.getQuaternionFromEuler(ORNS[int(orientation_idx)])
        out = {"transport_ok": True, "settle_ok": True, "displacement": 0.0, "angle_deg": 0.0,
               "settled_local": tuple(float(v) for v in local_pos), "drift": 0.0, "drift_xy": 0.0,
               "transport_hit": None}

        # the box, spawned off the sweep's start
        length, width, height = entry["length"], entry["width"], entry["height"]
        thickness, buffer, cut_x = entry["thickness"], entry["buffer"], entry["cut_x"]
        x_min = -length / 2.0 + thickness + cut_x + half[0] + self.start_margin
        x_max = length / 2.0 - thickness - half[0] - self.start_margin
        rel_x = min(max(float(local_pos[0]), x_min), x_max)
        effective_start_z = self.start_z
        bottom_z = target[2] - half[2]
        for r_z in (thickness, height / 2.0 + thickness + buffer):
            if 0 <= (bottom_z - r_z) <= 0.05:
                effective_start_z = 0.0
                break
        top_z = target[2] + half[2]
        if effective_start_z > 0.0:
            for c_z in (height / 2.0 + buffer, height + buffer - thickness):
                clearance = c_z - top_z
                if 0 <= clearance < (effective_start_z + self.ceiling_margin):
                    effective_start_z = max(0.0, clearance - self.ceiling_margin - 0.0005)
                    break
        rel_z = min(height + buffer - thickness - half[2] - self.start_margin, float(local_pos[2]) + effective_start_z)
        start = (rel_x + offset_x, -width / 2.0, rel_z)

        # the simulator spawns with the original extents and the orientation
        # as a quaternion, so the collision box is the unrotated l, w, h
        col = client.createCollisionShape(p.GEOM_BOX, halfExtents=[lwh[0] / 2.0, lwh[1] / 2.0, lwh[2] / 2.0])
        body = client.createMultiBody(baseMass=float(item.get("mass", 1.0)), baseCollisionShapeIndex=col,
                                      basePosition=start, baseOrientation=orn)
        client.changeDynamics(body, -1, **_dynamics(item))
        state = client.saveState()
        try:
            if transport:
                # the simulator sweeps against this container's packed items,
                # its shelf (when it has one) and the small shelf; the walls
                # are not in the sweep, only in the settle
                obstacles = list(entry.get("item_ids", []))
                if entry["shelf_id"] is not None:
                    obstacles.append(entry["shelf_id"])
                obstacles.append(entry["small_shelf_id"])
                ok, current, hit = self._move(body, orn, start, (start[0], target[1], start[2]), obstacles)
                if ok:
                    ok, current, hit = self._move(body, orn, current, (target[0], target[1], start[2]), obstacles)
                out["transport_ok"] = bool(ok)
                out["transport_hit"] = hit
                client.restoreState(stateId=state)
            if settle and out["transport_ok"]:
                client.resetBasePositionAndOrientation(body, target, orn)
                rest = 0
                v_lin = self.rest_velocity
                v_ang = self.rest_velocity * 10.0
                used = 0
                for _ in range(self.settle_steps):
                    client.stepSimulation()
                    used += 1
                    if self.rest_steps > 0:
                        lin, ang = client.getBaseVelocity(body)
                        if (abs(lin[0]) < v_lin and abs(lin[1]) < v_lin and abs(lin[2]) < v_lin
                                and abs(ang[0]) < v_ang and abs(ang[1]) < v_ang and abs(ang[2]) < v_ang):
                            rest += 1
                            if rest >= self.rest_steps:
                                break
                        else:
                            rest = 0
                self.settle_steps_used = used
                out["settle_steps"] = used
                final_pos, final_orn = client.getBasePositionAndOrientation(body)
                displacement = float(np.linalg.norm(np.asarray(final_pos) - np.asarray(target)))
                dot = min(1.0, abs(sum(a * b for a, b in zip(orn, final_orn))))
                angle = 2.0 * math.acos(dot)
                out["displacement"] = displacement
                out["angle_deg"] = math.degrees(angle)
                out["settle_ok"] = not (displacement > self.displacement_threshold or angle > self.angle_threshold)
                out["settled_local"] = (float(final_pos[0]) - offset_x, float(final_pos[1]), float(final_pos[2]))
                out["drift"] = displacement
                # the drop from the lifted target to the surface is expected
                # (2-5 cm on the ladder's poses); a slide is not
                out["drift_xy"] = float(math.hypot(final_pos[0] - target[0], final_pos[1] - target[1]))
                if shake and out["settle_ok"]:
                    out["shake"] = self._shake(body, final_pos, final_orn)
                client.restoreState(stateId=state)
        finally:
            client.removeState(state)
            client.removeBody(body)
        self.checks += 1
        self.seconds += _time.perf_counter() - t0
        return out

    def _shake(self, body: int, pos, orn) -> dict:
        """The bench's stability proxy on the settled load with the new
        box in it: gravity tilted by ``shake_tilt`` of g in four directions
        for ``shake_steps`` steps each, then a settle; what moved by more
        than ``shake_max_shift`` or tipped by more than ``shake_max_angle``
        -- the new box or any packed one -- fails it.  The official test
        is undisclosed; this is the bench's stand-in, so a pass is no
        promise, but a fail is a box that falls over under a small
        lateral acceleration."""
        client = self.client
        g = 9.8
        lateral = self.shake_tilt * g
        bodies = [body] + list(self._item_ids)
        before = {b: client.getBasePositionAndOrientation(b) for b in bodies}
        try:
            for gravity in ((lateral, 0, -g), (-lateral, 0, -g), (0, lateral, -g), (0, -lateral, -g)):
                client.setGravity(*gravity)
                for _ in range(self.shake_steps):
                    client.stepSimulation()
            client.setGravity(0, 0, -g)
            for _ in range(self.shake_settle_steps):
                client.stepSimulation()
            worst_shift, worst_angle, moved = 0.0, 0.0, []
            for b in bodies:
                p0, o0 = before[b]
                p1, o1 = client.getBasePositionAndOrientation(b)
                shift = float(np.linalg.norm(np.asarray(p1) - np.asarray(p0)))
                dot = min(1.0, abs(sum(a * c for a, c in zip(o0, o1))))
                angle = math.degrees(2.0 * math.acos(dot))
                worst_shift = max(worst_shift, shift)
                worst_angle = max(worst_angle, angle)
                # hard boxes slide on each other by 5-10 cm under the tilt
                # (box-on-box friction 0.4 x 0.4 against the 0.3 g), as
                # they do in the bench's proxy, so a slide counts for the
                # new box only; a tip counts for every box
                if angle > self.shake_max_angle or (b == body and shift > self.shake_max_shift):
                    moved.append(int(b))
        finally:
            client.setGravity(0, 0, -g)
        return {"ok": not moved, "max_shift": worst_shift, "max_angle_deg": worst_angle,
                "moved": moved, "new_box_moved": int(body) in moved}

    def _move(self, body: int, orn, start, target, obstacles) -> tuple[bool, tuple, dict | None]:
        """The simulator's ``_move_item``: the box is warped along the
        segment in ``step_len`` steps and every step is tested against the
        obstacles within ``safety_margin``.  Returns (ok, last position,
        the first hit as {"body", "at", "distance"} or None)."""
        client = self.client
        steps = max(math.ceil(max(abs(target[0] - start[0]), abs(target[1] - start[1]), abs(target[2] - start[2])) / self.step_len), 1)
        current = start
        for i in range(steps + 1):
            frac = i / steps
            current = (start[0] + (target[0] - start[0]) * frac,
                       start[1] + (target[1] - start[1]) * frac,
                       start[2] + (target[2] - start[2]) * frac)
            client.resetBasePositionAndOrientation(body, current, orn)
            client.performCollisionDetection()
            for other in obstacles:
                pts = client.getClosestPoints(bodyA=body, bodyB=other, distance=self.safety_margin)
                if pts:
                    return False, current, {"body": int(other), "at": tuple(round(float(v), 4) for v in current),
                                            "distance": round(float(min(pt[8] for pt in pts)), 5)}
        return True, current, None
