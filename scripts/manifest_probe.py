"""manifest_probe.py <items_per_container> <seeds...>: Task A episodes on c1 with a
manifest of another size, the v32 rule, with and without the scratch's manifest
(the fix that went in with v34), physics replay -- plan count, placed, soft,
priority, optimize seconds."""
import io, json, sys, time, contextlib
sys.path.insert(0, ".")
S = "reports/bench"  # v32arm.txt: the v32 arm string; output in reports/bench/manifest-probe-a.txt
from bench.scenes import make_scene
from bench.arms import make_arm
from bench.episode import run_episode

BASE = open(S + "/v32arm.txt").read().strip() + ",plan_variants=first;after-hard"
n = int(sys.argv[1]); seeds = [int(s) for s in sys.argv[2:]] or [1, 2, 3]
for seed in seeds:
    for name, extra in (("v32-dryrun(41-based)", ",scratch_manifest=false"), ("fix(manifest-based)", "")):
        scene = make_scene(seed, "c1", "A", items_per_container=n)
        arm = make_arm(BASE + extra)
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink):
            rec = run_episode(scene, arm, policy_budget=4.5)
        m = rec["metrics"]
        print(f"n={n} seed={seed} {name:22s} source={rec.get('plan_source')!r:10s} placed {m['placed_count']}/{m['total_items']} "
              f"soft {m['soft_count']} prio {m['priority_count']} fill {m['fill_volume']:.1f} com {m['com_z_above_floor_ratio']:.3f} "
              f"prio_cov {m.get('priority_covered', 0)} optimize {m.get('optimize_seconds', 0):.0f}s", flush=True)
