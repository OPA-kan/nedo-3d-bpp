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
        return set(re.findall(r'"stream":"(permute-\d+-\d+)"', self.text))

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

    def rule_alpha_command(self):
        """The rule-alpha invocation, up to the next policy or loop."""
        head, _sep, tail = self.text.partition("--policy rule-alpha")
        self.assertTrue(_sep, "no rule-alpha episode in the workflow")
        return tail.split("--output-dir")[0]

    def test_cup_009_gives_rule_alpha_the_union_and_its_own_fork_budget(self):
        """Cup 009+ amendment: the union and the budget are rule-alpha's
        alone, so the other five horses stay comparable to Cup 008."""
        command = self.rule_alpha_command()
        self.assertIn("--union-rule-alpha", command)
        self.assertIn("--rule-alpha-union-limit", command)
        self.assertIn("inputs.rule_alpha_fork_budget", command)
        self.assertNotIn("inputs.mine_fork_budget", command)

    def test_no_other_horse_gets_the_rule_alpha_union(self):
        # exactly one episode carries the union flag
        self.assertEqual(self.text.count("--union-rule-alpha"), 1)
        for policy in ("learned", "current-agent"):
            block = self.text.partition(f"--policy {policy}")[2].split(
                "--output-dir"
            )[0]
            self.assertNotIn("--union-rule-alpha", block)

    def test_the_shared_stud_fork_budget_is_untouched(self):
        # the three compact studs still run the runbook's fixed 12
        self.assertIn('default: "12"', self.text)
        self.assertIn("inputs.mine_fork_budget", self.text)

    def test_the_exact_agent_safety_net_stays_on(self):
        """Proved a no-op when the union works; kept as cheap insurance,
        and candidate_support_hit still records what the provider gave."""
        self.assertNotIn("--no-exact-agent-candidate", self.text)

    def test_six_cells_run_champion_two_exact_agents_and_three_mining_studs(self):
        # the course is a dispatch input; the baked default is Cup 001
        self.assertIn("fromJSON(inputs.cells ||", self.text)
        self.assertEqual(self.text.count('"cell":"'), 6)
        self.assertEqual(len(self.cup_streams()), 6)
        self.assertIn("--policy learned", self.text)
        self.assertIn("--policy current-agent", self.text)
        self.assertIn("--policy rule-alpha", self.text)
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
