from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from scripts.analyze_safety_shadow import (
    collect_episodes,
    rank_auc,
    summarize,
)


def _write_episode(
    root: pathlib.Path,
    label: str,
    case_id: str,
    channel: str,
    logits: list[float],
    returncode: int = 0,
) -> None:
    """Materialize one run_risk_ablation output dir with a shadow trace."""
    out_dir = root / label
    run_dir = out_dir / "runs" / label
    run_dir.mkdir(parents=True)
    row = {
        "label": label,
        "arm": "base",
        "repeat": 0,
        "process_returncode": returncode,
        "cases": {
            case_id: {
                "terminal_channel": channel,
                "steps": len(logits) + 1,
                "placed_count": len(logits),
            }
        },
    }
    (out_dir / "rows.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8"
    )
    with (run_dir / "policy-trace.jsonl").open("w", encoding="utf-8") as f:
        for step, logit in enumerate(logits):
            f.write(json.dumps({"event": "decision", "step": step}) + "\n")
            f.write(
                json.dumps(
                    {
                        "event": "safety_shadow",
                        "step": step,
                        "logit": logit,
                        "candidate_kind": "settled" if step % 2 else "release",
                    }
                )
                + "\n"
            )


class AnalyzeSafetyShadowTests(unittest.TestCase):
    def test_labeling_follows_the_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write_episode(root, "e1", "b000-k15", "safe_end", [1.0, 2.0])
            _write_episode(root, "e2", "c000-k1", "topple", [3.0, -1.0])
            _write_episode(
                root, "e3", "c001-k1", "transport_invalid", [4.0, 5.0]
            )
            episodes = collect_episodes(root)
        by_label = {episode["label"]: episode for episode in episodes}
        self.assertEqual(
            [event["label"] for event in by_label["e1"]["events"]],
            ["surviving", "surviving"],
        )
        self.assertEqual(
            [event["label"] for event in by_label["e2"]["events"]],
            ["surviving", "fatal"],
        )
        # transport_invalid dies through the fixed fallback, which has no
        # shadow event: no fatal label may be assigned.
        self.assertEqual(
            [event["label"] for event in by_label["e3"]["events"]],
            ["surviving", "surviving"],
        )

    def test_rank_auc(self) -> None:
        self.assertEqual(rank_auc([2.0, 3.0], [1.0]), 1.0)
        self.assertEqual(rank_auc([1.0], [1.0]), 0.5)
        self.assertEqual(rank_auc([1.0, 3.0], [2.0]), 0.5)
        self.assertIsNone(rank_auc([], [1.0]))

    def test_summary_gates_and_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            # 15 completed episodes over b and c configs; 5 fatal endings
            # whose final logits sit below every surviving logit.
            for index in range(10):
                _write_episode(
                    root, f"safe{index}", "b000-k20", "safe_end",
                    [6.0, 7.0, 8.0],
                )
            for index in range(5):
                _write_episode(
                    root, f"dead{index}", "c000-k1", "topple",
                    [6.5, -2.0],
                )
            episodes = collect_episodes(root)
            summary = summarize(episodes)
        self.assertEqual(summary["episodes_completed_with_shadow"], 15)
        self.assertEqual(summary["fatal_events"], 5)
        self.assertEqual(summary["pooled_auc_surviving_over_fatal"], 1.0)
        self.assertTrue(all(summary["gates"].values()))
        self.assertEqual(
            summary["verdict"], "calibration_pass_gate2_licensed"
        )
        band = summary["calibration_by_logit_band"]["below_0"]
        self.assertEqual(band["n"], 5)
        self.assertEqual(band["empirical_survival"], 0.0)
        self.assertEqual(len(summary["fatal_event_detail"]), 5)

    def test_underpowered_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for index in range(16):
                _write_episode(
                    root, f"s{index}",
                    "b000-k15" if index % 2 else "c000-k1",
                    "safe_end", [5.0],
                )
            summary = summarize(collect_episodes(root))
        self.assertEqual(summary["fatal_events"], 0)
        self.assertEqual(summary["verdict"], "underpowered_extend_wave")

    def test_failed_process_is_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            _write_episode(
                root, "bad", "b000-k15", "topple", [1.0], returncode=1
            )
            summary = summarize(collect_episodes(root))
        self.assertEqual(summary["episodes_completed_with_shadow"], 0)
        self.assertEqual(summary["fatal_events"], 0)


if __name__ == "__main__":
    unittest.main()
