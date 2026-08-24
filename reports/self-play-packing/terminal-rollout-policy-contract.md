# V-free terminal-rollout policy contract

## Question

Can exact physical continuation improve the live single-agent trajectory before
we trust a learned value function?  This ablation compares the frozen legacy
safe-rank-0 policy with a policy that evaluates every retained safe root action
by continuing it to genuine termination under the same frozen rank-0 policy.

No value model, policy network, learned proposal, scalar score, or weighted
utility participates in selection.

## Root decision

For each live state:

1. generate and physically validate the same bounded root candidate set;
2. force each safe root action in an isolated PyBullet reconstruction;
3. continue with frozen safe rank-0 until genuine terminal;
4. retain the raw terminal component vector;
5. if every sibling has complete terminal truth and the incumbent is dominated,
   execute the lowest legacy-rank action on the terminal Pareto frontier;
6. otherwise execute the incumbent.

A rollout cap is censoring, not terminal evidence.  Any censored sibling makes
the decision fail safe to the incumbent.  The policy therefore changes an
action only on complete evidence of terminal vector dominance.

## Evaluation

Paired episodes use identical scenario, item stream, environment seed and
physics.  The aggregate reports raw deltas for placed count, fill, CoG,
soft/priority violations, surface variation and shake measurements.  Terminal
relations are Pareto relations over the registered direction-aware component
vector; no local exchange rate is invented.

The first gate is empirical trajectory improvement and its physical cost:

- number of proven terminal-dominance switches;
- final terminal-vector relation versus legacy;
- fill and violation deltas without scalarization;
- terminal rollout physical steps and censored roots.

## Scope boundary

The continuation policy and candidate provider remain frozen.  Consequently,
this measures exact rollout improvement within their bounded action support;
it does not establish global optimality or solve candidate recall.  A later
value model may approximate this oracle only after the direct rollout policy is
shown useful and its cost is measured.
