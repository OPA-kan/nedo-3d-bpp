"""pref_pairs.py: preference pairs for the ladder's choices, labelled by the outcome.

Can the choice among the ladder's survivors be learned?  At every step of
an analytic episode (``bench.analytic``, deterministic budgets) the
ladder's pick and up to ``--k`` alternatives -- the first candidate of
every other rung with one, and the next ones of the chosen rung -- are
each placed on a clone of the board and the agent, and the episode is
continued by the agent itself to the decline.  The label of an
alternative is the final count it leads to against the ladder's own
continuation (the crossing kept or lost first, then the count, then the
fill); the proxies are the pieces the pose makes (``piece_makers``) and
the usable surface it closes (``rule_alpha.surface``); the features are
the candidate's (footprint, row waste, the neighbour step, the level
match, the surface, the bottom, the archetype) and the state's (the
phase variable, the step, the survivors).  One JSON line an alternative:

  {scene, step, item, ladder: {archetype, ...}, alt: {archetype, ...},
   d_count, d_fill, crossing_ladder, crossing_alt, d_pieces, d_usable,
   features: {...}}

``--shard i/n`` takes every n-th scene; ``--steps`` caps the branched
steps an episode (the first ones, where the structure is decided);
``--max-episode-steps`` caps the continuations.
"""
import argparse
import copy
import json
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from bench.arms import make_arm  # noqa: E402
from bench.scenes import build_suite  # noqa: E402
from rule_alpha import layer1  # noqa: E402
from rule_alpha.surface import usable_surface_ratio  # noqa: E402


def _threshold(total: int) -> int:
    return total // 2 + 1  # strictly more than a half (count_mode_strict)


class Episode:
    """The analytic episode as mutable state that can be cloned."""

    def __init__(self, scene, arm):
        self.scene = scene
        self.config = arm.config
        containers = scene.rule_alpha_containers()
        self.agent = arm(scene)
        self.agent.get_init_states({"optimize": scene.optimize, "lookahead_k": scene.look_ahead,
                                    "container_list": containers})
        items = [dict(i) for i in scene.items]
        if scene.optimize:
            order = self.agent.optimize([dict(i) for i in items])
            by_index = {int(i["index"]): i for i in items}
            items = [by_index[int(i)] for i in order]
        self.board = layer1.Board(containers, self.config)
        self.queue = list(items)
        self.pool: list[dict] = []
        self._refill()
        self.placed = 0

    def _refill(self):
        while len(self.pool) < self.scene.look_ahead and self.queue:
            self.pool.append(self.queue.pop(0))

    def observation(self):
        return {"optimize": self.scene.optimize, "lookahead_k": self.scene.look_ahead,
                "container_list": self.board.containers, "pool_list": [dict(i) for i in self.pool]}

    def decide(self):
        """The agent's action for the current pool, or None (the decline)."""
        if not self.pool:
            return None
        return self.agent.policy(self.observation())

    def apply(self, placement, pool_index: int):
        self.pool.pop(pool_index)
        placement.step = self.placed + 1
        self.board.apply(placement)
        self.placed += 1
        self._refill()

    def clone(self):
        return copy.deepcopy(self)

    def run_out(self, max_steps: int = 400):
        for _ in range(max_steps):
            action = self.decide()
            if action is None:
                break
            self.apply(self.agent.last_decision.placement, int(action["item_idx"]))
        return self.placed

    def fill(self) -> float:
        usable = sum(float(m.usable_volume) for m in self.board.models)
        vol = sum(float(p.volume) for ps in self.board.placements for p in ps)
        return 100.0 * vol / usable if usable else 0.0


def alternatives(decision, config, k: int):
    """Up to k alternatives to the ladder's pick among its survivors: the
    first candidate of every other rung that has one, in the ladder's
    order, then the next candidates of the chosen rung."""
    chosen = decision.chosen
    survivors = decision.survivors or []
    out = []
    seen = {id(chosen)}
    chosen_rung = str(decision.placement.archetype).split("/")[-1]
    for name in decision.ladder or []:
        if name == chosen_rung or name not in layer1.ARCHETYPE_KEYS:
            continue
        pool = [c for c in survivors if name in c.archetypes]
        if not pool:
            continue
        pick = layer1.rung_pick(name, pool, config)
        if id(pick) in seen:
            continue
        seen.add(id(pick))
        out.append((name, pick))
        if len(out) >= k:
            return out
    if chosen_rung in layer1.ARCHETYPE_KEYS:
        pool = [c for c in survivors if chosen_rung in c.archetypes]
        if pool:
            for c in layer1.rung_order(chosen_rung, pool, config)[1:]:
                if id(c) in seen:
                    continue
                seen.add(id(c))
                out.append((chosen_rung, c))
                if len(out) >= k:
                    break
    return out


def pieces_volume(board, container_idx: int, extra_box=None, extra_soft: bool = False) -> float:
    """The pieces volume of one container (``piece_makers.Volume``) with an
    optional extra box, as a share of the container."""
    from piece_makers import Volume

    container = board.container(container_idx)
    v = Volume(container)
    from rule_alpha._reuse import packed_aabbs_local
    for box, soft, _p in packed_aabbs_local(container):
        v.add({"pos_local": [float(x) for x in box.center], "size": [float(x) for x in box.size]}, soft)
    if extra_box is not None:
        v.add({"pos_local": [float(x) for x in extra_box.center], "size": [float(x) for x in extra_box.size]}, extra_soft)
    head, _u, _l, pieces = v.masks()
    return v.pieces_volume(head, pieces)


def candidate_record(cand, name: str) -> dict:
    f = cand.features or {}
    return {
        "archetype": name, "surface": cand.surface, "role": cand.role,
        "bottom": round(float(cand.box.minimum[2]), 3), "top": round(float(cand.box.maximum[2]), 3),
        "x": round(float(cand.box.center[0]), 3), "y": round(float(cand.box.center[1]), 3),
        "dims": [round(float(v), 3) for v in cand.box.size],
        "footprint": round(float(f.get("footprint", 0.0)), 4),
        "row_waste": round(float(f.get("row_waste", 0.0)), 4),
        "neighbour_step": round(float(f.get("neighbour_height_step", 0.0)), 4),
        "level_match": float(f.get("level_match", 0.0)),
        "plateau_gain": round(float(f.get("plateau_gain", 0.0)), 4),
        "open_free_area": round(float(f.get("open_free_area", 0.0)), 4),
        "largest_residual_rect": round(float(f.get("largest_residual_rect", 0.0)), 4),
        "y_back": round(float(f.get("y_back", 0.0)), 4),
        "stability_margin": round(float(f.get("stability_margin", 0.0)), 4),
    }


def branch(scene, arm, k: int, steps_cap: int, max_steps: int, log=print):
    rows = []
    ep = Episode(scene, arm)
    total = len(scene.items)
    threshold = _threshold(total)
    t_scene = time.perf_counter()
    for step in range(max_steps):
        action = ep.decide()
        if action is None:
            break
        decision = ep.agent.last_decision
        pool_index = int(action["item_idx"])
        item = ep.pool[pool_index]
        chosen = decision.chosen
        if step < steps_cap and chosen is not None and decision.survivors and len(decision.survivors) > 1:
            alts = alternatives(decision, ep.config, k)
            if alts:
                ci = int(decision.placement.container_idx)
                phase = usable_surface_ratio(ep.board, ci)
                soft = bool(chosen.profile.is_soft)
                pieces_before = pieces_volume(ep.board, ci)
                pieces_ladder = pieces_volume(ep.board, ci, chosen.box, soft)
                # the ladder's own continuation from a clone (the baseline;
                # equal to the real one under deterministic budgets)
                base = ep.clone()
                base.apply(copy.deepcopy(decision.placement), pool_index)
                t0 = time.perf_counter()
                count_ladder = base.run_out(max_steps)
                fill_ladder = base.fill()
                t_base = time.perf_counter() - t0
                for name, alt in alts:
                    if ci != int(alt.container_idx):
                        continue
                    pieces_alt = pieces_volume(ep.board, ci, alt.box, soft)
                    br = ep.clone()
                    try:
                        placement = layer1.build_placement(alt, name, br.board, ci, chosen.profile, br.config)
                    except Exception as exc:  # a candidate the builder refuses
                        log(f"  build failed at step {step}: {exc!r}")
                        continue
                    br.apply(placement, pool_index)
                    count_alt = br.run_out(max_steps)
                    rows.append({
                        "scene": scene.name, "step": step, "item": int(item["index"]), "total": total,
                        "survivors": len(decision.survivors), "phase": round(float(phase), 3),
                        "ladder": candidate_record(chosen, str(decision.placement.archetype)),
                        "alt": candidate_record(alt, name),
                        "count_ladder": count_ladder, "count_alt": count_alt, "d_count": count_alt - count_ladder,
                        "d_fill": round(br.fill() - fill_ladder, 3),
                        "crossing_ladder": count_ladder >= threshold, "crossing_alt": count_alt >= threshold,
                        "d_pieces": round(pieces_alt - pieces_ladder, 4),
                        "pieces_made_ladder": round(pieces_ladder - pieces_before, 4),
                        "pieces_made_alt": round(pieces_alt - pieces_before, 4),
                    })
                log(f"  {scene.name} step {step} item {item['index']} {decision.placement.archetype}: ladder {count_ladder}, "
                    f"alts {[r['count_alt'] for r in rows if r['scene'] == scene.name and r['step'] == step]} "
                    f"({t_base:.1f}s a continuation)")
        ep.apply(decision.placement, pool_index)
    log(f"{scene.name}: placed {ep.placed} in {time.perf_counter() - t_scene:.0f}s, {len(rows)} pairs")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", required=True)
    ap.add_argument("--suite", default="core")
    ap.add_argument("--shard", default="0/1")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--steps", type=int, default=25, help="branched steps an episode (the first ones)")
    ap.add_argument("--max-episode-steps", type=int, default=400)
    ap.add_argument("--scenes", default="", help="comma list of scene names (overrides the suite shard)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    arm = make_arm(args.arm)
    i, n = (int(v) for v in args.shard.split("/"))
    scenes = list(build_suite(args.suite))
    if args.scenes:
        names = set(args.scenes.split(","))
        scenes = [s for s in scenes if s.name in names]
    else:
        scenes = [s for j, s in enumerate(scenes) if j % n == i]
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in open(out):
            try:
                done.add(json.loads(line)["scene"])
            except Exception:
                pass
    with open(out, "a") as fh:
        for scene in scenes:
            if scene.name in done:
                continue
            rows = branch(scene, arm, args.k, args.steps, args.max_episode_steps)
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            fh.flush()


if __name__ == "__main__":
    main()
