"""physsum.py <jsonl>...: physics rows a line, and per-override totals."""
import sys, json, collections
rows = []
for f in sys.argv[1:]:
    rows += [json.loads(l) for l in open(f)]
tot = collections.OrderedDict()
for r in sorted(rows, key=lambda r: (r["scene"], r["ov"])):
    cs = r.get("cs") or {}
    print(f"{r['ov'][-40:]:40s} {r['scene']:9s} thr {r['thr']:3d} placed {r['placed']:3d} fill {r['fill']:5.1f} soft {r['soft']:2d}/{r['soft_cov']} prio {r['prio']}/{r['prio_cov']} topples {r['topples']} com {r['com']:.3f} {r['end']:9s} plan {r['plan_n']} {cs.get('chosen', '-')} pmax {r['pmax']:.1f}")
    t = tot.setdefault(r["ov"], collections.Counter())
    t["n"] += 1; t["cross"] += r["placed"] >= r["thr"]; t["placed"] += r["placed"]; t["fill"] += r["fill"]
    t["soft"] += r["soft"]; t["soft_cov"] += r["soft_cov"]; t["prio"] += r["prio"]; t["prio_cov"] += r["prio_cov"]
    t["topples"] += r["topples"]; t["com"] += r["com"]
for ov, t in tot.items():
    n = t["n"]
    print(f"{ov[-60:]:60s} n {n} cross {t['cross']} placed {t['placed']/n:.2f} fill {t['fill']/n:.1f} soft {t['soft']}/{t['soft_cov']} prio {t['prio']}/{t['prio_cov']} topples {t['topples']} com {t['com']/n:.3f}")
