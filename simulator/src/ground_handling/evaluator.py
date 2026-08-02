import pybullet as p
import numpy as np
import math
import os
from pybullet_utils.bullet_client import BulletClient
from .containers import Container
from .items import Item
from .diagnostics import (
    calculate_attribute_placement,
    calculate_settled_metrics,
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
        return metrics
