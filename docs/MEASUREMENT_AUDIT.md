# 計測監査 — 状態 / action / 遷移 / episode

作成: 2026-08-02。対象: `context/evidence.json` 全51エントリと、その根拠となる
`reports/` 配下の実験。

## なぜこれを作ったか

2026-08-02、Task A の採用変更に対して `reports/benchmarks/baseline.json` の
回帰ガードを回したところ placed 88 → 86 と出た。原因を追ったが、実際には

1. **保存された baseline は別マシンの値**で、変更前のagentでも再現しない
   （同一箱で旧agent 86 / 新agent 86、差はゼロ）
2. **同一agent・同一箱でも b000-k40 は 13〜18 と5個振れる**

の2点で、コードの寄与は測定できていなかった。空振りの原因は測定の不在では
なく、**測定に「どの計測器で、標本いくつで、どのマシンか」が付いていない**
ことである。台帳は事実を持っているが、その事実の**精度**を持っていない。

この監査は、既存計測を4軸で棚卸しし、各主張に信頼度を付け直すためのもの。

## 方法

### 軸（MDPの分解）

| 軸 | 何についての主張か |
|---|---|
| **状態** | s の表現、特徴量、状態価値 `V(sigma(s))`、残余容量 |
| **action** | 候補生成・列挙・被覆・順序、および選択効用 `Q(s,a)` |
| **遷移** | 解放後の物理 — 回転、滑り、settle、公式判定 |
| **episode** | 終局チャネル、集計 placed/fill、公式スコア |

### 信頼度階層

| tier | 定義 |
|---|---|
| **A** | 独立に再現済み（別run、できれば別マシン）で一致 |
| **B** | 同一run内で反復あり（n>1） |
| **C** | 単一試行 / 単一run（n=1） |
| **D** | 単一スナップショット・単一ケース |
| **E** | 外部権威（公式QA・公式評価）。自前の計測ではない |

## 軸別の地図（51件）

### 状態 — 8件（最少）

`preview-term-same-score`, `three-modes-degenerate-run30340049061`,
`lookahead-modes-degenerate-rich-search`, `stage-a-settled-only-negative`(superseded),
`capacity-instrument-calibration`, `stage-a-calibrated-negative`,
`visible-pool-rollout-step9-signal`, `visible-pool-rollout-enforce-rejected-v1`

### action — 16件（最多）

`ranker-volume-dual-role`, `anchor-recall-one-snapshot`, `class-aware-coverage-effect`,
`gate-high-recall-low-precision`, `support06-low-risk-region`,
`shadow-rerank-low-live-leverage`(superseded), `shadow-rerank-low-live-leverage-33snap`,
`late-snapshots-not-starved`, `aabb-cache-guard-mixed`,
`deadline-reserved-rescue-rejected`, `cross-step-incumbent-top2-rejected-as-fallback`,
`task-a-offline-budget-starved-by-unbounded-scan`, `task-a-bounded64-rejected`,
`task-a-bounded128-adopted`, `task-a-offline-proxy-is-relative-only`,
`task-a-bounded128-replicated`

### 遷移 — 14件

`current-failure-release-settle-topple`, `rotation-signal-coefficients-unfrozen`,
`dxy-unresolved`(superseded), `mechanics-features-dominate-static`(superseded),
`risk-rule-family-comparison`(superseded), `official-loss-step-in-angle`,
`mechanics-features-dominate-static-33snap`, `risk-rule-family-comparison-33snap`,
`risk-freeze-mech-lambda1`, `final-holdout-passed-default-switch`,
`slide-direction-downhill`, `dxy-equivariant-s0`,
`slide-lambda-not-adopted-v1`(superseded), `slide-lambda-05-adopted`

### episode — 12件

`risk-gate-ablation-off-baseline`, `floor-lift-era-fix`(historical),
`online-ablation-round2-positive`, `terminal-failure-channels`,
`b000-k20-regression-is-slide-death`, `transport-now-leading-death-channel`,
`transport-deaths-are-fallback-poison`, `score-cutoff-gate`(E),
`shake-test-stability`(E), `com-centroid-official`(E),
`wall-flush-fill-exclusion`(E), `official-score-calibration-point-1`(E)

### meta — 1件

`split-assignment`

## 所見

### F1. 最も測っていない軸に、最大の未解決問題がある

件数は action 16 / 遷移 14 / episode 12 / **状態 8**。状態が最少である。

ところが `HANDOFF.md` の `Not established` の筆頭は
「graded state value `V_hat(sigma(s'))` が効くかどうか」である。**投資が最も
薄い軸に、最大の未解決問題が置かれている。**

しかも状態8件の内訳が偏っている。3件は残余容量の計測器較正と否定結果
（`stage-a-*`, `capacity-instrument-calibration`）、2件は「モードが退化して
差が出なかった」（`three-modes-degenerate`, `lookahead-modes-degenerate-rich-search`）、
2件は rollout の signal あり／採用棄却。**肯定的に確立された状態表現の主張が
実質ゼロ**である。遷移軸が回転モデル・滑りモデルという2本の使えるモデルを
産んだのと対照的で、この非対称は意図されたものではなく履歴の産物に見える。

### F2. 9割の主張に精度が付いていない

| | 件数 |
|---|---:|
| 反復数に言及 | 6 / 51 |
| 構造化 `values` を持つ | 9 / 51 |
| 実行マシンを明記 | 7 / 51 |

台帳の契約は status（active/superseded/historical）で**鮮度**を管理するが、
**精度**を管理する欄が無い。「いつの測定か」は分かるが「どれだけ信じてよい
測定か」が分からない。2026-08-02 の空振りはここから来ている。

### F3/F5 [2026-08-02 REWRITTEN]. 反復数ではなく、分散軸を指定する

初稿は「1試行では足りないので反復を増やせ」と書いた。**それは誤りである。**
stride branch の `development-suite-noise-floor-permutation` が、この環境では
同一configの再実行が**ビット一致**することを測っている。反復は有効標本数を
増やさない。

結果を次のように置く。

    Y(pi, omega, m, xi)
      pi    : 方策
      omega : 到着順
      m     : 荷物multiset
      xi    : runtime / timing noise

測定済みの分散:

| 軸 | 大きさ | 出典 |
|---|---|---|
| `xi`（同一config再実行） | **config依存**。b000-k15 と b001-* は完全一致、b000-k40 は placed 幅5（13/17/18） | 本監査の同一箱A/B、および stride の base 17/17/17 |
| `omega`（同一multisetの並べ替え） | **大**。8順序で placed sd 2.315、range 7（11〜18）、fill sd 3.948 | `development-suite-noise-floor-permutation` |
| `m`（multiset間） | **未推定** | development suite は2 streamから look-ahead を変えて作った5 config なので、stream間変動が推定できない（`arrival-distribution-not-estimable-from-two-streams`） |

**`xi` について2つの測定は矛盾しない。** どちらも config 固有であることを示して
いる。安定な config（b000-k15、b001-k20、b001-k30）では `xi` はゼロで、
b000-k40 では5。したがって「反復はビット一致だから無意味」も
「反復で分散が測れる」も、config を指定せずには言えない。

したがって規則は次のようになる。

- **反復数ではなく、推定対象の分散軸を明示する。** 同一configの再実行が
  決定論的な config では、runtime反復は有効標本数を1のままにする。
  `n_xi = 3` と書かず `n_omega = 1, n_xi = 3` と書く。
- **到着順効果には paired permutation** を使う。同一multisetの複数順序で、
  arm間を対応付ける。これが `item-cap-16-wins-on-every-permutation` の設計で、
  8/8・sign-test p = 0.0039 という符号の安定性を出せたのはこの設計による。
- **multiset一般化には複数 source case** を使う。現在の cap16 結果は
  ケース000の1 multiset の8順序であり、`m` 軸は未検証である。
- **UNPAIRED な per-config 差は、約2 sd 以下なら到着順の偶然と区別できない。**
  live interleave のスクリーニング（+5/-4/-3/-1/0）はこの帯に完全に収まり、
  「測定された否定」から「未確立」へ格下げされた。

証拠の階層はこうなる。

    同一順序で改善  <  同一multisetの複数順序で改善  <  複数multisetで改善

cap16 は現在**中央**にいる。

`reports/benchmarks/baseline.json` については、初稿の「反復付きで作り直す」は
**不十分**である。反復は `xi` しか標本しない。必要なのは
**同一マシン上の paired 比較**を正式手順にすることと、保存値との比較をやめる
ことである。マシン速度依存（F6）と `omega` 依存は別の問題で、前者は同一箱
A/Bで、後者は permutation で消す。

### F8. オフライン評価器はリスクrerankを通っていない(ADR-001 §2違反)

F7 を fingerprint 化する過程で見つかった。**共有されていないものがある。**

- `Agent.policy` は
  `live_lambda = RELEASE_RISK_RERANK_LAMBDA if RELEASE_RISK_LIVE_RERANK else None`
  を `risk_lambda` として選択スタックへ渡す。
- `DryRunEvaluator.evaluate` は `PlacementCore.rescue_choose` /
  `choose` を **`risk_lambda` なしで呼ぶ**。`apply_release_risk` は
  `risk_lambda is None` で素通しなので、release候補のスコアは無調整。

実証: `RELEASE_RISK_RERANK_LAMBDA` を 1.0 / 50.0 / rerank無効 の3通りにしても、
同一入力に対するdry-run結果は**ビット一致**する。

したがって現状は、

- 出荷される実行器: risk-on (`Q - 1.0*P_rot - 0.5*P_slide`)
- オフライン評価器が模擬する方策: **pre-risk greedy**

ADR-001 §2 は共有対象に「候補生成、幾何制約、支持判定、**ランキング処理**」を
明示的に含めている。**ランキングは共有されていない。** これは記録された設計
判断ではなく、未文書の simulation gap である。

影響:

1. `task-a-offline-proxy-is-relative-only` の差について、**候補原因が一つ
   特定された**。risk-off proposal と risk-on execution の方策差である。
   ただし proxy 23 対 物理 25〜26 という差の**符号も大きさも説明できていない**
   ので、「系統バイアスが判明した」と書くのは過大である(初稿の誤り)。
2. bounded128 は「pre-risk greedy 実行器向けに最適化した順序」を選び、それを
   risk-on 実行器が走らせている。それでも +5 配置改善したのは、頑健だった
   ということであって、設計どおりではない。
3. 逆に言えば、**リスクモデルの変更は E_theta を動かしていない**。F7 で挙げた
   12件のうち `8669efc` / `00ddc64` / `70a72a4` / `2cb450c` の4件は、
   オフライン評価器を変えていない。F7 の一覧はその点で過大だった。

**決着済み(ADR-003)。** 「揃えない」に倒した。課題Aの実構造は
「risk-off dry-run で順序候補を探索 → risk-on 実agent + 公式物理で最終検証」
という二段階であり、`DryRunEvaluator` は本番の忠実な模擬ではなく**安価で
決定論的な proposal oracle** である。本番rankerとの一致より、相対的な絞り込み
能力・マシン非依存性・最終物理検証で良い順序を拾えることが重要。したがって
`E_proposal != E_execution` は許容し、問題になるのは proposal oracle が良い
候補を取りこぼしているかどうかだけ。ADR-001 §2 は ADR-003 により
「可行性契約は共有、ranking と列挙予算は非共有可」へ限定された。
risk-on dry-run は棄却ではなく**将来の比較arm**として残す。
`context/optimizer_fingerprint.json` の `adr001_section2_ranking_shared` が
現状を `VIOLATED` として保持し、`tests/test_optimizer_fingerprint.py` が
無断の変更を落とす。

## 提案

### 0. behavioural regression fingerprint (実装済み)

`scripts/fingerprint_optimizer.py` が、`DryRunEvaluator` が到達する依存グラフ
全体に同一性を与える。2層構造:

- `component_sha256`: theta を宣言している定数群。
- `behaviour_sha256`: 固定した微小状態集合で**実際に何をするか** —— 列挙結果、
  `choose` / `rescue_choose` の決定、完全なdry-run結果、構築的初期順序。
- `live_ranking_sha256`: オンライン選択器を**別ハッシュ**で持つ。F8 の乖離を
  隠さず可視化するため。片方だけ動いたら、その変更はオフラインに届いていない。

全probeは `deadline=無限` かつ試行予算固定で走る。F6 の教訓どおり、fingerprint
がマシン速度に依存したら無意味だからである。

検証済みの性質:

| 変更 | component | behaviour |
|---|---|---|
| `Ranker` の重み `2.0*support` → `2.5*support` | 不変 | **変化** |
| `depth_score` 係数 0.35 → 0.30 | 不変 | **変化** |
| `MIN_SUPPORT_RATIO` 0.55 → 0.50 | **変化** | 不変(probeが閾値に触れず) |
| `13381bd`(出荷既定のみ変更) vs `58c4408` | **変化** | 不変 |

最後の行が肝で、**出荷設定の変更とコア意味論の変更が区別できている**。
`behaviour` が動いたら Task A の全測定が古い。

**限界を明示する。これは optimizer の数学的同一性ではない。**

- **probe 依存。** probe が触れない意味論変化は見逃す。既に2例ある —— probe の
  勝者が settled 候補なので risk ranking の乖離を露出できず、`MIN_SUPPORT_RATIO`
  0.55→0.50 も probe の配置が閾値から遠いため `behaviour` を動かさない。
- **API世代を跨げない。** `PlacementCore.rescue_choose` 以前のコア(`a893922`
  より前)は probe 自体が動かない。履歴全体の指紋は取れない。
- **等値であって距離ではない。** ハッシュ相違は「違う」しか言わず、
  「どれだけ違うか」「悪化か改善か」は言わない。

したがって呼称は semantic fingerprint ではなく
**behavioural regression fingerprint over declared probes** とする。
「不変」は常に**probe被覆の範囲内で不変**の意味である。

### 1. 台帳に計測メタを加法的に足す

`ff9b25e` で `replicates` を足したのと同じ手順で、`measurement` を追加する。
既存エントリは書き換えず、埋められるものから順に新エントリで補う。

```json
"measurement": {
  "tier": "C",
  "repeats": 1,
  "unit": "episode",
  "machine": "github-ubuntu-24.04-4vcpu",
  "core_ref": "227cad2",
  "reproduced": false
}
```

`core_ref` は F7 への対策で、その測定が**どの共通配置コアの上で**取られたかを
指す(`agent/agent.py` を最後に変えたコミット)。これが無いと、下が動いた
だけで古くなった主張を機械的に洗い出せない。`status` は人が置き換えを宣言
したときしか動かないが、`core_ref` は自動で照合できる。

### 2. `baseline.json` を作り直す

反復付き（最低3、b000-k40 のような不安定configは5）で、マシン指紋を保存し、
**保存値との比較ではなく同一マシンA/Bを正式手順にする**。ハード差が定義上
消え、今日のような空振りが構造的に起きなくなる。

### 3. 再測定の優先順位

1. **`baseline.json` の再構築。** これが無い限り、今後の Task B の採用判定は
   すべて同じ空振りを繰り返す。最も安く、最も効く。
2. **`online-ablation-round2-positive` の再検定。** off 13.0 vs lam1 16.8 は
   5config集計の差3.8で、そのうち2configが不安定。差が分散に埋もれていない
   か確認する価値がある。なお `final-holdout-passed-default-switch` は
   **offline AUC** の確認であって episode 水準の再検定ではないので、この主張
   を独立に支えてはいない。
3. **状態軸への投資。** F1 のとおり、最も薄い軸に最大の問題がある。

## この監査が主張していないこと

- 既存の結論が誤りだとは言っていない。**誤差が記録されていない**と言っている。
  F4 の2件だけが明確な食い違いで、それも前提の誤りであって結論の否定ではない。
- 分散の推定は b000-k20 / b000-k40 について2〜3試行に基づく。**分散の分散**は
  まだ測っていない。3試行から「振れ幅5」と言うのは点推定である。
- **Task A が例外的に強い、とは言えない。** 初稿ではそう書いたが、F6 のとおり
  誤りだったので撤回した。強いのは**オフラインの順序選択**だけである。
