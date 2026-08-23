"""Run behavior-policy terminal continuations from counterfactual sibling leaves.

For each searched root of a paired run, every root candidate is executed
in a fresh environment after replaying the trajectory prefix, then the
continuation follows the rank-0 behavior policy (same provider, same
fresh-replay legal filter, same genuine-termination semantics as the
game loop) until the stream ends, no retained candidate survives, or a
step cap censors it. Recorded per (root, candidate): metrics at the
root, after the candidate action (the sibling leaf s'), and at
termination, including the post-shake stability evaluation.

This yields the terminal rung of the depth ladder —
tau(H1 ordering, terminal ordering), tau(H2, terminal) — and the ground
truth for within-root V validation: the realized suffix beyond s' is
terminal minus after-action metrics, directly comparable with the
V^pi_behavior heads predicted at the same leaf.

Chance note: exogenous handoff draws only reassign which player moves,
and both players follow the same rank-0 policy, so the physical
continuation is world-independent. One physical probe per candidate
therefore covers every paired world; per-world game bookkeeping can be
replayed offline from the recorded action sequence.
"""

from __future__ import annotations

import argparse
import copy
import json
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
    cumulative_metrics,
)
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    require_supported_python,
)
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _compact_evaluation,
    _safe,
    _status,
    build_exact_physical_legal_filter,
)

GENUINE_TERMINATIONS = {
    "stream_exhausted", "no_retained_candidate", "no_safe_retained_candidate",
}


def _merge_shake(final_metrics: dict[str, Any], evaluation: Any) -> None:
    if not isinstance(evaluation, dict):
        return
    shake = evaluation.get("shake_response") or {}
    for source, target in (
        ("shake_max_shift", "post_shake_max_shift"),
        ("shake_peak_kinetic_energy", "post_shake_peak_kinetic_energy"),
        ("shake_items_toppled", "post_shake_items_toppled"),
    ):
        if source in shake:
            final_metrics[target] = shake[source]


def probe_candidate(
    task_config: dict[str, Any], *, environment_seed: int,
    prefix_actions: list[Any], candidate: dict[str, Any],
    provider, legal_filter, top_k: int, root_step: int,
    max_continuation_steps: int,
) -> dict[str, Any]:
    from src.ground_handling.env import GroundHandlingEnv

    env = GroundHandlingEnv(
        config=copy.deepcopy(task_config), verbose=False, render_mode=None,
    )
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=environment_seed)
        executed: list[Any] = []
        for action in prefix_actions:
            observation, _r, terminated, truncated, info = env.step(action)
            if not _safe(_status(info)) or terminated or truncated:
                raise RuntimeError(
                    f"prefix replay failed at action {len(executed)}"
                )
            executed.append(action)
        root_metrics = cumulative_metrics(env)
        action = _candidate_action(candidate)
        observation, _r, terminated, truncated, info = env.step(action)
        executed.append(action)
        if not _safe(_status(info)):
            return {
                "termination": "root_action_failure",
                "continuation_steps": 0,
                "root_metrics": root_metrics,
            }
        after_action_metrics = cumulative_metrics(env)
        termination = None
        if truncated:
            termination = "simulator_truncated"
        elif terminated:
            termination = "stream_exhausted"
        continuation_steps = 0
        while termination is None:
            if continuation_steps >= max_continuation_steps:
                termination = "continuation_cap"
                break
            proposals = list(provider(env, observation, int(top_k)))
            if not proposals:
                termination = "no_retained_candidate"
                break
            retained, _audit = legal_filter(
                env=env, observation=observation, candidates=proposals,
                actions=list(executed),
                step=root_step + 1 + continuation_steps,
                max_safe_candidates=1,
            )
            if not retained:
                termination = "no_safe_retained_candidate"
                break
            step_action = _candidate_action(retained[0])
            observation, _r, terminated, truncated, info = env.step(
                step_action
            )
            executed.append(step_action)
            if not _safe(_status(info)):
                termination = "selected_action_failure"
                break
            continuation_steps += 1
            if truncated:
                termination = "simulator_truncated"
            elif terminated:
                termination = "stream_exhausted"
        final_metrics = cumulative_metrics(env)
        evaluation = None
        if termination in GENUINE_TERMINATIONS:
            evaluation = _compact_evaluation(env.evaluate())
            _merge_shake(final_metrics, evaluation)
        return {
            "termination": termination,
            "genuine_terminal": termination in GENUINE_TERMINATIONS,
            "continuation_steps": continuation_steps,
            "root_metrics": root_metrics,
            "after_action_metrics": after_action_metrics,
            "terminal_metrics": final_metrics,
            "executed_actions": [json_safe(a) for a in executed],
        }
    finally:
        env.close()


def run_probe(
    agent_module, task_config: dict[str, Any], *, case_id: str,
    environment_seed: int, manifest: dict[str, Any],
    attempt_budget: int, top_k: int, max_continuation_steps: int,
    max_roots: int | None,
) -> dict[str, Any]:
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    legal_filter = build_exact_physical_legal_filter(
        task_config, case_id=case_id, environment_seed=environment_seed,
    )
    game = manifest["games"][0]
    records = sorted(game.get("records") or [], key=lambda r: int(r["step"]))
    rows = []
    probed = 0
    for record in records:
        if "search" not in record:
            continue
        if max_roots is not None and probed >= max_roots:
            break
        probed += 1
        step = int(record["step"])
        prefix = [
            r["action"] for r in records if int(r["step"]) < step
        ]
        for candidate in record.get("candidate_set") or []:
            result = probe_candidate(
                task_config, environment_seed=environment_seed,
                prefix_actions=prefix, candidate=candidate,
                provider=provider, legal_filter=legal_filter,
                top_k=top_k, root_step=step,
                max_continuation_steps=max_continuation_steps,
            )
            rows.append({
                "schema_version": 1,
                "contract": "paired_terminal_probe_v1",
                "behavior_policy": "rank0_same_as_game_loop",
                "case_id": case_id,
                "root_step": step,
                "candidate_set_id": record.get("candidate_set_id"),
                "root_candidate_id": candidate.get("candidate_id"),
                "world_independence": (
                    "physical_continuation_shared_by_all_worlds"
                ),
                **result,
            })
            print(
                f"probe step={step} candidate={candidate.get('candidate_id')[:20]} "
                f"termination={result['termination']} "
                f"steps={result['continuation_steps']}",
                flush=True,
            )
    if not rows:
        raise ValueError("manifest contained no searched roots to probe")
    return {
        "schema_version": 1,
        "contract": "paired_terminal_probe_v1",
        "case_id": case_id,
        "environment_seed": environment_seed,
        "attempt_budget": attempt_budget,
        "top_k": top_k,
        "max_continuation_steps": max_continuation_steps,
        "probed_roots": probed,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--max-continuation-steps", type=int, default=40)
    parser.add_argument("--max-roots", type=int, default=None)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    task_config = config[args.case] if args.case in config else config
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    agent_module = load_agent_module()
    report = run_probe(
        agent_module, task_config, case_id=args.case,
        environment_seed=args.environment_seed, manifest=manifest,
        attempt_budget=args.attempt_budget, top_k=args.top_k,
        max_continuation_steps=args.max_continuation_steps,
        max_roots=args.max_roots,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(report), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    genuine = sum(1 for row in report["rows"] if row.get("genuine_terminal"))
    print(
        f"rows={len(report['rows'])} roots={report['probed_roots']} "
        f"genuine_terminal={genuine}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
