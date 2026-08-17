import json
import pathlib
import tempfile
import unittest

from scripts.analyze_physics_probe import (
    collect_episodes,
    join_events,
    rank_auc,
    summarize,
)


def probe_event(step, angle, displacement, elapsed=0.05):
    predicted_safe = None
    if angle is not None and displacement is not None:
        predicted_safe = angle <= 30.0 and displacement <= 0.3
    return {
        "event": "physics_probe",
        "step": step,
        "angle_deg": angle,
        "displacement": displacement,
        "predicted_safe": predicted_safe,
        "scene_bodies": 7,
        "elapsed_seconds": elapsed if angle is not None else None,
    }


def step_metric(step, angle, displacement):
    return {
        "step": step,
        "settle_angle_deg": angle,
        "settle_displacement_norm": displacement,
    }


def write_run(
    root,
    label,
    arm,
    case_id,
    events,
    step_metrics,
    terminal_channel,
    placed,
    steps,
):
    run_dir = root / "runs" / label
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "policy-trace.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    (run_dir / "evaluation_results.json").write_text(
        json.dumps(
            {case_id: {"evaluation": {"step_metrics": step_metrics}}}
        ),
        encoding="utf-8",
    )
    row = {
        "label": label,
        "arm": arm,
        "repeat": 0,
        "process_returncode": 0,
        "cases": {
            case_id: {
                "terminal_channel": terminal_channel,
                "placed_count": placed,
                "steps": steps,
                "policy_seconds": 10.0,
            }
        },
    }
    with (root / "rows.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


class JoinTests(unittest.TestCase):
    def test_joins_by_step_index_and_audits_the_rest(self):
        events = [
            {
                "step": 0,
                "angle_deg": 1.0,
                "displacement": 0.01,
                "predicted_safe": True,
                "elapsed_seconds": 0.04,
            },
            {
                "step": 1,
                "angle_deg": None,
                "displacement": None,
                "predicted_safe": None,
                "elapsed_seconds": None,
            },
            {
                "step": 9,
                "angle_deg": 2.0,
                "displacement": 0.02,
                "predicted_safe": True,
                "elapsed_seconds": 0.04,
            },
        ]
        metrics = [step_metric(0, 0.5, 0.005), step_metric(1, 0.5, 0.005)]

        joined, audit = join_events(events, metrics)

        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0]["step"], 0)
        self.assertEqual(audit["events"], 3)
        self.assertEqual(audit["events_failed"], 1)
        self.assertEqual(audit["events_out_of_range"], 1)
        self.assertEqual(audit["step_field_mismatches"], 0)

    def test_step_field_mismatch_is_refused_not_misjoined(self):
        events = [
            {
                "step": 0,
                "angle_deg": 1.0,
                "displacement": 0.01,
                "predicted_safe": True,
                "elapsed_seconds": 0.04,
            }
        ]
        metrics = [step_metric(5, 0.5, 0.005)]

        joined, audit = join_events(events, metrics)

        self.assertEqual(joined, [])
        self.assertEqual(audit["step_field_mismatches"], 1)

    def test_predicted_score_is_the_normalized_max(self):
        events = [
            {
                "step": 0,
                "angle_deg": 15.0,
                "displacement": 0.24,
                "predicted_safe": True,
                "elapsed_seconds": 0.04,
            }
        ]
        metrics = [step_metric(0, 40.0, 0.1)]

        joined, _audit = join_events(events, metrics)

        self.assertAlmostEqual(joined[0]["predicted_score"], 0.8)
        self.assertFalse(joined[0]["predicted_unsafe"])
        self.assertTrue(joined[0]["actual_unsafe"])


class RankAucTests(unittest.TestCase):
    def test_perfect_separation_and_ties(self):
        self.assertEqual(rank_auc([2.0], [0.1, 0.2]), 1.0)
        self.assertEqual(rank_auc([1.0], [1.0]), 0.5)
        self.assertIsNone(rank_auc([], [1.0]))


class SummarizeTests(unittest.TestCase):
    def build_wave(self, root):
        # Probe arm: a topple episode where the probe called the fatal
        # step and every safe step correctly.
        write_run(
            root,
            "b000-k20-physics_probe-r0",
            "physics_probe",
            "b000-k20",
            [
                probe_event(0, 1.0, 0.01),
                probe_event(1, 2.0, 0.02),
                probe_event(2, None, None),
                probe_event(3, 60.0, 0.5),
            ],
            [
                step_metric(0, 0.4, 0.004),
                step_metric(1, 0.6, 0.006),
                step_metric(2, 0.5, 0.005),
                step_metric(3, 80.0, 0.6),
            ],
            terminal_channel="topple",
            placed=3,
            steps=4,
        )
        # Base arm floor for the same case.
        write_run(
            root,
            "b000-k20-base-r0",
            "base",
            "b000-k20",
            [],
            [],
            terminal_channel="safe_end",
            placed=3,
            steps=4,
        )

    def test_gates_and_verdict_on_a_clean_wave(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.build_wave(root)
            episodes = collect_episodes(root)
            summary = summarize(episodes, "physics_probe", "base")

        self.assertEqual(summary["probe_episodes"], 1)
        self.assertEqual(summary["base_episodes"], 1)
        self.assertEqual(summary["joined_steps"], 3)
        self.assertEqual(summary["actual_unsafe_steps"], 1)
        self.assertEqual(summary["join_audit"]["events_failed"], 1)
        self.assertEqual(summary["pooled_auc"], 1.0)
        self.assertEqual(summary["fatal_steps_total"], 1)
        self.assertEqual(summary["fatal_recall"], 1.0)
        self.assertGreater(
            summary["mean_predicted"]["displacement_unsafe"],
            summary["mean_predicted"]["displacement_safe"],
        )
        self.assertGreater(
            summary["mean_predicted"]["angle_unsafe"],
            summary["mean_predicted"]["angle_safe"],
        )
        footprint = summary["zero_footprint_by_case"]["b000-k20"]
        self.assertTrue(footprint["placed_within_floor"])
        self.assertTrue(footprint["steps_within_floor"])
        self.assertEqual(
            summary["gates"],
            {
                "discrimination": True,
                "fatal_recall": True,
                "calibration_direction": True,
                "zero_footprint": True,
            },
        )
        self.assertEqual(
            summary["verdict"],
            "fidelity_pass_behavioral_experiment_licensed",
        )
        self.assertEqual(
            summary["confusion"],
            {
                "predicted_unsafe_actual_unsafe": 1,
                "predicted_safe_actual_unsafe": 0,
                "predicted_unsafe_actual_safe": 0,
                "predicted_safe_actual_safe": 2,
            },
        )

    def test_missing_base_arm_leaves_footprint_gate_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.build_wave(root)
            episodes = collect_episodes(root)
            summary = summarize(episodes, "physics_probe", "no_such_arm")

        self.assertIsNone(summary["gates"]["zero_footprint"])
        self.assertEqual(
            summary["verdict"], "incomplete_wave_gates_not_evaluable"
        )

    def test_probe_below_base_floor_fails_zero_footprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.build_wave(root)
            # A second base replicate with a higher floor cannot lower
            # the minimum; a probe episode below the floor must fail.
            write_run(
                root,
                "b000-k20-base-r1",
                "base",
                "b000-k20",
                [],
                [],
                terminal_channel="safe_end",
                placed=5,
                steps=6,
            )
            write_run(
                root,
                "b000-k20-physics_probe-r1",
                "physics_probe",
                "b000-k20",
                [probe_event(0, 1.0, 0.01)],
                [step_metric(0, 0.4, 0.004)],
                terminal_channel="slide",
                placed=1,
                steps=2,
            )
            episodes = collect_episodes(root)
            summary = summarize(episodes, "physics_probe", "base")

        self.assertFalse(summary["gates"]["zero_footprint"])
        self.assertEqual(summary["verdict"], "fidelity_fail_line_closed")


if __name__ == "__main__":
    unittest.main()
