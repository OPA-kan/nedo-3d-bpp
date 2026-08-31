# What a working RL 3D-BPP loop looks like, and what ours is instead

Date: 2026-08-31. Read against `alexfrom0815/Online-3D-BPP-PCT`
(Zhao, Yu, Xu, ICLR 2022, "Learning Efficient Online 3D Bin Packing on
Packing Configuration Trees") and its predecessor
`alexfrom0815/Online-3D-BPP-DRL` (AAAI 2021), both cloned read-only at
`/home/user/alexfrom0815/`.

This is a reading note, not a measurement of our repo. Every claim about
their code cites the file it came from.

## The architecture is the one we converged on

`pct_envs/PctDiscrete0/bin3D.py::get_possible_position` enumerates
candidate placements for the next item (EMS / event point / extreme
point / corner point / full coord), screens each with
`space.drop_box_virtual`, and pads the survivors into a fixed-size
`leaf_node_vec` (default 50). `attention_model.py` embeds packed items,
leaf nodes and the next item, runs a small graph-attention encoder, and
emits a **pointer distribution over the leaf nodes**. The action *is* a
candidate.

That is our candidate provider, our legal filter and our ranker, with
the same shape. **The union work was the right instinct**: their action
space is literally "the set the generator proposed", so a proposal
family that the generator cannot express is a move the policy cannot
make, exactly as Cup 008 measured for rule-alpha.

Their generator is one scheme chosen by a flag, not a union of expert
families -- an argument for `C = C_generic | C_rule-alpha | ...` being a
generalisation of, not a departure from, the published design.

## Five things they do that we do not

### 1. The reward is dense and per-item, not terminal

`bin3D.py::step`: `reward = box_ratio * 10`, where `box_ratio` is the
placed item's volume as a fraction of the container. Every step pays.
The episode ends when a placement fails (`succeeded == False` -> `done`),
and that terminal is booked at **zero remaining value** -- correctly,
because everything already packed is already in the accumulated return.

**This is the root of our tail problem.** We score a board with a
terminal *vector* and a dominance verdict, so a rollout that stops early
mis-values the whole comparison, and 96.3% of Cup 009's rollouts stopped
early. Two attempts to fix that (widen the continuation, bootstrap it
with V_theta) both failed. Under a dense reward the question does not
arise: a truncated rollout has already banked the value of what it
placed, and `no_retained_candidate` is a real terminal rather than a
2-4x underestimate.

Note their reward is *also* blind to arrangement -- it is pure item
volume, exactly like our `fill_score_proxy`. Arrangement quality reaches
the gradient only through future feasibility, i.e. through the return.
So "the reward is degenerate w.r.t. where the item goes" is not the
defect we took it for; **not accumulating a return is**.

### 2. The training policy is stochastic

`attention_model.py::_inner`: `dist.sample()` during training,
`dist.mode()` only when `deterministic` (test). An entropy term is
logged and optimised. Every actor in our league is deterministic, so we
have never had exploration at all -- a horse visits exactly one
trajectory per cell, forever.

### 3. One network is the policy, the bootstrap and (in the MCTS
   variant) the rollout policy and the prior

`model.py::DRL_GAT` is an actor and a linear critic sharing the encoder.
`train_tools.py` collects `num_steps`, calls
`storage.compute_returns(next_value)` -- `returns[-1] = next_value`,
then `returns[t] = reward[t] + gamma * returns[t+1] * mask` -- forms
`advantages = returns - value`, and takes one A2C/ACKTR step. The
network that acted is the network that is updated is the network that
acts next.

In the older repo's search (`MCTS/node.py::PutNode.expand`,
`roll_out`): the prior `p` comes from the policy head, the leaf value
from the value head, and the truncated rollout **samples from the policy
net** (`np.random.choice(prev.shape[0], p=prev)`), backing up
`value = reward + gamma * value` with `value = 0` only at a genuine
terminal. That is precisely the AlphaGo shape proposed in this session.

We had three separate frozen objects: a rank-0 rollout policy frozen
since Cup 001, a champion that only ranked root candidates, and a
V_theta trained offline. The bootstrap failed partly *because* it was
trained separately -- its tail term averaged 17.371 fill points against
a 0.729 measured gap. A critic trained on the same trajectories as the
reward it bootstraps cannot have that scale mismatch.

### 4. The learning signal is an advantage, not a verdict

`advantages = returns - value; actor_loss = -(advantages.detach() *
logProb).mean()`. There is no dominance rule, no strict-pair
construction, no "incomparable". We spend most of our compute deciding
whether one board strictly dominates another on four heads, and throw
away every pair that does not. **Our pipeline is supervised learning
from search verdicts -- imitation of a search -- not policy improvement
against a return.**

### 5. Sample volume

Data is generated on the fly (`RandomBoxCreator`) across
`num_processes` parallel envs, for millions of steps. `space.py` is pure
numpy heightmap arithmetic; there is no physics engine in the loop.

## The one thing that genuinely does not transfer

Their environment is analytic. Ours settles every placement in PyBullet:
a control episode in today's A/B did 154 rollout physical steps in 174
seconds (~1.1 s/step), and `scripts/fast_afterstate_env.py`'s own
docstring puts one full episode at one to two minutes. A PCT-shaped A2C
run needs 10^6-10^7 steps. **We cannot train their way in our
simulator**, and no amount of loop-closing changes that.

The repo already knows this: `scripts/fast_afterstate_env.py` is a
physics-free heightmap afterstate model built for exactly this reason,
and `reports/hazard/afterstate-fidelity.json` measures its agreement
with physics over 2409 rows (candidate rows: median position error
0.0116 normalised, p90 0.245; release-candidate rows are much worse,
median 0.0927, p90 0.602, and 90th-percentile orientation error 90
degrees). That fidelity is the gate on whether a PCT-shaped loop is
possible here at all, and it has never been evaluated as such -- it was
measured for a different purpose.

## What this implies for the plan

1. The candidate-space work (the inference-side union, Cup 009) is on
   the published architecture's own terms and stands.
2. Closing the teacher's policy-iteration loop is a real fix to a real
   gap, but it improves a *verdict-mining* pipeline. It does not turn
   the pipeline into RL, and today's six-cell A/B says it moves few
   verdicts (below).
3. The decision worth making is whether to build a PCT-shaped loop on
   `fast_afterstate_env`, with PyBullet demoted to a validator. The
   blocking question is the fidelity number above, not the algorithm.

## Today's six-cell A/B, for the record

Continuation policy on (`--rollout-continuation-top-k 3`) vs off, same
actor (`rule-grid`, which executes its own heuristic action whatever the
teacher says, so both arms visit identical states and fork identical
pairs). Streams: the `permute-000-607` scenario matrix. Not a cup.

| cell | continuation switches | strict pairs off -> on | verdicts changed |
|---|---|---|---|
| dual-empty | 19/87 | 2 -> 1 | 1/4 (strict -> void) |
| dual-shelf-mixed | 23/66 | 2 -> 2 | 1/4 (winner flipped) |
| single-empty-noshelf | 5/19 | 1 -> 2 | 1/3 (void -> strict) |
| dual-preloaded-dedicated | 2/21 | 1 -> 1 | 0/2 |
| single-empty-shelf | 0/34 | 2 -> 2 | 0/4 |
| single-preloaded | 0/9 | 3 -> 3 | 0/3 |
| **total** | **49/236 (20.8%)** | **11 -> 11** | **3/20 forks** |

The mechanism fires (it is not the null the design record warned
about) on four of six cells, and where it fires it moves about one
verdict per cell in both directions. **Net teaching signal: unchanged.**
Cost, from the one uncontended serial pair measured today: 2m54s ->
5m06s, **1.76x** at k=3.

On these numbers a Cup 011 dispatched only to close this loop would buy
a 1.76x bill for no measurable change in the corpus it produces. The
value of the change, if any, is that the teacher is no longer frozen and
*can* compound across cups -- which cannot be demonstrated without
running consecutive cups, and which is a property of the
verdict-mining pipeline the section above argues is the wrong frame.
