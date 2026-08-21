# Physical PUCT stream-matrix audit

Run: [GitHub Actions 32513651324](https://github.com/OPA-kan/nedo-3d-bpp/actions/runs/32513651324)

## Outcome

Eight paired rank-0/PUCT games completed with authoritative PyBullet legal
filtering. PUCT diverged from rank-0 in every pair and had no selected-action
physics failures.

- mean fill-score delta: `+0.735104`
- mean placed-count delta: `+0.75`
- mean soft/priority violation delta: `-0.75`
- fill wins/ties/losses: `2/4/2`
- mean shake peak-KE delta: `+18.578759` (worse)

These are descriptive results on a synthetic development matrix, not evidence
of competition-distribution improvement.

## Teacher audit

The raw counts overstate the learnable sample size:

- 92 valid policy rows across 61 unique model-visible root states
- only 4 non-uniform visit distributions
- those 4 rows collapse to only 2 unique model-visible states
- 22 terminal-return rows across 12 unique model-visible states
- 6 of 8 PUCT games were censored at `max_steps=12`

The stream permutation did produce distinct physical trajectories, but the
only search-informative roots repeated the same two model-visible boards. A
policy network trained now would mostly learn a uniform target, and a value
network would have only two independently terminated trajectories. This is a
valid PUCT/data-contract milestone, not yet a useful P/V training set.

## Next gate

Expand the matrix to four stream families (`original`, `source-001`,
`reverse-000`, and `permute-000-17`) and extend games to 24 steps. Count
teacher diversity by model-visible state signature, not candidate ID or raw
trajectory signature. Train the first value bootstrap only after the expanded
run supplies terminal returns from multiple scenario/stream groups; do not
feed the hand-written immediate candidate score into P or V.
