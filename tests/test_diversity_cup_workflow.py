import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "diversity-cup.yml"
EVAL_STREAMS = {
    "permute-000-191", "permute-000-193", "permute-000-197",
    "permute-001-167", "permute-001-173", "permute-001-179",
    "permute-001-181",
}


class DiversityCupWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def cup_streams(self):
        return set(re.findall(r"stream: (permute-\d+-\d+)", self.text))

    def test_dispatch_only_and_season_isolated(self):
        # the push trigger exists ONLY to register the workflow (a
        # dispatch-only workflow on a non-default branch is never
        # indexed); the event guard keeps pushes from running the cup,
        # and nothing writes to the season ledger, registry or matrices
        self.assertIn("workflow_dispatch:", self.text)
        self.assertIn(
            "if: github.event_name == 'workflow_dispatch'", self.text
        )
        push_paths = self.text.split("push:")[1].split("permissions:")[0]
        self.assertIn(".github/workflows/diversity-cup.yml", push_paths)
        self.assertNotIn("scripts/", push_paths)
        self.assertIn("contents: read", self.text)
        self.assertNotIn("git push", self.text)
        self.assertNotIn("reports/league/season", self.text)
        self.assertNotIn("registry.json", self.text)

    def test_six_cells_run_champion_and_three_mining_studs(self):
        self.assertEqual(self.text.count("- {cell: "), 6)
        self.assertEqual(len(self.cup_streams()), 6)
        self.assertIn("--policy learned", self.text)
        self.assertIn("for stud in rule-grid rule-lowcog rule-edge", self.text)
        self.assertIn("--mine-against-model reports/cup/model", self.text)
        self.assertIn("--mine-fork-budget", self.text)
        self.assertIn("analyze_diversity_cup.py", self.text)
        self.assertIn("side-corpus-pairs.jsonl", self.text)

    def test_cup_streams_are_disjoint_from_eval_and_season(self):
        streams = self.cup_streams()
        self.assertFalse(streams & EVAL_STREAMS)
        plan = json.loads(
            (ROOT / "reports" / "league" / "season" / "waves.json")
            .read_text(encoding="utf-8")
        )
        season_primes = {
            prime
            for wave in plan["waves"].values()
            for key in ("primes_000", "primes_001")
            for prime in wave.get(key, [])
        }
        cup_primes = {int(stream.rsplit("-", 1)[1]) for stream in streams}
        self.assertFalse(cup_primes & season_primes)
        # virgin territory by construction: strictly above every
        # season prime
        self.assertGreater(min(cup_primes), max(season_primes))


if __name__ == "__main__":
    unittest.main()
