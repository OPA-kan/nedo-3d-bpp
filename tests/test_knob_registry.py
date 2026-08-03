import ast
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

ENV_READ = re.compile(
    r"""os\.environ\.get\(\s*["']([A-Z][A-Z0-9_]*)["']"""
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

    def test_the_dead_offline_weights_stay_dead(self) -> None:
        """
        OFFLINE_FILL_WEIGHT and OFFLINE_STABILITY_WEIGHT are registered
        semantic=false on one specific ground: their only read is a default
        argument of DryRunResult.weighted_score, and nothing calls it.
        Offline selection is the lexicographic rank_key.

        That is a claim about the source, not a property of the knob, so it
        can stop being true without anyone touching knobs.json -- and then
        two knobs that DO change behaviour would sit outside the
        fingerprint's projection. Assert the claim rather than trusting it:
        parse agent.py and require that weighted_score has exactly one
        occurrence, its definition.
        """
        source = AGENT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        definitions = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "weighted_score"
        ]
        self.assertEqual(
            len(definitions), 1,
            "weighted_score is expected to exist exactly once",
        )
        references = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "weighted_score"
        ] + [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id == "weighted_score"
        ]
        self.assertEqual(
            references, [],
            "weighted_score now has a caller, so OFFLINE_FILL_WEIGHT and "
            "OFFLINE_STABILITY_WEIGHT can change behaviour -- flip them "
            "back to semantic=true in context/knobs.json",
        )
        for name in ("OFFLINE_FILL_WEIGHT", "OFFLINE_STABILITY_WEIGHT"):
            with self.subTest(knob=name):
                self.assertFalse(self.knobs[name]["semantic"])


if __name__ == "__main__":
    unittest.main()
