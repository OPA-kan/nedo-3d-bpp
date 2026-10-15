"""diverge.py <scene> <extra-a> <extra-b>: first step where two analytic arms differ."""
import sys
sys.path.insert(0, '/home/user/nedo-3d-bpp')
from bench.arms import make_arm
from bench.scenes import make_scene
from bench.analytic import run_analytic_episode
S = '/home/user/nedo-3d-bpp/reports/wedge/bridge-generator/'
spec = open(S + 'arm_light_c.txt').read().strip()
task, layout, s = sys.argv[1].split('-'); seed = int(s[1:])
recs = []
for extra in sys.argv[2:4]:
    recs.append(run_analytic_episode(make_scene(seed, layout, task.upper()), make_arm(spec + ',' + extra)))
a, b = ([st for st in r['steps']] for r in recs)
for i, (x, y) in enumerate(zip(a, b)):
    kx = (x.get('event'), x.get('item_index'), x.get('pos_local'), x.get('orientation'))
    ky = (y.get('event'), y.get('item_index'), y.get('pos_local'), y.get('orientation'))
    if kx != ky:
        print('first difference at step', i)
        for st in (x, y):
            print('  ', {k: st.get(k) for k in ('event', 'item_index', 'archetype', 'role', 'pos_local', 'size', 'considered', 'survivors', 'policy_seconds')})
        break
else:
    print('identical over', min(len(a), len(b)), 'steps')
print('placed', [r['metrics']['placed_count'] for r in recs])
print('b archetypes after the split:', [st.get('archetype') for st in b[i:i + 12]])
