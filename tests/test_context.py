from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

from scripts.context import (
    load_manifest,
    profile_files,
    render_profile,
    resolve_repo_path,
)


class ContextRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_manifest()

    def test_expected_profiles_exist(self) -> None:
        profiles = self.manifest["profiles"]
        self.assertTrue(
            {
                "handoff",
                "competition",
                "agent",
                "simulator",
                "theory",
                "preview-value",
                "abc-spec",
                "preview-experiments",
            }
            <= set(profiles)
        )

    def test_competition_rules_are_a_separate_summary(self) -> None:
        files = profile_files(self.manifest, "competition", full=True)
        self.assertEqual(files, ["docs/COMPETITION_RULES.md"])
        self.assertNotIn(
            "docs/COMPETITION_RULES.md",
            profile_files(self.manifest, "overview", full=True),
        )

    def test_abc_spec_is_separate_from_default_theory(self) -> None:
        self.assertEqual(
            profile_files(self.manifest, "abc-spec", full=True),
            ["docs/theory/ABC_IMPLEMENTATION_SPEC.md"],
        )
        self.assertNotIn(
            "docs/theory/ABC_IMPLEMENTATION_SPEC.md",
            profile_files(self.manifest, "theory", full=True),
        )

    def test_preview_value_summary_is_separate_from_full_theory(self) -> None:
        files = profile_files(self.manifest, "preview-value")
        self.assertEqual(
            files,
            ["docs/theory/PREVIEW_VALUE_CONTEXT.md"],
        )
        rendered = render_profile(self.manifest, "preview-value")
        self.assertNotIn(
            "--- BEGIN docs/theory/PREVIEW_RESIDUAL_VALUE.md ---",
            rendered,
        )

    def test_preview_experiments_do_not_pollute_default_experiments(self) -> None:
        default_files = profile_files(self.manifest, "experiments", full=True)
        preview_files = profile_files(
            self.manifest,
            "preview-experiments",
            full=True,
        )
        self.assertNotIn("reports/lookahead/README.md", default_files)
        self.assertEqual(preview_files, ["reports/lookahead/README.md"])

    def test_handoff_profile_is_a_single_short_entrypoint(self) -> None:
        self.assertEqual(
            profile_files(self.manifest, "handoff"),
            ["HANDOFF.md"],
        )

    def test_summary_does_not_load_detailed_agent_source(self) -> None:
        files = profile_files(self.manifest, "agent")
        self.assertEqual(files, ["agent/CONTEXT.md"])
        rendered = render_profile(self.manifest, "agent")
        self.assertNotIn("--- BEGIN agent/agent.py ---", rendered)

    def test_full_profile_adds_detail_files(self) -> None:
        files = profile_files(self.manifest, "simulator", full=True)
        self.assertIn("docs/simulator/API_REFERENCE.md", files)
        self.assertIn("simulator/src/ground_handling/validator.py", files)

    def test_all_manifest_paths_resolve_inside_repository(self) -> None:
        for profile_name in self.manifest["profiles"]:
            for relative_path in profile_files(
                self.manifest, profile_name, full=True
            ):
                self.assertTrue(resolve_repo_path(relative_path).is_file())

    def test_path_escape_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_repo_path("../outside.md")

    def test_full_cli_handles_utf8_reference_on_windows(self) -> None:
        root = pathlib.Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "context.py"),
                "show",
                "simulator",
                "--full",
            ],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        self.assertIn(
            "docs/simulator/API_REFERENCE.md",
            completed.stdout.decode("utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
