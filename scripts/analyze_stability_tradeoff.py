"""
Read a paired ablation on placed AND the components placed gates.

placed is the cutoff gate for cog / stability / placement / soft
(`docs/COMPETITION_QA.md:9`), so an arm that buys placed by damaging those
components can be a net loss on the official total even while every local
number this project used to track goes up. Until the shake proxy and the
attribute-violation counts existed there was no way to see that trade at
all. This reads both sides of it from the same episodes.

Reported per arm, paired against the baseline on (case, repeat):

* **placed / fill** -- what was already visible;
* **shifted fraction** -- items moving more than 5 cm in the shake,
  normalised by item count, because an arm that places more items would
  otherwise show a larger raw count for free;
* **peak kinetic energy** and **max shift** -- the unnormalised severity;
* **priority / soft clean ratio** -- the attribute rules, skipped where the
  stream carries none of that attribute rather than counted as perfect.

No total is formed. The official weights are unknown -- 83 weight vectors
reproduce the one score we have -- so a combined number here would be an
invention, and the point is to see whether the axes disagree.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(output_dir: pathlib.Path):
    rows = [
        json.loads(line)
        for line in (output_dir / "rows.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    episodes = []
    for row in rows:
        for case_id, case in row["cases"].items():
            shake = case.get("shake_response") or {}
            attributes = case.get("attribute_placement") or {}
            items = int(shake.get("shake_items") or 0)
            episodes.append(
                {
                    "arm": row["arm"],
                    "case": case_id,
                    "repeat": str(row.get("repeat", 0)),
                    "placed": int(case.get("placed_count") or 0),
                    "fill": float(case.get("fill_score") or 0.0),
                    "shake_items": items,
                    "shifted_fraction": (
                        float(shake.get("shake_items_shifted") or 0) / items
                        if items
                        else None
                    ),
                    "toppled": int(shake.get("shake_items_toppled") or 0),
                    "max_shift": shake.get("shake_max_shift"),
                    "peak_energy": shake.get("shake_peak_kinetic_energy"),
                    "priority_clean": attributes.get("priority_clean_ratio"),
                    "soft_clean": attributes.get("soft_clean_ratio"),
                }
            )
    return episodes


FIELDS = (
    "placed",
    "fill",
    "shifted_fraction",
    "toppled",
    "max_shift",
    "peak_energy",
    "priority_clean",
    "soft_clean",
)


def mean_of(values):
    present = [float(v) for v in values if v is not None]
    return round(statistics.fmean(present), 4) if present else None


def per_arm(episodes):
    arms: dict[str, dict] = {}
    for episode in episodes:
        arms.setdefault(episode["arm"], []).append(episode)
    return {
        arm: {
            "episodes": len(rows),
            **{field: mean_of([r[field] for r in rows]) for field in FIELDS},
        }
        for arm, rows in arms.items()
    }


def paired(episodes, baseline_arm):
    base = {
        (e["case"], e["repeat"]): e
        for e in episodes
        if e["arm"] == baseline_arm
    }
    out = []
    for episode in episodes:
        if episode["arm"] == baseline_arm:
            continue
        reference = base.get((episode["case"], episode["repeat"]))
        if reference is None:
            continue
        diff = {"arm": episode["arm"], "case": episode["case"],
                "repeat": episode["repeat"]}
        for field in FIELDS:
            a, b = episode[field], reference[field]
            diff[field] = (
                None if a is None or b is None else round(float(a) - float(b), 4)
            )
        out.append(diff)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=pathlib.Path,
        default=ROOT / "reports" / "stability-tradeoff",
    )
    parser.add_argument("--baseline-arm", default="base")
    args = parser.parse_args()

    episodes = load(args.output_dir)
    payload = {
        "episodes": len(episodes),
        "baseline_arm": args.baseline_arm,
        "note": (
            "No combined total: the official component weights are unknown, "
            "so any total formed here would be an invention."
        ),
        "per_arm": per_arm(episodes),
        "paired_vs_baseline": paired(episodes, args.baseline_arm),
        "per_episode": episodes,
    }
    (args.output_dir / "tradeoff_summary.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["per_arm"], indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
