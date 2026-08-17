# Guard attribute filter: preregistered protocol

Committed 2026-08-17 JST before any result is opened. Motivated by the
official quietguard submission (35.195, docs/OFFICIAL_SCORE_LOG.md):
the guard's component signature appeared as designed (cog +2.4%,
stability +0.4%) but soft fell 7.7% — the swap checks settle safety
only and is blind to the scored attribute-placement rules, so a rescue
pose may cover soft or priority cargo.

## Mechanism (one clause added to the swap eligibility)

When the guard evaluates an alternative, it additionally computes the
candidate's attribute violations with the agent's existing
candidate_attribute_violations contract (the same one the offline
scorer and diagnostics use). An alternative is ineligible if it
INCREASES priority or soft coverage violations relative to the
incumbent's own violations. Trigger, probe order, physics arbitration,
caps, never-refuse: unchanged. If every safe alternative worsens
coverage, the incumbent stands (the swap must never buy survival by
selling scored placement quality).

## Matrix and gates

{base, quiet_guard (current default), guard_attr (filter on)} x 3
replicates x the seven guard configs. Gates, all required:

1. Attribute mechanism: pooled soft_clean_ratio and
   priority_clean_ratio under guard_attr each no worse than
   quiet_guard, and soft_clean strictly better pooled.
2. Survival preserved: pooled placed and steps under guard_attr within
   each config's baseline floor of quiet_guard (the filter must not
   give back the confirmed survival gains).
3. No harm vs base: the adopted-default gates still hold (pooled
   placed >= base, per-config floors).
4. Physical deaths non-increasing vs quiet_guard.

Pass: guard_attr replaces guard_quiet as the shipped default (same
adoption ritual, submission rebuilt). Fail: recorded, filter stays
off, and the soft regression is attacked from the candidate-generation
side instead. No retuning on these streams.
