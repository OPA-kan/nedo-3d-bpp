import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "residual-diversity-pilot.yml"
SCALE_WORKFLOW = (
    ROOT / ".github" / "workflows" / "residual-diversity-scale.yml"
)


class ResidualDiversityWorkflowTests(unittest.TestCase):
    def test_workflow_runs_bounded_physics_pilot_and_persists_summary(self):
        text = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("experiment/residual-diversity-dataset", text)
        self.assertIn("requirements-simulator.txt", text)
        self.assertIn(
            "--sampling-mode residual_diversity_safe_split", text
        )
        self.assertIn("--overdraw-factor 2", text)
        self.assertIn("--per-stratum 4", text)
        self.assertIn("--steps 3 6 9", text)
        self.assertIn("summarize_residual_diversity_pilot.py", text)
        self.assertIn("reports/residual-diversity/history/${{ github.run_id }}", text)
        self.assertIn("actions/upload-artifact@v4", text)

    def test_scale_workflow_stratifies_the_container_condition_matrix(self):
        text = SCALE_WORKFLOW.read_text(encoding="utf-8")

        for scenario in (
            "single-empty-noshelf",
            "single-empty-shelf",
            "dual-empty",
            "dual-shelf-mixed",
        ):
            self.assertIn(scenario, text)
        self.assertIn("build_scenario_matrix.py", text)
        self.assertIn("experiment/residual-diversity-dataset", text)
        self.assertIn("[skip residual-diversity-scale]", text)
        self.assertIn("--sampling-mode residual_diversity_safe_split", text)
        self.assertIn("--overdraw-factor 3", text)
        self.assertIn("--steps 3 9 15", text)
        self.assertIn("summarize_residual_diversity_matrix.py", text)
        self.assertIn("actions/download-artifact@v4", text)
        self.assertIn(
            "reports/residual-diversity-scale/history/${{ github.run_id }}",
            text,
        )
