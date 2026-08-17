import importlib.util
import json
import math
import pathlib
import sys
import unittest
from unittest import mock

import numpy as np

AGENT_PATH = pathlib.Path(__file__).parents[1] / "agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location(
    "safety_rerank_agent", AGENT_PATH
)
agent = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = agent
SPEC.loader.exec_module(agent)


class _FakeDecision:
    def __init__(self, item, pos, score, orientation=0):
        self.action = {
            "item_idx": item,
            "container_idx": 0,
            "place_pos": list(pos),
            "orientation": orientation,
        }
        self.score = score
        self.candidate = object()


def _rerank(logits, decisions, incumbent, extra_pool=None):
    """Run safety_rerank_record with the scorer mocked out.

    logits[0] is the incumbent's own score; the rest are consumed by
    the deduplicated pool in rank order (only when triggered).
    """
    with mock.patch.object(
        agent, "safety_shadow_logit", side_effect=list(logits)
    ):
        return agent.safety_rerank_record(
            {}, decisions, incumbent, extra_pool=extra_pool
        )


class SafetyRerankRecordTests(unittest.TestCase):
    def test_above_trigger_never_scores_the_pool(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        other = _FakeDecision(1, (1, 0, 0), 4.9)
        # Only ONE logit provided: an untriggered record must not score
        # the pool at all (the lazy-compute contract).
        record, proposed = _rerank([3.5], [incumbent, other], incumbent)
        self.assertFalse(record["triggered"])
        self.assertFalse(record["would_swap"])
        self.assertIsNone(record["pool_size"])
        self.assertIsNone(proposed)

    def test_triggered_swap_picks_highest_eligible_logit(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        near = _FakeDecision(1, (1, 0, 0), 4.9)
        far = _FakeDecision(2, (2, 0, 0), 4.8)
        record, proposed = _rerank(
            [-0.5, -0.5, 4.0, 9.0], [incumbent, near, far], incumbent
        )
        self.assertTrue(record["triggered"])
        self.assertTrue(record["would_swap"])
        self.assertEqual(record["proposed_rank"], 2)
        self.assertEqual(record["proposed_logit"], 9.0)
        self.assertIs(proposed, far)

    def test_extra_pool_is_merged_and_deduplicated(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        clone = _FakeDecision(0, (0, 0, 0), 5.0)  # same action key
        deep = _FakeDecision(3, (3, 0, 0), 4.6)
        record, proposed = _rerank(
            [-1.0, -1.0, 8.0],
            [incumbent],
            incumbent,
            extra_pool=[clone, deep],
        )
        self.assertEqual(record["pool_size"], 2)  # incumbent + deep only
        self.assertTrue(record["would_swap"])
        self.assertIs(proposed, deep)

    def test_score_conservation_excludes_expensive_swaps(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 10.0)
        cheap = _FakeDecision(1, (1, 0, 0), 8.9)  # loses 1.1 > 1.0 abs
        record, proposed = _rerank(
            [-0.5, -0.5, 9.0], [incumbent, cheap], incumbent
        )
        self.assertTrue(record["triggered"])
        self.assertFalse(record["would_swap"])
        self.assertIsNone(proposed)

    def test_absolute_bound_rescues_near_zero_score_states(self) -> None:
        # The Gate 2 inertness case: incumbent score near zero, safe
        # alternative one score unit below. The relative rule blocked
        # every such rescue; the absolute rule licenses it.
        incumbent = _FakeDecision(0, (0, 0, 0), -0.023)
        rescue = _FakeDecision(1, (1, 0, 0), -0.658)
        record, proposed = _rerank(
            [-2.0, -2.0, 6.2], [incumbent, rescue], incumbent
        )
        self.assertTrue(record["would_swap"])
        self.assertIs(proposed, rescue)

    def test_margin_requires_real_escape(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        # Logit 2.5 clears the trigger but not incumbent+margin (1+2).
        marginal = _FakeDecision(1, (1, 0, 0), 5.0)
        record, proposed = _rerank(
            [1.0, 1.0, 2.5], [incumbent, marginal], incumbent
        )
        self.assertTrue(record["triggered"])
        self.assertFalse(record["would_swap"])

    def test_never_refuses_when_no_alternative_exists(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        record, proposed = _rerank([-3.0, -3.0], [incumbent], incumbent)
        self.assertTrue(record["triggered"])
        self.assertFalse(record["would_swap"])
        self.assertIsNone(proposed)

    def test_recorded_candidates_are_capped(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        pool = [
            _FakeDecision(i + 1, (i + 1, 0, 0), 4.9) for i in range(20)
        ]
        logits = [-3.0, -3.0] + [float(i) for i in range(20)]
        record, _proposed = _rerank(
            logits, [incumbent], incumbent, extra_pool=pool
        )
        self.assertEqual(record["pool_size"], 21)
        self.assertEqual(
            len(record["candidates"]),
            agent.SAFETY_RERANK_RECORDED_CANDIDATES,
        )
        # Highest logits kept, descending.
        logit_list = [c["logit"] for c in record["candidates"]]
        self.assertEqual(logit_list, sorted(logit_list, reverse=True))

    def test_missing_model_returns_none(self) -> None:
        incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        with mock.patch.object(
            agent, "safety_shadow_logit", return_value=None
        ):
            record, proposed = agent.safety_rerank_record(
                {}, [incumbent], incumbent
            )
        self.assertIsNone(record)
        self.assertIsNone(proposed)

    def test_default_mode_is_off_and_constants_are_preregistered(self):
        # The 2026-08-17 guard_quiet adoption deliberately left the rerank
        # machinery off: the guard consumes the observed pool and the
        # calibrated logit directly, without per-step rerank records.
        self.assertEqual(agent.SAFETY_RERANK_MODE, "off")
        self.assertEqual(agent.SAFETY_RERANK_TRIGGER_LOGIT, 2.0)
        self.assertEqual(agent.SAFETY_RERANK_MARGIN_LOGIT, 2.0)
        self.assertEqual(agent.SAFETY_RERANK_MAX_SCORE_LOSS_ABS, 1.0)
        self.assertEqual(agent.SAFETY_RERANK_POOL_CAP, 4096)


ARTIFACT_PATH = (
    pathlib.Path(__file__).parents[1]
    / "reports" / "state-model" / "candidate-mlp-safety-v1.json"
)


def _forward_logit(model, phi_raw, candidate_raw):
    """The exact forward stack safety_shadow_logit applies."""
    x = np.concatenate([
        (phi_raw - model["phi_mean"]) / model["phi_scale"],
        (candidate_raw - model["cand_mean"]) / model["cand_scale"],
    ])
    for layer in model["layers"]:
        if layer["kind"] == "linear":
            x = layer["weight"] @ x + layer["bias"]
        elif layer["kind"] == "gelu":
            x = np.asarray([
                0.5 * value * (1.0 + math.erf(value / math.sqrt(2.0)))
                for value in x
            ])
    return float(x[0])


class EmbeddedSafetyModelTests(unittest.TestCase):
    """The 2026-08-17 adoption contract: with no environment at all, the
    quiet guard's instrument loads from the embedded artifact and scores
    identically to the committed JSON file."""

    def _load(self, path_value):
        with mock.patch.object(
            agent, "SAFETY_RERANK_SHADOW", path_value
        ), mock.patch.dict(
            agent._SAFETY_SHADOW_CACHE, {"path": None, "model": None}
        ):
            return agent._safety_shadow_model()

    def test_empty_path_loads_the_embedded_model(self):
        model = self._load("")
        self.assertIsNotNone(model)
        self.assertTrue(model["phi_features"])

    def test_embedded_json_round_trips_the_committed_artifact(self):
        embedded = json.loads(agent._EMBEDDED_SAFETY_MODEL_JSON)
        committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(embedded, committed)

    def test_embedded_model_scores_a_known_input_like_the_file(self):
        embedded = self._load("")
        from_file = self._load(str(ARTIFACT_PATH))
        self.assertIsNotNone(embedded)
        self.assertIsNotNone(from_file)
        self.assertEqual(
            embedded["phi_features"], from_file["phi_features"]
        )
        rng = np.random.default_rng(20260817)
        phi_raw = rng.normal(
            size=embedded["phi_mean"].shape[0]
        ) * embedded["phi_scale"] + embedded["phi_mean"]
        candidate_raw = rng.normal(
            size=embedded["cand_mean"].shape[0]
        ) * embedded["cand_scale"] + embedded["cand_mean"]
        logit_embedded = _forward_logit(embedded, phi_raw, candidate_raw)
        logit_file = _forward_logit(from_file, phi_raw, candidate_raw)
        self.assertEqual(logit_embedded, logit_file)

    def test_set_path_still_overrides_the_embedded_copy(self):
        # Instrument replay compatibility: an explicit artifact path wins.
        bogus = self._load(str(ARTIFACT_PATH) + ".does-not-exist")
        self.assertIsNone(bogus)


if __name__ == "__main__":
    unittest.main()
