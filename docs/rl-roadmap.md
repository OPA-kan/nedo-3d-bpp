# RL roadmap: local skills, a learned manager, search as the teacher

Status as of the wedge experiment (`reports/wedge/findings.md`,
`reports/bench/stable-vs-wedge-core*.md`).  This is the plan we are
following and why; the wedge policy itself is parked until the manager
exists.

## What is established

* A local structure can be learned.  The chamfer-strip policy (PPO over
  geometry-generated candidates, PASS allowed, analytic validator) beats
  the hand staircase on held-out streams (0.068 vs 0.049 m^3 of a 0.111 m^3
  wedge) and every placement is accepted by the official simulator.
* Its gain does not transfer on its own.  Asked before the ladder for every
  hard item, it recovers four times the wedge volume inside real containers
  and the item count does not move (-0.4 analytic, -0.7 physics per scene,
  intervals spanning zero).  It takes the large suitcases the ladder builds
  floor terraces from.  Local reward and global currency disagree.
* Pricing items by regression has failed twice (candidate-feature ranker,
  value net over board tensors): with a deterministic policy and seven SKUs
  the labels had no variance and the boards no diversity.

## The plan

Hierarchy with rule-alpha as the lower level and a learned manager above it.
Local skills (wedge now; shelf exhaustion, sealing, row tiling later) are
options.  The manager decides, per item, which option gets it.  The lower
levels are never retrained on the global reward; the manager is.

The manager is taught by search, not by regression on its own guesses
(expert iteration, the AlphaZero shape with a two-to-four-way action):

1. Run the current manager (initially: always ask the option).  At every
   decision where an option wants the item, expand the alternatives
   (hand to the option / hand to the ladder), depth 2, and roll each leaf
   out to the end with the ladder on the analytic model.  The best branch
   is the policy label, its final count the value label.
2. Train a small model with two heads (hand-off, final count) on
   aggregate features: remaining large hard items (manifest on Task A,
   observed SKU mix otherwise), free floor area, strip state, shelf
   headroom, item SKU.  Not a CNN over board tensors: that needs 10^5-10^6
   labels and we produce about 10^4 a day.
3. Deploy the hand-off head only (no search at play time; 8 s per action).
   Compare paired on the core suite, analytic then physics.  Iterate:
   re-label under the new manager, retrain, compare.

Costs, measured: an analytic ladder step is about 1 s; a depth-2 search
with full rollouts is about 2 minutes per decision; eight runners with
four processes each give about 6,000 labelled decisions per Actions run.
Ways to cut it, in order: truncate rollouts at 15 steps once a value head
exists; cache candidate generation across a rollout (the container changes
by one box per step); label only decisions where an option wants the item.

Decision rule: 5,000 labels, train, compare on core.  If the manager beats
the stable ladder, collect the next 5,000.  If it does not, suspect the
features and the search depth before the data volume.

## Deferred

* Polishing the wedge policy: the continuation run from iteration 180, a
  c1s (main shelf) run, restricting bases to small SKUs.  None of these
  change the transfer problem; they wait for the manager.
* Other local structures.  Each is added as an option once the manager
  can arbitrate between two.
* Fine-tuning options on the global reward, only after the manager has
  converged, with a KL constraint.

## Reuse

* `bench/rollouts.py`: counterfactual branches, continuation boards
  (28,502 from the train suite), `--explore-eps` for diversity.
* `bench/tensor.py`: summary features (`SUMMARY_KEYS`) as a starting
  feature set; tensors kept for a later CNN if labels ever allow.
* `wedge_rl/option.py`: the option interface (`propose(board, profile)`),
  which the manager will gate.
* `.github/workflows/bench-rollouts.yml`: sharded runners for labelling.
