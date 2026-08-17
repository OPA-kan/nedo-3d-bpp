import importlib.util
import os
import pathlib
import sys
import unittest

AGENT_PATH = pathlib.Path(__file__).parents[1] / "agent" / "agent.py"
SPEC = importlib.util.spec_from_file_location(
    "probe_guard_agent", AGENT_PATH
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


def _probe_fn(verdicts):
    """Stub probe: pops the next scripted verdict per call.

    True/False becomes a predicted_safe record; None is a probe failure.
    """
    calls = []

    def probe(decision):
        calls.append(decision)
        verdict = verdicts.pop(0)
        if verdict is None:
            return None
        return {"predicted_safe": verdict}

    probe.calls = calls
    return probe


def _never_expired():
    return False


class KnobAndConstantsTests(unittest.TestCase):
    def test_default_mode_is_off_and_constants_are_preregistered(self):
        self.assertEqual(agent.PHYSICS_PROBE_MODE, "off")
        self.assertEqual(
            agent.PHYSICS_PROBE_MODES, frozenset({"off", "guard"})
        )
        self.assertEqual(agent.PHYSICS_PROBE_GUARD_MAX_PROBES, 6)
        self.assertEqual(agent.PHYSICS_PROBE_GUARD_SECONDS, 1.5)

    def test_unknown_mode_is_refused_at_import(self):
        previous = os.environ.get("PHYSICS_PROBE_MODE")
        os.environ["PHYSICS_PROBE_MODE"] = "bogus"
        try:
            spec = importlib.util.spec_from_file_location(
                "probe_guard_agent_bogus", AGENT_PATH
            )
            module = importlib.util.module_from_spec(spec)
            with self.assertRaises(ValueError):
                spec.loader.exec_module(module)
        finally:
            sys.modules.pop("probe_guard_agent_bogus", None)
            if previous is None:
                os.environ.pop("PHYSICS_PROBE_MODE", None)
            else:
                os.environ["PHYSICS_PROBE_MODE"] = previous


class ProbeGuardChooseTests(unittest.TestCase):
    def setUp(self):
        self.incumbent = _FakeDecision(0, (0, 0, 0), 5.0)
        self.alternatives = [
            _FakeDecision(1, (1, 0, 0), 4.9),
            _FakeDecision(2, (2, 0, 0), 4.8),
            _FakeDecision(3, (3, 0, 0), 4.7),
        ]

    def test_safe_incumbent_passes_through_with_zero_alt_probes(self):
        probe = _probe_fn([True])
        chosen, record = agent.probe_guard_choose(
            self.incumbent, self.alternatives, probe, _never_expired
        )
        self.assertIs(chosen, self.incumbent)
        self.assertEqual(record["probes_used"], 1)
        self.assertIs(record["incumbent_safe"], True)
        self.assertFalse(record["swapped"])
        self.assertIsNone(record["swap_rank"])
        self.assertFalse(record["budget_exhausted"])
        self.assertEqual(probe.calls, [self.incumbent])

    def test_probe_failure_plays_incumbent_with_null_verdict(self):
        probe = _probe_fn([None])
        chosen, record = agent.probe_guard_choose(
            self.incumbent, self.alternatives, probe, _never_expired
        )
        self.assertIs(chosen, self.incumbent)
        self.assertEqual(record["probes_used"], 1)
        self.assertIsNone(record["incumbent_safe"])
        self.assertFalse(record["swapped"])

    def test_unsafe_incumbent_swaps_to_first_safe_alternative(self):
        probe = _probe_fn([False, False, True])
        chosen, record = agent.probe_guard_choose(
            self.incumbent, self.alternatives, probe, _never_expired
        )
        self.assertIs(chosen, self.alternatives[1])
        self.assertEqual(record["probes_used"], 3)
        self.assertIs(record["incumbent_safe"], False)
        self.assertTrue(record["swapped"])
        self.assertEqual(record["swap_rank"], 1)
        self.assertFalse(record["budget_exhausted"])

    def test_failed_alternative_probe_is_skipped_not_played(self):
        probe = _probe_fn([False, None, True])
        chosen, record = agent.probe_guard_choose(
            self.incumbent, self.alternatives, probe, _never_expired
        )
        self.assertIs(chosen, self.alternatives[1])
        self.assertEqual(record["swap_rank"], 1)
        self.assertEqual(record["probes_used"], 3)

    def test_all_unsafe_keeps_incumbent(self):
        probe = _probe_fn([False, False, False, False])
        chosen, record = agent.probe_guard_choose(
            self.incumbent, self.alternatives, probe, _never_expired
        )
        self.assertIs(chosen, self.incumbent)
        self.assertEqual(record["probes_used"], 4)
        self.assertFalse(record["swapped"])
        self.assertFalse(record["budget_exhausted"])

    def test_probe_cap_bounds_total_probes_incumbent_included(self):
        alternatives = [
            _FakeDecision(i + 1, (i + 1, 0, 0), 4.9) for i in range(10)
        ]
        probe = _probe_fn([False] * 11)
        chosen, record = agent.probe_guard_choose(
            self.incumbent, alternatives, probe, _never_expired
        )
        self.assertIs(chosen, self.incumbent)
        self.assertEqual(
            record["probes_used"], agent.PHYSICS_PROBE_GUARD_MAX_PROBES
        )
        self.assertTrue(record["budget_exhausted"])
        self.assertFalse(record["swapped"])

    def test_expired_deadline_keeps_incumbent_without_any_probe(self):
        probe = _probe_fn([True])
        chosen, record = agent.probe_guard_choose(
            self.incumbent, self.alternatives, probe, lambda: True
        )
        self.assertIs(chosen, self.incumbent)
        self.assertEqual(record["probes_used"], 0)
        self.assertTrue(record["budget_exhausted"])
        self.assertEqual(probe.calls, [])

    def test_deadline_expiring_mid_walk_keeps_incumbent(self):
        expirations = iter([False, False, True])
        probe = _probe_fn([False, False, True])
        chosen, record = agent.probe_guard_choose(
            self.incumbent,
            self.alternatives,
            probe,
            lambda: next(expirations),
        )
        self.assertIs(chosen, self.incumbent)
        self.assertEqual(record["probes_used"], 2)
        self.assertTrue(record["budget_exhausted"])
        self.assertFalse(record["swapped"])


if __name__ == "__main__":
    unittest.main()
