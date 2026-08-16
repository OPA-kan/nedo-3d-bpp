"""
Self-play data generation on the physics-free afterstate environment.

Everything learned here has been starved of data. The afterstate value run
had 233 labelled rows over eight scenes, which cannot separate a model class
from noise; the replay dataset has 2732 physics-labelled candidates and took
hours of settling to make. This generates the same shape of data without
calling physics at all, which is the step that makes a Transformer -- or any
model with more parameters than the six-feature linear fit -- a question that
can actually be answered.

Three choices in here are load-bearing, and each is a constraint the record
already established rather than a preference.

ARRIVALS ARE SAMPLED FROM THE PUBLISHED CATALOG, not replayed from the two
bundled streams. `arrival-distribution-not-estimable-from-two-streams` says
those two cannot stand in for the distribution, and a policy trained on them
learns them. `item_params.xlsx` publishes seven types; sampling from it is
the closest available thing to the generator the official cases come from.
It is NOT a claim that the official mix is uniform over the seven -- that is
unknown, and is recorded as a caveat rather than assumed away.

LEGALITY IS THE SHIPPED CONTRACT PLUS THE RISK GATE. Accepting on geometry
alone admits poses physics rejects about a third of the time (measured:
weighted safe rate 0.641 on release candidates, versus 0.855 among those the
gate passes). A policy trained against the looser contract learns to seek
exactly the poses it should avoid, so the gate is part of legality here.

THE LABEL IS SURVIVAL, NOT PLACEMENT COUNT. "How many more items fit" is
dominated by arrival order and has failed twice. Each row records how many
further placements the rollout achieved from that board, which is a Monte
Carlo return under the sampled prior -- the honest version of the same
quantity, and the caller can threshold it into whatever target it wants.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.fast_afterstate_env import (  # noqa: E402
    AfterstateBoard,
    board_grid,
    largest_free_span,
    sealed_void_fraction,
)
from scripts.measure_board_value import BAGGAGE_TYPES, type_representative  # noqa: E402


def sample_item(rng, index):
    entry_index = rng.randrange(len(BAGGAGE_TYPES))
    item = dict(type_representative(BAGGAGE_TYPES[entry_index], entry_index))
    item["index"] = index
    item["type_index"] = entry_index
    return item


def legal_afterstates(agent_module, board, item, *, stride, risk_gate, rng, cap):
    """
    Candidate placements with the board each leaves.

    Positions are visited in a shuffled order and the scan stops at ``cap``,
    so a board with thousands of legal drops does not spend the whole
    episode budget enumerating them and does not bias the sample toward one
    corner of the container by scan order.
    """
    orientations = list(agent_module.unique_orientations(item))
    xs = np.arange(board.x0 + stride / 2.0, -board.x0, stride)
    ys = np.arange(board.y0 + stride / 2.0, -board.y0, stride)
    grid = [
        (o, float(x), float(y)) for o in orientations for x in xs for y in ys
    ]
    rng.shuffle(grid)
    out = []
    for orientation, cx, cy in grid:
        result = board.afterstate(item, orientation, cx, cy)
        if result is None:
            continue
        child, candidate = result
        if risk_gate is not None:
            probability = risk_gate(candidate, item, orientation)
            if probability is not None and probability >= 0.5:
                continue
        out.append((child, candidate, orientation))
        if len(out) >= cap:
            break
    return out


def rollout(agent_module, container, *, seed, stride, cap, max_steps, risk_gate):
    """One episode. Returns a row per placement, labelled by what followed."""
    rng = random.Random(seed)
    board = AfterstateBoard(agent_module, container)
    rows = []
    for step in range(max_steps):
        item = sample_item(rng, step)
        options = legal_afterstates(
            agent_module,
            board,
            item,
            stride=stride,
            risk_gate=risk_gate,
            rng=rng,
            cap=cap,
        )
        if not options:
            break
        # Behaviour policy: lowest resulting surface, ties broken randomly.
        # It is deliberately simple and NOT the shipped ranker -- the point
        # is coverage of boards to learn from, and a strong behaviour policy
        # would only visit the boards it already likes.
        best = min(
            options, key=lambda o: (o[0].features()["occupancy_max"], rng.random())
        )
        child, candidate, orientation = best
        # Schema 2: the raw substrate rides along so the representation
        # question (can a model learn receptivity the hand features
        # missed?) is answerable without regenerating. Sealed void is the
        # one quantity a heightmap cannot express; the scalar six all
        # collapse onto the fullness axis.
        sealed_total, sealed_by_items = sealed_void_fraction(
            agent_module, child
        )
        rows.append(
            {
                "schema_version": 2,
                "step": step,
                "type_index": int(item["type_index"]),
                "features": board.features(),
                "afterstate": child.features(),
                "afterstate_grid": board_grid(child),
                "afterstate_sealed_void": float(sealed_total),
                "afterstate_sealed_void_by_items": float(sealed_by_items),
                "afterstate_largest_free_span": float(
                    largest_free_span(child)
                ),
                "candidate": {
                    "center": [float(v) for v in candidate.center],
                    "size": [float(v) for v in candidate.size],
                    "orientation": int(orientation),
                },
                "container": {
                    "length": float(container["length"]),
                    "width": float(container["width"]),
                    "height": float(container["height"]),
                },
                "options": len(options),
            }
        )
        board = child
    total = len(rows)
    for row in rows:
        row["placements_after"] = total - row["step"] - 1
        row["terminal_in_3"] = 1.0 if (total - row["step"] - 1) <= 3 else 0.0
    return rows


def build_risk_gate(agent_module, container):
    """P_rot from the shipped model, or None when it cannot be evaluated."""

    def gate(candidate, item, orientation):
        try:
            _adjusted, probability = agent_module.risk_adjusted_score(
                0.0, candidate, item, container, int(orientation), 1.0
            )
        except Exception:
            return None
        return None if probability is None else float(probability)

    return gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=pathlib.Path, required=True)
    parser.add_argument("--episodes", type=int, default=200)
    parser.add_argument("--stride", type=float, default=0.10)
    parser.add_argument("--cap", type=int, default=48)
    parser.add_argument("--max-steps", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-risk-gate", action="store_true")
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    from scripts.measure_anchor_recall import load_agent_module, policy_observation

    agent_module = load_agent_module()
    sys.path.insert(0, str(ROOT / "simulator"))
    from src.ground_handling.env import GroundHandlingEnv

    config = json.loads(args.config.read_text(encoding="utf-8"))
    case = next(iter(config.values()))
    env = GroundHandlingEnv(
        config=json.loads(json.dumps(case)), verbose=False, render_mode=None
    )
    solver = agent_module.Agent("")
    env.reset_settings()
    solver.get_init_states(env.get_init_states())
    env.reset_item_stream()
    raw, _ = env.reset(seed=42)
    observation = policy_observation(env, raw)
    containers = [json.loads(json.dumps(c)) for c in observation["container_list"]]
    env.close()

    started = time.perf_counter()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    episodes = 0
    with open(args.output, "w", encoding="utf-8") as handle:
        for episode in range(args.episodes):
            container = containers[episode % len(containers)]
            gate = None if args.no_risk_gate else build_risk_gate(agent_module, container)
            rows = rollout(
                agent_module,
                container,
                seed=args.seed + episode,
                stride=args.stride,
                cap=args.cap,
                max_steps=args.max_steps,
                risk_gate=gate,
            )
            episodes += 1
            for row in rows:
                row["episode"] = episode
                row["container_index"] = episode % len(containers)
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                written += 1
            if (episode + 1) % 20 == 0:
                rate = written / max(time.perf_counter() - started, 1e-9)
                print(
                    f"  {episode + 1}/{args.episodes} episodes, "
                    f"{written} rows, {rate:,.0f} rows/s",
                    flush=True,
                )
    elapsed = time.perf_counter() - started
    print(
        f"\n{written} rows from {episodes} episodes in {elapsed:.1f}s "
        f"({written / max(elapsed, 1e-9):,.0f} rows/s) -> {args.output}"
    )
    print(
        "caveat carried with this data: arrivals are sampled uniformly over "
        "the seven published types, which is the closest available stand-in "
        "for the official generator and NOT a measurement of it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
