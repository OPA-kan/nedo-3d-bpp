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
    _torch_batch,
    build_arrays,
    candidate_token,
    load_allocator_ensemble,
    predict_allocator,
    predict_preference,
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
        self.objective = str(self.metadata.get("objective") or "allocator")
        if self.objective not in {"allocator", "preference"}:
            raise ValueError(f"unsupported objective: {self.objective}")
        self.switch_threshold = float(
            self.metadata.get("switch_threshold") or 0.5
        )

    def build_example(
        self, snapshot: dict[str, Any],
        root_candidates: list[dict[str, Any]], *, incumbent_id: str,
    ) -> dict[str, Any] | None:
        """Build the live training-format example, or None to fail safe."""
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
            return None
        if self.objective == "preference" and incumbent_id not in candidate_ids:
            # preference deltas are meaningless without the incumbent in
            # the scored set; fail safe (runner keeps the incumbent)
            return None
        incumbent_index = (
            candidate_ids.index(incumbent_id)
            if incumbent_id in candidate_ids else 0
        )
        return {
            "group": "live",
            "root_id": "live",
            "container": state["container_values"],
            "packed_item": state["packed_item_values"],
            "visible_item": state["visible_item_values"],
            "candidate": tokens,
            "candidate_ids": candidate_ids,
            "incumbent_index": incumbent_index,
            "selected_index": 0,
            "label": 0.0,
        }

    def score_candidates(
        self, snapshot: dict[str, Any],
        root_candidates: list[dict[str, Any]], *, incumbent_id: str,
    ) -> dict[str, float]:
        """Return {candidate_id: probability} over the safe candidates."""
        example = self.build_example(
            snapshot, root_candidates, incumbent_id=incumbent_id,
        )
        if example is None:
            return {}
        candidate_ids = example["candidate_ids"]
        if self.objective == "preference":
            # sigmoid(score_j - score_incumbent): the incumbent's own
            # entry is exactly 0.5; raising it to the switch threshold
            # makes the runner's argmax implement "keep the incumbent
            # unless an alternate clearly beats it"
            probabilities = predict_preference(
                self._torch, self.members, [example]
            )[0]
            scores = dict(zip(candidate_ids, probabilities))
            scores[incumbent_id] = max(
                self.switch_threshold, scores[incumbent_id]
            )
            return scores
        scores = predict_allocator(self._torch, self.members, [example])[0]
        return dict(zip(candidate_ids, scores))


class OnlineAdapterPolicy(LearnedAllocatorPolicy):
    """Frozen champion body + per-episode preference-head adapter.

    theta (the loaded ensemble) is never modified; phi is a per-member
    delta on the final linear scoring head, starts at zero, and lives
    only as long as this object (one episode).  Updates come only from
    strict-dominance A/B fork outcomes, as one-to-few pairwise-logistic
    SGD steps under a hard trust region — online preference
    calibration, not online RL.
    """

    def __init__(
        self, model_dir: pathlib.Path, *, learning_rate: float = 0.05,
        update_steps: int = 2, trust_radius: float = 1.0,
    ):
        super().__init__(model_dir)
        if self.objective != "preference":
            raise ValueError(
                "online adapter requires a preference-objective ensemble"
            )
        torch = self._torch
        self.learning_rate = float(learning_rate)
        self.update_steps = int(update_steps)
        self.trust_radius = float(trust_radius)
        self.updates_applied = 0
        self._adapters = []
        for model, _stats in self.members:
            head = model.score[2]
            self._adapters.append((
                torch.zeros(int(head.in_features), requires_grad=True),
                torch.zeros(1, requires_grad=True),
            ))

    def _member_logits(self, member_index: int, example: dict[str, Any]):
        """Frozen base logits and penultimate activations (no grad)."""
        import numpy as np

        torch = self._torch
        model, stats = self.members[member_index]
        arrays = build_arrays([example], stats)
        batch = _torch_batch(torch, arrays, np.arange(1))
        captured: dict[str, Any] = {}
        handle = model.score[2].register_forward_hook(
            lambda _module, inputs, _output: captured.__setitem__(
                "z", inputs[0]
            )
        )
        try:
            with torch.no_grad():
                logits = model(batch)
        finally:
            handle.remove()
        return logits[0], captured["z"][0]

    def _adapted_deltas(self, example: dict[str, Any]):
        """Per-member adapted (logit - incumbent logit); phi carries grad."""
        incumbent = int(example["incumbent_index"])
        deltas = []
        for index in range(len(self.members)):
            base, activations = self._member_logits(index, example)
            weight, bias = self._adapters[index]
            adapted = base + activations @ weight + bias
            deltas.append(adapted - adapted[incumbent])
        return deltas

    def _pair_probability(
        self, example: dict[str, Any], candidate_index: int,
    ) -> float:
        torch = self._torch
        with torch.no_grad():
            return float(torch.stack([
                torch.sigmoid(delta[candidate_index])
                for delta in self._adapted_deltas(example)
            ]).mean())

    def adapter_norms(self) -> list[float]:
        torch = self._torch
        with torch.no_grad():
            return [
                float(torch.sqrt(
                    weight.pow(2).sum() + bias.pow(2).sum()
                ))
                for weight, bias in self._adapters
            ]

    def score_candidates(
        self, snapshot: dict[str, Any],
        root_candidates: list[dict[str, Any]], *, incumbent_id: str,
    ) -> dict[str, float]:
        example = self.build_example(
            snapshot, root_candidates, incumbent_id=incumbent_id,
        )
        if example is None:
            return {}
        torch = self._torch
        with torch.no_grad():
            probabilities = torch.stack([
                torch.sigmoid(delta)
                for delta in self._adapted_deltas(example)
            ]).mean(dim=0)
        scores = dict(zip(
            example["candidate_ids"], map(float, probabilities)
        ))
        scores[incumbent_id] = max(
            self.switch_threshold, scores[incumbent_id]
        )
        return scores

    def update_from_fork(
        self, snapshot: dict[str, Any],
        root_candidates: list[dict[str, Any]], *, incumbent_id: str,
        alternate_id: str, alternate_wins: bool,
    ) -> dict[str, Any] | None:
        """SGD on phi from one strict-dominance fork verdict, or None."""
        example = self.build_example(
            snapshot, root_candidates, incumbent_id=incumbent_id,
        )
        if example is None:
            return None
        return self.update_from_example(
            example, alternate_id=alternate_id,
            alternate_wins=alternate_wins,
        )

    def update_from_example(
        self, example: dict[str, Any], *, alternate_id: str,
        alternate_wins: bool,
    ) -> dict[str, Any] | None:
        """Apply one verified pair already encoded in training format."""
        torch = self._torch
        if alternate_id not in example["candidate_ids"]:
            return None
        index = example["candidate_ids"].index(alternate_id)
        target = torch.tensor(1.0 if alternate_wins else 0.0)
        before = self._pair_probability(example, index)
        parameters = [
            parameter for pair in self._adapters for parameter in pair
        ]
        for _ in range(self.update_steps):
            loss = sum(
                torch.nn.functional.binary_cross_entropy_with_logits(
                    delta[index], target
                )
                for delta in self._adapted_deltas(example)
            ) / len(self.members)
            gradients = torch.autograd.grad(loss, parameters)
            with torch.no_grad():
                flat = iter(gradients)
                for weight, bias in self._adapters:
                    weight -= self.learning_rate * next(flat)
                    bias -= self.learning_rate * next(flat)
                    norm = torch.sqrt(
                        weight.pow(2).sum() + bias.pow(2).sum()
                    )
                    if float(norm) > self.trust_radius:
                        scale = self.trust_radius / float(norm)
                        weight *= scale
                        bias *= scale
        after = self._pair_probability(example, index)
        self.updates_applied += 1
        return {
            "alternate_probability_before": before,
            "alternate_probability_after": after,
            "alternate_wins": bool(alternate_wins),
            "update_steps": self.update_steps,
            "learning_rate": self.learning_rate,
            "trust_radius": self.trust_radius,
            "adapter_norms": self.adapter_norms(),
        }

    def materialize(
        self, output_dir: pathlib.Path, *, memory: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge phi into a load-compatible frozen preference ensemble.

        The source model files and in-memory theta remain untouched.  The
        returned artifact can be loaded by ``LearnedAllocatorPolicy`` and is
        therefore suitable for a later frozen league challenge that isolates
        carried memory from race-time fork authority.
        """
        output_dir = pathlib.Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        metadata = json.loads(json.dumps(self.metadata))
        for index, ((model, _stats), (weight, bias)) in enumerate(zip(
            self.members, self._adapters
        )):
            state = {
                key: value.detach().clone()
                for key, value in model.state_dict().items()
            }
            state["score.2.weight"] += weight.detach().unsqueeze(0)
            state["score.2.bias"] += bias.detach()
            weights_name = str(metadata["members"][index]["weights"])
            self._torch.save(state, output_dir / weights_name)
        metadata["memory"] = {
            "contract": "persistent_preference_head_memory_v1",
            "updates_applied": int(self.updates_applied),
            "adapter_norms": self.adapter_norms(),
            **memory,
        }
        (output_dir / "model.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return metadata
