"""
What is a good residual space? Measure it instead of asserting it.

The dataset line exists to spread candidates across *different residual
states*. "Different" is currently decided by a hand-made Gower distance over
fourteen chosen fields in `residual_diversity.py`, applied to the observed
`x_plus` after every candidate has been replayed through PyBullet. Two things
follow that nobody has checked:

1. The definition is hand-made. If a learned representation orders pairs of
   candidates by residual difference better than the fourteen fields do, the
   sampler is using the wrong metric and should use the learned one.

2. The metric needs the replay it is supposed to be planning. Settling every
   overdrawn candidate is the expensive step of the whole pipeline. Anything
   that predicts observed residual difference *before* the replay could pick
   a spread-out portfolio without paying for physics first.

So the question here is one question, asked pairwise inside a board:

    given two candidates from the same state, how far apart will their
    settled afterstates be -- and what predicts that best, knowing only what
    is available before the replay?

Ground truth is the same Gower distance the acceptance guard reports, applied
to the observed `x_plus` records. Predictors, all available pre-replay:

  command_proxy    the same Gower distance on the COMMAND features. This is
                   the incumbent: what the sampler uses before it has
                   replayed anything.
  candidate_mlp    L2 in the penultimate representation of the arm that has
                   no board inputs at all.
  set_attention    L2 in the board-aware representation.

Pairs are formed strictly within a board. Cross-board pairs would be
dominated by how different the two boards are, which is not the question and
would inflate every correlation equally. The representations come from models
trained leave-one-case-out, so a board is never embedded by a model that
trained on its own case.

A win for `set_attention` here means the residual space should be learned and
the sampler's distance function replaced. A win for `command_proxy` means the
fourteen hand-made fields are already doing the job and attention is not
earning its place in this pipeline. Both are useful answers; the point is
that it is currently unmeasured.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.residual_diversity import (  # noqa: E402
    CONTINUOUS_FIELDS,
    feature_vector_distance,
    proxy_feature_vector,
    scale_vector,
    settled_proxy_record,
)
from scripts.train_state_model import (  # noqa: E402
    fit_arm,
    load_examples,
)

EMBEDDING_ARMS = ("candidate_mlp", "set_attention")


def spearman(x: list[float], y: list[float]) -> float | None:
    """Rank correlation. The question is ordering, not calibration."""
    if len(x) < 3:
        return None

    def ranks(values: list[float]) -> np.ndarray:
        order = np.argsort(np.argsort(values))
        result = np.empty(len(values), dtype=float)
        array = np.asarray(values, dtype=float)
        # Average ranks over ties, otherwise a predictor that is constant on
        # a subset gets credited for an arbitrary ordering of it.
        for value in np.unique(array):
            positions = np.flatnonzero(array == value)
            result[positions] = order[positions].mean()
        return result

    a, b = ranks(x), ranks(y)
    if a.std() <= 0 or b.std() <= 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def command_record(example: dict[str, Any]) -> dict[str, Any]:
    """The row as the sampler sees it before any replay."""
    return {
        "pool_index": example["pool_index"],
        "item_index": example["item_index"],
        "container_index": example["container_index"],
        "orientation": example["orientation"],
        "kind": example["kind"],
        "center": example["center"],
        "size": example["size"],
        "release_risk": example.get("release_risk"),
    }


def observed_record(example: dict[str, Any]) -> dict[str, Any] | None:
    return settled_proxy_record(
        command_record(example), {"x_plus": example.get("x_plus")}
    )


def board_pairs(
    examples: list[dict[str, Any]],
    embeddings: dict[str, np.ndarray],
) -> dict[str, list[float]]:
    """Every within-board pair, scored by truth and by each predictor."""
    by_board: dict[Any, list[int]] = collections.defaultdict(list)
    for index, example in enumerate(examples):
        if observed_record(example) is not None:
            by_board[example["state"]].append(index)

    columns: dict[str, list[float]] = collections.defaultdict(list)
    per_board: list[dict[str, float]] = []
    for indexes in by_board.values():
        if len(indexes) < 3:
            continue
        observed = [observed_record(examples[i]) for i in indexes]
        commanded = [command_record(examples[i]) for i in indexes]
        # Scales come from the board's own population, matching how
        # residual_proxy_coverage normalises inside a portfolio.
        observed_scales = scale_vector(
            [proxy_feature_vector(record) for record in observed]
        )
        command_scales = scale_vector(
            [proxy_feature_vector(record) for record in commanded]
        )
        observed_vectors = [proxy_feature_vector(r) for r in observed]
        command_vectors = [proxy_feature_vector(r) for r in commanded]

        local: dict[str, list[float]] = collections.defaultdict(list)
        for left in range(len(indexes)):
            for right in range(left + 1, len(indexes)):
                local["truth"].append(
                    feature_vector_distance(
                        observed_vectors[left],
                        observed_vectors[right],
                        scales=observed_scales,
                    )
                )
                local["command_proxy"].append(
                    feature_vector_distance(
                        command_vectors[left],
                        command_vectors[right],
                        scales=command_scales,
                    )
                )
                for arm, matrix in embeddings.items():
                    a = matrix[indexes[left]]
                    b = matrix[indexes[right]]
                    local[arm].append(float(np.linalg.norm(a - b)))
        row = {
            name: spearman(local[name], local["truth"])
            for name in local
            if name != "truth"
        }
        if any(value is not None for value in row.values()):
            per_board.append(row)
        for name, values in local.items():
            columns[name].extend(values)
    columns["_per_board"] = per_board
    return columns


def measure(
    root: pathlib.Path, *, seeds: int, epochs: int
) -> dict[str, Any]:
    import torch

    torch.set_num_threads(4)
    examples = load_examples(root)
    examples = [e for e in examples if observed_record(e) is not None]
    cases = sorted({e["case_id"] for e in examples})
    if len(cases) < 2:
        return {"verdict": "insufficient_corpus", "cases": cases}

    embeddings: dict[str, np.ndarray] = {}
    for case in cases:
        test_index = [
            i for i, e in enumerate(examples) if e["case_id"] == case
        ]
        train = [e for e in examples if e["case_id"] != case]
        test = [examples[i] for i in test_index]
        for arm in EMBEDDING_ARMS:
            stacked = None
            for seed in range(seeds):
                _out, vectors = fit_arm(
                    torch,
                    arm,
                    train,
                    test,
                    seed=seed,
                    epochs=epochs,
                    return_embeddings=True,
                )
                stacked = vectors if stacked is None else stacked + vectors
            matrix = embeddings.setdefault(
                arm, np.zeros((len(examples), stacked.shape[1]))
            )
            matrix[test_index] = stacked / seeds

    columns = board_pairs(examples, embeddings)
    per_board = columns.pop("_per_board")
    predictors = [name for name in columns if name != "truth"]

    def mean_board(name: str) -> float | None:
        values = [
            row[name] for row in per_board if row.get(name) is not None
        ]
        return sum(values) / len(values) if values else None

    report = {
        "schema_version": 1,
        "corpus": {
            "rows": len(examples),
            "boards": len({e["state"] for e in examples}),
            "cases": cases,
            "pairs": len(columns["truth"]),
            "boards_scored": len(per_board),
        },
        "design": {
            "split": "leave_one_case_out",
            "seeds": seeds,
            "epochs": epochs,
            "pairs": "within_board_only",
            "truth": "gower_distance_over_observed_x_plus",
            "proxy_fields": list(CONTINUOUS_FIELDS),
        },
        "mean_within_board_spearman": {
            name: mean_board(name) for name in predictors
        },
        "pooled_spearman": {
            name: spearman(columns[name], columns["truth"])
            for name in predictors
        },
    }
    ranked = sorted(
        (
            (report["mean_within_board_spearman"][name] or -1.0, name)
            for name in predictors
        ),
        reverse=True,
    )
    best_value, best_name = ranked[0]
    incumbent = report["mean_within_board_spearman"]["command_proxy"] or 0.0
    report["best_predictor"] = best_name
    report["verdict"] = (
        "learned_residual_space_wins"
        if best_name != "command_proxy" and best_value > incumbent + 0.02
        else "hand_made_proxy_holds"
    )
    report["interpretation"] = (
        "Pairs are formed inside a board, so this measures ordering of "
        "candidate-versus-candidate residual difference, not how different "
        "two boards are. Truth is the same Gower distance the acceptance "
        "guard reports, on observed x_plus. Every predictor is available "
        "before the replay, which is the expensive step -- so a learned "
        "winner would also mean a portfolio can be spread out without "
        "settling every overdrawn candidate first. A win for command_proxy "
        "means the fourteen hand-made fields already do the job."
    )
    return report


def markdown(report: dict[str, Any]) -> str:
    if "mean_within_board_spearman" not in report:
        return f"# Residual space\n\n- Verdict: **{report['verdict']}**\n"
    corpus = report["corpus"]
    lines = [
        "# Residual space: what predicts observed afterstate difference",
        "",
        f"- Verdict: **{report['verdict']}**"
        f" (best: `{report['best_predictor']}`)",
        (
            f"- {corpus['pairs']} within-board pairs from "
            f"{corpus['boards']} boards, {len(corpus['cases'])} cases"
        ),
        f"- Truth: `{report['design']['truth']}`",
        "",
        "| predictor | mean within-board Spearman | pooled Spearman |",
        "|---|---:|---:|",
    ]
    for name, value in report["mean_within_board_spearman"].items():
        pooled = report["pooled_spearman"][name]
        lines.append(
            f"| {name} | "
            f"{'—' if value is None else f'{value:.3f}'} | "
            f"{'—' if pooled is None else f'{pooled:.3f}'} |"
        )
    lines.extend(["", report["interpretation"], ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--epochs", type=int, default=200)
    args = parser.parse_args()

    report = measure(args.root, seeds=args.seeds, epochs=args.epochs)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=float) + "\n",
        encoding="utf-8",
    )
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(args.markdown_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
