#!/usr/bin/env python3
"""Entry gate: does the selfplay hazard model rank real branch siblings?

Implements the gate fixed in reports/hazard/selfplay-hazard-protocol.md.
For each committed deviation-corpus stream, the base episode is replayed
with observations captured at the branch steps (the corpus's
parent_fingerprint verifies each reconstruction); every recorded sibling
action is converted to a fast-env afterstate and scored by the winning
mlp_scalars arm through the exact schema-2 scalar path. The pooled
within-state sibling AUC against final placed must beat the committed
bar of 0.561 before any physics or live spend.

Two phases so the expensive replay is cached:
  --phase capture  writes one features.jsonl row per (state, branch)
  --phase score    fits mlp_scalars on the full selfplay corpus and
                   reports the pooled AUC
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BAR = 0.561


def capture_stream(corpus_path: pathlib.Path, config_path: pathlib.Path,
                   out_handle) -> dict[str, Any]:
    from scripts.build_branch_labels import run_episode, state_fingerprint
    from scripts.measure_anchor_recall import load_agent_module
    from scripts.fast_afterstate_env import (
        AfterstateBoard,
        largest_free_span,
        sealed_void_fraction,
    )
    from scripts.generate_selfplay import build_risk_gate, legal_afterstates

    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    task = json.loads(config_path.read_text(encoding="utf-8"))
    case = next(iter(task.values()))
    agent_module = load_agent_module()
    sys.path.insert(0, str(ROOT / "simulator"))
    steps = [int(state["step"]) for state in corpus["states"]]
    episode = run_episode(
        agent_module, json.loads(json.dumps(case)), capture_steps=steps
    )
    stats = {"stream": corpus["task_id"], "states": 0, "branches": 0,
             "fingerprint_mismatches": 0, "unreconstructable": 0}
    for state in corpus["states"]:
        step = int(state["step"])
        observation = episode["captured"].get(step)
        if observation is None:
            continue
        fingerprint_ok = (
            state_fingerprint(observation) == state["parent_fingerprint"]
        )
        if not fingerprint_ok:
            stats["fingerprint_mismatches"] += 1
        containers = observation.get("container_list", [])
        pool_list = observation.get("pool_list", [])
        boards = {}
        stats["states"] += 1
        for branch in state["branches"]:
            action = branch["action"]
            container_idx = int(action["container_idx"])
            item_idx = int(action["item_idx"])
            if not (0 <= container_idx < len(containers)
                    and 0 <= item_idx < len(pool_list)):
                stats["unreconstructable"] += 1
                continue
            if container_idx not in boards:
                boards[container_idx] = AfterstateBoard(
                    agent_module, containers[container_idx]
                )
            board = boards[container_idx]
            item = pool_list[item_idx]
            cx, cy = (
                float(action["place_pos"][0]),
                float(action["place_pos"][1]),
            )
            result = board.afterstate(
                item, int(action["orientation"]), cx, cy
            )
            if result is None:
                stats["unreconstructable"] += 1
                continue
            child, _candidate = result
            gate = build_risk_gate(
                agent_module, containers[container_idx]
            )
            options = len(legal_afterstates(
                agent_module, board, item,
                stride=0.10, risk_gate=gate,
                rng=random.Random(0), cap=48,
            ))
            after = child.features()
            sealed_total, sealed_items = sealed_void_fraction(
                agent_module, child
            )
            placed_runs = [
                float(run["evaluation"].get("num_placed_items", 0.0))
                for run in branch.get("runs", [])
                if isinstance(run, dict) and run.get("evaluation")
            ]
            if not placed_runs:
                stats["unreconstructable"] += 1
                continue
            row = {
                "stream": corpus["task_id"],
                "collection": corpus_path.parent.name,
                "step": step,
                "sibling_index": int(branch.get("sibling_index", -1)),
                "fingerprint_ok": bool(fingerprint_ok),
                "scalars": (
                    [float(after[name]) for name in (
                        "occupancy_mean", "occupancy_max", "occupancy_std",
                        "roughness", "headroom_deficit",
                        "floor_fraction_free", "placed",
                    )]
                    + [float(sealed_total), float(sealed_items),
                       float(largest_free_span(child)), float(options)]
                ),
                "label_placed": sum(placed_runs) / len(placed_runs),
            }
            out_handle.write(json.dumps(row) + "\n")
            stats["branches"] += 1
    return stats


def score(features_path: pathlib.Path, corpus_dir: pathlib.Path,
          *, epochs: int, seed: int) -> dict[str, Any]:
    import torch
    from scripts.train_hazard_model import (
        build_arms, load_rows, scalar_vector,
    )
    import math

    rows = load_rows(sorted(corpus_dir.rglob("*.jsonl")))
    if not rows:
        raise SystemExit("no selfplay rows for the final fit")
    torch.manual_seed(seed)
    scalars = np.asarray(
        [scalar_vector(r) for r in rows], dtype=np.float32
    )
    mean = scalars.mean(axis=0)
    scale = scalars.std(axis=0)
    scale[scale <= 0] = 1.0
    survival = np.asarray(
        [math.log1p(float(r["placements_after"])) for r in rows],
        dtype=np.float32,
    )
    terminal = np.asarray(
        [float(r["terminal_in_3"]) for r in rows], dtype=np.float32
    )
    s_mean, s_scale = survival.mean(), survival.std() or 1.0
    _Linear, Mlp, _Attention = build_arms(torch, scalars.shape[1], 0, 0)
    model = Mlp(scalars.shape[1])
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=3e-3, weight_decay=1e-2
    )
    mse, bce = torch.nn.MSELoss(), torch.nn.BCEWithLogitsLoss()
    normalized = torch.tensor((scalars - mean) / scale)
    target_s = torch.tensor((survival - s_mean) / s_scale)
    target_t = torch.tensor(terminal)
    order = np.arange(len(rows))
    rng = np.random.default_rng(seed)
    for _epoch in range(epochs):
        rng.shuffle(order)
        for start in range(0, len(order), 4096):
            chunk = order[start:start + 4096]
            optimizer.zero_grad()
            out = model(normalized[chunk])
            loss = mse(out[:, 0], target_s[chunk]) + bce(
                out[:, 1], target_t[chunk]
            )
            loss.backward()
            optimizer.step()
    model.eval()

    branches = []
    with features_path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                branches.append(json.loads(line))
    inputs = torch.tensor(
        (np.asarray([b["scalars"] for b in branches], dtype=np.float32)
         - mean) / scale
    )
    with torch.no_grad():
        predictions = model(inputs)[:, 0].numpy()
    for branch, prediction in zip(branches, predictions):
        branch["prediction"] = float(prediction)

    def pooled_auc(subset):
        states: dict[tuple, list[dict]] = {}
        for branch in subset:
            states.setdefault(
                (branch["collection"], branch["stream"], branch["step"]),
                [],
            ).append(branch)
        wins = 0.0
        pairs = 0
        for group in states.values():
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    if a["label_placed"] == b["label_placed"]:
                        continue
                    high, low = (
                        (a, b)
                        if a["label_placed"] > b["label_placed"]
                        else (b, a)
                    )
                    if high["prediction"] > low["prediction"]:
                        wins += 1.0
                    elif high["prediction"] == low["prediction"]:
                        wins += 0.5
                    pairs += 1
        return (wins / pairs) if pairs else None, pairs

    overall, pairs = pooled_auc(branches)
    by_collection = {}
    for name in sorted({b["collection"] for b in branches}):
        auc, n = pooled_auc(
            [b for b in branches if b["collection"] == name]
        )
        by_collection[name] = {"auc": auc, "pairs": n}
    verified = [b for b in branches if b["fingerprint_ok"]]
    verified_auc, verified_pairs = pooled_auc(verified)
    return {
        "protocol": "reports/hazard/selfplay-hazard-protocol.md",
        "bar": BAR,
        "branches_scored": len(branches),
        "fingerprint_verified_branches": len(verified),
        "pooled_auc": overall,
        "pairs": pairs,
        "pooled_auc_fingerprint_verified_only": verified_auc,
        "verified_pairs": verified_pairs,
        "by_collection": by_collection,
        "gate_passed": overall is not None and overall > BAR,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["capture", "score"],
                        required=True)
    parser.add_argument("--corpus-file", type=pathlib.Path, nargs="*")
    parser.add_argument("--config", type=pathlib.Path, nargs="*")
    parser.add_argument("--features", type=pathlib.Path, required=True)
    parser.add_argument("--selfplay-corpus", type=pathlib.Path)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    if args.phase == "capture":
        if not args.corpus_file or not args.config or (
            len(args.corpus_file) != len(args.config)
        ):
            raise SystemExit(
                "--corpus-file and --config must pair one-to-one"
            )
        args.features.parent.mkdir(parents=True, exist_ok=True)
        with args.features.open("a", encoding="utf-8") as handle:
            for corpus_path, config_path in zip(
                args.corpus_file, args.config
            ):
                stats = capture_stream(corpus_path, config_path, handle)
                print(json.dumps(stats), flush=True)
        return 0
    if not args.selfplay_corpus or not args.output:
        raise SystemExit("score needs --selfplay-corpus and --output")
    result = score(
        args.features, args.selfplay_corpus,
        epochs=args.epochs, seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
