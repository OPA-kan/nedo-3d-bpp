"""Score live root candidates with a frozen distilled allocator ensemble.

This is the runtime half of the pi_1 distillation: the ensemble saved by
``train_rollout_trigger.py --save-model-dir`` is loaded once per episode
and asked, at each live decision, to rank the physically safe root
candidates from the current snapshot alone.  It never sees terminal
rollouts, never predicts values, and its choice is executed directly —
so its quality is measured only by the league gate on executed episodes.
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_replay_dataset import json_safe  # noqa: E402
from scripts.counterfactual_graph import (  # noqa: E402
    ITEM_TENSOR_FEATURES,
    state_tensor_from_snapshot,
)
from scripts.train_rollout_trigger import (  # noqa: E402
    candidate_token,
    load_allocator_ensemble,
    predict_allocator,
)


class LearnedAllocatorPolicy:
    """Frozen ensemble that maps (snapshot, safe candidates) to scores."""

    def __init__(self, model_dir: pathlib.Path):
        import torch

        torch.set_num_threads(4)
        self._torch = torch
        self.members, self.metadata = load_allocator_ensemble(
            torch, pathlib.Path(model_dir)
        )
        self.feature_mode = str(
            (self.metadata.get("feature_contract") or {}).get(
                "candidate_feature_mode"
            )
        )
        if self.feature_mode not in {"h1", "geometry"}:
            raise ValueError(
                f"unsupported candidate feature mode: {self.feature_mode}"
            )

    def score_candidates(
        self, snapshot: dict[str, Any],
        root_candidates: list[dict[str, Any]], *, incumbent_id: str,
    ) -> dict[str, float]:
        """Return {candidate_id: probability} over the safe candidates."""
        # replicate the training-time input exactly: examples were built
        # from json round-tripped snapshots on disk
        snapshot = json.loads(json.dumps(json_safe(snapshot)))
        state = state_tensor_from_snapshot(snapshot)
        visible_items = dict(zip(
            state["visible_item_indices"], state["visible_item_values"]
        ))
        tokens = []
        candidate_ids = []
        for row in root_candidates:
            if not row.get("safe"):
                continue
            item_values = visible_items.get(
                int(row.get("stable_item_index", -1)),
                [0.0] * len(ITEM_TENSOR_FEATURES),
            )
            token = candidate_token(
                self.feature_mode, snapshot, row, list(item_values),
                incumbent=str(row.get("root_candidate_id")) == incumbent_id,
            )
            if token is None:
                continue
            tokens.append(token)
            candidate_ids.append(str(row["root_candidate_id"]))
        if not tokens:
            return {}
        example = {
            "group": "live",
            "root_id": "live",
            "container": state["container_values"],
            "packed_item": state["packed_item_values"],
            "visible_item": state["visible_item_values"],
            "candidate": tokens,
            "candidate_ids": candidate_ids,
            "incumbent_index": 0,
            "selected_index": 0,
            "label": 0.0,
        }
        scores = predict_allocator(self._torch, self.members, [example])[0]
        return dict(zip(candidate_ids, scores))
