import json
import pathlib
import tempfile
import unittest

from scripts.render_self_play_replay import build_payload, render_html


class SelfPlayReplayRendererTests(unittest.TestCase):
    def test_builds_ordered_frames_with_game_and_attribute_overlays(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            game = root / "game-000"
            game.mkdir()
            snapshot = {
                "observation": {"container_list": [{
                    "index": 0, "length": 2, "width": 1, "height": 1.5,
                    "cut_x": .44, "cut_y": .4, "thickness": .04,
                    "center": [0, 0, 0.75], "is_prioritized": True,
                    "shelf": True,
                    "packed_items": [{
                        "index": 7, "length": .4, "width": .3, "height": .2,
                        "pos": [0, 0, .1], "is_soft": True,
                        "is_prioritized": False,
                    }],
                }]},
                "self_play_game": {
                    "player_to_move": 1, "block_length": 0,
                    "is_handoff_state": True,
                },
            }
            (game / "step-000-state.json").write_text(
                json.dumps(snapshot), encoding="utf-8"
            )
            manifest = {
                "selection": {"mode": "temperature"},
                "games": [{
                    "starting_player": 0, "terminal_reason": "max_steps",
                    "rewards": [-5, 5],
                    "captures": [{
                        "step": 0, "snapshot_path": "step-000-state.json",
                    }],
                    "records": [{
                        "step": 0, "player": 1, "selected_rank": 2,
                        "candidate_count": 3, "handoff": True,
                        "attribute_reward": {"new_violations": 1},
                    }],
                }],
            }
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")

            payload = build_payload(path, 0)

        frame = payload["frames"][0]
        self.assertEqual(frame["player"], 1)
        self.assertEqual(frame["selected_rank"], 2)
        self.assertTrue(frame["is_handoff_state"])
        self.assertTrue(frame["containers"][0]["items"][0]["is_soft"])
        self.assertTrue(frame["containers"][0]["has_shelf"])
        self.assertEqual(frame["containers"][0]["cut_x"], .44)
        self.assertEqual(frame["containers"][0]["cut_y"], .4)
        self.assertEqual(frame["containers"][0]["thickness"], .04)
        self.assertEqual(frame["new_violations"], 1)

    def test_html_is_standalone_and_has_replay_controls(self):
        html = render_html({"title": "demo", "frames": [], "game": {}})
        self.assertIn("<canvas", html)
        self.assertIn('id="play"', html)
        self.assertIn('id="step"', html)
        self.assertIn("SELF_PLAY_REPLAY", html)
        self.assertIn("PRIORITY", html)
        self.assertIn("SHELF", html)
        self.assertIn("function containerWire", html)
        self.assertIn("ULD CUT PROFILE", html)
        self.assertNotIn("https://", html)


if __name__ == "__main__":
    unittest.main()
