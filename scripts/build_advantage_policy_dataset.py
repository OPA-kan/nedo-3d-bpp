"""Turn logged packing episodes into advantage-weighted policy examples.

This is the PCT method (`alexfrom0815/Online-3D-BPP-PCT`, ICLR 2022)
applied to data we already have, and only the method -- their training
loop is impossible here, because their environment is analytic numpy at
microseconds a step and ours settles every placement in PyBullet at
about a second (`reports/value/pct-reference-reading-20260831.md`).

What is copied is the *shape of the learning signal*:

* their reward is dense and per-item -- the volume fraction of the item
  just placed, paid at every step -- so the return of a state is simply
  the volume packed from there onward. Ours is `fill_score_proxy`, the
  same quantity, and it telescopes:

      G_t = final_fill - fill_before(t)

  No terminal is required and no rollout is required. An episode that
  ends `no_retained_candidate` labels its prefix states exactly as well
  as one that exhausts the stream -- which is the whole reason the tail
  problem that blocked Cups 009 and 010 does not arise here.
* their learning signal is an advantage, not a dominance verdict. Every
  logged decision teaches; nothing is discarded for being
  `incomparable`. Cup 009's strict-pair corpus was 156 rows from the
  same episodes that hold ~1500 decisions.

**Baseline.** The advantage subtracts a per-(cell, step) mean over the
horses that ran that cell. Within a cell the item stream is identical,
so step t means the same items have arrived; this is the standard
time-dependent baseline b(t), computed empirically with no model in the
loop. Using the fitted V_theta instead would put a model trained on
these same states inside the label, which is a leak this cannot afford.

**What this is not.** The behaviour policies are ours (rule studs,
current-agent, rule-alpha, the champion), so this is offline,
off-policy, single-sample-per-state learning. Advantage-weighted
regression is a legitimate offline method, but it is bounded by the
support of what those policies did: it can learn to prefer the better of
the moves that were tried, never a move nobody tried.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONTRACT = "advantage_policy_dataset_v1"


def _cell_of(path: pathlib.Path) -> str | None:
    for part in path.parts:
        if part.startswith("cup-cell-"):
            return part
    return None


def episode_rows(
    manifest_path: pathlib.Path, *, cell: str, horse: str,
) -> list[dict[str, Any]]:
    """One row per logged decision, carrying its telescoped return."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for episode in manifest.get("episodes") or []:
        final = (episode.get("final_metrics") or {}).get("fill_score_proxy")
        if not isinstance(final, (int, float)):
            continue
        for record in episode.get("records") or []:
            before = (record.get("metrics_before") or {}).get(
                "fill_score_proxy"
            )
            selected = (record.get("selection") or {}).get(
                "selected_candidate_id"
            )
            candidates = [
                candidate
                for candidate in (record.get("search") or {}).get(
                    "root_candidates"
                ) or []
                if candidate.get("safe")
            ]
            if not isinstance(before, (int, float)) or selected is None:
                continue
            if len(candidates) < 2:
                # one option is not a decision: no gradient, and it would
                # bias the baseline toward states nobody could act on
                continue
            if selected not in {
                str(candidate["root_candidate_id"])
                for candidate in candidates
            }:
                # the actor executed a move outside its own safe root
                # support -- the Cup 008 mismatch. Not trainable here.
                continue
            snapshot = (
                manifest_path.parent / "episode-000"
                / str(record["snapshot_path"])
            )
            if not snapshot.is_file():
                continue
            rows.append({
                "cell": cell,
                "horse": horse,
                "step": int(record.get("step", 0)),
                "root_id": f"{cell}:{horse}:{record.get('root_id')}",
                "board_fingerprint": record.get("board_fingerprint"),
                "snapshot_path": str(snapshot),
                "candidates": candidates,
                "selected_candidate_id": str(selected),
                "fill_before": float(before),
                "fill_final": float(final),
                # r_t summed from t onward, gamma = 1
                "return": float(final) - float(before),
            })
    return rows


def add_advantages(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """A_t = G_t - mean over the horses that reached step t in this cell."""
    pools = collections.defaultdict(list)
    for row in rows:
        pools[(row["cell"], row["step"])].append(row["return"])
    baselines = {
        key: sum(values) / len(values) for key, values in pools.items()
    }
    for row in rows:
        key = (row["cell"], row["step"])
        row["baseline"] = baselines[key]
        row["baseline_support"] = len(pools[key])
        row["advantage"] = row["return"] - baselines[key]
    values = [row["advantage"] for row in rows]
    mean = sum(values) / len(values) if values else 0.0
    variance = (
        sum((value - mean) ** 2 for value in values) / len(values)
        if values else 0.0
    )
    return {
        "rows": len(rows),
        "advantage_mean": mean,
        "advantage_std": math.sqrt(variance),
        "singleton_baselines": sum(
            1 for row in rows if row["baseline_support"] < 2
        ),
    }


def build(roots: list[pathlib.Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    manifests = 0
    for root in roots:
        for path in sorted(root.rglob("rollout/manifest.json")):
            cell = _cell_of(path)
            if cell is None:
                continue
            manifests += 1
            rows.extend(episode_rows(
                path, cell=f"{root.name}/{cell}", horse=path.parent.parent.name,
            ))
    if not rows:
        raise ValueError("no trainable decisions found under the given roots")
    stats = add_advantages(rows)
    stats["manifests"] = manifests
    stats["cells"] = len({row["cell"] for row in rows})
    stats["horses"] = sorted({row["horse"] for row in rows})
    return {"contract": CONTRACT, "stats": stats, "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episodes-root", type=pathlib.Path, action="append", required=True,
        help="directory searched recursively for */rollout/manifest.json",
    )
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    dataset = build([path.resolve() for path in args.episodes_root])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(dataset["stats"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
