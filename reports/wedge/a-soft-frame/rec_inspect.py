"""inspect.py <record.json> [steps]: an episode record's metrics, count_secure, optimize, the steps and the log tail."""
import json, sys
r = json.load(open(sys.argv[1])); m = r['metrics']
print('placed', m['placed_count'], 'of', m['total_items'], 'end', m['end_reason'], 'src', r.get('plan_source'),
      'soft', m['soft_count'], 'prio', m['priority_count'], 'topples', m.get('shake_topples'),
      'com', m.get('com_z_above_floor_ratio'), 'fill', m.get('fill_volume'))
print('count_secure', json.dumps(m.get('count_secure')))
print('optimize', json.dumps(m.get('optimize')))
if len(sys.argv) > 2:
    steps = r['steps']
    print(len(steps), 'steps; keys', list(steps[0].keys()))
    for s in steps:
        print({k: (round(v, 2) if isinstance(v, float) else ([round(x, 2) for x in v] if isinstance(v, list) and v and isinstance(v[0], float) else v))
               for k, v in s.items() if k not in ('features',)})
    print('\n'.join(r.get('log_tail', [])[-40:]))
