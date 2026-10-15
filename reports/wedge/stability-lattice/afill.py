"""afill.py: the Task A pipeline's fill and placed fraction on dense single-container manifests (physics)."""
import sys, json, time
sys.path.insert(0,'/home/user/nedo-3d-bpp')
from bench.arms import make_arm
from bench.episode import run_episode
from bench.scenes import make_scene
arm=make_arm(open(sys.argv[1]).read().strip())
out=[]
for K in [int(x) for x in sys.argv[2].split(',')]:
    for seed in [int(x) for x in sys.argv[3].split(',')]:
        sc=make_scene(seed,'c1','A',items_per_container=K)
        t0=time.time(); rec=run_episode(sc, arm, policy_budget=8.0, with_shake=True); m=rec['metrics']
        row=dict(K=K,seed=seed,items=m['total_items'],placed=m['placed_count'],frac=round(m['placed_count']/m['total_items'],3),fill=round(m['fill_volume'],1),end=m['end_reason'],secs=round(time.time()-t0))
        out.append(row); print(json.dumps(row), flush=True)
json.dump(out, open(sys.argv[4],'w'))
