"""race_stats.py <dir>...: per run directory, the re-plan's and the race's record (metrics.count_secure):
episodes re-planned, re-plan chosen, re-plans skipped / cut by the budget, the race's count decisions and how
often they overrode the score's pick, and the plan source; with the suite's counts (suite_stats.py)."""
import sys, json, glob, collections, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from suite_stats import stats, fmt  # noqa: E402

for d in sys.argv[1:]:
    rs = [json.load(open(f)) for f in sorted(glob.glob(d + "/[abc]-*.json"))]
    c = collections.Counter()
    switched = []
    for r in rs:
        cs = r["metrics"].get("count_secure") or {}
        c["source_" + str(r.get("plan_source"))] += 1
        if not cs:
            continue
        c["replanned"] += bool(cs.get("replanned"))
        c["chosen"] += cs.get("chosen") not in (None, "base")
        for v in cs.get("variants") or []:
            c["skipped"] += bool(v.get("skipped"))
            c["cut"] += bool(v.get("cut"))
        race = cs.get("race") or {}
        if race.get("decision"):
            c["race_" + race["decision"]] += 1
            final = "dry-run" if r.get("plan_source") == "dry-run" else "planner"
            if final != race.get("score_pick"):
                c["race_switched"] += 1
                switched.append(f"{r['scene']}({race.get('score_pick')}->{final} {race.get('planner')}/{race.get('dry_run')})")
    print(d)
    print("  ", fmt(stats(rs)))
    print("  ", dict(sorted(c.items())), " ".join(switched))
