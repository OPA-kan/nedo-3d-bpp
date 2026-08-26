import json
import pathlib
import tempfile
import unittest

from scripts.host_diversity_cup import (
    allocate_course,
    next_cup_id,
    preregister,
    resolve_champion,
)


STATE = {
    "champion": "pi2-pref-w6",
    "history": [
        {
            "promoted": True,
            "champion_after": "pi2-pref-w6",
            "runs": {"learning": "32890092906"},
        }
    ],
}

LEDGER = """# Diversity Cup ledger

| cup | date | vs model (learning run) | champion | streams (000/001 primes) | run | strict pairs | novel board rate | notes |
|---|---|---|---|---|---|---|---|---|
| 001 | 2026-08-26 | 32890092906 | pi2-pref-w6 プリフヒバリ | 000: 401,419,431,433 · 001: 409,421 | 32920552027 | 15 | 0.81 | inaugural |

Pool allocation note: keep this footer.
"""


class DiversityCupHostingTests(unittest.TestCase):
    def test_one_click_workflow_preregisters_then_dispatches(self):
        text = (
            pathlib.Path(__file__).resolve().parents[1]
            / ".github" / "workflows" / "host-diversity-cup.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", text)
        self.assertIn("contents: write", text)
        self.assertIn("actions: write", text)
        prereg = text.index("python scripts/host_diversity_cup.py")
        commit = text.index("git commit")
        dispatch = text.index("gh workflow run diversity-cup.yml")
        self.assertLess(prereg, commit)
        self.assertLess(commit, dispatch)
        self.assertIn('test "$running" = "0"', text)
        self.assertIn("terminal-rollout-hard-state.yml", text)
        self.assertIn("league-match.yml", text)

    def test_resolves_current_promoted_champion_and_next_id(self):
        self.assertEqual(
            resolve_champion(STATE), ("pi2-pref-w6", "32890092906")
        )
        self.assertEqual(next_cup_id(LEDGER), "002")

    def test_allocates_six_fresh_source_specific_streams(self):
        course = allocate_course(LEDGER)
        self.assertEqual(len(course), 6)
        streams = {row["stream"] for row in course}
        self.assertEqual(len(streams), 6)
        self.assertNotIn("permute-000-401", streams)
        self.assertNotIn("permute-001-409", streams)
        self.assertEqual(
            {row["scenario"] for row in course},
            {
                "dual-preloaded-dedicated", "dual-empty",
                "single-empty-noshelf", "dual-shelf-mixed",
                "single-empty-shelf", "single-preloaded",
            },
        )

    def test_preregistration_appends_before_footer_and_emits_dispatch_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = pathlib.Path(tmp) / "cup-ledger.md"
            ledger.write_text(LEDGER, encoding="utf-8")
            result = preregister(
                ledger, STATE, date="2026-08-26",
                display_name="プリフヒバリ",
            )
            updated = ledger.read_text(encoding="utf-8")

        self.assertIn("| 002 | 2026-08-26 | 32890092906 |", updated)
        self.assertLess(updated.index("| 002 |"), updated.index("Pool allocation"))
        self.assertEqual(result["cup_id"], "002")
        self.assertEqual(result["model_run_id"], "32890092906")
        self.assertEqual(len(json.loads(result["cells_json"])), 6)

    def test_preregister_refuses_an_unfinished_cup(self):
        pending = LEDGER.replace(
            "32920552027 | 15 | 0.81",
            "pending | pending | pending",
        )
        with tempfile.TemporaryDirectory() as tmp:
            ledger = pathlib.Path(tmp) / "cup-ledger.md"
            ledger.write_text(pending, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "pending preregistration"):
                preregister(ledger, STATE, date="2026-08-26")


if __name__ == "__main__":
    unittest.main()
