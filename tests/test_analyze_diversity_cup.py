import json
import pathlib
import tempfile
import unittest

from scripts.analyze_diversity_cup import analyze

FINAL = {
    "placed_count": 10, "fill_score_proxy": 9.0,
    "soft_covered_by_other": 0, "priority_covered_by_other": 0,
    "priority_misrouted": 0, "center_of_mass_z": 0.5,
    "post_shake_max_shift": 0.1, "post_shake_items_toppled": 0,
}


def manifest(
    policy, fingerprints, mining=None, final=None,
    *, termination="stream_exhausted", genuine_termination=True,
):
    records = []
    for index, fingerprint in enumerate(fingerprints):
        record = {
            "step": index, "board_fingerprint": fingerprint,
            "snapshot_path": f"step-{index:03d}-state.json",
            "root_id": f"root-{index}",
        }
        if mining and index in mining:
            record["mining"] = mining[index]
        records.append(record)
    episode = {
        "steps": len(records), "termination": termination,
        "genuine_termination": genuine_termination,
        "records": records,
        "final_metrics": dict(final or FINAL),
    }
    if mining is not None:
        forked = [m for m in mining.values() if "pair_rows" in m]
        episode["mining_disagreements"] = len(mining)
        episode["mining_forks"] = len(forked)
        episode["mining_strict_pairs"] = sum(
            1 for m in forked if m.get("winner_candidate_id")
        )
        episode["mining_fork_physical_step_equivalents"] = 2_000_000
    return {
        "case_id": "m-x", "environment_seed": 42, "policy": policy,
        "episodes": [episode],
    }


def mining_event(winner, soft=0.0):
    return {
        "rule_candidate_id": "a", "champion_candidate_id": "b",
        "champion_probability": 0.7,
        "terminal_truth_complete": True,
        "terminal_pareto_candidates": [winner] if winner else ["a", "b"],
        "winner_candidate_id": winner,
        "pair_rows": [
            {"root_candidate_id": "a", "terminal_genuine": True,
             "terminal_termination": "stream_exhausted",
             "terminal_vector": {"fill_gain": 1.0,
                                 "soft_violation_gain": soft}},
            {"root_candidate_id": "b", "terminal_genuine": True,
             "terminal_termination": "stream_exhausted",
             "terminal_vector": {"fill_gain": 1.2,
                                 "soft_violation_gain": 0.0}},
        ],
    }


def exact_agent_mining_event(winner, policy="current-agent"):
    event = mining_event(winner)
    event["actor_policy"] = policy
    event["actor_candidate_id"] = event.pop("rule_candidate_id")
    return event


class DiversityCupAnalysisTests(unittest.TestCase):
    def build(self, root: pathlib.Path):
        cell = root / "cup-cell-dual-empty-permute-000-419"
        for horse, payload in (
            ("learned", manifest("learned", ["f1", "f2", "f3"])),
            ("current-agent", manifest(
                "current-agent", ["a1", "a2", "a3"],
                mining={1: exact_agent_mining_event("a", "rule-alpha")},
                final={**FINAL, "fill_score_proxy": 14.25,
                       "placed_count": 12},
            )),
            ("rule-alpha", manifest(
                "rule-alpha", ["r1", "r2", "r3"],
                mining={1: exact_agent_mining_event("a")},
                final={**FINAL, "fill_score_proxy": 15.0,
                       "placed_count": 13},
            )),
            ("rule-grid", manifest(
                "rule-grid", ["f1", "g2", "g3"],
                mining={
                    1: mining_event("b", soft=1.0),
                    2: {"skipped": "fork_budget_exhausted",
                        "rule_candidate_id": "a",
                        "champion_candidate_id": "b"},
                },
            )),
            ("rule-lowcog", manifest(
                "rule-lowcog", ["f1", "f2"], mining={},
                final={**FINAL, "placed_count": 9},
            )),
            ("rule-edge", manifest(
                "rule-edge", ["e1"], mining={0: mining_event(None)},
            )),
        ):
            target = cell / horse / "rollout"
            target.mkdir(parents=True)
            (target / "manifest.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

    def test_metrics_tables_and_side_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.build(root)
            report = analyze(root)

        totals = report["stud_totals"]
        # grid visited two boards the champion never reached
        self.assertEqual(totals["rule-grid"]["novel_boards"], 2)
        self.assertAlmostEqual(
            totals["rule-grid"]["novel_board_rate"], 2 / 3
        )
        # one strict pair from one executed fork; the budget-exhausted
        # disagreement still counts as a disagreement
        self.assertEqual(totals["rule-grid"]["disagreements"], 2)
        self.assertEqual(totals["rule-grid"]["forks"], 1)
        self.assertEqual(totals["rule-grid"]["strict_pairs"], 1)
        self.assertAlmostEqual(
            totals["rule-grid"]["pairs_per_million_step_equivalents"], 0.5
        )
        # the tied fork mines nothing
        self.assertEqual(totals["rule-edge"]["strict_pairs"], 0)
        # lowcog trails the champion on placed only -> champion wins
        table = report["race_tables"]["learned_vs_rule-lowcog"]
        self.assertEqual(table["counts"]["challenger_wins"], 1)
        # identical vectors -> equal
        table = report["race_tables"]["learned_vs_rule-grid"]
        self.assertEqual(table["counts"]["equal"], 1)
        # side corpus keeps only strict-winner forks
        self.assertEqual(report["side_corpus_pairs"], 3)
        self.assertEqual(totals["current-agent"]["strict_pairs"], 1)
        self.assertEqual(
            report["max_terminal_fill"]["horse"], "rule-alpha"
        )
        self.assertEqual(report["max_terminal_fill"]["fill_score_proxy"], 15.0)
        self.assertEqual(
            report["max_terminal_fill_by_horse"]["learned"][
                "fill_score_proxy"
            ],
            9.0,
        )
        # event coverage saw the soft-violation terminal
        grid_row = next(
            row for row in report["stud_rows"]
            if row["horse"] == "rule-grid"
        )
        self.assertEqual(
            grid_row["event_coverage"]["soft_violation_gain"], 1
        )

    def test_non_genuine_termination_is_unmeasured_not_a_crash(self):
        # current-agent always executes its own action, including a
        # physically rejected one, so its episode can legitimately end
        # without a shake test (no post_shake_* heads). The race table
        # must record that pairing as "unmeasured" rather than raising.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            cell = root / "cup-cell-dual-empty-permute-000-419"
            for horse, payload in (
                ("learned", manifest("learned", ["f1"])),
                ("current-agent", manifest(
                    "current-agent", ["a1"],
                    final={"placed_count": 3, "fill_score_proxy": 2.0,
                           "soft_covered_by_other": 0,
                           "priority_covered_by_other": 0,
                           "priority_misrouted": 0},
                    termination="selected_action_failure",
                    genuine_termination=False,
                )),
            ):
                target = cell / horse / "rollout"
                target.mkdir(parents=True)
                (target / "manifest.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )
            report = analyze(root)

        table = report["race_tables"]["learned_vs_current-agent"]
        self.assertEqual(table["relations"]["dual-empty-permute-000-419"],
                          "unmeasured")
        self.assertEqual(table["counts"]["unmeasured"], 1)
        self.assertEqual(sum(table["counts"].values()), 1)


if __name__ == "__main__":
    unittest.main()
