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

    def test_runs_never_cancel_each_other(self):
        text = SCALE_WORKFLOW.read_text(encoding="utf-8")

        # Two ways this went wrong. cancel-in-progress killed a run
        # mid-measurement when a push whose jobs all skipped entered the
        # group. And a concurrency group holds at most one PENDING run, so
        # even with cancellation off, dispatching several runs to accumulate
        # states cancelled all but the last before they started. A run is a
        # measurement; the group must not be shared at all.
        self.assertIn("cancel-in-progress: false", text)
        group = text.split("group:", 1)[1].split("\n", 1)[0]
        self.assertIn("github.run_id", group)

    def test_scale_workflow_retains_the_rows_not_only_the_verdict(self):
        text = SCALE_WORKFLOW.read_text(encoding="utf-8")

        # Artifacts expire 90 days out and the trajectory is wall-clock
        # dependent, so rows that live only in artifacts cannot be trained on
        # later and cannot be regenerated either.
        self.assertIn('"$HISTORY_DIR/dataset/$name/"', text)
        self.assertIn("index_replay_corpus.py", text)

    def test_the_run_stops_before_its_own_job_timeout(self):
        text = SCALE_WORKFLOW.read_text(encoding="utf-8")

        # A job killed by the 180-minute timeout never runs its upload step,
        # so every step it already measured is lost. The builder stops itself
        # first and exits cleanly with what it has.
        self.assertIn("--max-seconds", text)
        budget = int(text.split("--max-seconds", 1)[1].split()[0])
        timeout = int(text.split("timeout-minutes:", 1)[1].split()[0])
        self.assertLess(budget, timeout * 60)

    def test_growth_is_bounded_and_fails_loudly_rather_than_silently(self):
        text = SCALE_WORKFLOW.read_text(encoding="utf-8")

        # Unbounded retention is the failure mode that only shows up once the
        # repository is already too big to fix cheaply.
        self.assertIn("--budget-bytes", text)
        self.assertIn("::warning::", text)
        self.assertIn('rm -rf "$HISTORY_DIR/dataset"', text)

    def test_a_lost_push_race_is_retried_rather_than_dropped(self):
        text = SCALE_WORKFLOW.read_text(encoding="utf-8")

        # Queued runs land close together and race on the corpus push;
        # losing the race silently would lose that run's whole dataset.
        self.assertIn("for attempt in 1 2 3 4 5 6; do", text)
        self.assertIn("::error::", text)
