"""Phase 3A conjunction gates: beta proposals vs raw coverage, physically.

On held-out cells' recorded trajectories, both arms propose K actions
per root at equal measurement budget and are validated by one bounded
physical step each (fresh replay):

- coverage arm: the first K raw coverage points (evaluation seed);
- beta arm: sample_budget raw points, feasibility-weighted soft
  resampling of K-floor, plus the permanent floor of raw points.

Gates are a conjunction, never a single number: safe yield above the
coverage arm, stratum diversity maintained, novel-safe-strata discovery
maintained, and recall of the reference run's coverage-safe strata
maintained.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from scripts.beta_proposal import (  # noqa: E402
    beta_feasibility_proposals,
    stratum_entropy,
)
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
    state_snapshot,
)
from scripts.counterfactual_graph import (  # noqa: E402
    state_tensor_from_snapshot,
)
from scripts.coverage_action_sampler import coverage_candidates  # noqa: E402
from scripts.run_single_agent_packing import (  # noqa: E402
    _fresh_env,
    measure_candidates,
)
from scripts.run_self_play_packing import _safe, _status  # noqa: E402
from scripts.train_feasibility_head import FeasibilityEnsemble  # noqa: E402


def _stratum(sample: dict[str, Any]) -> tuple:
    command = sample["command_action"]
    return (
        sample.get("stable_item_index"),
        int(command["container_idx"]),
        int(command["orientation"]),
    )


def evaluate_cell(
    task_config: dict[str, Any], *, case_id: str, environment_seed: int,
    manifest: dict[str, Any], ensemble, eval_seed: int,
    proposals_per_root: int, floor: int, sample_budget: int,
    max_roots: int | None,
) -> list[dict[str, Any]]:
    episode = manifest["episodes"][0]
    env = _fresh_env(task_config)
    rows = []
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        executed: list[Any] = []
        for record in episode.get("records") or []:
            if max_roots is not None and len(rows) >= max_roots:
                break
            step = int(record["step"])
            observed = policy_observation(env, observation)
            snapshot = state_snapshot(
                env, observed, case_id=case_id, step=step
            )
            state_tensor = state_tensor_from_snapshot(snapshot)
            coverage_arm = coverage_candidates(
                observed, coverage_seed=eval_seed + step,
                budget=proposals_per_root, z_mode="volume",
            )
            beta_arm, _base_set = beta_feasibility_proposals(
                observed, state_tensor,
                ensemble=ensemble,
                coverage_seed=eval_seed + step,
                sample_budget=sample_budget,
                keep=proposals_per_root - floor, floor=floor,
                draw_seed=eval_seed * 1000 + step,
            )

            def measure(candidates):
                return measure_candidates(
                    task_config, env=env, observation=observation,
                    candidates=candidates, executed_actions=executed,
                    case_id=case_id, environment_seed=environment_seed,
                    step=step, root_id=record["root_id"],
                )

            coverage_measured = measure(coverage_arm)
            beta_measured = measure(beta_arm)
            # reference: safe strata the collection run's own measurement
            # found (legacy + full coverage budget)
            reference = record.get("measurement_samples") or []
            reference_safe = {
                _stratum(sample) for sample in reference
                if sample.get("physical_safe")
                and sample.get("command_action") is not None
            }
            legacy_safe = {
                _stratum(sample) for sample in reference
                if sample.get("physical_safe")
                and sample.get("command_action") is not None
                and sample["root_candidate_provenance"]["source"]
                == "legacy_provider"
            }

            def arm_summary(candidates, measured):
                safe = [row for row in measured if row["physical_safe"]]
                safe_strata = {_stratum(row) for row in safe}
                return {
                    "proposed": len(measured),
                    "safe": len(safe),
                    "stratum_entropy": stratum_entropy(candidates),
                    "novel_safe_strata": len(safe_strata - legacy_safe),
                    "reference_recall": (
                        len(safe_strata & reference_safe)
                        / len(reference_safe)
                        if reference_safe else None
                    ),
                }

            rows.append({
                "step": step,
                "coverage": arm_summary(coverage_arm, coverage_measured),
                "beta": arm_summary(beta_arm, beta_measured),
            })
            print(
                f"root step={step} "
                f"cov_safe={rows[-1]['coverage']['safe']}"
                f"/{rows[-1]['coverage']['proposed']} "
                f"beta_safe={rows[-1]['beta']['safe']}"
                f"/{rows[-1]['beta']['proposed']}",
                flush=True,
            )
            action = record["action"]
            observation, _r, terminated, truncated, info = env.step(action)
            executed.append(action)
            if terminated or truncated or not _safe(_status(info)):
                break
    finally:
        env.close()
    return rows


def summarize(cells: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = [row for cell_rows in cells.values() for row in cell_rows]

    def aggregate(arm: str) -> dict[str, Any]:
        proposed = sum(row[arm]["proposed"] for row in rows)
        safe = sum(row[arm]["safe"] for row in rows)
        recalls = [
            row[arm]["reference_recall"] for row in rows
            if row[arm]["reference_recall"] is not None
        ]
        return {
            "safe_yield": safe / proposed if proposed else None,
            "safe": safe,
            "proposed": proposed,
            "mean_stratum_entropy": (
                sum(row[arm]["stratum_entropy"] for row in rows) / len(rows)
            ),
            "novel_safe_strata": sum(
                row[arm]["novel_safe_strata"] for row in rows
            ),
            "mean_reference_recall": (
                sum(recalls) / len(recalls) if recalls else None
            ),
        }

    coverage = aggregate("coverage")
    beta = aggregate("beta")
    return {
        "roots": len(rows),
        "coverage": coverage,
        "beta": beta,
        "gates": {
            "safe_yield_above_coverage": (
                beta["safe_yield"] is not None
                and coverage["safe_yield"] is not None
                and beta["safe_yield"] > coverage["safe_yield"]
            ),
            "diversity_maintained": (
                beta["mean_stratum_entropy"]
                >= 0.8 * coverage["mean_stratum_entropy"]
            ),
            "discovery_maintained": (
                beta["novel_safe_strata"] >= coverage["novel_safe_strata"]
            ),
            "recall_maintained": (
                beta["mean_reference_recall"] is not None
                and coverage["mean_reference_recall"] is not None
                and beta["mean_reference_recall"]
                >= coverage["mean_reference_recall"]
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cell", action="append", required=True,
        metavar="CELL=CONFIG:CASE:MANIFEST",
    )
    parser.add_argument("--model-dir", type=pathlib.Path, required=True)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--eval-seed", type=int, default=777000)
    parser.add_argument("--proposals-per-root", type=int, default=12)
    parser.add_argument("--floor", type=int, default=3)
    parser.add_argument("--sample-budget", type=int, default=48)
    parser.add_argument("--max-roots", type=int, default=None)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    ensemble = FeasibilityEnsemble(args.model_dir)
    agent_module = load_agent_module()  # noqa: F841  (env parity with runner)
    cells = {}
    for spec in args.cell:
        cell, _, rest = spec.partition("=")
        config_path, case_id, manifest_path = rest.split(":")
        config = json.loads(pathlib.Path(config_path).read_text())
        task_config = config[case_id] if case_id in config else config
        manifest = json.loads(pathlib.Path(manifest_path).read_text())
        cells[cell] = evaluate_cell(
            task_config, case_id=case_id,
            environment_seed=args.environment_seed,
            manifest=manifest, ensemble=ensemble,
            eval_seed=args.eval_seed,
            proposals_per_root=args.proposals_per_root,
            floor=args.floor, sample_budget=args.sample_budget,
            max_roots=args.max_roots,
        )
    report = {
        "schema_version": 1,
        "contract": "beta_3a_conjunction_gates_v1",
        "acceptance_model_id": ensemble.model_id,
        "proposals_per_root": args.proposals_per_root,
        "floor": args.floor,
        "sample_budget": args.sample_budget,
        "cells": cells,
        "summary": summarize(cells),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
