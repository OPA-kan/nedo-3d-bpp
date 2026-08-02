import pybullet as p
import numpy as np
import math
import os
from pybullet_utils.bullet_client import BulletClient
from .containers import Container
from .items import Item
from .diagnostics import (
    calculate_attribute_placement,
    calculate_center_of_gravity,
    calculate_settled_metrics,
    shake_response_metrics,
)


class Evaluator:
    """
    コンテナ内の積載状態を計算する評価モジュール
    """
    def __init__(self, client: BulletClient, config: dict):
        self.client = client
        self.config = config
        self.inclusion_margin: float = config.get('inclusion_margin', 0.01)


    def calculate_fill_rate(self, containers: list[Container]) -> tuple[float, list[Item]]:
        """
        充填率の計算. コンテナ内に完全に収まっている荷物のみを抽出する
        """
        total_item_volume = 0
        total_container_volume = sum(c.volume for c in containers)
        out_items = []
        for container in containers:
            if not container.packed_items:
                continue

            for item in container.packed_items:
                pos, orn = item.get_pose(self.client)
                if pos is None or orn is None:
                    continue
                rot_mat = np.array(self.client.getMatrixFromQuaternion(orn)).reshape(3,3)
                hl, hw, hh = item.length/2, item.width/2, item.height/2
                local_corners = np.array([
                    [hl, hw, hh],
                    [hl, hw, -hh],
                    [hl, -hw, hh],
                    [hl, -hw, -hh],
                    [-hl, hw, hh],
                    [-hl, hw, -hh],
                    [-hl, -hw, hh],
                    [-hl, -hw, -hh]
                ])
                global_corners = np.dot(local_corners, rot_mat.T) + np.array(pos)
                is_inside = True
                n_vecs = np.array(container.n_vecs)
                points = np.array(container.points)
                for corner in global_corners:
                    # コーナーから各平面の点へのベクトル
                    vecs = corner - points
                    # 法線ベクトルとの内積を計算
                    dots = np.sum(n_vecs * vecs, axis=1)
                    if np.any(dots > self.inclusion_margin):
                        is_inside = False
                        print(f'item {item.index} not inside (hit boundary plane), {dots}')
                        out_items.append(item)
                        break
                
                # 全ての条件を満たした(完全に収まっている)荷物だけを体積に加算
                if is_inside:
                    total_item_volume += item.volume


        if total_item_volume==0:
            return 0, out_items

        fill_score = min(100*total_item_volume / total_container_volume, 100)

        return fill_score, out_items


    def evaluate(self, containers: list[Container], total_items: int) -> dict[str, float]:
        """現在のコンテナの評価を辞書形式で返す"""
        num_packed_items = sum(len(c.packed_items) for c in containers)
        packed_items_percent = num_packed_items / total_items
        fill_score, out_items = self.calculate_fill_rate(containers)

        report = {
            "fill_score": fill_score,
            "num_placed_items": packed_items_percent
        }

        return report


    def settled_snapshot(
        self,
        containers: list[Container],
        grid_size: float = 0.02,
    ) -> dict:
        """Collect diagnostic metrics from the settled PyBullet state."""
        snapshots = []
        for container in containers:
            packed_items = []
            for item in container.packed_items:
                if item.pybullet_id is None:
                    continue
                pos, _ = item.get_pose(self.client)
                if pos is None:
                    continue
                aabb_min, aabb_max = self.client.getAABB(item.pybullet_id)
                packed_items.append(
                    {
                        "index": int(item.index),
                        "mass": float(item.mass),
                        "volume": float(item.volume),
                        "pos": [float(value) for value in pos],
                        "aabb_min": [float(value) for value in aabb_min],
                        "aabb_max": [float(value) for value in aabb_max],
                        "is_soft": bool(item.is_soft),
                        "is_prioritized": bool(item.is_prioritized),
                    }
                )
            snapshots.append(
                {
                    "index": int(container.index),
                    "offset_x": float(container.offset_x),
                    "length": float(container.length),
                    "width": float(container.width),
                    "height": float(container.height),
                    "thickness": float(container.thickness),
                    "buffer": float(container.buffer),
                    "cut_x": float(container.cut_x),
                    "require_shelf": bool(container.require_shelf),
                    "is_prioritized": bool(container.is_prioritized),
                    "volume": float(container.volume),
                    "packed_items": packed_items,
                }
            )
        metrics = calculate_settled_metrics(snapshots, grid_size=grid_size)
        # placement_score and soft_item_score are computed only on the
        # evaluation platform. These are the published rules behind them,
        # as violation counts rather than a score -- see
        # calculate_attribute_placement for what that does and does not buy.
        metrics.update(calculate_attribute_placement(snapshots))
        # cog_score has no published procedure, only a direction, so the
        # raw centre travels with its handling contract in com_contract.
        metrics.update(calculate_center_of_gravity(snapshots))
        return metrics


    # --- Local stability proxy: the shake the rules describe ---
    #
    # docs/COMPETITION_RULES.md:70 says stability_score comes from closing
    # the lid and VARYING GRAVITY, scored on displacement from the initial
    # position, force on each item, and kinetic energy. The magnitudes,
    # durations and thresholds are undisclosed, so this is a proxy, not the
    # official number -- see shake_response_metrics for the contract.
    #
    # The schedule is fixed and deterministic on purpose: a stability
    # measurement that varies run to run cannot separate two arms, and this
    # project has already lost two experiments to wall-clock nondeterminism.
    #
    # Known deviation, stated rather than hidden: no lid is added. Building
    # one would need the container's opening geometry and would change what
    # the test measures if it were placed wrongly. Without it an item near
    # the top can leave through the opening; that is counted as lost, and
    # lost items are charged as both a shift and a topple rather than
    # dropped from the averages.
    SHAKE_TILT_FRACTION = 0.3
    SHAKE_STEPS_PER_PHASE = 60
    SHAKE_SETTLE_STEPS = 120
    SHAKE_BASE_GRAVITY = 9.8

    def _live_poses(self, containers: list[Container]) -> list[dict]:
        poses = []
        for container in containers:
            for item in container.packed_items:
                if item.pybullet_id is None:
                    continue
                pos, orn = item.get_pose(self.client)
                if pos is None:
                    continue
                poses.append(
                    {
                        "index": int(item.index),
                        "mass": float(item.mass),
                        "pybullet_id": item.pybullet_id,
                        "pos": [float(value) for value in pos],
                        "orn": [float(value) for value in orn],
                    }
                )
        return poses

    def _kinetic_energy(self, poses: list[dict]) -> float:
        total = 0.0
        for entry in poses:
            linear, angular = self.client.getBaseVelocity(
                entry["pybullet_id"]
            )
            speed_squared = sum(float(v) ** 2 for v in linear)
            spin_squared = sum(float(v) ** 2 for v in angular)
            total += 0.5 * entry["mass"] * (speed_squared + spin_squared)
        return total

    def shake_test(self, containers: list[Container]) -> dict:
        """Vary gravity over the settled state and report what moved.

        The simulation state is saved and restored, so this leaves the
        episode exactly as it found it and is safe to call at any point.
        """
        before = self._live_poses(containers)
        if not before:
            return shake_response_metrics([], [], 0.0)

        g = self.SHAKE_BASE_GRAVITY
        lateral = self.SHAKE_TILT_FRACTION * g
        schedule = [
            (lateral, 0.0, -g),
            (-lateral, 0.0, -g),
            (0.0, lateral, -g),
            (0.0, -lateral, -g),
        ]

        state_id = self.client.saveState()
        peak_energy = 0.0
        try:
            for gravity in schedule:
                self.client.setGravity(*gravity)
                for _ in range(self.SHAKE_STEPS_PER_PHASE):
                    self.client.stepSimulation()
                    peak_energy = max(
                        peak_energy, self._kinetic_energy(before)
                    )
            self.client.setGravity(0.0, 0.0, -g)
            for _ in range(self.SHAKE_SETTLE_STEPS):
                self.client.stepSimulation()
            after = self._live_poses(containers)
        finally:
            self.client.setGravity(0.0, 0.0, -g)
            self.client.restoreState(stateId=state_id)
            self.client.removeState(state_id)

        return shake_response_metrics(before, after, peak_energy)
