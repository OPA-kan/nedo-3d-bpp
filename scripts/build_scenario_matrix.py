"""
Build the container-configuration matrix the competition says will appear.

docs/COMPETITION_RULES.md section 2 states that every task is posed with
combinations of:

  * one or two containers
  * shelf present or absent
  * empty or pre-loaded initial state
  * a priority-dedicated container present or absent

The bundled `sample_config.json` covers exactly ONE of those axes. Both of
its cases are single-container, empty, with no dedicated container; only
the shelf differs. The whole development suite is derived from those two
cases by changing look-ahead, so it inherits the same blind spot: two
containers, pre-loaded state and a dedicated priority container have never
been executed against the physics at all.

That is a different kind of gap from an unmeasured effect size. The rules
also require one agent to handle every task by self-detecting the setup,
so these branches WILL be taken in evaluation. Code exists for all of them
(`is_prioritized` container routing, AABB reconstruction from
`packed_items`, residual-volume comparison across containers) and is
pinned by unit tests, but no episode has ever run them.

This builds the matrix from the bundled cases so it stays honest about
geometry: containers and items are taken from the real sample rather than
invented, and only the combination varies. Pre-loaded items are placed on
the floor with a conservative margin and settled by the simulator before
the episode begins, exactly as a genuine pre-loaded scene would be.

    python3 scripts/build_scenario_matrix.py --output-dir reports/scenario-matrix

The output is deliberately NOT a benchmark. It is a coverage probe: the
question it answers is "does this configuration run at all", not "how well
does it score". Scores from it are not comparable to the development suite,
because the scenes are synthetic combinations rather than competition ones.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "simulator" / "configs" / "sample_config.json"

# Combination axes from COMPETITION_RULES section 2. `shelf` is the only one
# the bundled cases already cover, and it is kept so the matrix contains a
# known-good row to read the others against.
SCENARIOS = (
    ("single-empty-noshelf", dict(containers=1, shelf=False, preloaded=0, dedicated=False)),
    ("single-empty-shelf", dict(containers=1, shelf=True, preloaded=0, dedicated=False)),
    ("single-preloaded", dict(containers=1, shelf=False, preloaded=3, dedicated=False)),
    ("dual-empty", dict(containers=2, shelf=False, preloaded=0, dedicated=False)),
    ("dual-shelf-mixed", dict(containers=2, shelf="mixed", preloaded=0, dedicated=False)),
    ("dual-dedicated-priority", dict(containers=2, shelf=False, preloaded=0, dedicated=True)),
    ("dual-preloaded-dedicated", dict(containers=2, shelf=False, preloaded=2, dedicated=True)),
    # COMPETITION_RULES section 2 also states the scale: up to two containers
    # holding roughly eighty items. Every scenario above reuses the 41-item
    # mix from case 000 across however many containers it builds, so two
    # containers arrive already half empty and contention -- which is what
    # allocation has to solve -- never appears. `stream="both"` concatenates
    # both bundled streams to reach that scale. Measured consequence of the
    # gap: two submitted builds differing 15.3% officially return identical
    # fill, placed and com_z on the bundled cases
    # (submitted-pair-is-nearly-identical-on-local-cases).
    ("dual-full-stream", dict(containers=2, shelf="mixed", preloaded=0,
                              dedicated=True, stream="both")),
)

STREAM_VARIANTS = (
    "original", "source-001", "reverse-000", "interleave", "rotate-000-7",
    "rotate-001-5",
    "permute-000-17", "permute-000-29", "permute-001-23", "permute-001-31",
    "permute-000-41", "permute-000-53", "permute-001-43", "permute-001-59",
    "permute-000-61", "permute-001-67",
    "permute-000-71", "permute-000-79", "permute-000-89", "permute-000-97",
    "permute-001-73", "permute-001-83", "permute-001-101", "permute-001-107",
)


def _hashed_permutation(items: list[dict], salt: int) -> list[dict]:
    return sorted(
        items,
        key=lambda item: hashlib.sha256(
            f"{salt}:{int(item['index'])}".encode()
        ).digest(),
    )


def _stream_items(source: dict, spec: dict, variant: str) -> list[dict]:
    """Build a declared development stream while preserving item identity."""
    if variant not in STREAM_VARIANTS:
        raise ValueError(
            f"unknown stream variant {variant!r}; expected one of "
            + ", ".join(STREAM_VARIANTS)
        )
    base = copy.deepcopy(source["000"]["item_stream"]["item_list"])
    shelf = copy.deepcopy(source["001"]["item_stream"]["item_list"])
    if variant == "source-001":
        items = shelf
    elif variant == "reverse-000":
        items = list(reversed(base))
    elif variant == "rotate-000-7":
        items = base[7:] + base[:7]
    elif variant == "rotate-001-5":
        items = shelf[5:] + shelf[:5]
    elif variant.startswith("permute-000-"):
        items = _hashed_permutation(base, int(variant.rsplit("-", 1)[1]))
    elif variant.startswith("permute-001-"):
        items = _hashed_permutation(shelf, int(variant.rsplit("-", 1)[1]))
    elif variant == "interleave":
        items = [
            item
            for position in range(max(len(base), len(shelf)))
            for stream in (base, shelf)
            for item in stream[position:position + 1]
        ]
    elif spec.get("stream") == "both":
        items = base + shelf
    else:
        return base
    # A combined stream contains overlapping source indices. The action
    # protocol requires identity to be globally unique, while reordering a
    # single source must keep its original identities.
    if variant == "interleave" or (
        variant == "original" and spec.get("stream") == "both"
    ):
        for position, item in enumerate(items):
            item["index"] = position
    return items


def _preloaded_items(items: list[dict], count: int, container: dict) -> list[dict]:
    """
    Seat `count` items on the container floor as a pre-existing load.

    Positions are laid out along the container's length with a margin well
    inside the inclusion clearance, then the simulator settles them before
    the episode starts (containers.py steps physics until everything
    sleeps). Only non-soft, non-priority items are used: a pre-loaded soft
    item would change what the agent may stack on, which is a separate
    question from whether pre-loading runs at all.
    """
    usable = [
        item for item in items
        if not item.get("is_soft") and not item.get("is_prioritized")
    ]
    chosen = usable[:count]
    placed = []
    cursor = -float(container["length"]) / 2.0 + 0.25
    for item in chosen:
        seated = copy.deepcopy(item)
        seated["pos"] = [
            round(cursor + float(item["length"]) / 2.0, 4),
            0.0,
            round(float(item["height"]) / 2.0 + 0.02, 4),
        ]
        seated["orn"] = [0.0, 0.0, 0.0, 1.0]
        placed.append(seated)
        cursor += float(item["length"]) + 0.05
    return placed


def build_scenario(source: dict, name: str, spec: dict,
                   *, look_ahead: int, policy_timeout: float,
                   stream_variant: str = "original") -> dict:
    base = copy.deepcopy(source["000"])
    shelf_source = copy.deepcopy(source["001"])
    items = _stream_items(source, spec, stream_variant)

    template = copy.deepcopy(base["containers"]["container_list"][0])
    shelf_template = copy.deepcopy(
        shelf_source["containers"]["container_list"][0]
    )

    containers = []
    for index in range(spec["containers"]):
        if spec["shelf"] == "mixed":
            want_shelf = index == 1
        else:
            want_shelf = bool(spec["shelf"])
        container = copy.deepcopy(shelf_template if want_shelf else template)
        container["index"] = index
        container["require_shelf"] = want_shelf
        container["packed_items"] = []
        # A dedicated container is the LAST one, so the agent has to route
        # priority items away from the container it would reach first.
        container["is_prioritized"] = bool(
            spec["dedicated"] and index == spec["containers"] - 1
        )
        containers.append(container)

    if spec["preloaded"]:
        containers[0]["packed_items"] = _preloaded_items(
            items, spec["preloaded"], containers[0]
        )
        seated = {int(i["index"]) for i in containers[0]["packed_items"]}
        items = [i for i in items if int(i["index"]) not in seated]

    case = copy.deepcopy(base)
    case["containers"]["container_list"] = containers
    case["item_stream"]["item_list"] = items
    case["item_stream"]["look_ahead"] = look_ahead
    # Task B replenishes the visible pool as soon as one slot opens.  Using
    # `look_ahead` here waits until the whole pool is empty and changes the
    # stream dynamics together with the container condition, confounding the
    # matrix this builder exists to isolate.
    case["item_stream"]["max_space"] = 1
    case["item_stream"]["visible_pool"] = []
    case["item_stream"]["development_stream_variant"] = stream_variant
    case["agent"]["optimize"] = False
    case["agent"]["policy_timeout"] = float(policy_timeout)
    # camera.num_containers sizes the simulator's shared depth-map array
    # (env.py:80-88). The bundled cases are single-container, so copying
    # their camera block verbatim makes reset() raise IndexError on the
    # second container -- which is what happened, and is exactly the class
    # of defect an untried configuration hides.
    case["camera"]["num_containers"] = len(containers)
    return {f"m-{name}": case}


def observation_containers(case: dict) -> list[dict]:
    """
    The container payload shape the SIMULATOR sends, not the raw config.

    `center` is absent from the config: containers.py build() lays them out
    with `offset_x = i * spacing` and get_init_states ships the resulting
    centre. Handing the raw config to the agent instead is a shape the
    harness never produces, and it hides exactly the defect that matters
    here -- with one container a missing offset is invisible, with two it
    is the whole question of whether the second is addressable.

    This mirrors containers.py deliberately and is therefore a duplicate of
    simulator logic. It is kept narrow (offset only) and the physical
    runner remains the real check; if the simulator changes its layout this
    helper must follow.
    """
    spacing = float(case["containers"]["spacing"])
    payload = []
    for index, container in enumerate(case["containers"]["container_list"]):
        seat = copy.deepcopy(container)
        seat["center"] = [index * spacing, 0.0, 0.0]
        seat["shelf"] = container["require_shelf"]
        payload.append(seat)
    return payload


def build_all(source: dict, *, look_ahead: int,
              policy_timeout: float,
              stream_variant: str = "original") -> dict[str, dict]:
    return {
        name: build_scenario(
            source, name, spec,
            look_ahead=look_ahead, policy_timeout=policy_timeout,
            stream_variant=stream_variant,
        )
        for name, spec in SCENARIOS
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE)
    parser.add_argument("--look-ahead", type=int, default=10)
    parser.add_argument("--policy-timeout", type=float, default=8.0)
    parser.add_argument(
        "--stream-variant", choices=STREAM_VARIANTS, default="original",
        help=(
            "Declared synthetic development stream. original preserves the "
            "existing matrix exactly; other variants test model-visible "
            "trajectory support and are not score-comparable."
        ),
    )
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()

    source = json.loads(args.source.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, config in build_all(
        source, look_ahead=args.look_ahead,
        policy_timeout=args.policy_timeout,
        stream_variant=args.stream_variant,
    ).items():
        path = args.output_dir / f"{name}.json"
        path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        case = next(iter(config.values()))
        containers = case["containers"]["container_list"]
        manifest.append({
            "scenario": name,
            "path": path.name,
            "containers": len(containers),
            "shelves": sum(1 for c in containers if c["require_shelf"]),
            "dedicated": sum(1 for c in containers if c["is_prioritized"]),
            "preloaded": sum(len(c["packed_items"]) for c in containers),
            "items": len(case["item_stream"]["item_list"]),
        })
    (args.output_dir / "manifest.json").write_text(
        json.dumps({
            "schema_version": 1,
            "purpose": (
                "Coverage probe for the container combinations "
                "COMPETITION_RULES section 2 says will be posed. Answers "
                "'does this configuration run', not 'how well does it "
                "score' -- the scenes are synthetic combinations of the "
                "bundled geometry, so scores are not comparable to the "
                "development suite."
            ),
            "source": str(args.source.relative_to(ROOT)),
            "look_ahead": args.look_ahead,
            "stream_variant": args.stream_variant,
            "scenarios": manifest,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    for row in manifest:
        print(
            f"{row['scenario']:26s} containers={row['containers']} "
            f"shelves={row['shelves']} dedicated={row['dedicated']} "
            f"preloaded={row['preloaded']} items={row['items']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
