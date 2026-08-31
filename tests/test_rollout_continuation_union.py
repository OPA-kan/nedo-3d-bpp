"""The teacher's rollout continuation can be widened, and says so."""

from __future__ import annotations

import inspect
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_terminal_rollout_policy as policy  # noqa: E402
from scripts import run_vector_mcts  # noqa: E402


class SearchSignatureTests(unittest.TestCase):
    def test_the_union_is_opt_in_so_old_runs_stay_reproducible(self):
        parameters = inspect.signature(
            run_vector_mcts.vector_search_root
        ).parameters
        self.assertIs(parameters["union_rule_alpha"].default, False)
        self.assertEqual(parameters["rule_alpha_union_limit"].default, 4)

    def test_run_episode_defaults_to_the_narrow_continuation(self):
        parameters = inspect.signature(policy.run_episode).parameters
        self.assertIs(
            parameters["union_rollout_continuation"].default, False,
        )


class ThreadingTests(unittest.TestCase):
    """Every vector_search_root call has to carry the flag.

    The root search, the online adapter fork and the mining fork are
    three separate call sites. One left behind would silently keep the
    old teacher for that path, and the run would still look configured.
    """

    def setUp(self):
        self.source = (
            ROOT / "scripts" / "run_terminal_rollout_policy.py"
        ).read_text(encoding="utf-8")

    def test_every_search_call_site_receives_it(self):
        self.assertEqual(
            self.source.count("vector_search_root("),
            self.source.count("union_rule_alpha=union_rollout_continuation"),
        )

    def test_there_are_three_call_sites(self):
        self.assertEqual(self.source.count("vector_search_root("), 3)


class ProvenanceTests(unittest.TestCase):
    def test_the_manifest_records_whether_the_teacher_was_widened(self):
        """A cup run with a widened teacher is not comparable to Cups
        001-009, so the artifact has to say which teacher produced it."""
        source = (
            ROOT / "scripts" / "run_terminal_rollout_policy.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"union_rollout_continuation": bool(', source)


if __name__ == "__main__":
    unittest.main()
