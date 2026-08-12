"""
Do the local proxies point the same way as the official components?

Every adoption decision on this branch has been made on `placed`, because
`placed` is the only local quantity whose official direction is known -- the
cutoff-gate model held across three submissions at 14x, 6.7x and 7.6x
amplification, once with the sign flipped. The other four official
components (cog, stability, placement, soft) are computed only by the
evaluation service, and the local raw quantities that stand in for them have
never been checked against a single official observation.

That gap is what stops adoption. The attribute guard measured on this branch
loses placements and drives priority violations to zero: a clean trade, and
nothing local can say which side is worth more.

`docs/BLOCKED_WORK.md` section 0 states the way out, and this is it. All four
scored submissions are reconstructible as knob settings on the current
agent, with published six-component breakdowns:

    base           submissiontrueenvelope   total 35.375
    death_band     submissiondeathband      total 29.959
    box_envelope   submission3334 level     total 23.246
    submission22   box envelope + depth 64  total 17.581

Run all four locally, read the raw proxies, and check whether each proxy
orders the configurations the same way its official component does. Four
points still do not identify the unpublished score function. They can refute
a direction and expose nonlinear or configuration-dependent relationships; a
proxy that points the wrong way across a 12-point official spread is not
evidence about anything.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# From docs/OFFICIAL_SCORE_LOG.md. Each is a submission whose configuration
# this run reproduces with a knob.
OFFICIAL = {
    "base": {
        "submission": "trueenvelope",
        "total": 35.375, "fill": 34.246, "cog": 40.683,
        "stability": 53.240, "placement": 16.95, "soft": 21.30,
        "placed": 0.5047,
    },
    "death_band": {
        "submission": "deathband",
        "total": 29.959, "fill": 33.635, "cog": 32.243,
        "stability": 41.288, "placement": 14.70, "soft": 17.45,
        "placed": 0.4915,
    },
    "box_envelope": {
        "submission": "3334",
        "total": 23.246, "fill": 31.413, "cog": 21.505,
        "stability": 29.424, "placement": 10.85, "soft": 12.65,
        "placed": 0.4524,
    },
    "submission22": {
        "submission": "22",
        "total": 17.581, "fill": 29.276, "cog": 14.224,
        "stability": 20.721, "placement": 4.45, "soft": 7.65,
        "placed": 0.4341,
    },
}

# proxy -> (official component, expected sign of the relationship)
#
# `sign` is what the proxy's DIRECTION should be relative to the component:
# +1 means a higher proxy should accompany a higher official score, -1 means
# a higher proxy should accompany a LOWER one. cog and stability score
# higher when the cargo is lower and moves less, so their raw proxies are
# inverted.
PROXIES = {
    "fill": ("fill", +1),
    "placed": ("placed", +1),
    "com_z": ("cog", -1),
    "shake_max_shift": ("stability", -1),
    "shake_items_toppled": ("stability", -1),
    "priority_covered_by_other": ("placement", -1),
    "soft_covered_by_other": ("soft", -1),
}


def metrics(case: dict) -> dict:
    out = {
        "placed": case.get("placed_fraction"),
        "fill": case.get("fill_score"),
        "com_z": case.get("final_com_z"),
    }
    attribute = case.get("attribute_placement") or {}
    for key in ("priority_covered_by_other", "soft_covered_by_other"):
        if attribute.get(key) is not None:
            out[key] = float(attribute[key])
    shake = case.get("shake_response") or {}
    for key in ("shake_max_shift", "shake_items_toppled"):
        if shake.get(key) is not None:
            out[key] = float(shake[key])
    return {k: v for k, v in out.items() if v is not None}


def collect(root: pathlib.Path):
    """(scenario, arm) -> proxy -> repeats.

    Keyed by scenario, not pooled. Pooling four scenarios into one mean puts
    the between-scenario spread into the noise floor -- it made the floor for
    `fill` 15.1 against a local span of 1.7 and reported every proxy as
    untested. Arms are only comparable within the scenario they ran on.
    """
    per_arm = collections.defaultdict(lambda: collections.defaultdict(list))
    for path in sorted(glob.glob(f"{root}/**/rows.jsonl", recursive=True)):
        for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            arm = row.get("arm")
            if arm not in OFFICIAL and arm != "base_null":
                continue
            for case_id, case in (row.get("cases") or {}).items():
                if case.get("status") != "success":
                    continue
                for name, value in metrics(case).items():
                    per_arm[(case_id, arm)][name].append(float(value))
    return per_arm


def concordant(pairs):
    """Kendall-style agreement over the available ordered configurations."""
    agree = 0
    total = 0
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            (lx, ox), (ly, oy) = pairs[i], pairs[j]
            if abs(ox - oy) < 1e-12 or abs(lx - ly) < 1e-12:
                continue
            total += 1
            if (lx - ly) * (ox - oy) > 0:
                agree += 1
    return agree, total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path)
    parser.add_argument(
        "--require-all", action="store_true",
        help="fail unless every official calibration arm is present",
    )
    args = parser.parse_args()

    per_arm = collect(args.root)
    present_arms = {arm for _, arm in per_arm if arm in OFFICIAL}
    missing_arms = sorted(set(OFFICIAL) - present_arms)
    if missing_arms:
        print(f"missing official calibration arms: {missing_arms}", file=sys.stderr)
        if args.require_all:
            return 2
    scenarios = sorted({key[0] for key in per_arm})
    report = {}

    for proxy, (component, sign) in PROXIES.items():
        print(f"\n=== {proxy}  ->  official {component} "
              f"(sign {sign:+d}) ===")
        agree = disagree = untested = 0
        for scenario in scenarios:
            arms = [
                a for a in OFFICIAL
                if (scenario, a) in per_arm and proxy in per_arm[(scenario, a)]
            ]
            if len(arms) < 2:
                continue
            local = {
                a: statistics.fmean(per_arm[(scenario, a)][proxy]) for a in arms
            }
            # noise floor from the two identical configurations, in THIS
            # scenario only
            floor = 0.0
            b = per_arm.get((scenario, "base"), {}).get(proxy)
            n = per_arm.get((scenario, "base_null"), {}).get(proxy)
            if b and n:
                floor = max(
                    abs(statistics.fmean(b) - statistics.fmean(n)),
                    (max(b) - min(b)) if len(b) > 1 else 0.0,
                    (max(n) - min(n)) if len(n) > 1 else 0.0,
                )
            pairs = [(sign * local[a], OFFICIAL[a][component]) for a in arms]
            ok, total = concordant(pairs)
            span = max(local.values()) - min(local.values())
            if span <= floor or total == 0:
                verdict = "untested"
                untested += 1
            elif ok == total:
                verdict = "agrees"
                agree += 1
            elif ok == 0:
                verdict = "DISAGREES"
                disagree += 1
            else:
                verdict = f"partial {ok}/{total}"
            values = "  ".join(f"{a}={local[a]:.3f}" for a in arms)
            print(f"  {scenario:24s} {values}")
            print(f"  {'':24s} span {span:.3f} floor {floor:.3f}  -> {verdict}")
        print(f"  SUMMARY  agrees {agree}  disagrees {disagree}  "
              f"untested {untested}")
        report[proxy] = {
            "component": component, "sign": sign,
            "agrees": agree, "disagrees": disagree, "untested": untested,
        }

    print(
        "Four points do not identify the unpublished score function. They "
        "can refute a direction: a "
        "proxy that DISAGREES across a 12-point official spread is not "
        "evidence about its component, and one whose local spread sits "
        "inside the noise floor has not been tested at all."
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
