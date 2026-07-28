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
        self.assertTrue({"agent", "simulator", "theory"} <= set(profiles))

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
