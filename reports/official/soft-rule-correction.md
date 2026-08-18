# Correction: the soft rule was published, and I did not read it

This retracts the premise of `reports/official/soft-rule-gap.md`,
`reports/hazard/soft-stack/verdict.md` and
`reports/hazard/soft-stack/generation-verdict.md`. Those documents'
measurements stand; their framing does not.

## What the primary source says

`simulator/README.md`, 評価指標 section, defining the Placement Score:

> 優先手荷物やソフト貨物が自分以外の属性の手荷物の下敷き**(上方向からの
> 接触判定がある)**になっている ... 優先手荷物とソフト貨物はそれぞれ独立に
> 評価される

An explicit **upward CONTACT determination**. And immediately after, in
the same section:

> なお, 手荷物を一定数以上コンテナに積載できていないと充填率スコア以外は
> **0となる**

`docs/ATTRIBUTE_PLACEMENT.md` had already transcribed the first of
those from that exact source, and `docs/COMPETITION_QA.md:9` had already
recorded the second as the 積載数カットオフ, naming placed as the gate on
cog / stability / placement / soft.

## Three errors, each avoidable by reading it

**1. The stack-aware reading contradicts the published rule.** I
introduced "charge any ordinary item resting anywhere above" as a
better reading of a sentence I called ambiguous. It is not ambiguous
and it says contact. I chose the variant because its number (25.17) sat
nearest the official 19.65 — fitting a rule to one data point. The
shipped contact-only predicate is a faithful transcription, not a
defect.

**2. The 5x discrepancy compared incommensurable quantities.**
`docs/ATTRIBUTE_PLACEMENT.md` states that the violation-count to 0–100
mapping is unpublished, and instructs in as many words: **clean_ratio を
スコアとして提示しないこと**. I put local clean ratio 98.14 beside
official soft_item_score 19.65 and called the gap five-fold. There is no
gap because there is no shared scale.

**3. The placed gating is documented, not discovered.** The r = 0.988
regression in `reports/official/placed-regression.md` rediscovered the
loading cutoff. That regression is still a correct description of the
five submissions and its residual analysis still stands, but it
establishes nothing new: the rule was already written down twice.

## What survives, and it inverts the conclusion

The measurement itself is unaffected. With the **shipped** predicate,
across 42 recorded terminal states:

- **0.19** violated soft items per episode
- **34 of 42** boards completely clean
- mean `soft_clean_ratio` **0.98**

Under the rule as published, that is not an inert instrument. It is the
finding that **we are already compliant with the soft rule on nearly
every board**. There is almost no violation left to remove, so no
selector, filter, guard or ranking term on this axis can buy anything —
and the attribute filter's 0-of-16 result was the correct answer, not a
symptom of a broken predicate.

The low official `soft_item_score` is explained by two documented facts
that have nothing to do with our coverage: the loading cutoff, and the
unpublished normalization.

## Consequence

Soft is not a separate lever. The route to it is placed, which is what
the cutoff rule says outright. That is the same destination the earlier
documents reached, but they reached it through a rule I invented, and a
conclusion that survives its premise being wrong was not established by
that premise.

The `stack_aware` flag stays in `agent/agent.py`, default off, as the
reproduction of a negative. It must not be described as a better
reading of the rule.

## Root cause

`AGENTS.md` 情報の優先順位 puts the running official simulator source and
config **first**. I read one line of `docs/COMPETITION_RULES.md` and
never opened `simulator/README.md`'s own 評価指標 section, nor
`docs/ATTRIBUTE_PLACEMENT.md`, which existed precisely to stop this.
Thirty-two episodes bought this correction.
