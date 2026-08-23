"""Tests for the direct post-shake recorder.

Protocol: reports/hazard/post-shake-direct-protocol.md. Gate G3 (no
reimplementation of the attribute contract) is adjudicated here --
these are the structural tests the protocol names. G1a and G2 are
adjudicated on recorded episodes by scripts/adjudicate_postshake.py.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from scripts import postshake_capture  # noqa: E402

PYBULLET_AVAILABLE = importlib.util.find_spec("pybullet") is not None


def _require_evaluator() -> None:
    # The install no-op tests import the official Evaluator, which imports
    # pybullet at module scope. Same convention as the e2e suites: skip
    # without pybullet, fail loudly when integration coverage is required.
    if not PYBULLET_AVAILABLE:
        if os.environ.get("NEDO_REQUIRE_INTEGRATION") == "1":
            raise RuntimeError(
                "NEDO_REQUIRE_INTEGRATION=1 but pybullet is unavailable"
            )
        raise unittest.SkipTest(
            "pybullet not installed; integration CI must run this test "
            "without skip"
        )


class AttributeProjectionTests(unittest.TestCase):
    def test_missing_keys_are_omitted_not_defaulted(self):
        # A contract change must surface as an absent key in the gate
        # report, never as a silent zero that reads like a measurement.
        counts = postshake_capture.attribute_counts({"soft_items": 3})
        self.assertEqual(counts, {"soft_items": 3})

    def test_none_metrics_project_to_empty(self):
        self.assertEqual(postshake_capture.attribute_counts(None), {})
        self.assertEqual(postshake_capture.attribute_counts({}), {})

    def test_extra_keys_are_dropped(self):
        counts = postshake_capture.attribute_counts(
            {"soft_items": 1, "fill_score": 9.0}
        )
        self.assertEqual(counts, {"soft_items": 1})


class InProcessCaptureTests(unittest.TestCase):
    def test_capture_reads_the_exact_two_states_and_restores_the_method(self):
        class Evaluator:
            def __init__(self):
                self.phase = "settled"

            def _live_poses(self, _containers):
                return [{"phase": self.phase}]

            def settled_snapshot(self, _containers):
                return {"phase": self.phase, "soft_covered_by_other": 0}

            def shake_test(self, containers):
                before = self._live_poses(containers)
                self.phase = "shaken"
                after = self._live_poses(containers)
                self.phase = "settled"
                return {"before": before, "after": after}

        evaluator = Evaluator()
        original = evaluator._live_poses

        captured = postshake_capture.capture_shake_labels(evaluator, [])

        self.assertEqual(captured["live_poses_calls"], 2)
        self.assertEqual(captured["pre_shake"]["phase"], "settled")
        self.assertEqual(captured["post_shake"]["phase"], "shaken")
        self.assertEqual(evaluator.phase, "settled")
        self.assertEqual(evaluator._live_poses([]), original([]))
        self.assertNotIn("_live_poses", evaluator.__dict__)

    def test_capture_restores_the_method_when_the_shake_raises(self):
        class Evaluator:
            def _live_poses(self, _containers):
                return []

            def settled_snapshot(self, _containers):
                return {}

            def shake_test(self, containers):
                self._live_poses(containers)
                raise RuntimeError("shake failed")

        evaluator = Evaluator()
        with self.assertRaisesRegex(RuntimeError, "shake failed"):
            postshake_capture.capture_shake_labels(evaluator, [])
        self.assertNotIn("_live_poses", evaluator.__dict__)


class ContractSourceTests(unittest.TestCase):
    """Gate G3: the post-shake counts come from the simulator, not a copy."""

    def test_every_projected_key_is_produced_by_the_official_function(self):
        from src.ground_handling.diagnostics import (
            calculate_attribute_placement,
        )

        produced = calculate_attribute_placement([])
        for key in postshake_capture.ATTRIBUTE_KEYS:
            self.assertIn(
                key,
                produced,
                f"{key} is not a key the bundled "
                "calculate_attribute_placement produces -- the "
                "projection has drifted from the contract",
            )

    def test_recorder_does_not_reimplement_the_contract(self):
        # The recorder must delegate to settled_snapshot. If it ever
        # grows its own soft/priority arithmetic, this catches it: no
        # comparison or accumulation over item attributes may appear.
        source = (ROOT / "scripts" / "postshake_capture.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        banned = {"is_soft", "is_prioritized"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in banned:
                self.fail(
                    f"recorder reads item.{node.attr} directly; the "
                    "attribute contract must come from "
                    "settled_snapshot/calculate_attribute_placement"
                )
            if isinstance(node, ast.Constant) and node.value in banned:
                self.fail(
                    f"recorder references {node.value!r} as a literal; "
                    "the attribute contract must come from "
                    "settled_snapshot/calculate_attribute_placement"
                )

    def test_live_poses_is_only_called_from_shake_test(self):
        # The interception point is unambiguous only while this holds.
        source = (
            ROOT
            / "simulator"
            / "src"
            / "ground_handling"
            / "evaluator.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        callers = set()
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.FunctionDef):
                continue
            for node in ast.walk(cls):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_live_poses"
                ):
                    callers.add(cls.name)
        self.assertEqual(
            callers,
            {"shake_test"},
            "_live_poses gained a caller outside shake_test; the "
            "recorder's two-call assumption no longer holds",
        )


class InstallTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("NEDO_POSTSHAKE_CAPTURE")
        postshake_capture._INSTALLED = False

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("NEDO_POSTSHAKE_CAPTURE", None)
        else:
            os.environ["NEDO_POSTSHAKE_CAPTURE"] = self._saved
        postshake_capture._INSTALLED = False

    def test_install_is_a_noop_without_the_variable(self):
        _require_evaluator()
        os.environ.pop("NEDO_POSTSHAKE_CAPTURE", None)
        from src.ground_handling.evaluator import Evaluator

        before = Evaluator.shake_test
        self.assertFalse(postshake_capture.install())
        self.assertIs(Evaluator.shake_test, before)

    def test_install_is_a_noop_for_a_blank_variable(self):
        _require_evaluator()
        os.environ["NEDO_POSTSHAKE_CAPTURE"] = "   "
        from src.ground_handling.evaluator import Evaluator

        before = Evaluator.shake_test
        self.assertFalse(postshake_capture.install())
        self.assertIs(Evaluator.shake_test, before)


class WrapperEntryPointTests(unittest.TestCase):
    def test_wrapper_delegates_to_the_bundled_runner(self):
        source = (ROOT / "scripts" / "run_test_capture.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from run_test import main", source)
        self.assertIn("install()", source)

    def test_nothing_under_simulator_is_touched_by_the_recorder(self):
        source = (ROOT / "scripts" / "postshake_capture.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("write_text", "open("):
            # The only write is _write's, which targets the capture path.
            occurrences = source.count(forbidden)
            if forbidden == "write_text":
                self.assertEqual(occurrences, 1, source.count(forbidden))
            else:
                self.assertEqual(occurrences, 0)


if __name__ == "__main__":
    unittest.main()
