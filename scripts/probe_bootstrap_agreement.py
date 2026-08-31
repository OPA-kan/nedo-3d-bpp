"""Does the bootstrapped verdict agree with a higher-ceiling one?

The bootstrap rewrites what a dominance verdict *is*: on a smoke run its
term contributed 9-15 fill points to a measured signal of 0.5-3.3, and
one pair's order flipped. Whether that flip is V_theta seeing further or
V_theta's error drowning the signal cannot be read off the magnitude, so
it is measured.

Three ways to score the same candidate from the same board:

  incumbent      rank-0 continuation, tail booked as 0   (Cups 001-010)
  bootstrapped   the same continuation, tail = V_theta   (proposed)
  reference      rule-alpha's own continuation           (ground truth)

The reference is not V*, but today's ceiling probe measured it two to
four times above the incumbent, so it is the better-informed judge
available. Agreement with it is the test:

  bootstrapped agrees more than incumbent  -> the bootstrap sees further
  bootstrapped agrees less                 -> it is breaking the teacher

Verdicts are compared on **fill alone**. The bootstrap only touches
fill_gain, and the four-head partial order answers "incomparable" often
enough that it would dilute the very comparison being made.

Incumbent and bootstrapped share one physical continuation -- the second
is the first plus V_theta on the board it stopped at -- so this costs two
continuations per candidate, not three.
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

from scripts.board_value_model import BoardValue  # noqa: E402
from scripts.build_counterfactual_graph import (  # noqa: E402
    build_candidate_provider,
    cumulative_metrics,
)
from scripts.build_replay_dataset import (  # noqa: E402
    json_safe,
    load_agent_module,
    policy_observation,
    require_supported_python,
)
from scripts.counterfactual_graph import canonical_action  # noqa: E402
from scripts.run_self_play_packing import (  # noqa: E402
    _candidate_action,
    _safe,
    _status,
)
from scripts.run_single_agent_packing import _fresh_env  # noqa: E402

CONTRACT = "bootstrap_agreement_probe_v1"


def continue_from(task, prefix, forced, *, policy, agent_module, seed,
                  attempt_budget, max_steps, value=None):
    """Force one action after the prefix, then continue with `policy`."""
    env = _fresh_env(task)
    try:
        env.reset_settings()
        solver = None
        provider = None
        if policy == "rule-alpha":
            from rule_alpha.agent import RuleAlphaAgent

            solver = RuleAlphaAgent()
            solver.get_init_states(env.get_init_states())
        else:
            provider = build_candidate_provider(
                agent_module, attempt_budget=attempt_budget,
                scan_all_visible_items=True,
            )
        env.reset_item_stream()
        observation, _info = env.reset(seed=seed)
        for action in list(prefix) + [forced]:
            observation, _r, terminated, truncated, info = env.step(action)
            if not _safe(_status(info)) or terminated or truncated:
                return None
        steps = 0
        termination = None
        for _ in range(max_steps):
            observed = policy_observation(env, observation)
            if solver is not None:
                action = solver.policy(observed)
                action = None if action is None else canonical_action(action)
            else:
                candidates = list(provider(env, observation, 3))
                action = (
                    _candidate_action(candidates[0]) if candidates else None
                )
            if action is None:
                termination = "no_retained_candidate"
                break
            observation, _r, terminated, truncated, info = env.step(action)
            steps += 1
            if not _safe(_status(info)):
                termination = "selected_action_failure"
                break
            if terminated or truncated:
                termination = "stream_exhausted" if terminated else "truncated"
                break
        else:
            termination = "continuation_cap"
        metrics = cumulative_metrics(env)
        fill = float(metrics.get("fill_score_proxy") or 0.0)
        bootstrap = 0.0
        if value is not None and termination != "stream_exhausted":
            prediction = value.fill_return(
                policy_observation(env, observation)
            )
            bootstrap = float(prediction["fill_return"]["mean"])
    finally:
        env.close()
    return {
        "termination": termination, "steps": steps,
        "fill": fill, "bootstrap": bootstrap,
        "bootstrapped_fill": fill + bootstrap,
    }


def verdict(a: float, b: float, eps: float = 1e-9) -> str:
    if a > b + eps:
        return "a"
    if b > a + eps:
        return "b"
    return "tie"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=pathlib.Path, required=True)
    parser.add_argument("--cases", nargs="+", required=True)
    parser.add_argument("--value-dir", type=pathlib.Path, required=True)
    parser.add_argument("--steps", type=int, nargs="+", default=[4, 8])
    parser.add_argument("--candidates", type=int, default=3)
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    agent_module = load_agent_module()
    value = BoardValue(args.value_dir)

    pairs: list[dict[str, Any]] = []
    for case in args.cases:
        config = json.loads(
            (args.config_dir / f"{case}.json").read_text(encoding="utf-8")
        )
        task = next(
            v for v in config.values()
            if isinstance(v, dict) and "containers" in v
        )
        # Walk rule-alpha to build prefixes, and take the provider's
        # candidates at the probed steps as the actions to compare.
        from rule_alpha.agent import RuleAlphaAgent

        env = _fresh_env(task)
        prefixes: dict[int, tuple] = {}
        try:
            env.reset_settings()
            actor = RuleAlphaAgent()
            actor.get_init_states(env.get_init_states())
            provider = build_candidate_provider(
                agent_module, attempt_budget=args.attempt_budget,
                scan_all_visible_items=True,
            )
            env.reset_item_stream()
            observation, _info = env.reset(seed=args.environment_seed)
            executed: list[Any] = []
            for step in range(max(args.steps) + 1):
                if step in args.steps:
                    found = [
                        _candidate_action(c)
                        for c in provider(env, observation, args.candidates)
                    ]
                    if len(found) >= 2:
                        prefixes[step] = (list(executed), found)
                action = actor.policy(policy_observation(env, observation))
                if action is None:
                    break
                action = canonical_action(action)
                observation, _r, t, tr, info = env.step(action)
                executed.append(action)
                if not _safe(_status(info)) or t or tr:
                    break
        finally:
            env.close()

        for step, (prefix, actions) in sorted(prefixes.items()):
            scored = []
            for action in actions[: args.candidates]:
                incumbent = continue_from(
                    task, prefix, action, policy="rank0",
                    agent_module=agent_module, seed=args.environment_seed,
                    attempt_budget=args.attempt_budget,
                    max_steps=args.max_steps, value=value,
                )
                reference = continue_from(
                    task, prefix, action, policy="rule-alpha",
                    agent_module=agent_module, seed=args.environment_seed,
                    attempt_budget=args.attempt_budget,
                    max_steps=args.max_steps,
                )
                if incumbent is None or reference is None:
                    continue
                scored.append({
                    "action": action,
                    "incumbent_fill": incumbent["fill"],
                    "bootstrapped_fill": incumbent["bootstrapped_fill"],
                    "bootstrap_term": incumbent["bootstrap"],
                    "reference_fill": reference["fill"],
                    "incumbent_steps": incumbent["steps"],
                    "reference_steps": reference["steps"],
                })
            for i in range(len(scored)):
                for j in range(i + 1, len(scored)):
                    a, b = scored[i], scored[j]
                    pairs.append({
                        "case": case, "step": step,
                        "incumbent": verdict(
                            a["incumbent_fill"], b["incumbent_fill"]
                        ),
                        "bootstrapped": verdict(
                            a["bootstrapped_fill"], b["bootstrapped_fill"]
                        ),
                        "reference": verdict(
                            a["reference_fill"], b["reference_fill"]
                        ),
                        "a": a, "b": b,
                    })
            print(
                f"{case[:40]:40s} step {step:2d}: {len(scored)} candidates,"
                f" {len(scored) * (len(scored) - 1) // 2} pairs", flush=True,
            )

    decided = [p for p in pairs if p["reference"] != "tie"]
    incumbent_ok = sum(
        1 for p in decided if p["incumbent"] == p["reference"]
    )
    bootstrap_ok = sum(
        1 for p in decided if p["bootstrapped"] == p["reference"]
    )
    changed = [p for p in pairs if p["incumbent"] != p["bootstrapped"]]
    changed_decided = [p for p in changed if p["reference"] != "tie"]
    summary = {
        "pairs": len(pairs),
        "pairs_the_reference_decides": len(decided),
        "incumbent_agrees": incumbent_ok,
        "bootstrapped_agrees": bootstrap_ok,
        "incumbent_agreement_rate": (
            round(incumbent_ok / len(decided), 4) if decided else None
        ),
        "bootstrapped_agreement_rate": (
            round(bootstrap_ok / len(decided), 4) if decided else None
        ),
        "verdicts_the_bootstrap_changed": len(changed),
        "of_those_the_reference_decides": len(changed_decided),
        "changed_toward_the_reference": sum(
            1 for p in changed_decided if p["bootstrapped"] == p["reference"]
        ),
        "changed_away_from_the_reference": sum(
            1 for p in changed_decided if p["incumbent"] == p["reference"]
        ),
        "mean_bootstrap_term": (
            round(sum(
                p["a"]["bootstrap_term"] + p["b"]["bootstrap_term"]
                for p in pairs
            ) / (2 * len(pairs)), 3) if pairs else None
        ),
        "mean_incumbent_gap": (
            round(sum(
                abs(p["a"]["incumbent_fill"] - p["b"]["incumbent_fill"])
                for p in pairs
            ) / len(pairs), 3) if pairs else None
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe({
            "schema_version": 1, "contract": CONTRACT,
            "question": (
                "does booking the tail with V_theta agree with a"
                " higher-ceiling judge more often than booking it as 0?"
            ),
            "reference": "rule-alpha's own continuation (not V*)",
            "compared_on": "fill only; the bootstrap touches only fill_gain",
            "summary": summary, "pairs": pairs,
        }), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("\n=== agreement with the higher-ceiling judge ===", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
