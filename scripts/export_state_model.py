#!/usr/bin/env python3
"""Export the candidate_mlp safety ranker to plain numpy weights.

`train_state_model.py` established `state_model_beats_incumbent`
(candidate_mlp within-state safety AUC 0.842 versus the incumbent 0.733,
top-1 safe rate 0.969 versus 0.882) but torch is an offline dependency and
the shipped agent must stay numpy-only. This script fits the winning arm
once on the full committed corpus with the training script's own
architecture and normalization, then writes a JSON artifact containing the
feature contract, normalization statistics and layer weights, plus a
torch-versus-numpy forward parity check. The artifact is the bridge that
lets a future live shadow score release candidates with the learned safety
ranker inside the CPU-first agent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.train_state_model import (  # noqa: E402
    FEATURES,
    REGRESSION_TARGETS,
    build_models,
    load_examples,
)


def final_fit(torch, rows: list[dict[str, Any]], *, seed: int, epochs: int):
    """Fit candidate_mlp on every row, early-stopped on a held-out case."""
    torch.manual_seed(seed)
    Mlp, _SetAttention = build_models(
        torch,
        {"phi": len(rows[0]["phi"]), "candidate": len(rows[0]["candidate"])},
    )
    model = Mlp(use_candidate=True)

    phi = np.array([r["phi"] for r in rows], dtype=np.float32)
    cand = np.array([r["candidate"] for r in rows], dtype=np.float32)
    targets = np.array([r["targets"] for r in rows], dtype=np.float32)
    safe = np.array([r["safe"] for r in rows], dtype=np.float32)
    stats = {}
    for name, block in (("phi", phi), ("cand", cand), ("targets", targets)):
        mean = block.mean(axis=0)
        spread = block.std(axis=0)
        spread[spread <= 0] = 1.0
        stats[name] = (mean, spread)

    def norm_tensors(indices):
        return (
            torch.tensor((phi[indices] - stats["phi"][0]) / stats["phi"][1]),
            torch.tensor(
                (cand[indices] - stats["cand"][0]) / stats["cand"][1]
            ),
            torch.tensor(
                (targets[indices] - stats["targets"][0])
                / stats["targets"][1]
            ),
            torch.tensor(safe[indices]),
        )

    cases = sorted({row["case_id"] for row in rows})
    held = {cases[seed % len(cases)]} if len(cases) > 1 else set()
    train_idx = [i for i, r in enumerate(rows) if r["case_id"] not in held]
    valid_idx = [i for i, r in enumerate(rows) if r["case_id"] in held]
    if not train_idx or not valid_idx:
        train_idx = valid_idx = list(range(len(rows)))
    t_phi, t_cand, t_targets, t_safe = norm_tensors(train_idx)
    v_phi, v_cand, v_targets, v_safe = norm_tensors(valid_idx)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=3e-3, weight_decay=1e-2
    )
    bce = torch.nn.BCEWithLogitsLoss()
    mse = torch.nn.MSELoss()
    best = (float("inf"), None)
    for _epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        out = model(t_phi, t_cand, None, None)
        loss = bce(out[:, 0], t_safe) + mse(out[:, 1:], t_targets)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        model.eval()
        with torch.no_grad():
            v_out = model(v_phi, v_cand, None, None)
            v_loss = float(
                bce(v_out[:, 0], v_safe) + mse(v_out[:, 1:], v_targets)
            )
        if v_loss < best[0]:
            best = (
                v_loss,
                {k: v.detach().clone() for k, v in model.state_dict().items()},
            )
    if best[1] is not None:
        model.load_state_dict(best[1])
    model.eval()
    return model, stats


def export_weights(model) -> list[dict[str, Any]]:
    layers = []
    body = model.head.body
    for module in body:
        name = type(module).__name__
        if name == "Linear":
            layers.append({
                "kind": "linear",
                "weight": module.weight.detach().numpy().tolist(),
                "bias": module.bias.detach().numpy().tolist(),
            })
        elif name == "GELU":
            layers.append({"kind": "gelu"})
        # Dropout is identity at inference and is omitted.
    layers.append({
        "kind": "linear",
        "weight": model.head.out.weight.detach().numpy().tolist(),
        "bias": model.head.out.bias.detach().numpy().tolist(),
    })
    return layers


def numpy_forward(artifact: dict[str, Any], phi_rows, cand_rows) -> np.ndarray:
    """Reference inference: the exact function a live shadow must compute."""
    phi = (
        np.asarray(phi_rows, dtype=np.float64)
        - np.asarray(artifact["normalization"]["phi_mean"])
    ) / np.asarray(artifact["normalization"]["phi_scale"])
    cand = (
        np.asarray(cand_rows, dtype=np.float64)
        - np.asarray(artifact["normalization"]["candidate_mean"])
    ) / np.asarray(artifact["normalization"]["candidate_scale"])
    x = np.concatenate([phi, cand], axis=1)
    for layer in artifact["layers"]:
        if layer["kind"] == "linear":
            x = x @ np.asarray(layer["weight"]).T + np.asarray(layer["bias"])
        elif layer["kind"] == "gelu":
            x = 0.5 * x * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))
    return x[:, 0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--parity-rows", type=int, default=512)
    args = parser.parse_args()
    import torch

    rows = load_examples(args.root)
    if not rows:
        raise SystemExit("no rows loaded")
    model, stats = final_fit(torch, rows, seed=args.seed, epochs=args.epochs)
    artifact = {
        "schema_version": 1,
        "model": "candidate_mlp_safety_v1",
        "provenance": {
            "trainer": "scripts/train_state_model.py architecture",
            "corpus_rows": len(rows),
            "corpus_cases": sorted({r["case_id"] for r in rows}),
            "seed": args.seed,
            "epochs": args.epochs,
            "loco_verdict": "state_model_beats_incumbent "
                            "(reports/state-model/summary.md)",
        },
        "input_contract": {
            "phi_features": list(FEATURES),
            "phi_source": "release_risk.features (the agent's own live "
                          "risk feature vector)",
            "candidate_width": len(rows[0]["candidate"]),
            "candidate_source": "train_state_model.candidate_vector "
                                "(candidate geometry plus container frame)",
            "output": "index 0 is the safety logit; regression heads "
                      f"{list(REGRESSION_TARGETS)} follow and are unused "
                      "at inference",
        },
        "normalization": {
            "phi_mean": stats["phi"][0].tolist(),
            "phi_scale": stats["phi"][1].tolist(),
            "candidate_mean": stats["cand"][0].tolist(),
            "candidate_scale": stats["cand"][1].tolist(),
        },
        "layers": export_weights(model),
    }
    probe = rows[: max(2, min(args.parity_rows, len(rows)))]
    phi_rows = [r["phi"] for r in probe]
    cand_rows = [r["candidate"] for r in probe]
    with torch.no_grad():
        torch_logits = model(
            torch.tensor(
                (np.array(phi_rows, dtype=np.float32) - stats["phi"][0])
                / stats["phi"][1]
            ),
            torch.tensor(
                (np.array(cand_rows, dtype=np.float32) - stats["cand"][0])
                / stats["cand"][1]
            ),
            None,
            None,
        )[:, 0].numpy()
    numpy_logits = numpy_forward(artifact, phi_rows, cand_rows)
    parity = float(np.max(np.abs(torch_logits - numpy_logits)))
    artifact["parity"] = {
        "rows": len(probe),
        "max_abs_logit_diff": parity,
        "passed": parity < 1e-4,
    }
    safe = np.array([r["safe"] for r in rows])
    all_logits = numpy_forward(
        artifact, [r["phi"] for r in rows], [r["candidate"] for r in rows]
    )
    order = np.argsort(all_logits)
    ranks = np.empty(len(order)); ranks[order] = np.arange(len(order))
    positives = ranks[safe > 0.5]
    negatives = ranks[safe <= 0.5]
    auc = (
        (positives.mean() - (len(positives) - 1) / 2.0) / len(negatives)
        if len(positives) and len(negatives) else None
    )
    artifact["training_fit_auc_not_heldout"] = auc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, indent=2) + "\n", encoding="utf-8"
    )
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(json.dumps({
        "output": str(args.output),
        "sha256": digest,
        "parity_max_abs_diff": parity,
        "parity_passed": artifact["parity"]["passed"],
        "rows": len(rows),
        "training_fit_auc_not_heldout": auc,
    }, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
