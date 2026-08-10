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

        # The core 1/2-container x shelf/no-shelf cells are the guard's
        # requirement and must stay. Scenarios beyond them are additive, so
        # this pins the floor rather than the exact list.
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
        self.assertIn("summarize_residual_diversity_matrix.py", text)
        self.assertIn("actions/download-artifact@v4", text)
        self.assertIn(
            "reports/residual-diversity-scale/history/${{ github.run_id }}",
            text,
        )

    def test_scale_workflow_carries_the_priority_and_preloaded_conditions(
        self,
    ):
        text = SCALE_WORKFLOW.read_text(encoding="utf-8")

        # Dedicated-priority and pre-loaded containers are conditioning
        # variables the core 2x2 has no instance of at all. Dropping them
        # would silently narrow what any learner is trained across.
        for scenario in (
            "single-preloaded",
            "dual-dedicated-priority",
            "dual-preloaded-dedicated",
            "dual-full-stream",
        ):
            self.assertIn(scenario, text)

    def test_scale_workflow_measures_several_steps_per_scenario(self):
        text = SCALE_WORKFLOW.read_text(encoding="utf-8")

        # Distinct states are what the learnability audit is short of, and
        # steps are one of the two axes that produce them. The count is a
        # dispatch input so scaling does not need a code change; the default
        # must still be more than one step.
        self.assertIn("--steps ${{ inputs.steps ||", text)
        default = text.split('default: "3', 1)[1].split('"', 1)[0]
        self.assertGreaterEqual(len(("3" + default).split()), 3)

    def test_a_push_does_not_cancel_a_measurement_already_running(self):
        text = SCALE_WORKFLOW.read_text(encoding="utf-8")

        # The skip guard is a job-level `if` and cancellation is run-level, so
        # a push whose jobs all skip once killed a run mid-measurement and
        # committed a partial corpus under a "fail" verdict.
        self.assertIn("cancel-in-progress: false", text)

    def test_scale_workflow_retains_the_rows_not_only_the_verdict(self):
        text = SCALE_WORKFLOW.read_text(encoding="utf-8")

        # Artifacts expire 90 days out and the trajectory is wall-clock
        # dependent, so rows that live only in artifacts cannot be trained on
        # later and cannot be regenerated either.
        self.assertIn('"$HISTORY_DIR/dataset/$name/"', text)
        self.assertIn("index_replay_corpus.py", text)
