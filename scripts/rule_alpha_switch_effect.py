"""Which switches actually change the board, and which are decorative?

    python3 -m scripts.rule_alpha_switch_effect            # task 000
    python3 -m scripts.rule_alpha_switch_effect --task 001

Runs the official task once per switch and hashes the placement sequence.  A
score can stay the same while the board changes, and -- far more often here --
a switch can change the internal state visibly and leave the board byte for
byte identical.  Five consecutive changes were reported as "no effect on the
score" when the truth was stronger and more useful: no effect at all.  Ask this
before writing up a result.
""" 
import dataclasses, hashlib, json, pathlib, sys
sys.path.insert(0, "/home/user/nedo-3d-bpp")
from rule_alpha.config import DEFAULT_CONFIG as C
from rule_alpha.physics import run_physics_episode
from scripts.rule_alpha_official_task import scenario_from_task

import argparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--task", default="000")
parser.add_argument("--config", type=pathlib.Path,
                    default=pathlib.Path("simulator/configs/sample_config.json"))
args = parser.parse_args()

payload = json.loads(args.config.read_text())
sc = scenario_from_task(args.task, payload[args.task])
print(f"task {args.task}: {len(sc.items)} items, look_ahead={sc.look_ahead}")

arms = {
    "current": {},
    "no prefilter": dict(prefilter_dead_candidates=False),
    "no shelf relief": dict(count_all_shelves_as_relief=False),
    "no headroom fix": dict(front_release_back_share_of_headroom=0.0),
    "perch on": dict(support_coverage_at_any_depth=True),
    "no bridge guard": dict(bridge_keeps_floor=False),
    "no raised compaction": dict(compact_raised=False),
    "no row tiling": dict(row_tiling=False),
}
base = None
for arm, over in arms.items():
    cfg = dataclasses.replace(C, **over)
    r = run_physics_episode(sc, cfg, verbose=False)
    seq = [
        (p.profile.index, round(float(p.box.center[0]), 3),
         round(float(p.box.center[1]), 3), round(float(p.box.center[2]), 3),
         p.orientation.index)
        for p in sorted(r["placements"][0], key=lambda q: q.step or 0)
    ]
    h = hashlib.sha1(repr(seq).encode()).hexdigest()[:10]
    ok = sum(1 for s in r["steps"]
             if s.get("event") == "step" and s.get("settle_ok"))
    if base is None:
        base, base_seq = h, seq
        note = "(baseline)"
    else:
        if h == base:
            note = "IDENTICAL"
        else:
            first = next((i for i, (a, b) in enumerate(zip(base_seq, seq))
                          if a != b), min(len(base_seq), len(seq)))
            note = f"differs from step {first + 1}"
    print(f"  {arm:<22} placed {ok:>2}  fill "
          f"{r['evaluation']['fill_score']:>7.3f}  {h}  {note}", flush=True)


