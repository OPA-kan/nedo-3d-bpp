import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

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

LEDGER = """# Research Cup ledger

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

    def test_cli_can_run_as_a_direct_script(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            ledger = tmp_path / "cup-ledger.md"
            state = tmp_path / "state.json"
            names = tmp_path / "names.json"
            ledger.write_text(LEDGER, encoding="utf-8")
            state.write_text(json.dumps(STATE), encoding="utf-8")
            names.write_text(
                json.dumps({"names": {"w6": {"name": "bird"}}}),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    str(root / "scripts" / "host_diversity_cup.py"),
                    "--ledger", str(ledger),
                    "--state", str(state),
                    "--names", str(names),
                    "--date", "2026-08-26",
                ],
                cwd=tmp_path,
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["cup_id"], "002")


class PreregistrationRowTests(unittest.TestCase):
    def test_the_row_asserts_no_rule_alpha_commit(self):
        """The note hardcoded rule-alpha@7908b09 and kept saying so after
        Cup 008 had moved to 803fd6f. An auto-generated preregistration
        must not claim an actor version it cannot verify; the real commit
        goes in the per-cup report, written by someone who checked."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger = pathlib.Path(tmp) / "cup-ledger.md"
            ledger.write_text(LEDGER, encoding="utf-8")
            preregister(ledger, STATE, date="2026-08-26")
            updated = ledger.read_text(encoding="utf-8")
        row = next(
            line for line in updated.splitlines()
            if line.startswith("| 002 |")
        )
        self.assertIn("rule-alpha", row)
        self.assertNotRegex(row, r"[0-9a-f]{7,40}\b(?<!32890092906)")
        self.assertNotIn("@", row)


if __name__ == "__main__":
    unittest.main()
