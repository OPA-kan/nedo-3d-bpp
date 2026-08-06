"""
The stowage-sections page: the prose that goes around the drawings.

`build_sections_page.py` draws; this holds the reading. Split because the
notes below are a claim about three specific episodes and must not be
carried along by a generic drawing tool.

Usage:
    python scripts/make_stowage_page.py OUT.html DUMP.json [DUMP.json ...]

where each DUMP.json comes from `scripts/dump_packing_geometry.py`. The
paths used to be hardcoded to `scripts/packing-*.json`, which is not where
dumps are written and not where they were when the published page was
built -- the entry point could not be run at all.
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_sections_page import build  # noqa: E402

INTRO = (
    "Every number in the packing pipeline has been read through summary "
    "statistics until now. These are the boards themselves: orthographic "
    "sections cut through three episodes the shipped agent actually played, "
    "drawn from the container's published half-spaces and the item AABBs the "
    "simulator reports after settling."
)

NOTES = """
<div class="note">
<p><b>What the reachability plan shows, and what it does not.</b> Transport
enters along <code>y = -width/2</code> and runs toward <code>+y</code>, so an
item parked in front spends the lane behind it. In all three episodes the
unreachable columns sit deeper than the placeable ones — median
<code>y</code> of blocked against legal is +0.12 vs -0.28, -0.07 vs -0.42,
and +0.23 vs -0.28. That is the symptom, measured three times.</p>
<p>It is <b>not</b> a diagnosis. Filling the deep zones earlier was tested
directly — four scenarios, four arms, three repeats — and it <i>lost</i>
placements well past the noise floor, up to 20 down to 7 on one shelf scene,
with the centre of mass rising and more items toppling. A single unsafe
placement ends the episode outright, so the deep space is not merely
unclaimed; reaching for it early costs the stability that keeps the run
alive. These drawings are the shipped agent's behaviour, not a list of its
mistakes.</p>
</div>
<div class="note">
<p><b>How to read these.</b> The outline is the intersection of the
container's seven half-spaces, so the diagonal at low&nbsp;x is the real
chamfer and the two side walls really are at different |y| — the envelope is
not the box that <code>length × width × height</code> implies. Solid boxes are
cut by the section plane; dashed ones are behind or in front of it. Hatching
marks space that is free but has something above it.</p>
</div>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("dumps", nargs="+", type=pathlib.Path)
    args = parser.parse_args()

    missing = [p for p in args.dumps if not p.exists()]
    if missing:
        print(
            "no such dump: " + ", ".join(str(p) for p in missing),
            file=sys.stderr,
        )
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    build(args.dumps, args.output, "Stowage sections", INTRO, NOTES)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
