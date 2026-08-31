"""Can cheap board features rank remaining capacity better than the rollout?

The terminal-rollout teacher values a board by continuing with frozen
rank-0, which today measured out at 9-11 placements before
`no_retained_candidate` -- two to four times below what rule-alpha
reaches from the same board.  If that estimate ranks boards worse than a
handful of free geometric features do, then the rollout is the weak link
and a learned value function has something to beat.

The comparison must not be circular.  Cup strict pairs are *defined* by
the rollout's own verdict, so scoring the rollout against them is 100%
by construction.  Ground truth here is instead rule-alpha's actual
continuation: run it once per cell and every prefix state gets a label
for free by telescoping,

    V^ra(s_t) = sum of the volume rule-alpha places from t onward,

which is the same return the n-step TD formulation would use with
r_t = newly placed volume and gamma = 1.  It is not V*, and rule-alpha
declines early too -- but it is a measurably higher ceiling than the
incumbent estimate, which is all a ranking comparison needs.

Ranking is evaluated WITHIN a step index.  Later boards trivially have
less left to place, so a global correlation would mostly measure "how
far into the episode is this", which any feature correlated with step
count would win without saying anything useful.  A value function's job
in search is to rank boards at the same depth against each other.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "simulator") not in sys.path:
    sys.path.insert(0, str(ROOT / "simulator"))

import numpy as np  # noqa: E402

from rule_alpha.agent import RuleAlphaAgent  # noqa: E402
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

CONTRACT = "value_rankability_probe_v1"


def board_features(observation: dict[str, Any]) -> dict[str, float]:
    """Free geometry. No physics, no rollout, no learning."""
    # `or []` on a live observation raises: depth_map arrives as an
    # ndarray, whose truth value is ambiguous. Test for None explicitly.
    raw = observation.get("depth_map")
    depth = (
        np.asarray(raw, dtype=float) if raw is not None
        else np.zeros((0, 0, 0))
    )
    containers = observation.get("container_list") or []
    pool = observation.get("pool_list") or []
    out: dict[str, float] = {}
    if depth.ndim == 3 and depth.size:
        heights = depth.reshape(depth.shape[0], -1)
        ceiling = float(
            max((float(c.get("height", 0.0) or 0.0) for c in containers),
                default=0.0)
        )
        out["free_height_sum"] = float(np.sum(np.clip(ceiling - depth, 0, None)))
        out["mean_height"] = float(np.mean(heights))
        out["max_height"] = float(np.max(heights))
        out["height_std"] = float(np.std(heights))
        # Total variation: how broken up the surface is. A flat plateau
        # takes a big box; the same volume as scattered steps does not.
        tv = 0.0
        for plane in depth:
            tv += float(np.abs(np.diff(plane, axis=0)).sum())
            tv += float(np.abs(np.diff(plane, axis=1)).sum())
        out["surface_total_variation"] = tv
        flat = 0
        for plane in depth:
            dy = np.abs(np.diff(plane, axis=0)) < 0.01
            dx = np.abs(np.diff(plane, axis=1)) < 0.01
            flat += int(dy.sum() + dx.sum())
        out["flat_cell_fraction"] = flat / max(tv + 1.0, 1.0)
        out["flat_cells"] = float(flat)
    out["placed_count"] = float(sum(
        len(c.get("packed_items") or []) for c in containers
    ))
    out["visible_pool_volume"] = float(sum(
        float(i.get("length", 0)) * float(i.get("width", 0))
        * float(i.get("height", 0)) for i in pool
    ))
    out["visible_pool_count"] = float(len(pool))
    return out


def item_volume(observation: dict[str, Any], action: dict[str, Any]) -> float:
    pool = observation.get("pool_list") or []
    index = int(action["item_idx"])
    if not (0 <= index < len(pool)):
        return 0.0
    item = pool[index]
    return float(
        float(item.get("length", 0)) * float(item.get("width", 0))
        * float(item.get("height", 0))
    )


def rule_alpha_trajectory(task, *, seed, max_steps):
    """One episode; every prefix state gets a label by telescoping."""
    env = _fresh_env(task)
    states: list[dict[str, Any]] = []
    try:
        env.reset_settings()
        actor = RuleAlphaAgent()
        actor.get_init_states(env.get_init_states())
        env.reset_item_stream()
        observation, _info = env.reset(seed=seed)
        actions = []
        for step in range(max_steps):
            observed = policy_observation(env, observation)
            action = actor.policy(observed)
            if action is None:
                break
            action = canonical_action(action)
            states.append({
                "step": step,
                "features": board_features(observed),
                "reward": item_volume(observed, action),
                "prefix": list(actions),
            })
            observation, _r, terminated, truncated, info = env.step(action)
            actions.append(action)
            if not _safe(_status(info)) or terminated or truncated:
                break
    finally:
        env.close()
    # V^ra(s_t) = sum of rewards from t onward -- the gamma=1 return
    tail = 0.0
    for row in reversed(states):
        tail += float(row["reward"])
        row["rule_alpha_return"] = tail
    return states


def rank0_continuation(agent_module, task, prefix, *, seed, attempt_budget,
                       max_steps):
    """The incumbent oracle: replay the prefix, then frozen rank-0."""
    provider = build_candidate_provider(
        agent_module, attempt_budget=attempt_budget,
        scan_all_visible_items=True,
    )
    env = _fresh_env(task)
    try:
        env.reset_settings()
        env.reset_item_stream()
        observation, _info = env.reset(seed=seed)
        for action in prefix:
            observation, _r, terminated, truncated, info = env.step(action)
            if not _safe(_status(info)) or terminated or truncated:
                return None
        before = float(cumulative_metrics(env).get("fill_score_proxy") or 0.0)
        steps = 0
        for _ in range(max_steps):
            candidates = list(provider(env, observation, 3))
            if not candidates:
                break
            observation, _r, terminated, truncated, info = env.step(
                _candidate_action(candidates[0])
            )
            steps += 1
            if not _safe(_status(info)) or terminated or truncated:
                break
        after = float(cumulative_metrics(env).get("fill_score_proxy") or 0.0)
    finally:
        env.close()
    return {"gain": after - before, "steps": steps}


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Rank correlation. Ranking is the whole question, not calibration."""
    n = len(xs)
    if n < 3:
        return None

    def ranks(values):
        order = sorted(range(n), key=lambda i: values[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            average = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = average
            i = j + 1
        return out

    rx, ry = ranks(xs), ranks(ys)
    mx, my = statistics.fmean(rx), statistics.fmean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=pathlib.Path, required=True)
    parser.add_argument("--cases", nargs="+", required=True)
    parser.add_argument(
        "--steps", type=int, nargs="+", default=[6, 12],
        help="step indices to price with the incumbent rollout; ranking is"
             " compared WITHIN each of these, across cells",
    )
    parser.add_argument("--environment-seed", type=int, default=42)
    parser.add_argument("--attempt-budget", type=int, default=128)
    parser.add_argument("--max-steps", type=int, default=40)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    require_supported_python()
    agent_module = load_agent_module()

    rows: list[dict[str, Any]] = []
    for case in args.cases:
        config = json.loads(
            (args.config_dir / f"{case}.json").read_text(encoding="utf-8")
        )
        task = next(
            v for v in config.values()
            if isinstance(v, dict) and "containers" in v
        )
        states = rule_alpha_trajectory(
            task, seed=args.environment_seed, max_steps=args.max_steps,
        )
        print(f"{case}: {len(states)} states", flush=True)
        for step in args.steps:
            if step >= len(states):
                continue
            state = states[step]
            rollout = rank0_continuation(
                agent_module, task, state["prefix"],
                seed=args.environment_seed,
                attempt_budget=args.attempt_budget,
                max_steps=args.max_steps,
            )
            if rollout is None:
                continue
            rows.append({
                "case": case, "step": step,
                "rule_alpha_return": state["rule_alpha_return"],
                "rollout_gain": rollout["gain"],
                "rollout_steps": rollout["steps"],
                "features": state["features"],
            })
            print(
                f"  step {step:2d}  truth={state['rule_alpha_return']:.4f}"
                f"  rollout={rollout['gain']:7.3f} ({rollout['steps']} steps)",
                flush=True,
            )

    names = sorted({k for r in rows for k in r["features"]})
    by_step: dict[int, list[dict]] = {}
    for row in rows:
        by_step.setdefault(row["step"], []).append(row)

    report: dict[str, Any] = {"by_step": {}, "pooled": {}}
    for step, group in sorted(by_step.items()):
        truth = [r["rule_alpha_return"] for r in group]
        entry = {
            "n": len(group),
            "incumbent_rollout": spearman(
                [r["rollout_gain"] for r in group], truth
            ),
            "features": {
                name: spearman(
                    [r["features"].get(name, 0.0) for r in group], truth
                )
                for name in names
            },
        }
        report["by_step"][str(step)] = entry

    print("\n=== Spearman vs rule-alpha's actual remaining volume ===",
          flush=True)
    for step, entry in report["by_step"].items():
        best = max(
            ((k, v) for k, v in entry["features"].items() if v is not None),
            key=lambda kv: abs(kv[1]), default=(None, None),
        )
        rollout = entry["incumbent_rollout"]
        print(
            f"step {step:>3s} (n={entry['n']:2d})  "
            f"incumbent rollout {rollout if rollout is None else f'{rollout:+.3f}'}"
            f"   best free feature {best[0]} "
            f"{best[1] if best[1] is None else f'{best[1]:+.3f}'}",
            flush=True,
        )
        for name, value in sorted(
            entry["features"].items(),
            key=lambda kv: -abs(kv[1] or 0.0),
        ):
            print(f"      {name:26s} "
                  f"{value if value is None else f'{value:+.3f}'}", flush=True)

    payload = {
        "schema_version": 1, "contract": CONTRACT,
        "question": (
            "does the incumbent 10-step rollout rank boards by remaining"
            " capacity better than free geometric features do?"
        ),
        "ground_truth": (
            "rule-alpha's own continuation return (gamma=1, r=placed"
            " volume); not V*, but a measurably higher ceiling than the"
            " incumbent estimate"
        ),
        "not_circular_because": (
            "Cup strict pairs are defined by the rollout's verdict, so"
            " they cannot score the rollout; this ground truth is"
            " independent of it"
        ),
        "rows": rows, "report": report,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
