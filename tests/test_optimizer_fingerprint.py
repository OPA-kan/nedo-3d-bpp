import importlib.util
import json
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "fingerprint_optimizer", ROOT / "scripts" / "fingerprint_optimizer.py"
)
fingerprint_optimizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fingerprint_optimizer
SPEC.loader.exec_module(fingerprint_optimizer)

STORED_PATH = ROOT / "context" / "optimizer_fingerprint.json"


class OptimizerFingerprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.stored = json.loads(STORED_PATH.read_text(encoding="utf-8"))
        cls.current = fingerprint_optimizer.fingerprint(
            fingerprint_optimizer.load_agent()
        )

    def test_offline_optimizer_semantics_are_unchanged(self) -> None:
        """
        The whole point: Agent.optimize can sit untouched for 31 of 33
        commits while the optimizer it defines changes, because
        DryRunEvaluator replays PlacementCore (ADR-001 section 2). git
        cannot see that and the ledger's `status` cannot either.

        If this fails, E_theta moved. That is not necessarily wrong -- but
        every Task A measurement now predates the change. Re-run the Task A
        sweep, then `python3 scripts/fingerprint_optimizer.py --write`.
        """
        self.assertEqual(
            self.current["behaviour_sha256"],
            self.stored["behaviour_sha256"],
            "offline evaluator semantics changed; Task A numbers are stale",
        )

    def test_shipped_offline_configuration_is_unchanged(self) -> None:
        self.assertEqual(
            self.current["component_sha256"],
            self.stored["component_sha256"],
            "a shipped offline constant changed",
        )

    def test_live_ranking_is_fingerprinted_separately(self) -> None:
        """
        Tracked apart from E_theta on purpose. A live ranking change that
        moves this hash while leaving behaviour_sha256 alone means the
        change did NOT reach the offline evaluator -- the two drifted
        further apart rather than staying in step.
        """
        self.assertEqual(
            self.current["live_ranking_sha256"],
            self.stored["live_ranking_sha256"],
            "online ranking changed; check whether it reached the dry run",
        )

    def test_fingerprint_does_not_depend_on_machine_speed(self) -> None:
        """
        Probes run with infinite deadlines and a fixed attempt budget. A
        fingerprint that inherited the deadline-driven path would drift
        with load, which is exactly the failure documented in
        MEASUREMENT_AUDIT F6.
        """
        again = fingerprint_optimizer.fingerprint(
            fingerprint_optimizer.load_agent()
        )
        self.assertEqual(
            again["behaviour_sha256"], self.current["behaviour_sha256"]
        )
        self.assertEqual(
            again["live_ranking_sha256"], self.current["live_ranking_sha256"]
        )

    def test_records_whether_adr001_ranking_sharing_holds(self) -> None:
        note = self.current["adr001_section2_ranking_shared"]
        self.assertEqual(note, self.stored["adr001_section2_ranking_shared"])
        # Guard the finding itself: while the live rerank is on and the dry
        # run passes no risk_lambda, this must keep saying VIOLATED. If
        # somebody wires risk into the dry run, this fails and the Task A
        # baseline must be re-measured, because E_theta changed.
        if self.current["live_ranking"]["live_lambda"] is not None:
            self.assertIn("VIOLATED", note)


if __name__ == "__main__":
    unittest.main()
