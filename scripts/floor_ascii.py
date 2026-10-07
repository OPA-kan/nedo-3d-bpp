"""floor_ascii.py <record.json>: ASCII floor map (x down the page = length, y across = width), one char per 5 cm; letters = step order of floor boxes, '.' free, '#' wall."""
import json, sys, pathlib
import numpy as np
sys.path.insert(0, str(pathlib.Path('.').resolve()))
from bench.scenes import make_hard_scene, make_scene
r = json.load(open(sys.argv[1])); sp = r['scene_spec']
if 'hard' in sp['name']: sc = make_hard_scene(sp['seed'], sp['task'])
else: sc = make_scene(sp['seed'], sp['layout'], sp['task'], **{k: v for k, v in sp.items() if k in ('look_ahead','optimize','item_count')})
steps = [s for s in r['steps'] if s.get('event') == 'step' and 'pos_local' in s]
CELL = 0.05
chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
for ci, c in enumerate(sc.containers):
    L, W, t = c['length'], c['width'], c['thickness']
    nx, ny = int(round(L / CELL)), int(round(W / CELL))
    g = np.full((nx, ny), '.', dtype='<U1')
    tc = max(1, int(round(t / CELL))); cut = int(round((c['cut_x'] + t) / CELL))
    g[:cut, :] = '#'; g[-tc:, :] = '#'; g[:, :tc] = '#'; g[:, -tc:] = '#'
    n = 0
    for k, s in enumerate(steps):
        if s['container_idx'] != ci: continue
        x, y, z = s['pos_local']; sx, sy, sz = s['size']
        if z - sz / 2 > 0.06: continue
        i0 = int(round((x - sx/2 + L/2) / CELL)); i1 = int(round((x + sx/2 + L/2) / CELL))
        j0 = int(round((y - sy/2 + W/2) / CELL)); j1 = int(round((y + sy/2 + W/2) / CELL))
        g[max(i0,0):i1, max(j0,0):j1] = chars[n % len(chars)]
        print(chars[n % len(chars)], k, s.get('archetype'), f"x{x:+.2f} y{y:+.2f} {sx:.2f}x{sy:.2f}x{sz:.2f}", 'soft' if sc.items[s['item_index']].get('is_soft') else '')
        n += 1
    print(f"container {ci} L{L} W{W} cut{c['cut_x']}  (rows: x from -L/2 at top; columns: y from -W/2 at left)")
    for i in range(nx): print(''.join(g[i]))
