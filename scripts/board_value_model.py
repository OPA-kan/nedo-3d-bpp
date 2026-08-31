"""Load a fitted board value and speak the teacher's units.

`scripts/train_board_value.py` fits V_theta(s) to the volume a behaviour
policy goes on to place, in cubic metres. The teacher's dominance vector
carries `fill_gain`, which is a delta of `fill_score_proxy` -- a
percentage of container volume. Composing the two needs that conversion
made explicitly and once, here, rather than at each call site:

    fill_gain contribution = 100 * V_theta(s) / total container volume

The prediction is offered in the shape `compose_leaf_value` already
consumes (`{"fill_return": {"mean": ...}}`), so the n-step composition

    V(s_t) ~= measured prefix delta + gamma^n * V_theta(s_{t+n})

reuses the path built for the value shadow rather than a second one.

Only fill is predicted, but the other heads must still be *supplied as
zero* rather than omitted. `compose_leaf_value` sets any component whose
suffix it cannot find to **None**, not to the prefix value -- and a
vector with a None head fails `_oriented`, drops out of
`terminal_eligible_candidates`, and yields no verdict at all. Omitting
them does not mean "no further violations"; it means "no comparison".
That is a silent, total loss of teaching signal, so every head is
emitted explicitly here.

Zero for the violation heads is an assumption -- that nothing goes wrong
after the cap -- and it is the same one the pinned zero already made.
It is written where it can be seen and challenged.
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

CONTRACT = "board_value_model_v1"


class BoardValue:
    """V_theta(s) -> remaining placed volume, and its fill equivalent."""

    def __init__(self, model_dir: pathlib.Path):
        import torch

        from scripts.train_board_value import ValueHead

        model_dir = pathlib.Path(model_dir)
        self.metadata = json.loads(
            (model_dir / "model.json").read_text(encoding="utf-8")
        )
        if self.metadata.get("contract") != CONTRACT:
            raise ValueError(
                f"unsupported board value contract:"
                f" {self.metadata.get('contract')!r}"
            )
        self.names = list(self.metadata["feature_names"])
        self.mean = np.asarray(self.metadata["feature_mean"], dtype=np.float32)
        self.std = np.asarray(self.metadata["feature_std"], dtype=np.float32)
        self.model = ValueHead(
            len(self.names), hidden=int(self.metadata.get("hidden", 64))
        )
        self.model.load_state_dict(
            torch.load(model_dir / "value.pt", map_location="cpu")
        )
        self.model.eval()
        self.torch = torch
        self.calls = 0

    def volume(self, observation: dict[str, Any]) -> float:
        """Predicted remaining placed volume, in cubic metres."""
        from scripts.probe_value_rankability import board_features

        features = board_features(observation)
        row = np.asarray(
            [[float(features.get(n, 0.0)) for n in self.names]],
            dtype=np.float32,
        )
        row = (row - self.mean) / self.std
        with self.torch.no_grad():
            value = float(self.model(self.torch.from_numpy(row)).item())
        self.calls += 1
        # A negative remaining volume is not a board state; clamp rather
        # than let a regression artefact subtract from a measured prefix.
        return max(value, 0.0)

    def fill_return(self, observation: dict[str, Any]) -> dict[str, Any]:
        """The prediction in the shape compose_leaf_value consumes.

        Every suffix that function knows about is emitted, because one it
        cannot find becomes None and a None head silently voids the whole
        comparison.
        """
        from scripts.run_vector_mcts import LEAF_SUFFIX_TO_COMPONENT

        total = container_volume(observation)
        volume = self.volume(observation)
        prediction = {
            suffix: {"mean": 0.0} for suffix in LEAF_SUFFIX_TO_COMPONENT
        }
        prediction["fill_return"] = {
            "mean": (100.0 * volume / total) if total > 0 else 0.0,
            "predicted_volume": volume,
            "container_volume": total,
        }
        return prediction


def container_volume(observation: dict[str, Any]) -> float:
    """Denominator of fill_score_proxy: total container volume."""
    total = 0.0
    for container in observation.get("container_list") or []:
        declared = container.get("volume")
        if isinstance(declared, (int, float)) and declared > 0:
            total += float(declared)
            continue
        total += (
            float(container.get("length", 0.0) or 0.0)
            * float(container.get("width", 0.0) or 0.0)
            * float(container.get("height", 0.0) or 0.0)
        )
    return total
