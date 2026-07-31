# Release risk 評価プロトコル(凍結版 v1)

作成: 2026-07-31。以後の replay データ追加生成・モデル比較は本プロトコルに
従う。変更する場合は本ファイルを更新し、変更点と理由をコミットメッセージに
明記する(過去の数値との比較可能性が壊れるため、黙って変えない)。

## 現時点の結論(要引用時の正しい言い方)

- **既存Φには回転危険(`rotated_over_30`)の予測信号があるが、
  snapshot間外挿が不安定で係数は未確定**(LOSO AUC 0.699 [0.581, 0.804]、
  case外挿 0.784 / 0.676、pool外挿 0.745 / 0.646)。
- **水平変位は未解決**。item属性の結合で binary AUC 0.614→0.693 と改善する
  が、連続 d_xy の held-out Spearman は 0.176 と弱い。
- `support_ratio >= 0.6` は**低危険率領域**(rotation 0.004 [0.000, 0.016])
  であり、安全証明ではない。hard-accept 則としては実装しない。

## 1. 特徴集合(凍結)

回転リスク `Phi_rot`(この6項目・この順序・この変換):

| # | 特徴 | 変換 |
|--:|---|---|
| 1 | `support_ratio` | そのまま |
| 2 | `com_margin` | そのまま |
| 3 | `drop_normalized` | そのまま |
| 4 | `support_imbalance` | **絶対値** |
| 5 | `left_right_imbalance` | **絶対値** |
| 6 | `front_back_imbalance` | **絶対値** |

- `overhang_ratio` は `1 - support_ratio` と同一情報のため入れない。
- `initial_tilt_deg` は恒等的に 0 の placeholder のため学習に使わない
  (`phi_availability` を機械的に確認する)。
- 滑り評価用の拡張特徴 `Phi_slide` = `Phi_rot` + item属性
  (`mass`, `lateralFriction`, `restitution`, `is_soft`,
  `density = mass/volume`, `min_extent/max_extent`)。
  state snapshot の `observation.pool_list` から `item_index` で結合する。
  再生成は不要。

## 2. モデル(凍結)

- 標準化ロジスティック回帰: 訓練foldで各特徴を `(x - mean) / std` に標準化、
  切片あり、batch勾配降下 3000 epoch、学習率 0.5、正則化なし、クリップ
  |z| <= 30。実装は `scripts/evaluate_release_risk.py::fit_logistic_np`。
- これより複雑なモデル(木、GBM等)を試す場合も、この logistic を
  **必ずベースラインとして並記**する。

## 3. 評価(凍結)

### 3.1 データ分割(manifestの `split` フィールドで機械的に判定)

| split | 構成 | 用途 |
|---|---|---|
| `development` | b000-k20, b000-k40, b001-k20 とその追加step、新trajectory(b000-k15, b001-k30 等) | 係数fit・特徴選択・診断 |
| `validation` | b000-k10 | λ選択・モデル比較の検証(fitには使わない) |
| `final_holdout` | b001-k40(既存run含む)、b001-k10 | 最終報告で**一度だけ**開く |

- 各データセットの `manifest.json` に `split` を記録する。生成時は
  `build_replay_dataset.py --split` で指定する(既定 `development`)。
- **`final_holdout` は学習・特徴選択・λ選択・通常分析から機械的に除外**
  される: `analyze_replay_dataset.py` / `evaluate_release_risk.py` は
  manifest の `split == "final_holdout"` を読み飛ばし、明示フラグ
  `--open-final-holdout` を渡したときだけ読む。このフラグは§7の最終評価
  以外で渡してはならない。
- 既存の b001-k40 の2 run は provisional v1 の fit に混入済み(既知の汚染)。
  `final_holdout` に指定した時点から先は一切使わず、最終評価の報告時に
  この汚染を注記する。

1. **LOSO(leave-one-snapshot-out)**: development 内の診断・モデル比較用。
   全ての行は自分の snapshot を見ていないモデルで採点される。
2. **validation**: development で fit した係数を固定し、λ・特徴集合・
   モデル形の選択だけを validation で行う。
3. **不確実性**: 率・AUCとも snapshot-clustered bootstrap 1000回、
   percentile 2.5/97.5。行単位bootstrapは使わない(クラスタ相関を消すため)。
4. **重み付け**: 母集団率は必ず `sampling.sampling_weight` で
   Horvitz-Thompson 再重み付けし、raw件数を併記する。

## 4. 主要指標(凍結)

採用判断は AUC と score 損失だけでは行わない。**changed snapshot
(shadow rerank が baseline と異なる候補を選んだ step)上のペア比較**が
主要指標である。両候補とも counterfactual 物理ラベルが強制包含で
付いているため、直接差が取れる。

| 指標 | 定義 |
|---|---|
| 主 | changed snapshot 上の**回転危険差**: baseline の `rotated_over_30` 数 − shadow 選択の `rotated_over_30` 数 |
| 主 | changed snapshot 上の **placed-safe 差**: shadow 選択の placed-safe 数 − baseline の placed-safe 数 |
| 主 | **安全→危険の逆転数**: baseline が safe かつ shadow 選択が dangerous になった snapshot 数(この逆転は 0 に近いことが採用条件) |
| 主 | validation AUC(`rotated_over_30`) |
| 副 | オフライン再ランキング: λ∈{0.5, 1.0} での選択回転数の削減と平均score機会損失(snapshot単位) |
| 副 | LOSO AUC + 95% CI(`rotated_over_30`, `not_placed_safe`) |
| 副 | gate pass / reject 別の重み付き危険率 + CI |
| 副 | 連続 d_xy の held-out Spearman(`Phi_slide`) |

判断基準(目安、変更時は本文書を更新): validation AUC が 0.70 を下回る
場合は係数を凍結しない。score 損失 5% 超を要する λ は採用しない。
安全→危険の逆転が回転危険削減を上回る λ は採用しない。
**実 action の risk-adjusted への切り替えは、final_holdout 評価が
完了するまで行わない。**

## 5. データ追加の優先順位(凍結)

**候補行数を増やすことに価値はない。増やすのは独立性の軸:**

1. **独立 snapshot**(未使用の step、特に終了直前)
2. **独立 trajectory**(別の look_ahead、別の policy_timeout、
   `--seed` 違いの抽出ではなく軌道自体が変わる構成。
   development 用の新構成例: b000-k15, b001-k30)
3. **未使用 case 構成** — ただし §3.1 の split 割当に従う:
   b000-k10 は validation、b001-k10 / b001-k40 は final_holdout であり
   development の追加データにはならない。

追加生成は `RELEASE_RISK_SHADOW_RERANK=1` を併用し、changed=true の
snapshot では baseline 候補と shadow 候補の counterfactual ラベルが
**ペアで**保存されることを確認する(step summary の
`shadow_pair`、行の `selected` / `shadow_rerank_selected`)。

per-stratum は 8 のままでよい。1構成あたり数十行×snapshot数で足りる。

## 6. Shadow reranking(実装済み・計測手順)

`agent/agent.py` に環境変数ゲートで実装(実 action は不変):

- `RELEASE_RISK_SHADOW_RERANK=1` で有効化、
  `RELEASE_RISK_RERANK_LAMBDA`(既定 1.0)。
- baseline の選択が release candidate のときだけ、**現行 selection stack
  そのもの**(settled優先 + lookahead + 同一の探索)を risk調整score
  `Q - λ·P̂_rot` で再実行し、`diagnostics["shadow_rerank"]` に
  baseline / risk_selection / changed / p_rot を記録する。
  settled 選択時は risk 項が選択に影響し得ないため再探索しない。
- P̂ は `RELEASE_RISK_LOGISTIC_V1`(provisional、本プロトコルの
  refit手順で更新するまで係数は暫定)。
- `scripts/build_replay_dataset.py` は shadow 選択候補を
  `forced_reason: shadow_rerank_selection` で強制包含し、行に
  `shadow_rerank_selected` を付ける。→ 仮想選択の counterfactual
  物理ラベルが実選択と同じ列で手に入る。
- step summary に `shadow_rerank` / `shadow_rerank_matched` を記録。

計測実行例:

```bash
RELEASE_RISK_SHADOW_RERANK=1 RELEASE_RISK_RERANK_LAMBDA=1.0 \
python scripts/build_replay_dataset.py \
  --config <task-b config> --case <id> --steps <mid..late> \
  --per-stratum 8 --risk-gate-mode shadow
```

注意: shadow 再探索は release 選択 step の政策時間を最大2倍にする。
オンライン提出経路では必ず無効(既定値 0)のままにする。

## 7. 係数の refit / 凍結手順

1. 追加データ生成(§5の優先順位、holdout構成には触れない)。
2. `scripts/evaluate_release_risk.py` で LOSO + 外挿 + bootstrap を再計算。
3. §4 の基準を満たしたら、非holdoutデータ全体で refit し、
   `RELEASE_RISK_LOGISTIC_V1` を新バージョン名で置き換える
   (旧係数はgit履歴に残る)。
4. holdout 評価は**一度だけ**行い、結果を findings に記録する。

## 8. 改訂記録

- **2026-07-31 (4)**: **final_holdout 一度きり評価を実施(開封済み)、
  提出デフォルトを risk-on に切り替え。**
  オフライン: 凍結力学モデル(`mech-dev-v1-20260731`、refitなし)で
  holdout 198行/5 snapshot に対し rotated AUC 0.903 [0.761, 0.980]、
  not_placed_safe 0.877 [0.684, 0.969](case別 rotated: b001-k40 0.826、
  b001-k10 0.980)。b001-k40 の provisional-v1(static)汚染は注記の通り
  だが、力学係数は development のみで fit しておりこの評価に対して
  クリーン。オンライン(各case×2反復): placed 平均 off 16.25 → λ=1 18.0、
  fill 21.7 → 22.6、最大settle角の壊滅域(51–180°)が縮小。
  §4 の切り替え条件を満たしたため、`agent.py` のデフォルトを
  `RELEASE_RISK_LIVE_RERANK=1` / `RELEASE_RISK_P_MODEL=mech` /
  λ=1.0 に変更(env で従来動作に戻せる)。以後の「baseline」は
  risk-on の方策を指す。holdout は開封済みであり、今後の分析では
  development / validation と同格に扱わない(再度の「未見」評価には
  使えない)。
- **2026-07-31 (3)**: **確証的凍結: 特徴集合 = 力学のみ、λ = 1.0。**
  validation split(b000-k10, 74行/2 snapshot)は全特徴集合が
  AUC 0.96–0.99 と天井付近で弁別不能のため、§4 基準(val AUC ≥ 0.70)は
  全集合が満たし、選択は最悪方向外挿(力学 0.697 vs static 0.534)と
  オンライン実証に基づく。λ は未使用の validation case b000-k10 の
  オンライン episode で選択: baseline が既にほぼ最適な同 case で
  λ=1 のみ placed 同数・fill 損失 1.2–1.8%(≤5% 基準内)・最大 settle 角
  4°→1° 改善。λ=2 は placed −2 / fill −22% で棄却、λ=4 は不安定。
  development 構成では λ=1 が placed 集計最良(16.8 vs off 13.3)。
  凍結モデル: `RELEASE_RISK_MECH_LOGISTIC_V1`(`mech-dev-v1-20260731`、
  development のみで fit)。**提出デフォルトは引き続き off。次の手順は
  final_holdout の一度きり評価のみで、開封はオーナー判断を待つ。**
- **2026-07-31 (2)**: **オンラインablation実験と提出デフォルトの区別を明文化。**
  オフライン側は意思決定に必要な材料が出揃った(力学特徴の優位、線形
  ペナルティの非劣性、損失の閾値型、安全→危険逆転ゼロ)ため、残る主問
  「実 action に Q−λP̂ を使うと placed/fill が伸びるか」はオンラインで
  検証する。実装: `RELEASE_RISK_LIVE_RERANK=1`(実 action に risk調整
  ranking を適用)+ `RELEASE_RISK_P_MODEL=mech`(development のみで fit
  した `mech-dev-v1-20260731` 係数、実験中は再調整しない)。制約:
  (a) ablation は **development 構成のみ**。final_holdout の case
  (b001-k40, b001-k10)ではオンライン実験もしない。
  (b) **提出経路のデフォルトは off のまま**。§4 の「実 action の
  risk-adjusted への切り替えは final_holdout 評価が完了するまで行わない」
  は提出デフォルトについて引き続き有効であり、本実験はそれに含まれない。
  (c) validation split での確証的な特徴集合・λ 選択手続きは変更なし。
- **2026-07-31**: §1 の特徴集合に、MATHEMATICAL_MODEL §5.2.1 の力学特徴
  `Phi_mech = (d_min, theta_c_min, B_min, log1p(eta_max))` を**候補**として
  追加(定義・入力制約は §5.2.1 が正本)。development での凍結手続き比較で
  力学特徴が全主要指標を支配したため
  (LOSO AUC 0.841 vs 0.732、最悪方向外挿 0.771 vs 0.638、
  snapshot内ペアranking精度 0.842 vs 0.720)。
  **最終的な特徴集合の選択(static / mech / static+mech)と λ は
  §3.1 の validation split で行い、final_holdout は引き続き開かない。**
  評価指標・モデル仕様・split は変更なし。
