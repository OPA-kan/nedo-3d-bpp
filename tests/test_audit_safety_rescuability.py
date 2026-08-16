from __future__ import annotations

import unittest

from scripts.audit_safety_rescuability import apply_bound, trigger_boards


def _row(state: str, score: float, logit: float, safe: float) -> dict:
    return {"state": state, "score": score, "logit": logit, "safe": safe}


class RescuabilityAuditTests(unittest.TestCase):
    def test_trigger_boards_selects_highest_q_incumbent(self) -> None:
        rows = [
            _row("s1", 1.0, -1.0, 0.0),   # incumbent: max score, triggered
            _row("s1", 0.5, 5.0, 1.0),    # escape alternative
            _row("s2", 1.0, 8.0, 1.0),    # not triggered
            _row("s2", 0.9, 9.0, 1.0),
        ]
        boards = trigger_boards(rows)
        self.assertEqual(len(boards), 1)
        incumbent, alts = boards[0]
        self.assertEqual(incumbent["score"], 1.0)
        self.assertEqual(len(alts), 1)

    def test_relative_bound_blocks_near_zero_scores(self) -> None:
        # The Gate 2 inertness mechanism: incumbent score ~0 makes the
        # 15% relative budget vanish while an absolute unit rescues.
        rows = [
            _row("s1", -0.02, -2.0, 0.0),
            _row("s1", -0.66, 6.0, 1.0),
        ]
        boards = trigger_boards(rows)
        relative = apply_bound(boards, relative=0.15)
        absolute = apply_bound(boards, absolute=1.0)
        self.assertEqual(relative["rescued_safely"], 0)
        self.assertEqual(absolute["rescued_safely"], 1)

    def test_needless_swap_cost_is_tracked(self) -> None:
        rows = [
            _row("s1", 0.5, 1.0, 1.0),   # triggered but physically safe
            _row("s1", 0.1, 6.0, 1.0),
        ]
        boards = trigger_boards(rows)
        result = apply_bound(boards, absolute=1.0)
        self.assertEqual(result["needless_swaps"], 1)
        self.assertAlmostEqual(
            result["needless_swap_mean_cost"], 0.4, places=6
        )

    def test_escape_margin_is_respected(self) -> None:
        # Logit 2.5 clears the trigger but not incumbent+2.
        rows = [
            _row("s1", 0.5, 1.0, 0.0),
            _row("s1", 0.4, 2.5, 1.0),
        ]
        boards = trigger_boards(rows)
        _incumbent, alts = boards[0]
        self.assertEqual(alts, [])


if __name__ == "__main__":
    unittest.main()
