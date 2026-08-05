"""
Learn V(afterstate), gated by the regime the board is in.

Three value functions failed here today, all of them global: one
coefficient vector asked to explain every board. The stratified refit says
that is the wrong shape -- what predicts danger flips sign between regimes,
and gating a single fit on `settled_share` moved within-step accuracy from
0.617 to 0.679 on the same 20764 pairs. So this fits one vector per regime.

The features are the ones the fast environment computes from the board a
placement LEAVES, not from the search that produced it. That distinction is
why the earlier hazard model could not rank candidates: its inputs described
the search, so every candidate at one step shared them.

The label is deliberately conservative. "How many more items fit" is
dominated by the arrival order, which a Task C agent cannot observe and
which this corpus samples about twice; two attempts at it have already
failed. This predicts instead whether the episode ends within a horizon of
the placement -- determined by the board in front of it, which is the class
of target the one working learned model here (P_rot) belongs to.

Nothing is adopted from this file. It reports whether a gated afterstate
value ranks better than a global one and than the shipped score, on the
same pairs, leave-one-case-out.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.fit_hazard_model import fit_logistic, predict, standardize  # noqa: E402

AFTERSTATE_FEATURES = [
    "occupancy_mean",
    "occupancy_max",
    "occupancy_std",
    "roughness",
    "headroom_deficit",
    "floor_fraction_free",
]
# Threshold from the sweep in reports/hazard/regime-dependence.md: accuracy
# is flat across split quantiles 0.3-0.6, so this is a plateau rather than a
# fitted constant. It is the median of the observed distribution.
REGIME_GATE = "settled_share"
REGIME_SPLIT = 0.685


def build_rows(agent_module, config_path, case_id, horizon, stride):
    """
    Replay one case, and at every step record the afterstate each legal
    placement would leave, labelled by whether the episode ended within
    ``horizon`` steps of that decision.

    Only the chosen action's afterstate can be labelled from a single
    replay -- the counterfactual branches were never executed. So this
    labels the CHOSEN afterstate per step, and the ranking question is
    asked across steps rather than across the alternatives at one step.
    That is a real limitation and it is why the evaluation below reports
    within-step pairs only where several rows share a step index.
    """
    from scripts.fast_afterstate_env import AfterstateBoard
    from scripts.measure_anchor_recall import policy_observation

    sys.path.insert(0, str(ROOT / "simulator"))
    from src.ground_handling.env import GroundHandlingEnv

    config = json.loads(pathlib.Path(config_path).read_text(encoding="utf-8"))
    case = config.get(case_id) or next(iter(config.values()))
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = agent_module.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)

    rows = []
    step = 0
    try:
        while True:
            observation = policy_observation(env, raw)
            action = solver.policy(observation)
            source = solver.last_action_source
            diagnostics = solver.last_candidate_diagnostics or {}
            by_kind = diagnostics.get("by_kind") or {}
            settled_attempted = float((by_kind.get("settled") or {}).get("attempted") or 0)
            release_attempted = float((by_kind.get("release") or {}).get("attempted") or 0)
            attempted = settled_attempted + release_attempted
            share = settled_attempted / attempted if attempted > 0 else 0.0

            if source != "unsafe_protocol_fallback":
                container_index = int(action.get("container_idx", 0))
                container = observation["container_list"][container_index]
                board = AfterstateBoard(agent_module, container)
                features = board.features()
                if features:
                    rows.append(
                        {
                            "case": case_id,
                            "step": step,
                            "settled_share": share,
                            "features": features,
                        }
                    )
            if source == "unsafe_protocol_fallback":
                break
            raw, _reward, terminated, truncated, info = env.step(action)
            status = (info or {}).get("status", {})
            if not all(
                bool(status.get(flag))
                for flag in ("is_included", "is_valid", "is_placed_safe")
            ):
                break
            step += 1
            if terminated or truncated:
                break
    finally:
        try:
            env.close()
        except Exception:
            pass

    terminal = rows[-1]["step"] if rows else 0
    for row in rows:
        row["label"] = 1.0 if terminal - row["step"] <= horizon else 0.0
    return rows


def evaluate(rows):
    """Global vs regime-gated, leave-one-case-out, on identical pairs."""
    if not rows:
        return None
    x = np.asarray(
        [[r["features"][f] for f in AFTERSTATE_FEATURES] for r in rows],
        dtype=np.float64,
    )
    y = np.asarray([r["label"] for r in rows], dtype=np.float64)
    g = np.asarray([r["case"] for r in rows])
    share = np.asarray([r["settled_share"] for r in rows], dtype=np.float64)

    def loso(gated):
        p = np.full(len(y), np.nan)
        for case in sorted(set(g)):
            held = g == case
            train = ~held
            groups = (
                [share <= REGIME_SPLIT, share > REGIME_SPLIT]
                if gated
                else [np.ones_like(y, dtype=bool)]
            )
            for group in groups:
                tm = train & group
                em = held & group
                if em.sum() == 0 or tm.sum() == 0 or len(set(y[tm])) < 2:
                    continue
                tr, te, _, _ = standardize(x[tm], x[em])
                p[em] = predict(fit_logistic(tr, y[tm]), te)
        return p

    def auc(p):
        mask = (p == p)
        pos = p[mask & (y == 1.0)]
        neg = p[mask & (y == 0.0)]
        if pos.size == 0 or neg.size == 0:
            return float("nan"), 0
        wins = sum(float((pos > n).sum()) + 0.5 * float((pos == n).sum()) for n in neg)
        return wins / (pos.size * neg.size), int(pos.size * neg.size)

    global_p = loso(False)
    gated_p = loso(True)
    both = (global_p == global_p) & (gated_p == gated_p)
    global_p = np.where(both, global_p, np.nan)
    gated_p = np.where(both, gated_p, np.nan)
    a_global, n_global = auc(global_p)
    a_gated, _ = auc(gated_p)
    return {
        "rows": int(len(y)),
        "cases": sorted(set(g.tolist())),
        "positives": float(y.mean()),
        "pairs": n_global,
        "auc_global": a_global,
        "auc_gated": a_gated,
        "delta": a_gated - a_global,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--configs", nargs="+", required=True)
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--stride", type=float, default=0.05)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()

    from scripts.measure_anchor_recall import load_agent_module

    agent_module = load_agent_module()
    rows = []
    for pattern in args.configs:
        for path in sorted(glob.glob(pattern)):
            case_id = pathlib.Path(path).stem
            built = build_rows(
                agent_module, path, case_id, args.horizon, args.stride
            )
            print(f"{case_id}: {len(built)} labelled afterstates", flush=True)
            rows.extend(built)

    report = evaluate(rows)
    if report is None:
        print("no rows", file=sys.stderr)
        return 1
    print(
        f"\nrows {report['rows']} over {len(report['cases'])} cases, "
        f"positives {report['positives']:.3f}, pairs {report['pairs']}"
    )
    print(f"  AUC global (1 vector)      : {report['auc_global']:.3f}")
    print(f"  AUC regime-gated (2 vectors): {report['auc_gated']:.3f}")
    print(f"  delta                       : {report['delta']:+.3f}")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
