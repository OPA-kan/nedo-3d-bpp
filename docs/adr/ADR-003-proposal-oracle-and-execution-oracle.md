# ADR-003: 共有するのは可行性であって、ランキングではない

**Status:** Accepted
**Date:** 2026-08-02
**Amends:** ADR-001 §2「共通配置コア」
**Scope:** 課題Aの二段階探索（`Agent.optimize` と出荷 `policy()` の関係）

## Context

ADR-001 §2 はこう書いている。

> オンライン `policy()` とオフラインドライランは、同じ候補生成、幾何制約、
> 支持判定、ランキング処理を呼び出す。オフライン専用の別配置器は作らない。

**「ランキング処理」まで共有対象に含めたのは広すぎた。** 実装は既にそこを
共有していない。`Agent.policy` は
`risk_lambda = RELEASE_RISK_RERANK_LAMBDA`（`RELEASE_RISK_LIVE_RERANK` が
真のとき）を選択スタックへ渡すが、`DryRunEvaluator.evaluate` は
`PlacementCore.rescue_choose` / `choose` を `risk_lambda` なしで呼び、
`apply_release_risk` は `None` で素通しする。λ を 1.0 / 50.0 / 無効と振っても
dry-run 結果はビット一致する（`offline-evaluator-omits-risk-rerank`）。

つまり出荷実行器は risk-on（`Q - 1.0*P_rot - 0.5*P_slide`）、オフライン評価器は
pre-risk greedy を模擬している。文面には違反しているが、**この乖離を bug と
みなして risk-on へ揃えるのが自明に正しいわけではない。**

## Decision

課題Aの実際の構造は二段階である。

    risk-off dry-run で順序候補を探索
        --> risk-on 実agent + 公式物理で最終検証

`DryRunEvaluator` は**本番挙動の忠実なシミュレータではなく、安価で決定論的な
proposal oracle** である。この役割に対して重要なのは本番rankerとの一致では
なく、次の3つである。

1. 候補順序の相対的な絞り込み能力
2. マシン非依存性（ADR-002）
3. 最終物理検証で良い順序を拾えること

したがって ADR-001 §2 を次に置き換える。

> オンライン `policy()` とオフラインドライランは、**物理・幾何学的な可行性
> 契約**を共有する。候補列挙予算とランキング方策は、それぞれの目的に応じて
> 異なり得る。相違は明示し、最終採用は出荷 policy による物理検証を要する。

### 共有必須（feasibility semantics）

- コンテナ inclusion 判定
- 衝突判定
- 支持条件
- orientation・anchor の構成
- 配置状態遷移の proxy
- invalid 判定

ここが割れると、オフラインが物理的に成立しない順序を推薦する。それは
proposal oracle の失敗であって、許容できない。

### 共有必須ではない

- 候補列挙予算（attempt budget）
- deadline 規則
- rescue 探索
- ranking / risk 補正
- 外側の探索戦略

現状 risk 補正が非共有であることは、**この分類における設計判断として承認する**。
バグとして修正しない。

### 2026-08-12 experimental amendment

The default decision above remains unchanged, but the previously promised
comparison arm now exists. `OFFLINE_RISK_RERANK=1` constructs
`DryRunEvaluator` with the shipped rotation-risk lambda; the existing slide
lambda is then applied by the same `risk_adjusted_score` path used online.
The flag is read only by `Agent.optimize`, defaults off, and therefore does
not alter Task B/C or the shipped Task A proposal oracle.

Adoption requires a paired physical comparison against the unconfigured
`default` arm on both bundled Task A cases, three repeats each, under the
same 150 second offline and 180 second external budgets. A proxy-only win is
insufficient. Until that experiment passes, risk-off remains shipped.

## Consequences

- `E_proposal(pi) != E_execution(pi)` を明示的に許容する。二段階探索として
  正常であり、問題になるのは **proposal oracle が良い候補を取りこぼしている
  かどうかだけ**である。
- proxy 値（例: 採用runの23）と物理結果（25〜26）の差について、
  risk-off proposal と risk-on execution の**方策差が候補原因の一つとして
  特定された**。差の符号や大きさを説明したわけではないので、そこは未解明の
  ままである。`task-a-offline-proxy-is-relative-only` の運用（proxy を絶対値
  として報告しない）は変わらない。
- 可行性契約の共有は維持されるため、ADR-001 の本来の狙い（オフラインが
  実行不能な順序を出さない）は保たれる。
- **risk-on dry-run は棄却しない。** 採用変更としてではなく、将来の比較arm
  として残す。proposal oracle を risk-on にすると `E_theta` が変わるため、
  Task A の全数値が古くなる。実施するなら比較実験として設計し、
  「proposal oracle が本番に近いほど良い順序を出すか」を測る。これは未測定の
  問である。

## Non-goals

この ADR は次を主張しない。

- proposal oracle が本番と乖離していることが**望ましい**とは言っていない。
  現時点で揃える根拠が無く、揃えると再測定コストが発生する、と言っている。
- 現在の乖離幅が適切だとも言っていない。測っていない。
- ランキング以外の非共有項目（rescue、列挙予算）について、現在の設定が最適
  だとも言っていない。ADR-002 が扱うのは列挙予算だけである。

## Implementation

- `agent/agent.py`: `Agent.policy` の `live_lambda`、
  `DryRunEvaluator.evaluate` の既定呼び出し（`risk_lambda` を渡さない）、
  比較arm `OFFLINE_RISK_RERANK=1`
- `context/optimizer_fingerprint.json`: `live_ranking_sha256` を
  `behaviour_sha256` と別に保持し、乖離を可視化する
- `tests/test_optimizer_fingerprint.py`: 無断でこの分担が変わったら落ちる
- `docs/MEASUREMENT_AUDIT.md` F8
- `context/evidence.json`: `offline-evaluator-omits-risk-rerank`
