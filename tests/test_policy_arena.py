"""Comparing policy heads over enough cells to resolve a difference.

The Cup course is six cells; these pin the arena that replaces it for
policy-vs-policy questions, and above all pin that its streams can never
be mistaken for Cup streams.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import evaluate_policy_arena as arena  # noqa: E402
from scripts.build_scenario_matrix import STREAM_VARIANTS  # noqa: E402
from scripts.host_diversity_cup import (  # noqa: E402
    CUP_PRIME_RANGE,
    _available_primes,
)


class StreamBandTests(unittest.TestCase):
    def test_the_arena_band_is_disjoint_from_the_cup_pool(self):
        """The load-bearing invariant.

        A Cup prime is single-use; an arena stream is re-used on every
        arena run. If the two bands ever met, a re-used arena stream
        would be handed to a Cup as a fresh draw.
        """
        self.assertGreater(arena.ARENA_PRIME_FLOOR, CUP_PRIME_RANGE[1])
        drawable = _available_primes()
        for source, primes in drawable.items():
            self.assertTrue(
                all(prime <= CUP_PRIME_RANGE[1] for prime in primes),
                f"source {source} exposes an out-of-window prime to the Cup",
            )

    def test_the_arena_band_is_above_the_frozen_and_season_bands(self):
        # frozen eval variants are <= 197, season-1 wave primes <= 379
        self.assertGreater(arena.ARENA_PRIME_FLOOR, 379)

    def test_every_arena_stream_is_a_declared_variant(self):
        streams = arena.arena_streams()
        self.assertTrue(streams)
        for variant in streams:
            self.assertIn(variant, STREAM_VARIANTS)
            prime = int(re.fullmatch(
                r"permute-(?:000|001)-(\d+)", variant
            ).group(1))
            self.assertGreaterEqual(prime, arena.ARENA_PRIME_FLOOR)

    def test_the_band_is_balanced_across_both_sources(self):
        sources = [variant.split("-")[1] for variant in arena.arena_streams()]
        self.assertEqual(sources.count("000"), sources.count("001"))

    def test_truncating_the_stream_list_keeps_both_sources(self):
        """A short run must not become a single-source run."""
        head = arena.arena_streams()[:6]
        self.assertEqual(len({variant.split("-")[1] for variant in head}), 2)


class PairedStatisticsTests(unittest.TestCase):
    def _cells(self, pairs):
        return {
            f"s:{index}": {"a": {"fill": left}, "b": {"fill": right}}
            for index, (left, right) in enumerate(pairs)
        }

    def test_a_cell_missing_an_arm_is_dropped_rather_than_imputed(self):
        cells = self._cells([(1.0, 2.0), (3.0, 4.0)])
        cells["s:2"] = {"a": {"fill": 9.0}}
        result = arena.compare("a", "b", cells)
        self.assertEqual(result["cells"], 2)

    def test_wins_losses_and_the_mean_agree(self):
        result = arena.compare(
            "a", "b", self._cells([(1.0, 3.0), (5.0, 1.0), (2.0, 2.0)])
        )
        self.assertEqual((result["wins"], result["losses"], result["ties"]),
                         (1, 1, 1))
        self.assertAlmostEqual(result["mean_difference"], -0.6666666, places=5)

    def test_the_report_says_what_this_n_could_have_detected(self):
        """A null with a huge MDE is 'we could not tell', not 'no effect'."""
        result = arena.compare(
            "a", "b", self._cells([(0.0, 5.0), (0.0, -5.0), (0.0, 5.0),
                                   (0.0, -5.0)])
        )
        self.assertAlmostEqual(result["mean_difference"], 0.0)
        self.assertGreater(result["mde_at_this_n"], 5.0)

    def test_the_sign_test_is_exact_and_two_sided(self):
        self.assertAlmostEqual(arena._sign_test(5, 0), 2 * 0.5 ** 5)
        self.assertEqual(arena._sign_test(0, 0), None)
        self.assertAlmostEqual(arena._sign_test(3, 3), 1.0)

    def test_no_shared_cells_is_reported_not_crashed(self):
        self.assertEqual(
            arena.compare("a", "b", {"s:0": {"a": {"fill": 1.0}}}),
            {"cells": 0},
        )


class ReadCellTests(unittest.TestCase):
    def test_a_cell_reads_its_final_fill_and_placed_count(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "manifest.json"
            path.write_text(json.dumps({"episodes": [{
                "steps": 7,
                "termination": "no_retained_candidate",
                "final_metrics": {
                    "fill_score_proxy": 12.5, "placed_count": 9
                },
            }]}), encoding="utf-8")
            self.assertEqual(arena.read_cell(path), {
                "fill": 12.5, "placed": 9, "steps": 7,
                "termination": "no_retained_candidate",
            })


if __name__ == "__main__":
    unittest.main()


class ArmSpecTests(unittest.TestCase):
    """An arm is a learned head or one of the runner's own policies."""

    def test_a_model_directory_becomes_the_learned_head(self):
        self.assertEqual(
            arena.arm_command("/models/champ")[:2], ["--policy", "learned"]
        )
        self.assertIn("--model-dir", arena.arm_command("/models/champ"))

    def test_a_policy_arm_carries_no_model_dir(self):
        """The hand-coded actors generate their own moves.

        Passing --model-dir would silently turn current-agent into a
        learned run, and the whole point of entering it is that it is
        NOT confined to the generic candidate family.
        """
        command = arena.arm_command("policy:current-agent")
        self.assertEqual(command, ["--policy", "current-agent"])
        self.assertNotIn("--model-dir", command)

    def test_rule_alpha_is_enterable(self):
        self.assertEqual(
            arena.arm_command("policy:rule-alpha"), ["--policy", "rule-alpha"]
        )


class ArmModifierTests(unittest.TestCase):
    def test_the_union_modifier_widens_the_candidate_set(self):
        command = arena.arm_command("/models/champ,union")
        self.assertIn("--union-rule-alpha", command)
        self.assertEqual(command[:2], ["--policy", "learned"])

    def test_a_modifier_applies_to_a_policy_arm_too(self):
        command = arena.arm_command("policy:rule-grid,union")
        self.assertEqual(command[:2], ["--policy", "rule-grid"])
        self.assertIn("--union-rule-alpha", command)

    def test_an_unknown_modifier_is_refused_rather_than_ignored(self):
        """A silently dropped modifier would run the wrong arm."""
        with self.assertRaises(ValueError):
            arena.arm_command("/models/champ,unoin")

    def test_a_plain_arm_is_unchanged(self):
        self.assertNotIn("--union-rule-alpha", arena.arm_command("/m/champ"))


class ExpertAdvisorArmTests(unittest.TestCase):
    """An advisor offers its move; the acting policy still chooses."""

    def test_an_expert_advisor_does_not_change_the_acting_policy(self):
        command = arena.arm_command("/models/champ,expert-agent")
        self.assertEqual(command[:2], ["--policy", "learned"])
        self.assertIn("--union-expert", command)
        self.assertIn("current-agent", command)

    def test_advisors_compose_with_the_rule_alpha_union(self):
        command = arena.arm_command("/models/champ,union,expert-agent")
        self.assertIn("--union-rule-alpha", command)
        self.assertIn("--union-expert", command)


class TaskShapeTests(unittest.TestCase):
    """A, B and C differ only by the offline flag and the pool size."""

    def _source(self):
        return {"m-demo": {
            "agent": {"optimize": False},
            "item_stream": {"look_ahead": 10, "max_space": 3,
                            "visible_pool": [1, 2], "item_list": []},
            "containers": {"container_list": []},
        }}

    def _write(self, task):
        import json
        import tempfile

        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "demo.json").write_text(json.dumps(self._source()))
        path = arena.write_task_config(tmp, "demo", task)
        return json.loads(path.read_text())

    def test_task_b_uses_the_scenario_config_untouched(self):
        tmp = pathlib.Path(__file__).parent
        self.assertEqual(
            arena.write_task_config(tmp, "demo", "b").name, "demo.json"
        )

    def test_task_a_turns_the_offline_pass_on_and_the_pool_to_one(self):
        case = self._write("a")["am-demo"]
        self.assertTrue(case["agent"]["optimize"])
        self.assertEqual(case["item_stream"]["look_ahead"], 1)
        self.assertEqual(case["item_stream"]["visible_pool"], [])

    def test_task_c_keeps_the_offline_pass_off(self):
        """C is arrival order: no offline pass, pool of one."""
        case = self._write("c")["m-demo"]
        self.assertFalse(case["agent"]["optimize"])
        self.assertEqual(case["item_stream"]["look_ahead"], 1)
        self.assertEqual(case["item_stream"]["max_space"], 1)

    def test_the_case_id_follows_the_builder(self):
        self.assertEqual(arena.task_case("demo", "a"), "am-demo")
        self.assertEqual(arena.task_case("demo", "b"), "m-demo")
        self.assertEqual(arena.task_case("demo", "c"), "m-demo")
