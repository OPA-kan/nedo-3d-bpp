"""scene_delta.py <base_dir> <new_dir> [min abs delta]: the scenes whose platform-like score changed, with the
components that moved."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from bench.platform_score import COMPONENTS, load_run  # noqa: E402

base, new = load_run(sys.argv[1]), load_run(sys.argv[2])
floor = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
for s in sorted(set(base) & set(new)):
    b, n = base[s], new[s]
    d = n["score"] - b["score"]
    if abs(d) < floor:
        continue
    comps = ", ".join(f"{k} {n[k] - b[k]:+.1f}" for k in COMPONENTS if abs(n[k] - b[k]) > 0.05)
    print(f"{s}: {d:+.2f} (placed {b['placed']} -> {n['placed']}, soft ok {b['soft_ok']} -> {n['soft_ok']}, "
          f"prio ok {b['prio_ok']} -> {n['prio_ok']} of {n['prio_total']}, topples {b['topples']} -> {n['topples']}; {comps})")
