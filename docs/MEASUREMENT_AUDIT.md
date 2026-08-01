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

### F3. 分散は config 固有で、結論を担ぐ config に集中している

同一agent・同一箱での観測（2026-08-02）:

| config | 同一箱の観測(placed) | 振れ幅 |
|---|---|---:|
| b000-k15 | 17, 17 | 0 |
| b000-k20 | 17, 16, 17 | 1 |
| **b000-k40** | 17, 18, **13** | **5** |
| b001-k20 | 18, 18 | 0 |
| b001-k30 | 17, 17 | 0 |

5configのうち3つは完全に安定し、**b000-k40 だけが5個振れる**。つまり
「Task B は全体にノイジー」ではなく、**特定configだけが不安定**である。

これが重要なのは、`aabb-cache-guard-mixed` の証拠が
**b000-k40 (+10) と b000-k20 (−12) という、まさにその2つのconfig**だけで
構成されているからである。−12 は振れ幅を大きく超えるので結論自体は残る
公算が高いが、net −8 という数値と「mixed」という性格づけは、記録されている
より遥かに広い誤差を持つ。

### F4. 測定と食い違う記述が2件ある

1. `reports/benchmarks/baseline.json` の契約文
   「Timing-sensitive nondeterminism exists on **b001** configs」
   → **逆**。b001-k20 / b001-k30 は同一箱で完全に安定し、振れたのは b000 側。
2. `aabb-cache-guard-mixed`
   「b001 configs carry timing nondeterminism, but **the b000-k20 drop is
   deterministic-environment real**」
   → b000-k20 は同一コード・同一箱で placed 1個 / fill 4.6 振れる。
   「b000 は決定的環境」という前提は成立しない。−12 という差の大きさから
   結論は生き延びる可能性が高いが、**根拠として挙げられている決定性は誤り**。

規則どおり既存エントリは書き換えず、加法的に訂正エントリを足すこと。

### F5. 回帰ガードは自分の契約を支えられない

`baseline.json` の契約は「a drop in placed_count or fill_score must be
explained or the change rejected」。しかし baseline は**1config 1試行の点推定**
であり、b000-k40 の自己分散が5である以上、−5 までの低下は有意判定できない。
現状のガードは、検出したい効果よりノイズが大きい。

### F6. 「決定的」は層を指定しないと誤りになる（この監査自身が踏んだ）

この文書の初稿は「Task A は tier A、Task B online とは性質が違う、この非対称は
本物」と書いた。**誤りである。** 書いた直後の測定で崩れた。

ケース000を `OFFLINE_MAX_EVALUATIONS` = 50 / 55 / 60 / 無制限で実行した結果:

| 実行 | 評価1回(seed) | optimization | 選ばれた順序 | 物理 placed | fill |
|---|---:|---:|---|---:|---:|
| cap 50 (×2) | 1.26–1.29 s | 94.8–97.9 s | 同一 | 26 | 36.946 |
| cap 55 | 1.35 s | 100.0 s | 同一 | 26 | 36.946 |
| cap 60 | 1.27 s | 108.7 s | 同一 | 26 | 36.946 |
| 無制限（初回） | 1.93 s | 148.2 s | 同一 | **25** | **34.949** |

**41要素の順序は全実行で完全に一致している。** つまりオフライン探索は cap に
無関係に同じ答えへ収束しており、ここは正しく tier A である。にもかかわらず
**同じ順序から物理 26 と 25 の両方が出る。**

差はオンライン側にある。`policy_seconds` は全実行 6.515〜6.522 で**予算飽和**
しており、オンライン方策も anytime である。無制限実行時は seed 評価が 1.93 秒
（他は 1.26〜1.35 秒）で、箱が約45%遅かった。遅い箱では 6.5 秒で見られる候補
が減り、別の配置を選ぶ。

したがって:

- **オフラインの順序選択**: 決定的。機械速度に依存しない。tier A。
- **エピソードの物理結果**: 機械速度に依存する。Task B online と同じ。

`task-a-bounded128-adopted` / `task-a-bounded128-replicated` が
「3実行でビット一致」「run-to-run variance is not a confounder」と書いている
のは、**測定した範囲では真だが強すぎる**。それらの実行がたまたま同程度の速度
だっただけで、速い箱では 26/36.946 が出る。規則どおり既存エントリは書き換えず、
訂正エントリを加法的に足すこと。

**なお `OFFLINE_MAX_EVALUATIONS` の cap 自体に効果がある証拠は無い。** cap付き
実行を後から回したため、cap の効果と箱の速さが完全に交絡している。現在
無制限を同じ箱の状態で対照実行中で、それが 26 を出せば cap の寄与はゼロである。

この節の教訓は F3/F5 と同じもので、**Task B 固有の問題ではなかった**という点
が重要である。同一マシンA/Bの規律は Task A のエピソード測定にも要る。

### F7. 共通コアの下で、オフライン計測は黙って陳腐化する

`agent/agent.py` を触ったコミットは33件あるが、`Agent.optimize` 本体を変えた
のは `7b2b485`(初期) と `58c4408` の2件だけである。**それでもオフライン
オプティマイザの挙動は12回前後変わっている。**

ADR-001 §2 が「オンライン `policy()` とオフラインドライランは、同じ候補生成、
幾何制約、支持判定、ランキング処理を呼び出す」と定めており、
`DryRunEvaluator.evaluate()` は実際に `PlacementCore.choose` /
`rescue_choose` を呼ぶ。したがって**共通コアを変えた全コミットが、オフライン
探索の意味を変えている**:

`149559b` release候補 / `68395b3` anytime化 / `0d2e59b` shallow release probe /
`b32e2f8` settled優先 / `5c70943` support-plane anchor / `28e6150` support-plane
release / `227cad2` AABBキャッシュ6.4倍 / `8669efc`・`00ddc64` 回転リスク
rerank / `70a72a4`・`2cb450c` 滑りモデル。

この設計は正しい(オンラインとオフラインの乖離を防ぐのが ADR-001 の狙い)。
問題は**記録側がそれを追跡していない**ことにある。

- 台帳の `status` は「新しい測定が置き換えた」しか表現できない。**土台が動いた
  ことによる陳腐化を検出する手段が無い。** ある主張は、誰も再測定していなくても、
  下のコアが変わった瞬間に古くなりうる。
- 具体例: 本監査の元になった `task-a-offline-budget-starved-by-unbounded-scan`
  は「1ドライラン約35秒」を根拠にするが、これは**現在のコアでの値**である。
  AABBキャッシュ前のコアでは候補スループットが1/6.4なので、同じ主張は別の
  数字になる。ADR-001 Remaining Work 5 を「否定で閉じた」と書いたが、正しくは
  **現在のコアについて閉じた**である。
- 同じ理由で、キャッシュ前の Task A 数値と現在の数値は直接比較できない。

`slide-lambda-05-adopted` が記録した教訓「search, selection, and risk components
cannot be evaluated independently」は、**オフライン計測にも適用される**。あの
教訓はオンラインの採用判定について書かれているが、共通コア設計のため範囲は
より広い。

対策は F2 の提案に `core_ref` を含めること(下記)。

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

1. `task-a-offline-proxy-is-relative-only` に機構的な説明がつく。proxy 23 に
   対し物理 25〜26 という差は、単なる誤較正ではなく**別方策を模擬している
   ことによる系統バイアス**を含む。
2. bounded128 は「pre-risk greedy 実行器向けに最適化した順序」を選び、それを
   risk-on 実行器が走らせている。それでも +5 配置改善したのは、頑健だった
   ということであって、設計どおりではない。
3. 逆に言えば、**リスクモデルの変更は E_theta を動かしていない**。F7 で挙げた
   12件のうち `8669efc` / `00ddc64` / `70a72a4` / `2cb450c` の4件は、
   オフライン評価器を変えていない。F7 の一覧はその点で過大だった。

どちらに倒すかは設計判断であり、本監査は決めない。ただし**どちらでも
再測定が要る**: 揃えれば `E_theta` が変わって Task A の全数値が古くなり、
揃えないなら「揃えない」を ADR に書いて gap を明示する必要がある。
`context/optimizer_fingerprint.json` の `adr001_section2_ranking_shared` が
現状を `VIOLATED` として保持し、`tests/test_optimizer_fingerprint.py` が
無断の変更を落とす。

## 提案

### 0. optimizer fingerprint (実装済み)

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
