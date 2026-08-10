from __future__ import annotations

import json
import pathlib
import random
import tempfile
import unittest

import numpy as np

from scripts.audit_learnability import (
    FEATURES,
    audit,
    auc,
    load_rows,
    state_ranking,
)


def row(
    *,
    case_id: str,
    step: int,
    candidate: int,
    features: list[float],
    safe: bool,
    score: float,
) -> dict:
    return {
        "case_id": case_id,
        "step": step,
        "candidate_id": f"c{candidate}",
        "kind": "release_candidate",
        "score_immediate": score,
        "phi_modelling": dict(zip(FEATURES, features)),
        "physical": {
            "is_placed_safe": safe,
            "delta_theta_deg": features[0] * 10.0,
            "d_norm": features[0] * 2.0,
        },
    }


def write_corpus(
    root: pathlib.Path,
    *,
    cases: list[str],
    steps: list[int],
    per_state: int,
    signal: bool,
    seed: int = 7,
) -> None:
    """A corpus whose safety either follows feature 0 or is pure noise."""
    rng = random.Random(seed)
    for case in cases:
        directory = root / "run-1" / "dataset" / case
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "manifest.json").write_text("{}", encoding="utf-8")
        for step in steps:
            rows = []
            for index in range(per_state):
                driver = rng.random()
                features = [driver] + [rng.random() for _ in FEATURES[1:]]
                safe = driver > 0.4 if signal else rng.random() > 0.4
                rows.append(
                    row(
                        case_id=case,
                        step=step,
                        candidate=index,
                        features=features,
                        safe=safe,
                        # The incumbent is deliberately uninformative here.
                        score=rng.random(),
                    )
                )
            (directory / f"step-{step:03d}-candidates.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in rows),
                encoding="utf-8",
            )


class AucTests(unittest.TestCase):
    def test_a_constant_predictor_scores_exactly_one_half(self):
        scores = np.zeros(6)
        labels = np.array([1.0, 0.0, 1.0, 0.0, 1.0, 0.0])

        self.assertAlmostEqual(auc(scores, labels), 0.5)

    def test_a_perfect_ordering_scores_one(self):
        scores = np.array([0.1, 0.2, 0.9, 0.8])
        labels = np.array([0.0, 0.0, 1.0, 1.0])

        self.assertAlmostEqual(auc(scores, labels), 1.0)

    def test_one_class_only_is_undefined_not_one_half(self):
        self.assertIsNone(auc(np.array([0.1, 0.2]), np.array([1.0, 1.0])))


class TopOneTieTests(unittest.TestCase):
    def test_a_constant_predictor_gets_the_base_rate_not_a_perfect_score(self):
        # The defect this exists for: argmax over tied predictions returns
        # whichever row comes first, so a model that ranks nothing scored
        # 1.000 for top-1 safety.
        rows = [
            {"state": ("r", "a", 3), "safe": True},
            {"state": ("r", "a", 3), "safe": False},
            {"state": ("r", "a", 3), "safe": False},
            {"state": ("r", "a", 3), "safe": False},
        ]

        report = state_ranking(rows, np.zeros(4))

        self.assertAlmostEqual(report["top1_safe_rate"], 0.25)
        self.assertAlmostEqual(report["mean_state_auc"], 0.5)

    def test_a_perfect_ranker_takes_the_safe_candidate(self):
        rows = [
            {"state": ("r", "a", 3), "safe": False},
            {"state": ("r", "a", 3), "safe": True},
        ]

        report = state_ranking(rows, np.array([0.0, 1.0]))

        self.assertAlmostEqual(report["top1_safe_rate"], 1.0)


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_a_planted_signal_is_detected(self):
        # Positive control. Without this, "no_established_signal" on the real
        # corpus is indistinguishable from an audit that cannot detect
        # anything at all.
        write_corpus(
            self.root,
            cases=["m-a", "m-b", "m-c", "m-d"],
            steps=[3, 9],
            per_state=40,
            signal=True,
        )

        report = audit(self.root)

        self.assertEqual(report["verdict"], "signal_beyond_incumbent")
        self.assertGreater(
            report["classification"]["linear"]["mean_state_auc"], 0.8
        )

    def test_pure_noise_is_reported_as_no_signal(self):
        write_corpus(
            self.root,
            cases=["m-a", "m-b", "m-c", "m-d"],
            steps=[3, 9],
            per_state=40,
            signal=False,
        )

        report = audit(self.root)

        self.assertEqual(report["verdict"], "no_established_signal")

    def test_a_state_never_appears_on_both_sides_of_a_fold(self):
        write_corpus(
            self.root,
            cases=["m-a", "m-b"],
            steps=[3],
            per_state=30,
            signal=True,
        )

        report = audit(self.root)

        for fold in report["folds"]:
            self.assertGreater(fold["train_states"], 0)
            self.assertGreater(fold["test_states"], 0)
        # The assertion inside evaluate() would have raised otherwise.
        self.assertEqual(report["corpus"]["distinct_states"], 2)

    def test_a_corpus_too_small_to_hold_out_says_so(self):
        write_corpus(
            self.root, cases=["m-a"], steps=[3], per_state=4, signal=True
        )

        report = audit(self.root)

        self.assertEqual(report["verdict"], "insufficient_corpus")
        self.assertNotIn("classification", report)

    def test_rows_shared_between_arms_are_counted_once(self):
        directory = self.root / "run-1" / "dataset" / "m-a"
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text("{}", encoding="utf-8")
        entry = row(
            case_id="m-a",
            step=3,
            candidate=0,
            features=[0.5] * len(FEATURES),
            safe=True,
            score=1.0,
        )
        for suffix in ("candidates", "random-control"):
            (directory / f"step-003-{suffix}.jsonl").write_text(
                json.dumps(entry) + "\n", encoding="utf-8"
            )

        rows, skipped = load_rows(self.root)

        self.assertEqual(len(rows), 1)
        self.assertEqual(skipped["duplicate_across_arms"], 1)

    def test_rows_without_a_feature_vector_are_counted_and_excluded(self):
        directory = self.root / "run-1" / "dataset" / "m-a"
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text("{}", encoding="utf-8")
        settled = row(
            case_id="m-a",
            step=3,
            candidate=1,
            features=[0.5] * len(FEATURES),
            safe=True,
            score=1.0,
        )
        settled["kind"] = "candidate"
        settled["phi_modelling"] = {}
        (directory / "step-003-candidates.jsonl").write_text(
            json.dumps(settled) + "\n", encoding="utf-8"
        )

        rows, skipped = load_rows(self.root)

        self.assertEqual(rows, [])
        self.assertEqual(skipped["no_phi_candidate"], 1)


if __name__ == "__main__":
    unittest.main()
