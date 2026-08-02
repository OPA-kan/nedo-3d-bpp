import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scripts import measurement_budget as budget


class BudgetLedgerTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        patcher = mock.patch.object(
            budget, "LEDGER", pathlib.Path(self._dir.name) / "budget.json"
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_fresh_line_is_not_over_budget(self):
        status = budget.record("alpha", 3, quiet=True)

        self.assertEqual(status["episodes"], 3)
        self.assertFalse(status["over_budget"])

    def test_crossing_the_threshold_without_a_candidate_is_over_budget(self):
        budget.record("alpha", 9, quiet=True)
        status = budget.record("alpha", 1, quiet=True)

        self.assertEqual(status["episodes"], 10)
        self.assertTrue(status["over_budget"])

    def test_a_candidate_clears_the_warning(self):
        """
        The point is the ratio, not the count. A line that produced a
        shipping change has earned its episodes.
        """
        budget.record("alpha", 50, quiet=True)
        data = budget.load()
        data["lines"]["alpha"]["shipping_candidates"].append(
            {"change": "MAX_POOL_ITEMS_EVALUATED 10 -> 16", "evidence": "..."}
        )
        budget.save(data)

        self.assertFalse(budget.line_status(budget.load(), "alpha")["over_budget"])

    def test_the_warning_names_the_line_and_the_counts(self):
        budget.record("alpha", 12, quiet=True)
        stream = io.StringIO()

        budget.warn(budget.line_status(budget.load(), "alpha"), stream=stream)
        text = stream.getvalue()

        self.assertIn("alpha", text)
        self.assertIn("12 episodes", text)
        self.assertIn("not an instruction to stop", text)

    def test_episodes_accumulate_across_invocations(self):
        budget.record("alpha", 4, quiet=True)
        budget.record("alpha", 5, quiet=True)

        self.assertEqual(budget.load()["lines"]["alpha"]["episodes"], 9)


class RunnerHookTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        patcher = mock.patch.object(
            budget, "LEDGER", pathlib.Path(self._dir.name) / "budget.json"
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_hook_is_a_no_op_when_no_line_is_named(self):
        """
        Runners call this unconditionally, so an unnamed run must not
        invent a line or fail.
        """
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(budget.record_from_env(1))
        self.assertFalse(budget.LEDGER.exists())

    def test_the_hook_records_against_the_named_line(self):
        with mock.patch.dict(
            "os.environ", {budget.LINE_ENV: "beta"}, clear=True
        ):
            budget.record_from_env(1)
            budget.record_from_env(1)

        self.assertEqual(budget.load()["lines"]["beta"]["episodes"], 2)


class ContractTests(unittest.TestCase):
    def test_the_shipping_candidate_definition_excludes_instruments(self):
        """
        A loose definition makes the whole mechanism decoration, so the
        exclusions are part of the stored contract rather than prose in a
        docstring.
        """
        text = json.dumps(budget.CONTRACT)

        self.assertIn("DEFAULT", text)
        for excluded in ("script", "default-off knob", "negative result"):
            self.assertIn(excluded, text)


if __name__ == "__main__":
    unittest.main()
