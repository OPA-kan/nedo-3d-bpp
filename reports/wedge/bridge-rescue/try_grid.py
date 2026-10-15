import dataclasses
import sys
from unittest import mock

sys.path.insert(0, "/home/user/nedo-3d-bpp/.claude/worktrees/agent-aeca172b996317a87")
from bench.scenes import make_scene  # noqa: E402
from rule_alpha import classify as cls, layer1  # noqa: E402
from rule_alpha.agent import RuleAlphaAgent  # noqa: E402
from rule_alpha.config import DEFAULT_CONFIG  # noqa: E402


def column(index, x, y, w=0.1, d=0.5, h=0.5, z0=0.04):
    return {"index": index, "length": w, "width": d, "height": h, "mass": 10.0, "is_soft": False,
            "is_prioritized": False, "pos": (x, y, z0 + h / 2.0), "orn": (0.0, 0.0, 0.0, 1.0)}


def run(ysign, share):
    cfg = dataclasses.replace(DEFAULT_CONFIG, grid_rescue=0.05, grid_rescue_min_support=share,
                              no_cover_other_attribute=True, conservative_transport=False)
    cs = make_scene(1, "c1", "C").rule_alpha_containers()
    y = 0.4 * ysign
    cs[0]["packed_items"] += [column(1, 0.35, y), column(2, 0.75, y)]
    a = RuleAlphaAgent(config=cfg)
    a.board = layer1.Board(cs, cfg)
    item = {"index": 9, "length": 0.6, "width": 0.4, "height": 0.2, "mass": 5.0, "is_soft": False, "is_prioritized": False}
    pool = [item]
    profiles = [(0, cls.classify_item(9, item, cfg))]
    ordered = layer1.pool_order(profiles, cfg)
    a._shadow_synced = True
    a._shadow_observation = {"container_list": cs}
    seen = []
    real = layer1.validate

    def rec(box, model, container, c):
        ok, why = real(box, model, container, c)
        bottom = float(box.center[2]) - float(box.size[2]) / 2.0
        seen.append((round(bottom, 3), ok, why))
        return ok, why
    with mock.patch.object(layer1, "validate", side_effect=rec), \
            mock.patch.object(a, "_shadow_sim", return_value=object()), \
            mock.patch.object(a, "_shadow_verdict", return_value={}), \
            mock.patch.object(a, "_shadow_hard", return_value=True):
        a._grid_rescue(ordered, pool, float("inf"), count=False, own_window=False)
    high = [s for s in seen if s[0] > 0.3]
    import collections
    print(ysign, share, len(seen), len(high), sum(1 for s in high if s[1]), collections.Counter(w for _b, ok, w in high if not ok).most_common(4))


for ys in (1, -1):
    for sh in (-1.0, 0.25):
        run(ys, sh)
