"""
Give the development suite a measurable noise floor.

Every adopt/reject call on this project rests on five configurations derived
from **two** item streams by varying look-ahead. So a result like "+5 placed
here, -4 there" has no reference: there is no way to tell real per-scenario
structure from the trajectory coincidence of two sequences. This builds
variants so that the spread of a *null* comparison can be measured directly.

Two modes, and the difference matters:

* `permute` (default) - reorder the SAME item multiset. Content, class mix,
  total volume and difficulty are all held exactly fixed; only arrival order
  changes. This is the clean probe for "is the heterogeneity we keep seeing
  just trajectory noise?", because it varies the one thing that produces
  trajectory divergence and nothing else.
* `resample` - draw items i.i.d. from the observed empirical distribution,
  preserving whole items rather than dimensions alone, so mass, friction,
  soft and priority stay coherent. This varies content as well, which
  answers a generalisation question rather than a noise question, and it
  changes difficulty between variants.

Whole items are sampled, never synthesised: no dimension, mass or friction
value appears that was not already in the source stream.

These are **synthetic** streams for variance estimation. They are not
competition data, they are not a holdout, and a result measured on them
transfers only as far as the exchangeability each mode assumes - `permute`
assumes arrival order is exchangeable, `resample` additionally assumes the
class draw is i.i.d.
"""
from __future__ import annotations

import argparse
import copy
import json
import pathlib
import random
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_SOURCE = ROOT / "simulator" / "configs" / "sample_config.json"
SCHEMA_VERSION = 1
MODES = ("permute", "resample")


def class_signature(item: dict[str, Any]) -> tuple:
    return (
        round(float(item["length"]), 4),
        round(float(item["width"]), 4),
        round(float(item["height"]), 4),
        round(float(item.get("mass", 1.0)), 4),
        bool(item.get("is_soft", False)),
        bool(item.get("is_prioritized", False)),
    )


def build_variant(
    item_list: list[dict[str, Any]],
    *,
    mode: str,
    rng: random.Random,
) -> list[dict[str, Any]]:
    if mode == "permute":
        drawn = list(item_list)
        rng.shuffle(drawn)
    elif mode == "resample":
        drawn = [rng.choice(item_list) for _ in range(len(item_list))]
    else:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
    # `index` is positional identity in the stream, so it is reassigned
    # rather than carried; everything else travels with the item.
    variant = []
    for position, item in enumerate(drawn):
        clone = copy.deepcopy(item)
        clone["index"] = position
        variant.append(clone)
    return variant


def stream_profile(item_list: list[dict[str, Any]]) -> dict[str, Any]:
    classes: dict[tuple, int] = {}
    for item in item_list:
        signature = class_signature(item)
        classes[signature] = classes.get(signature, 0) + 1
    return {
        "items": len(item_list),
        "distinct_classes": len(classes),
        "soft_items": sum(
            1 for item in item_list if item.get("is_soft", False)
        ),
        "priority_items": sum(
            1 for item in item_list if item.get("is_prioritized", False)
        ),
        "total_volume": round(
            sum(
                float(item["length"] * item["width"] * item["height"])
                for item in item_list
            ),
            6,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE)
    parser.add_argument("--source-case", default="000")
    parser.add_argument("--look-ahead", type=int, required=True)
    parser.add_argument("--variants", type=int, default=8)
    parser.add_argument("--mode", choices=MODES, default="permute")
    parser.add_argument("--seed", type=int, default=20260802)
    parser.add_argument("--policy-timeout", type=float, default=8.0)
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.source.read_text(encoding="utf-8"))
    if args.source_case not in source:
        raise SystemExit(f"source case not found: {args.source_case}")
    template = source[args.source_case]
    item_list = template["item_stream"]["item_list"]
    if args.look_ahead > len(item_list):
        raise SystemExit(
            f"look_ahead {args.look_ahead} exceeds item count {len(item_list)}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "synthetic": True,
        "purpose": "variance estimation; not competition data, not a holdout",
        "mode": args.mode,
        "seed": args.seed,
        "source_case": args.source_case,
        "look_ahead": args.look_ahead,
        "source_profile": stream_profile(item_list),
        "variants": [],
    }
    for variant_index in range(args.variants):
        rng = random.Random(args.seed + variant_index)
        drawn = build_variant(item_list, mode=args.mode, rng=rng)
        task_id = (
            f"syn{args.source_case}-{args.mode[:3]}{variant_index:02d}"
            f"-k{args.look_ahead}"
        )
        task = copy.deepcopy(template)
        task["agent"]["optimize"] = False
        task["agent"]["policy_timeout"] = float(args.policy_timeout)
        task["item_stream"]["item_list"] = drawn
        task["item_stream"]["look_ahead"] = int(args.look_ahead)
        task["item_stream"]["max_space"] = 1
        task["item_stream"]["visible_pool"] = []
        path = args.output_dir / f"{task_id}.json"
        path.write_text(
            json.dumps({task_id: task}, indent=2) + "\n", encoding="utf-8"
        )
        profile = stream_profile(drawn)
        manifest["variants"].append(
            {
                "task_id": task_id,
                "path": path.name,
                "variant_index": variant_index,
                "profile": profile,
                "multiset_preserved": (
                    profile == manifest["source_profile"]
                    if args.mode == "permute"
                    else None
                ),
            }
        )
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(
        {
            "mode": args.mode,
            "variants": len(manifest["variants"]),
            "source_profile": manifest["source_profile"],
            "all_multisets_preserved": all(
                v["multiset_preserved"] for v in manifest["variants"]
            ) if args.mode == "permute" else None,
            "output_dir": args.output_dir.as_posix(),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
