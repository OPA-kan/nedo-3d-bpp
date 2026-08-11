"""
Train on the board, not on eight scalars.

The learnability audit tested a hand-picked eight-dimensional contact vector
with a linear model and a lookup table, and saturated near sixteen boards. It
was then used to argue against training anything bigger, which overreaches:
that null is a property of those eight scalars, not of the data. The retained
snapshots carry the whole board -- every placed item with its pose and
dimensions, the remaining pool, the container -- and none of it reaches the
eight scalars.

This trains models that do see it, on exactly the audit's protocol so the
numbers are comparable: leave-one-case-out, ranking scored inside each board,
and the incumbent `Ranker.score` in the table. Three arms, chosen so a win can
be attributed:

  phi_mlp        the eight scalars only, non-linear. Isolates model capacity.
  candidate_mlp  + the candidate's own geometry and the container. The eight
                 scalars describe predicted contact and never say where in
                 the container the item is going.
  set_attention  + attention over the placed items and the remaining pool.
                 This is the transformer arm; it is the only one that can see
                 a neighbour.

If set_attention does not beat candidate_mlp, attention over the board is not
buying anything here and the honest report says so. If candidate_mlp beats
phi_mlp, the eight scalars were the constraint rather than the model family,
which is the audit's own caveat coming true.

Torch is an offline analysis dependency (`requirements-learning.txt`) and is
deliberately NOT in the agent's runtime requirements: the shipped agent stays
CPU-first with numpy, and nothing here runs inside the policy.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import sys
from typing import Any

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.audit_learnability import (  # noqa: E402
    FEATURES,
    REGRESSION_TARGETS,
    auc,
)
from scripts.index_replay_corpus import state_fingerprint  # noqa: E402

MAX_PLACED = 24
MAX_POOL = 16


def item_token(item: dict[str, Any], origin: list[float]) -> list[float]:
    """One placed or pending item, positioned relative to the candidate."""
    pos = item.get("pos") or [0.0, 0.0, 0.0]
    orn = item.get("orn") or [0.0, 0.0, 0.0, 1.0]
    qx, qy = float(orn[0]), float(orn[1])
    tilt = math.degrees(
        math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * (qx * qx + qy * qy))))
    )
    return [
        float(pos[0]) - origin[0],
        float(pos[1]) - origin[1],
        float(pos[2]) - origin[2],
        float(item.get("length", 0.0)),
        float(item.get("width", 0.0)),
        float(item.get("height", 0.0)),
        float(item.get("mass", 0.0)),
        1.0 if item.get("is_soft") else 0.0,
        1.0 if item.get("is_prioritized") else 0.0,
        tilt,
        1.0,
    ]


def pool_token(item: dict[str, Any]) -> list[float]:
    return [
        0.0,
        0.0,
        0.0,
        float(item.get("length", 0.0)),
        float(item.get("width", 0.0)),
        float(item.get("height", 0.0)),
        float(item.get("mass", 0.0)),
        1.0 if item.get("is_soft") else 0.0,
        1.0 if item.get("is_prioritized") else 0.0,
        0.0,
        0.0,
    ]


TOKEN_WIDTH = 11


def board_tokens(
    snapshot: dict[str, Any], *, container_index: int, origin: list[float]
) -> np.ndarray:
    """Placed items nearest the candidate, then the pending pool."""
    observation = snapshot.get("observation") or {}
    placed: list[tuple[float, list[float]]] = []
    for container in observation.get("container_list") or []:
        same = int(container.get("index", -1)) == container_index
        for item in container.get("packed_items") or []:
            token = item_token(item, origin)
            if not same:
                # Another container's contents are context, not neighbours.
                token = token[:]
                token[10] = 0.5
            distance = math.sqrt(sum(value * value for value in token[:3]))
            placed.append((distance, token))
    placed.sort(key=lambda pair: pair[0])

    tokens = [token for _distance, token in placed[:MAX_PLACED]]
    tokens.extend(
        pool_token(item)
        for item in (observation.get("pool_list") or [])[:MAX_POOL]
    )
    if not tokens:
        tokens = [[0.0] * TOKEN_WIDTH]
    return np.array(tokens, dtype=np.float32)


def candidate_vector(
    row: dict[str, Any], snapshot: dict[str, Any]
) -> list[float]:
    """The action itself and the container it targets.

    None of this is in `phi_modelling`: the eight scalars describe predicted
    contact, and never say where in the container the item is going or what
    the container is shaped like.
    """
    center = list(row.get("center") or [0.0, 0.0, 0.0])
    size = list(row.get("size") or [0.0, 0.0, 0.0])
    container_index = int(row.get("container_index", 0))
    container = {}
    for entry in (snapshot.get("observation") or {}).get(
        "container_list"
    ) or []:
        if int(entry.get("index", -1)) == container_index:
            container = entry
            break
    orientation = int(row.get("orientation", 0))
    return [
        *(float(value) for value in center[:3]),
        *(float(value) for value in size[:3]),
        float(size[0] * size[1] * size[2]),
        *[1.0 if orientation == index else 0.0 for index in range(6)],
        1.0 if row.get("kind") == "release_candidate" else 0.0,
        float(container.get("length", 0.0)),
        float(container.get("width", 0.0)),
        float(container.get("height", 0.0)),
        1.0 if container.get("shelf") else 0.0,
        1.0 if container.get("is_prioritized") else 0.0,
        float(len(container.get("packed_items") or [])),
    ]


def load_examples(root: pathlib.Path) -> list[dict[str, Any]]:
    """Rows joined to the board they were measured on."""
    seen: set[tuple[Any, ...]] = set()
    examples: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/dataset/*/step-*-*.jsonl")):
        step_label = path.name.split("-")[1]
        snapshot_path = path.parent / f"step-{step_label}-state.json"
        board = state_fingerprint(snapshot_path)
        if board is None:
            continue
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        with path.open("r", encoding="utf-8") as handle:
            lines = [line for line in handle if line.strip()]
        for line in lines:
            row = json.loads(line)
            key = (board, str(row.get("candidate_id")))
            if key in seen:
                continue
            seen.add(key)
            phi = row.get("phi_modelling") or {}
            values = [phi.get(name) for name in FEATURES]
            if not phi or any(value is None for value in values):
                continue
            physical = row.get("physical") or {}
            origin = [float(v) for v in (row.get("center") or [0, 0, 0])[:3]]
            examples.append(
                {
                    "state": board,
                    "case_id": str(row.get("case_id")),
                    "phi": [float(value) for value in values],
                    "candidate": candidate_vector(row, snapshot),
                    "tokens": board_tokens(
                        snapshot,
                        container_index=int(row.get("container_index", 0)),
                        origin=origin,
                    ),
                    "safe": float(bool(physical.get("is_placed_safe"))),
                    "score": float(row.get("score_immediate", 0.0)),
                    "targets": [
                        float(physical.get(name) or 0.0)
                        for name in REGRESSION_TARGETS
                    ],
                }
            )
    return examples


def build_models(torch, widths: dict[str, int]):
    nn = torch.nn

    class Head(nn.Module):
        def __init__(self, width: int, hidden: int = 64):
            super().__init__()
            self.body = nn.Sequential(
                nn.Linear(width, hidden),
                nn.GELU(),
                nn.Dropout(0.1),
                nn.Linear(hidden, hidden),
                nn.GELU(),
            )
            self.out = nn.Linear(hidden, 1 + len(REGRESSION_TARGETS))

        def forward(self, features):
            return self.out(self.body(features))

    class Mlp(nn.Module):
        def __init__(self, *, use_candidate: bool):
            super().__init__()
            self.use_candidate = use_candidate
            width = widths["phi"] + (
                widths["candidate"] if use_candidate else 0
            )
            self.head = Head(width)

        def forward(self, phi, candidate, tokens, mask):
            if not self.use_candidate:
                return self.head(phi)
            return self.head(torch.cat([phi, candidate], dim=-1))

    class SetAttention(nn.Module):
        """Candidate token attends over the board; the transformer arm."""

        def __init__(self, dim: int = 64, heads: int = 4, layers: int = 2):
            super().__init__()
            self.query = nn.Linear(
                widths["phi"] + widths["candidate"], dim
            )
            self.token = nn.Linear(TOKEN_WIDTH, dim)
            self.blocks = nn.ModuleList(
                [
                    nn.ModuleDict(
                        {
                            "attention": nn.MultiheadAttention(
                                dim, heads, dropout=0.1, batch_first=True
                            ),
                            "norm1": nn.LayerNorm(dim),
                            "norm2": nn.LayerNorm(dim),
                            "ff": nn.Sequential(
                                nn.Linear(dim, 2 * dim),
                                nn.GELU(),
                                nn.Linear(2 * dim, dim),
                            ),
                        }
                    )
                    for _ in range(layers)
                ]
            )
            self.head = Head(dim + widths["phi"] + widths["candidate"])

        def forward(self, phi, candidate, tokens, mask):
            context = torch.cat([phi, candidate], dim=-1)
            state = self.query(context).unsqueeze(1)
            memory = self.token(tokens)
            for block in self.blocks:
                attended, _weights = block["attention"](
                    state, memory, memory, key_padding_mask=mask
                )
                state = block["norm1"](state + attended)
                state = block["norm2"](state + block["ff"](state))
            return self.head(
                torch.cat([state.squeeze(1), context], dim=-1)
            )

    return Mlp, SetAttention


def pad_tokens(
    examples: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
    longest = max(len(example["tokens"]) for example in examples)
    padded = np.zeros(
        (len(examples), longest, TOKEN_WIDTH), dtype=np.float32
    )
    mask = np.ones((len(examples), longest), dtype=bool)
    for index, example in enumerate(examples):
        tokens = example["tokens"]
        padded[index, : len(tokens)] = tokens
        mask[index, : len(tokens)] = False
    return padded, mask


def fit_arm(
    torch,
    arm: str,
    train: list[dict[str, Any]],
    test: list[dict[str, Any]],
    *,
    seed: int,
    epochs: int,
) -> np.ndarray:
    """Train one arm on `train`, return its raw outputs on `test`."""
    torch.manual_seed(seed)
    Mlp, SetAttention = build_models(
        torch,
        {
            "phi": len(train[0]["phi"]),
            "candidate": len(train[0]["candidate"]),
        },
    )
    model = {
        "phi_mlp": lambda: Mlp(use_candidate=False),
        "candidate_mlp": lambda: Mlp(use_candidate=True),
        "set_attention": SetAttention,
    }[arm]()

    def tensors(rows, stats=None):
        phi = np.array([r["phi"] for r in rows], dtype=np.float32)
        cand = np.array([r["candidate"] for r in rows], dtype=np.float32)
        tokens, mask = pad_tokens(rows)
        targets = np.array([r["targets"] for r in rows], dtype=np.float32)
        safe = np.array([r["safe"] for r in rows], dtype=np.float32)
        if stats is None:
            stats = {}
            for name, block in (
                ("phi", phi), ("cand", cand), ("targets", targets)
            ):
                mean = block.mean(axis=0)
                spread = block.std(axis=0)
                spread[spread <= 0] = 1.0
                stats[name] = (mean, spread)
            flat = tokens.reshape(-1, TOKEN_WIDTH)
            mean = flat.mean(axis=0)
            spread = flat.std(axis=0)
            spread[spread <= 0] = 1.0
            stats["tokens"] = (mean, spread)
        norm = {
            "phi": (phi - stats["phi"][0]) / stats["phi"][1],
            "cand": (cand - stats["cand"][0]) / stats["cand"][1],
            "tokens": (tokens - stats["tokens"][0]) / stats["tokens"][1],
            "targets": (
                targets - stats["targets"][0]
            ) / stats["targets"][1],
        }
        return (
            {
                "phi": torch.tensor(norm["phi"]),
                "candidate": torch.tensor(norm["cand"]),
                "tokens": torch.tensor(norm["tokens"]),
                "mask": torch.tensor(mask),
                "targets": torch.tensor(norm["targets"]),
                "safe": torch.tensor(safe),
            },
            stats,
        )

    # The validation split is by CASE, like the outer fold. Splitting rows
    # would put the same board on both sides and stop early on memorisation.
    cases = sorted({row["case_id"] for row in train})
    held = {cases[seed % len(cases)]} if len(cases) > 1 else set()
    inner_train = [r for r in train if r["case_id"] not in held] or train
    inner_valid = [r for r in train if r["case_id"] in held] or train

    batch, stats = tensors(inner_train)
    valid, _ = tensors(inner_valid, stats)
    probe, _ = tensors(test, stats)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=3e-3, weight_decay=1e-2
    )
    bce = torch.nn.BCEWithLogitsLoss()
    mse = torch.nn.MSELoss()
    best = (float("inf"), None)
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        out = model(
            batch["phi"], batch["candidate"], batch["tokens"], batch["mask"]
        )
        loss = bce(out[:, 0], batch["safe"]) + mse(
            out[:, 1:], batch["targets"]
        )
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        if epoch % 5 == 0 or epoch == epochs - 1:
            model.eval()
            with torch.no_grad():
                out = model(
                    valid["phi"],
                    valid["candidate"],
                    valid["tokens"],
                    valid["mask"],
                )
                score = float(
                    bce(out[:, 0], valid["safe"])
                    + mse(out[:, 1:], valid["targets"])
                )
            if score < best[0]:
                best = (
                    score,
                    {
                        key: value.detach().clone()
                        for key, value in model.state_dict().items()
                    },
                )
    if best[1] is not None:
        model.load_state_dict(best[1])
    model.eval()
    with torch.no_grad():
        out = model(
            probe["phi"], probe["candidate"], probe["tokens"], probe["mask"]
        ).numpy()
    # Undo target standardisation so R^2 is in the reported units.
    out[:, 1:] = out[:, 1:] * stats["targets"][1] + stats["targets"][0]
    return out


def state_metrics(
    rows: list[dict[str, Any]], scores: np.ndarray
) -> dict[str, Any]:
    by_state: dict[Any, list[int]] = collections.defaultdict(list)
    for index, row in enumerate(rows):
        by_state[row["state"]].append(index)
    aucs: list[float] = []
    hits = 0.0
    usable = 0
    for indexes in by_state.values():
        labels = np.array([rows[i]["safe"] for i in indexes])
        if labels.all() or not labels.any():
            continue
        usable += 1
        value = auc(scores[indexes], labels)
        if value is not None:
            aucs.append(value)
        values = scores[indexes]
        tied = np.flatnonzero(values >= values.max() - 1e-12)
        hits += sum(rows[indexes[i]]["safe"] for i in tied) / len(tied)
    return {
        "states": usable,
        "mean_state_auc": sum(aucs) / len(aucs) if aucs else None,
        "top1_safe_rate": hits / usable if usable else None,
    }


ARMS = ("phi_mlp", "candidate_mlp", "set_attention")


def run(
    root: pathlib.Path, *, seeds: int, epochs: int
) -> dict[str, Any]:
    import torch

    torch.set_num_threads(4)
    examples = load_examples(root)
    cases = sorted({example["case_id"] for example in examples})
    states = {example["state"] for example in examples}
    if len(cases) < 2 or len(examples) < 100:
        return {
            "verdict": "insufficient_corpus",
            "rows": len(examples),
            "cases": cases,
        }

    predictions = {
        arm: np.zeros((len(examples), 1 + len(REGRESSION_TARGETS)))
        for arm in ARMS
    }
    for case in cases:
        test_index = [
            i for i, e in enumerate(examples) if e["case_id"] == case
        ]
        train_index = [
            i for i, e in enumerate(examples) if e["case_id"] != case
        ]
        train = [examples[i] for i in train_index]
        test = [examples[i] for i in test_index]
        assert not (
            {e["state"] for e in train} & {e["state"] for e in test}
        ), "a board leaked across the fold"
        for arm in ARMS:
            stacked = np.mean(
                [
                    fit_arm(
                        torch, arm, train, test, seed=seed, epochs=epochs
                    )
                    for seed in range(seeds)
                ],
                axis=0,
            )
            predictions[arm][test_index] = stacked

    labels = np.array([e["safe"] for e in examples])
    incumbent = np.array([e["score"] for e in examples])
    report: dict[str, Any] = {
        "schema_version": 1,
        "corpus": {
            "rows": len(examples),
            "states": len(states),
            "cases": cases,
            "safe_rows": int(labels.sum()),
        },
        "design": {
            "split": "leave_one_case_out",
            "seeds": seeds,
            "epochs": epochs,
            "arms": list(ARMS),
            "max_placed_tokens": MAX_PLACED,
            "max_pool_tokens": MAX_POOL,
        },
        "classification": {
            "incumbent": {
                "pooled_auc": auc(incumbent, labels),
                **state_metrics(examples, incumbent),
            }
        },
        "regression": {},
    }
    for arm in ARMS:
        report["classification"][arm] = {
            "pooled_auc": auc(predictions[arm][:, 0], labels),
            **state_metrics(examples, predictions[arm][:, 0]),
        }
    for offset, target in enumerate(REGRESSION_TARGETS):
        actual = np.array([e["targets"][offset] for e in examples])
        # The constant baseline is the held-out-fold train mean, matching
        # how audit_learnability scores its own R^2.
        baseline = np.zeros(len(examples))
        for case in cases:
            test_index = [
                i for i, e in enumerate(examples) if e["case_id"] == case
            ]
            train_index = [
                i for i, e in enumerate(examples) if e["case_id"] != case
            ]
            baseline[test_index] = actual[train_index].mean()
        denominator = float(((actual - baseline) ** 2).sum())
        report["regression"][target] = {
            arm: (
                None
                if denominator <= 0
                else 1.0
                - float(
                    ((actual - predictions[arm][:, 1 + offset]) ** 2).sum()
                )
                / denominator
            )
            for arm in ARMS
        }

    best_arm = max(
        ARMS,
        key=lambda arm: report["classification"][arm]["mean_state_auc"] or 0.0,
    )
    best = report["classification"][best_arm]["mean_state_auc"] or 0.0
    incumbent_auc = report["classification"]["incumbent"]["mean_state_auc"]
    report["verdict"] = (
        "state_model_beats_incumbent"
        if incumbent_auc is not None and best > incumbent_auc + 0.02
        else "no_established_signal"
    )
    report["interpretation"] = (
        "Same protocol as scripts/audit_learnability.py, so these numbers sit "
        "beside its linear and lookup arms. phi_mlp isolates model capacity "
        "on the eight scalars; candidate_mlp adds the action's own geometry "
        "and its container; set_attention adds attention over the placed "
        "items and the pool and is the only arm that can see a neighbour. A "
        "win by candidate_mlp over phi_mlp means the features were the "
        "constraint; a win by set_attention over candidate_mlp means the "
        "board is. The corpus is small, so read the ordering of the arms, "
        "not the third decimal."
    )
    return report


def markdown(report: dict[str, Any]) -> str:
    if "classification" not in report:
        return (
            "# State-model training\n\n"
            f"- Verdict: **{report['verdict']}** "
            f"({report.get('rows', 0)} rows)\n"
        )
    corpus = report["corpus"]
    lines = [
        "# State-model training",
        "",
        f"- Verdict: **{report['verdict']}**",
        (
            f"- Corpus: {corpus['rows']} rows, {corpus['states']} boards, "
            f"{len(corpus['cases'])} cases"
        ),
        (
            f"- Split: `{report['design']['split']}`, "
            f"{report['design']['seeds']} seeds, "
            f"{report['design']['epochs']} epochs"
        ),
        "",
        "| model | mean within-state AUC | pooled AUC | top-1 safe rate |",
        "|---|---:|---:|---:|",
    ]
    order = ["incumbent", *ARMS]
    for name in order:
        values = report["classification"][name]
        lines.append(
            "| {name} | {a} | {p} | {t} |".format(
                name=name,
                a=_fmt(values["mean_state_auc"]),
                p=_fmt(values["pooled_auc"]),
                t=_fmt(values["top1_safe_rate"]),
            )
        )
    lines.extend(
        [
            "",
            "## settle regression (R^2 against a held-out constant)",
            "",
            "| target | " + " | ".join(ARMS) + " |",
            "|---|" + "---:|" * len(ARMS),
        ]
    )
    for target, values in report["regression"].items():
        lines.append(
            f"| {target} | "
            + " | ".join(_fmt(values[arm]) for arm in ARMS)
            + " |"
        )
    lines.extend(["", report["interpretation"], ""])
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--json-output", type=pathlib.Path, required=True)
    parser.add_argument("--markdown-output", type=pathlib.Path, required=True)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--epochs", type=int, default=300)
    args = parser.parse_args()

    report = run(args.root, seeds=args.seeds, epochs=args.epochs)
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
