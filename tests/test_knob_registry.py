import importlib.util
import json
import pathlib
import re
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "agent" / "agent.py"
KNOBS_PATH = ROOT / "context" / "knobs.json"

SPEC = importlib.util.spec_from_file_location(
    "fingerprint_optimizer", ROOT / "scripts" / "fingerprint_optimizer.py"
)
fingerprint_optimizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = fingerprint_optimizer
SPEC.loader.exec_module(fingerprint_optimizer)

# Two forms count as reading a knob. The second exists because the weight
# vectors call os.environ.get through a helper, with the NAME as an argument
# -- a literal-only pattern silently stops seeing them, which would let a
# registered knob be deleted from agent.py with no test noticing.
ENV_READ = re.compile(
    r"""(?:os\.environ\.get|_weight_vector)\(\s*["']([A-Z][A-Z0-9_]*)["']"""
)


def env_knobs_in_source() -> set[str]:
    return set(ENV_READ.findall(AGENT_PATH.read_text(encoding="utf-8")))


class KnobRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(KNOBS_PATH.read_text(encoding="utf-8"))
        cls.knobs = cls.registry["knobs"]

    def test_every_env_knob_the_agent_reads_is_registered(self) -> None:
        """
        The drift catcher. A knob that exists in the source but not here is
        invisible to the fingerprint, to the axis registry and to the
        coverage report at once -- which is how a merge that added three
        knobs left component_sha256 unchanged. Registering it forces a
        decision about which axis it belongs to.
        """
        unregistered = env_knobs_in_source() - set(self.knobs)
        self.assertEqual(
            unregistered,
            set(),
            f"agent.py reads {sorted(unregistered)} but context/knobs.json "
            f"does not list them; register each one with its axis",
        )

    def test_registry_does_not_invent_knobs(self) -> None:
        stale = set(self.knobs) - env_knobs_in_source()
        self.assertEqual(
            stale,
            set(),
            f"context/knobs.json lists {sorted(stale)} which agent.py no "
            f"longer reads",
        )

    def test_every_semantic_knob_reaches_the_fingerprint(self) -> None:
        tracked = set(fingerprint_optimizer.component_names())
        semantic = {
            name for name, spec in self.knobs.items() if spec["semantic"]
        }
        self.assertEqual(
            semantic - tracked,
            set(),
            "a semantic knob is not in the fingerprint's projection, so a "
            "change to it would not move component_sha256",
        )

    def test_diagnostic_knobs_are_excluded_deliberately(self) -> None:
        diagnostic = {
            name for name, spec in self.knobs.items()
            if not spec["semantic"]
        }
        self.assertTrue(diagnostic, "expected some telemetry-only knobs")
        tracked = set(fingerprint_optimizer.component_names())
        self.assertEqual(diagnostic & tracked, set())

    def test_every_knob_names_an_axis_the_registry_knows(self) -> None:
        axes = set(
            json.loads(
                (ROOT / "context" / "axes.json").read_text(encoding="utf-8")
            )["axes"]
        )
        axes.add("diagnostic")
        for name, spec in self.knobs.items():
            with self.subTest(knob=name):
                self.assertIn(spec["axis"], axes)

    def test_a_new_knob_moves_the_component_hash(self) -> None:
        """
        End to end: the registry is only useful if registration actually
        makes the fingerprint sensitive to the knob.
        """
        import os

        agent = fingerprint_optimizer.load_agent()
        before = fingerprint_optimizer.fingerprint(agent)["component_sha256"]
        previous = os.environ.get("MAX_POOL_ITEMS_EVALUATED")
        os.environ["MAX_POOL_ITEMS_EVALUATED"] = "16"
        try:
            reloaded = fingerprint_optimizer.load_agent()
            after = fingerprint_optimizer.fingerprint(
                reloaded
            )["component_sha256"]
        finally:
            if previous is None:
                os.environ.pop("MAX_POOL_ITEMS_EVALUATED", None)
            else:
                os.environ["MAX_POOL_ITEMS_EVALUATED"] = previous
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
