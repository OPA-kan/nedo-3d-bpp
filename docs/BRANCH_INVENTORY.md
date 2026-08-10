# Branch inventory — 2026-08-10

This inventory was produced after `git fetch --all --prune`. The canonical
implementation branch is `experiment/anchor-recall-oracle` at `fe39111` for
this snapshot. Counts are relative to that commit and will change as report
bots append results.

## Canonical branch

`experiment/anchor-recall-oracle` contains the accepted bounded Task A dry
run, first-pass depth 256, true container envelope, official transport-plane
contract, scenario matrix, six-component proxy vector, calibration reports,
and the latest support-exhaustion diagnosis. It is the only branch to extend
for new work unless a clean worktree branch is cut from it.

## Remote branches not ancestors of the canonical branch

| branch | live-only / branch-only commits | disposition |
|---|---:|---|
| `claude/algorithm-improvement-testing-uni3wj` | 294 / 1 | Archive. Its single soft-settle/MC-v1 evidence claim predates the later MC-v1/v2 rejection. |
| `claude/task-a-rollout-bounded128-dneq4n` | 158 / 10 | Archive. Task A adoption and scenario-matrix conclusions reached live trunk by later integration; wholesale merge would replay stale reports and raw runs. |
| `claude/task-bottleneck-optimization-o3qtkk` | 166 / 25 | Research source only. L1/L2 reachability and selection-gate instrumentation may be ported commit-by-commit after current-trunk negative controls. Do not merge wholesale. |
| `experiment/future-option-tiebreak` | 297 / 8 | Rejected experiment archive. Later evidence closes the live-policy path. |
| `experiment/route-survival-shadow` | 297 / 9 | Rejected experiment archive; route-loss was zero and the observed transport deaths came from protocol fallback. |

`git cherry` reports every listed exclusive commit as patch-distinct, but that
does not imply its conclusion is missing: many results were independently
reimplemented, remeasured, or merged through another branch. Commit identity
is not evidence identity.

## Preserved result branch

`experiment/task-a-rollout-transfer` was pushed through `ccb11e7` so the Codex
analysis is recoverable. Its implementation and compact official-budget report
are already represented on the canonical branch. Keep it as history; do not
merge it again.

## Already integrated notable branches

- `claude/l3-l4-allocation-ordering`
- `claude/stride-endgame-saturation-test-gqssix`
- `claude/taskc-algorithm-improvement-ivaqo1`
- `claude/test-audit-physical-validation-7oj0wu`
- `claude/release-counterfactual-replay`
- `experiment/cross-step-incumbent`
- `experiment/rescue-scan`
- `experiment/visible-pool-rollout`

These remote refs can remain as audit anchors. Deleting them saves little and
would make old evidence sources harder to inspect. If branch deletion is ever
desired, tag the exact tips first and perform it as a separate cleanup action.

## Merge rule

1. Fetch immediately before ancestry decisions.
2. Never choose a trunk by `agent.py` line count; stale research branches can
   be larger than the canonical branch.
3. Merge a current branch only when it is based on the current canonical tip
   and its proof/review gates pass.
4. From stale research branches, port the smallest logical commit or re-create
   the instrument on a fresh branch. Do not merge hundreds of stale commits to
   obtain one measurement.
5. Merge evidence ledgers additively by id. A later contradiction supersedes
   an older entry; it does not silently rewrite it.
