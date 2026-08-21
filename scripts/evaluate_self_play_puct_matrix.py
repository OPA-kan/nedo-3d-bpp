"""Aggregate paired rank-0 versus physical-PUCT Self-Play artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
from typing import Any


def _load_game(path: pathlib.Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    games = manifest.get("games", [])
    if len(games) != 1:
        raise ValueError(f"expected exactly one game in {path}, got {len(games)}")
    return manifest, games[0]


def _game_metrics(game: dict[str, Any]) -> dict[str, Any]:
    evaluation = game.get("evaluation") or {}
    terminal = evaluation.get("terminal_step_metrics") or {}
    shake = evaluation.get("shake_response") or {}
    records = game.get("records", [])
    learning_targets = game.get("learning_targets", [])
    captures_by_step = {
        int(row["step"]): row
        for row in game.get("captures", [])
        if row.get("step") is not None
    }
    search_records = [row for row in records if row.get("search")]
    nonuniform_roots = 0
    informative_policy_state_signatures = set()
    value_discriminating_state_signatures = set()
    for record in search_records:
        visits = [
            int(row.get("visits", 0))
            for row in record["search"].get("policy_target", [])
        ]
        is_nonuniform = bool(visits) and len(set(visits)) > 1
        nonuniform_roots += int(is_nonuniform)
        capture = captures_by_step.get(int(record.get("step", -1)), {})
        signature = capture.get("model_visible_state_signature")
        if is_nonuniform and signature:
            informative_policy_state_signatures.add(signature)
        q_values = {
            round(float(row["q"]), 12)
            for row in record["search"].get("policy_target", [])
            if row.get("q") is not None and int(row.get("visits", 0)) > 0
        }
        if len(q_values) > 1 and signature:
            value_discriminating_state_signatures.add(signature)
    policy_steps = {
        int(row["step"])
        for row in learning_targets
        if row.get("step") is not None and row.get("policy_target_eligible")
    }
    value_steps = {
        int(row["step"])
        for row in learning_targets
        if row.get("step") is not None and row.get("value_target_eligible")
    }
    model_visible_state_signatures = {
        row.get("model_visible_state_signature")
        for row in captures_by_step.values()
        if row.get("model_visible_state_signature")
    }
    policy_state_signatures = {
        captures_by_step[step].get("model_visible_state_signature")
        for step in policy_steps
        if step in captures_by_step
        and captures_by_step[step].get("model_visible_state_signature")
    }
    value_state_signatures = {
        captures_by_step[step].get("model_visible_state_signature")
        for step in value_steps
        if step in captures_by_step
        and captures_by_step[step].get("model_visible_state_signature")
    }
    return {
        "terminal_reason": game.get("terminal_reason"),
        "training_eligible": bool(game.get("training_eligible")),
        "outcome_target_eligible": bool(game.get("outcome_target_eligible")),
        "selected_action_failure": (
            game.get("terminal_reason") == "selected_action_failure"
        ),
        "steps": int(game.get("steps", 0)),
        "placements": int(terminal.get("placed_count", game.get("placements", 0))),
        "reward_player0": float(game.get("rewards", [0.0, 0.0])[0]),
        "attribute_violations": float(
            game.get("new_attribute_violations", 0.0)
        ),
        "fill_score": float(evaluation.get("fill_score", 0.0)),
        "fill_percent_proxy": float(terminal.get("fill_percent_proxy", 0.0)),
        "com_z": float(terminal.get("com_z", 0.0)),
        "shake_peak_kinetic_energy": float(
            shake.get("shake_peak_kinetic_energy", 0.0)
        ),
        "search_decisions": len(search_records),
        "search_simulations": sum(
            int(row["search"].get("simulations", 0))
            for row in search_records
        ),
        "nonuniform_roots": nonuniform_roots,
        "policy_targets": sum(
            bool(row.get("policy_target_eligible"))
            for row in learning_targets
        ),
        "value_targets": sum(
            bool(row.get("value_target_eligible"))
            for row in learning_targets
        ),
        "captured_targets": len(learning_targets),
        "model_visible_state_signatures": sorted(model_visible_state_signatures),
        "policy_state_signatures": sorted(policy_state_signatures),
        "informative_policy_state_signatures": sorted(
            informative_policy_state_signatures
        ),
        "value_discriminating_state_signatures": sorted(
            value_discriminating_state_signatures
        ),
        "value_state_signatures": sorted(value_state_signatures),
    }


def _delta(mcts: dict[str, Any], rank0: dict[str, Any], field: str) -> float:
    return float(mcts[field]) - float(rank0[field])


def _trajectory_signature(game: dict[str, Any]) -> str:
    payload = {
        "actions": [
            row.get("selected_candidate_id") for row in game.get("records", [])
        ],
        "boards": [
            row.get("board_fingerprint") for row in game.get("captures", [])
        ],
        "terminal_reason": game.get("terminal_reason"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]


def summarize(root: pathlib.Path) -> dict[str, Any]:
    pair_rows = []
    for rank0_path in sorted(root.rglob("rank0/manifest.json")):
        pair_dir = rank0_path.parents[1]
        mcts_path = pair_dir / "mcts" / "manifest.json"
        if not mcts_path.exists():
            raise FileNotFoundError(f"missing paired MCTS manifest: {mcts_path}")
        rank0_manifest, rank0_game = _load_game(rank0_path)
        mcts_manifest, mcts_game = _load_game(mcts_path)
        if rank0_manifest.get("case_id") != mcts_manifest.get("case_id"):
            raise ValueError(f"case mismatch in {pair_dir}")
        if rank0_game.get("environment_seed") != mcts_game.get("environment_seed"):
            raise ValueError(f"environment seed mismatch in {pair_dir}")
        for seed_field in ("handoff_seed", "policy_seed"):
            if rank0_game.get(seed_field) != mcts_game.get(seed_field):
                raise ValueError(f"{seed_field} mismatch in {pair_dir}")

        rank0 = _game_metrics(rank0_game)
        mcts = _game_metrics(mcts_game)
        matched_shake_path = pair_dir / "matched-shake.json"
        matched_shake = (
            json.loads(matched_shake_path.read_text(encoding="utf-8"))
            if matched_shake_path.exists() else None
        )
        rank0_actions = [
            row.get("selected_candidate_id") for row in rank0_game.get("records", [])
        ]
        mcts_actions = [
            row.get("selected_candidate_id") for row in mcts_game.get("records", [])
        ]
        first_divergence = next(
            (
                step for step, (left, right) in enumerate(
                    zip(rank0_actions, mcts_actions)
                )
                if left != right
            ),
            None,
        )
        deltas = {
            field: _delta(mcts, rank0, field)
            for field in (
                "reward_player0", "placements", "attribute_violations",
                "fill_score", "fill_percent_proxy", "com_z",
                "shake_peak_kinetic_energy",
            )
        }
        pair_rows.append({
            "pair": pair_dir.name,
            "case_id": rank0_manifest.get("case_id"),
            "environment_seed": rank0_game.get("environment_seed"),
            "first_action_divergence_step": first_divergence,
            "rank0_trajectory_signature": _trajectory_signature(rank0_game),
            "mcts_trajectory_signature": _trajectory_signature(mcts_game),
            "rank0": rank0,
            "mcts": mcts,
            "matched_shake": matched_shake,
            "delta_mcts_minus_rank0": deltas,
        })

    if not pair_rows:
        raise ValueError(f"no paired manifests found below {root}")

    delta_fields = list(pair_rows[0]["delta_mcts_minus_rank0"])
    mean_deltas = {
        field: statistics.mean(
            row["delta_mcts_minus_rank0"][field] for row in pair_rows
        )
        for field in delta_fields
    }
    total_search_decisions = sum(row["mcts"]["search_decisions"] for row in pair_rows)
    total_policy_targets = sum(row["mcts"]["policy_targets"] for row in pair_rows)
    total_value_targets = sum(row["mcts"]["value_targets"] for row in pair_rows)
    total_captured_targets = sum(
        row["mcts"]["captured_targets"] for row in pair_rows
    )
    unique_model_visible_states = {
        signature
        for row in pair_rows
        for signature in row["mcts"]["model_visible_state_signatures"]
    }
    unique_policy_states = {
        signature
        for row in pair_rows
        for signature in row["mcts"]["policy_state_signatures"]
    }
    unique_informative_policy_states = {
        signature
        for row in pair_rows
        for signature in row["mcts"]["informative_policy_state_signatures"]
    }
    unique_value_states = {
        signature
        for row in pair_rows
        for signature in row["mcts"]["value_state_signatures"]
    }
    unique_value_discriminating_states = {
        signature
        for row in pair_rows
        for signature in row["mcts"]["value_discriminating_state_signatures"]
    }
    matched_shake_rows = [
        row["matched_shake"] for row in pair_rows if row["matched_shake"]
    ]
    matched_shake_fields = (
        "peak_kinetic_energy", "peak_kinetic_energy_per_item",
        "peak_kinetic_energy_per_mass", "shifted_fraction",
        "toppled_fraction", "max_shift", "mean_shift", "max_rotation_deg",
    )
    matched_shake_mean_deltas = {}
    for field in matched_shake_fields:
        values = [
            float(row["delta_mcts_minus_rank0"][field])
            for row in matched_shake_rows
            if row.get("delta_mcts_minus_rank0", {}).get(field) is not None
        ]
        matched_shake_mean_deltas[field] = (
            statistics.mean(values) if values else None
        )
    policy_contract_ready = all(
        row["mcts"]["training_eligible"]
        and row["mcts"]["search_decisions"] > 0
        and row["mcts"]["policy_targets"] == row["mcts"]["search_decisions"]
        for row in pair_rows
    )
    value_contract_ready = all(
        row["mcts"]["outcome_target_eligible"]
        and row["mcts"]["value_targets"] == row["mcts"]["captured_targets"]
        for row in pair_rows
    )
    safety_noninferior = (
        not any(row["mcts"]["selected_action_failure"] for row in pair_rows)
        and sum(row["mcts"]["attribute_violations"] for row in pair_rows)
        <= sum(row["rank0"]["attribute_violations"] for row in pair_rows)
    )
    fill_wins = sum(
        row["delta_mcts_minus_rank0"]["fill_score"] > 1e-9
        for row in pair_rows
    )
    fill_losses = sum(
        row["delta_mcts_minus_rank0"]["fill_score"] < -1e-9
        for row in pair_rows
    )
    return {
        "schema_version": 1,
        "experiment": "paired physical PUCT scenario/seed matrix",
        "pairs": pair_rows,
        "aggregate": {
            "pair_count": len(pair_rows),
            "unique_rank0_trajectories": len({
                row["rank0_trajectory_signature"] for row in pair_rows
            }),
            "unique_mcts_trajectories": len({
                row["mcts_trajectory_signature"] for row in pair_rows
            }),
            "diverged_pairs": sum(
                row["first_action_divergence_step"] is not None
                for row in pair_rows
            ),
            "fill_wins": fill_wins,
            "fill_ties": len(pair_rows) - fill_wins - fill_losses,
            "fill_losses": fill_losses,
            "mean_delta_mcts_minus_rank0": mean_deltas,
            "search_decisions": total_search_decisions,
            "search_simulations": sum(
                row["mcts"]["search_simulations"] for row in pair_rows
            ),
            "nonuniform_roots": sum(
                row["mcts"]["nonuniform_roots"] for row in pair_rows
            ),
            "policy_targets": total_policy_targets,
            "value_targets": total_value_targets,
            "captured_targets": total_captured_targets,
            "unique_model_visible_states": len(unique_model_visible_states),
            "unique_policy_states": len(unique_policy_states),
            "unique_informative_policy_states": len(
                unique_informative_policy_states
            ),
            "unique_value_states": len(unique_value_states),
            "unique_value_discriminating_policy_states": len(
                unique_value_discriminating_states
            ),
            "matched_shake_pairs": len(matched_shake_rows),
            "matched_shake_mean_delta_mcts_minus_rank0": (
                matched_shake_mean_deltas
            ),
        },
        "gates": {
            "policy_contract_ready": policy_contract_ready,
            "value_contract_ready": value_contract_ready,
            "data_contract_ready": (
                policy_contract_ready and value_contract_ready
            ),
            "safety_noninferior": safety_noninferior,
            "score_improvement_observed": fill_wins > 0,
            "score_improvement_established": False,
            "score_improvement_note": (
                "Descriptive paired matrix only; no significance or "
                "competition-distribution claim is made."
            ),
        },
    }


def markdown(result: dict[str, Any]) -> str:
    aggregate = result["aggregate"]
    gates = result["gates"]
    delta = aggregate["mean_delta_mcts_minus_rank0"]
    matched = aggregate["matched_shake_mean_delta_mcts_minus_rank0"]
    lines = [
        "# Paired physical PUCT matrix", "",
        f"- pairs: {aggregate['pair_count']}",
        f"- unique rank-0 trajectories: {aggregate['unique_rank0_trajectories']}",
        f"- unique MCTS trajectories: {aggregate['unique_mcts_trajectories']}",
        f"- diverged trajectories: {aggregate['diverged_pairs']}",
        (
            "- fill wins / ties / losses: "
            f"{aggregate['fill_wins']} / {aggregate['fill_ties']} / "
            f"{aggregate['fill_losses']}"
        ),
        f"- mean fill-score delta: {delta['fill_score']:+.6f}",
        f"- mean placed-count delta: {delta['placements']:+.6f}",
        f"- mean attribute-violation delta: {delta['attribute_violations']:+.6f}",
        f"- mean CoM-z delta: {delta['com_z']:+.6f}",
        f"- mean shake-KE delta: {delta['shake_peak_kinetic_energy']:+.6f}",
        f"- matched-count shake pairs: {aggregate['matched_shake_pairs']}",
        (
            "- matched-count mean shake-KE/item delta: "
            + (
                f"{matched['peak_kinetic_energy_per_item']:+.6f}"
                if matched["peak_kinetic_energy_per_item"] is not None
                else "n/a"
            )
        ),
        (
            "- matched-count mean shake-KE/mass delta: "
            + (
                f"{matched['peak_kinetic_energy_per_mass']:+.6f}"
                if matched["peak_kinetic_energy_per_mass"] is not None
                else "n/a"
            )
        ),
        f"- search decisions: {aggregate['search_decisions']}",
        f"- physical simulations: {aggregate['search_simulations']}",
        f"- non-uniform roots: {aggregate['nonuniform_roots']}",
        f"- policy/value targets: {aggregate['policy_targets']} / {aggregate['value_targets']}",
        f"- unique model-visible states: {aggregate['unique_model_visible_states']}",
        f"- unique policy states: {aggregate['unique_policy_states']}",
        (
            "- unique informative policy states: "
            f"{aggregate['unique_informative_policy_states']}"
        ),
        f"- unique terminal-value states: {aggregate['unique_value_states']}",
        (
            "- unique search-value-discriminating policy states: "
            f"{aggregate['unique_value_discriminating_policy_states']}"
        ),
        f"- policy contract ready: {gates['policy_contract_ready']}",
        f"- terminal-value contract ready: {gates['value_contract_ready']}",
        f"- combined P/V contract ready: {gates['data_contract_ready']}",
        f"- safety non-inferior: {gates['safety_noninferior']}",
        f"- score improvement observed: {gates['score_improvement_observed']}",
        f"- score improvement established: {gates['score_improvement_established']}",
        "", "## Pair details", "",
        "| Pair | Divergence | Fill delta | Placed delta | Attr delta | Nonuniform roots |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in result["pairs"]:
        item_delta = row["delta_mcts_minus_rank0"]
        lines.append(
            f"| {row['pair']} | {row['first_action_divergence_step']} | "
            f"{item_delta['fill_score']:+.6f} | "
            f"{item_delta['placements']:+.0f} | "
            f"{item_delta['attribute_violations']:+.0f} | "
            f"{row['mcts']['nonuniform_roots']} |"
        )
    lines.extend(["", gates["score_improvement_note"], ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result = summarize(args.root)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(result), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
