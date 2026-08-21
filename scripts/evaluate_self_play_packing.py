"""Evaluate game validity, behavior, diversity, and degeneration signals."""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import statistics
from typing import Any


def summarize(manifest: dict[str, Any]) -> dict[str, Any]:
    games = list(manifest.get("games", []))
    minimum_block = int(manifest.get("rules", {}).get("minimum_block", 3))
    blocks = [
        int(length) for game in games
        for length in game.get("completed_block_lengths", [])
    ]
    captures = [capture for game in games for capture in game.get("captures", [])]
    handoff_captures = [
        capture for capture in captures if capture.get("is_handoff_state")
    ]
    terminal_reasons = collections.Counter(
        str(game.get("terminal_reason")) for game in games
    )
    player_wins = collections.Counter(
        str(game["winner"]) for game in games if game.get("winner") is not None
    )
    steps = [int(game.get("steps", 0)) for game in games]
    total_steps = sum(steps)
    proposals = sum(int(game.get("candidate_proposals", 0)) for game in games)
    legal_candidates = sum(int(game.get("legal_candidates", 0)) for game in games)
    prefilter_rejections = sum(
        int(game.get("prefilter_rejections", 0)) for game in games
    )
    action_failures = terminal_reasons.get("selected_action_failure", 0)
    early_failures = sum(
        game.get("terminal_reason") == "selected_action_failure"
        and int(game.get("final_block_length", 0)) < minimum_block
        for game in games
    )
    zero_sum = all(
        abs(sum(float(value) for value in game.get("rewards", []))) <= 1e-9
        for game in games
    )
    minimum_respected = all(length >= minimum_block for length in blocks)
    return {
        "schema_version": 1,
        "experiment": "self-play packing game evaluation",
        "validity": {
            "games": len(games),
            "training_eligible_games": sum(
                bool(game.get("training_eligible", True)) for game in games
            ),
            "outcome_target_eligible_games": sum(
                bool(game.get("outcome_target_eligible", False)) for game in games
            ),
            "zero_sum": zero_sum,
            "minimum_block_respected": minimum_respected,
            "handoff_observed": bool(blocks),
        },
        "behavior": {
            "mean_episode_length": statistics.mean(steps) if steps else 0.0,
            "handoffs": sum(int(game.get("handoff_count", 0)) for game in games),
            "block_length_distribution": dict(sorted(collections.Counter(blocks).items())),
            "terminal_reasons": dict(sorted(terminal_reasons.items())),
            "player_wins": dict(sorted(player_wins.items())),
            "non_rank0_actions": sum(
                int(game.get("non_rank0_action_count", 0)) for game in games
            ),
        },
        "distribution": {
            "captured_decision_states": len(captures),
            "captured_handoff_states": len(handoff_captures),
            "unique_board_fingerprints": len({
                row.get("board_fingerprint") for row in captures
                if row.get("board_fingerprint")
            }),
            "unique_model_visible_signatures": len({
                row.get("model_visible_state_signature") for row in captures
                if row.get("model_visible_state_signature")
            }),
            "unique_game_state_signatures": len({
                row.get("game_state_signature") for row in captures
                if row.get("game_state_signature")
            }),
        },
        "degeneracy": {
            "selected_action_failure_rate": (
                action_failures / len(games) if games else 0.0
            ),
            "early_selected_action_failures": early_failures,
            "candidate_proposals": proposals,
            "legal_candidates": legal_candidates,
            "prefilter_rejections": prefilter_rejections,
            "proposal_rejection_rate": (
                prefilter_rejections / proposals if proposals else 0.0
            ),
            "new_attribute_violations_per_step": (
                sum(float(game.get("new_attribute_violations", 0.0)) for game in games)
                / total_steps if total_steps else 0.0
            ),
        },
    }


def markdown(result: dict[str, Any]) -> str:
    valid = result["validity"]
    behavior = result["behavior"]
    distribution = result["distribution"]
    degeneracy = result["degeneracy"]
    return "\n".join([
        "# Self-Play Packing Game pilot", "",
        f"- games: {valid['games']}",
        f"- training-eligible games: {valid['training_eligible_games']}",
        f"- outcome-target-eligible games: {valid['outcome_target_eligible_games']}",
        f"- zero-sum: {valid['zero_sum']}",
        f"- minimum block respected: {valid['minimum_block_respected']}",
        f"- handoff observed: {valid['handoff_observed']}",
        f"- mean episode length: {behavior['mean_episode_length']:.3f}",
        f"- handoffs: {behavior['handoffs']}",
        f"- non-rank0 actions: {behavior['non_rank0_actions']}",
        f"- decision states: {distribution['captured_decision_states']}",
        f"- handoff states: {distribution['captured_handoff_states']}",
        f"- unique boards: {distribution['unique_board_fingerprints']}",
        f"- unique model-visible states: {distribution['unique_model_visible_signatures']}",
        f"- unique game states: {distribution['unique_game_state_signatures']}",
        f"- selected-action failure rate: {degeneracy['selected_action_failure_rate']:.3f}",
        f"- candidate proposals: {degeneracy['candidate_proposals']}",
        f"- physically legal candidates: {degeneracy['legal_candidates']}",
        f"- prefilter rejections: {degeneracy['prefilter_rejections']}",
        f"- proposal rejection rate: {degeneracy['proposal_rejection_rate']:.3f}",
        f"- new attribute violations/step: {degeneracy['new_attribute_violations_per_step']:.6f}",
        "", "The game reward is diagnostic only. Production P/V labels require relabelling these states under the original single-agent packing objective.", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = summarize(json.loads(args.manifest.read_text(encoding="utf-8")))
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.markdown_output.write_text(markdown(result), encoding="utf-8")
    print(args.markdown_output)
    return 0 if (
        result["validity"]["zero_sum"]
        and result["validity"]["minimum_block_respected"]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
