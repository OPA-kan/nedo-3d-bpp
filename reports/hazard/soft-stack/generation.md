# Is the soft-clean placement generated, or only unretained?

Protocol: `reports/hazard/soft-generation-protocol.md`. Measurements and reading thresholds fixed before the wave. Computed offline from `NEDO_CANDIDATE_AUDIT` and `NEDO_POSE_SNAPSHOT`; no agent change and no hot-path work.

- decisions where the played placement covers a soft item: **48**
- accepted candidates per such decision (mean): 311

| measurement | hits | fraction |
|---|---:|---:|
| G1 some accepted candidate covers fewer | 25/48 | 52.1% |
| **G2 some accepted candidate covers none** | 19/48 | **39.6%** |

| G3 split | decisions |
|---|---:|
| a clean candidate exists for the SAME item | 10 |
| a clean candidate exists for ANOTHER item | 13 |

## Reading: **ambiguous**

Ambiguous by the preregistered thresholds. No arm is licensed; the numbers and the G3 split are the finding.

## What this does not answer

The audit carries no score, so this is existence only. What a soft-clean candidate gives up in score -- and therefore whether a retention change could take one without losing placed -- is a separate question, deliberately not estimated here.

The audit's own recording cost changes the trajectory, so these episodes' placed and fill are not comparable with another wave's.
