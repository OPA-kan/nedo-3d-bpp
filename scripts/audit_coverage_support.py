"""Phase 1B: physically audit coverage support against the legacy provider.

For sampled roots of an existing run, generate strategy-free coverage
candidates (both z modes) and a wide legacy proposal set at the same
observed state, validate everything through the same fresh-replay
physical filter, and measure per z mode:

- ``P(safe | coverage)`` — how often geometry-only sampling lands a
  physically legal placement;
- legacy-safe recovery — for every legacy-safe action, the in-plane
  distance to the nearest safe coverage action in the same (item,
  container, orientation) stratum, and the share recovered within
  tolerance;
- coverage-only discoveries — safe coverage actions in strata where the
  legacy provider offered nothing safe: direct evidence of support the
  legacy generator cannot see.

Nothing here selects or executes actions; this is measurement only.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

from scripts.build_counterfactual_graph import (  # noqa: E402
    build_candidate_provider,
)
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
)
from scripts.coverage_action_sampler import (  # noqa: E402
    COVERAGE_GENERATOR,
    coverage_candidates,
)
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _safe,
    _status,
    build_exact_physical_legal_filter,
)

Z_MODES = ("volume", "release_top")


def _stratum(action: dict[str, Any], stable_item: Any) -> tuple:
    return (
        stable_item,
        int(action["container_idx"]),
        int(action["orientation"]),
    )


def _xy_distance(a: dict[str, Any], b: dict[str, Any]) -> float:
    # In-plane distance only: commanded z differs between settled-style
    # legacy actions and release-style coverage, while the settled outcome
    # is governed by (x, y) within the stratum.
    return math.sqrt(sum(
        (float(x) - float(y)) ** 2
        for x, y in zip(a["place_pos"][:2], b["place_pos"][:2])
    ))


def _stable_item(candidate: Any) -> Any:
    selection = (
        candidate.get("selection", {})
        if isinstance(candidate, dict)
        else dict(candidate.selection)
    )
    return selection.get("stable_item_index")


def _safe_actions(rows: list[dict[str, Any]]) -> list[tuple[tuple, dict]]:
    return [
        (
            _stratum(
                _candidate_action(row["candidate"]),
                _stable_item(row["candidate"]),
            ),
            _candidate_action(row["candidate"]),
        )
        for row in rows if row["safe"]
    ]


def audit_root(
    *, env, observation, executed_actions, step: int,
    provider, legal_filter, coverage_budget: int, coverage_seed: int,
    legacy_limit: int, recovery_tolerance: float,
) -> dict[str, Any]:
    observed = policy_observation(env, observation)

    def validate(candidates):
        retained, _audits = legal_filter(
            env=env, observation=observation, candidates=candidates,
            actions=list(executed_actions), step=step,
        )
        safe_ids = {id(c) for c in retained}
        return [
            {"candidate": candidate, "safe": id(candidate) in safe_ids}
            for candidate in candidates
        ]

    legacy_rows = validate(list(provider(env, observation, int(legacy_limit))))
    legacy_safe = _safe_actions(legacy_rows)
    legacy_safe_strata = {stratum for stratum, _a in legacy_safe}

    modes = {}
    for z_mode in Z_MODES:
        rows = validate(coverage_candidates(
            observed, coverage_seed=coverage_seed, budget=coverage_budget,
            z_mode=z_mode,
        ))
        coverage_safe = _safe_actions(rows)
        by_stratum: dict[tuple, list[dict[str, Any]]] = {}
        for stratum, action in coverage_safe:
            by_stratum.setdefault(stratum, []).append(action)
        recoveries = []
        for stratum, action in legacy_safe:
            nearest = None
            for coverage_action in by_stratum.get(stratum, []):
                distance = _xy_distance(action, coverage_action)
                if nearest is None or distance < nearest:
                    nearest = distance
            recoveries.append({
                "stratum": list(stratum),
                "nearest_safe_coverage_xy_distance": nearest,
                "recovered": (
                    nearest is not None and nearest <= recovery_tolerance
                ),
            })
        modes[z_mode] = {
            "proposed": len(rows),
            "safe": sum(row["safe"] for row in rows),
            "safe_strata": len(by_stratum),
            "legacy_safe_recovery": recoveries,
            "coverage_only_safe_strata": [
                list(stratum) for stratum in sorted(
                    set(by_stratum) - legacy_safe_strata
                )
            ],
        }
    return {
        "step": int(step),
        "legacy": {
            "proposed": len(legacy_rows),
            "safe": len(legacy_safe),
            "safe_strata": len(legacy_safe_strata),
        },
        "coverage": modes,
    }


def run_audit(
    agent_module, task_config: dict[str, Any], *, case_id: str,
    environment_seed: int, manifest: dict[str, Any],
    coverage_budget: int, coverage_seed: int, legacy_limit: int,
    recovery_tolerance: float, max_roots: int | None,
    attempt_budget: int,
) -> dict[str, Any]:
    from src.ground_handling.env import GroundHandlingEnv

    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    legal_filter = build_exact_physical_legal_filter(
        task_config, case_id=case_id, environment_seed=environment_seed,
    )
    game = manifest["games"][0]
    records = sorted(game.get("records") or [], key=lambda r: int(r["step"]))
    roots = []
    env = GroundHandlingEnv(
        config=copy.deepcopy(task_config), verbose=False, render_mode=None,
    )
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        executed: list[Any] = []
        for record in records:
            if max_roots is not None and len(roots) >= max_roots:
                break
            step = int(record["step"])
            result = audit_root(
                env=env, observation=observation,
                executed_actions=executed, step=step,
                provider=provider, legal_filter=legal_filter,
                coverage_budget=coverage_budget,
                coverage_seed=coverage_seed + step,
                legacy_limit=legacy_limit,
                recovery_tolerance=recovery_tolerance,
            )
            roots.append(result)
            release = result["coverage"]["release_top"]
            print(
                f"root step={step} "
                f"volume_safe={result['coverage']['volume']['safe']}"
                f"/{result['coverage']['volume']['proposed']} "
                f"release_safe={release['safe']}/{release['proposed']} "
                f"legacy_safe={result['legacy']['safe']} "
                f"release_discoveries={len(release['coverage_only_safe_strata'])}",
                flush=True,
            )
            action = record["action"]
            observation, _r, terminated, truncated, info = env.step(action)
            executed.append(action)
            if terminated or truncated or not _safe(_status(info)):
                break
    finally:
        env.close()

    def mode_summary(z_mode: str) -> dict[str, Any]:
        proposed = sum(r["coverage"][z_mode]["proposed"] for r in roots)
        safe = sum(r["coverage"][z_mode]["safe"] for r in roots)
        recoveries = [
            row
            for root in roots
            for row in root["coverage"][z_mode]["legacy_safe_recovery"]
        ]
        return {
            "p_safe_coverage": safe / proposed if proposed else None,
            "coverage_safe": safe,
            "coverage_proposed": proposed,
            "legacy_safe_actions": len(recoveries),
            "legacy_safe_recovered": sum(
                row["recovered"] for row in recoveries
            ),
            "legacy_safe_recovery_rate": (
                sum(row["recovered"] for row in recoveries) / len(recoveries)
                if recoveries else None
            ),
            "coverage_only_safe_strata": sum(
                len(root["coverage"][z_mode]["coverage_only_safe_strata"])
                for root in roots
            ),
        }

    return {
        "schema_version": 1,
        "contract": "coverage_support_audit_v1",
        "case_id": case_id,
        "coverage_generator": COVERAGE_GENERATOR,
        "coverage_budget_per_root": coverage_budget,
        "legacy_limit": legacy_limit,
        "recovery_tolerance": recovery_tolerance,
        "roots": roots,
        "summary": {
            "roots": len(roots),
            "legacy_safe_actions_total": sum(
                r["legacy"]["safe"] for r in roots
            ),
            **{z_mode: mode_summary(z_mode) for z_mode in Z_MODES},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--coverage-budget", type=int, default=96)
    parser.add_argument("--coverage-seed", type=int, default=20260823)
    parser.add_argument("--legacy-limit", type=int, default=32)
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--recovery-tolerance", type=float, default=0.10)
    parser.add_argument("--max-roots", type=int, default=None)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_config = config[args.case] if args.case in config else config
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    agent_module = load_agent_module()
    report = run_audit(
        agent_module, task_config, case_id=args.case,
        environment_seed=args.environment_seed, manifest=manifest,
        coverage_budget=args.coverage_budget,
        coverage_seed=args.coverage_seed,
        legacy_limit=args.legacy_limit,
        recovery_tolerance=args.recovery_tolerance,
        max_roots=args.max_roots,
        attempt_budget=args.attempt_budget,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
