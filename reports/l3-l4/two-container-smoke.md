# 2コンテナ smoke: 配分は動くが、偏りと人質構造がある

Date: 2026-08-03. Branch `claude/l3-l4-allocation-ordering`.
配布ケースは全て1コンテナのため、多コンテナ経路はこれが初のローカル実行。
合成 scene `m2-k15.json`(同梱): 優先コンテナ(000幾何・棚なし) + 通常(001幾何・棚あり)、
手荷物83個(000+001連結、priority 6 / soft 24)、pool 15。
注意: `camera.num_containers` を明示しないと env が depth バッファ不足で落ちる
(合成config作成時の必須項目)。

## 結果(base、1 run)

- **経路は動く**: 正常完走、priority 誤配 0(置けた2個は優先コンテナへ)
- placed 21/83、fill 13.68、step 21 の release 失敗でエピソード終了

## L3 発見 1: 配分が 19:3 に偏る

コンテナ選択は step ごとの ranker スコア比較の結果であり、19/22 が
棚あり通常コンテナへ、優先コンテナには3個のみ。roomiest-first は unit の
訪問順(第3キー)を決めるだけで、確定は score が握る。棚の +2.0 support 項が
恒常的に片側を勝たせている疑いが強い(未確認、次の測定対象)。

## L3 発見 2: 人質構造 — 1配置の失敗が空のコンテナごと道連れ

エピソードは unsafe 1回で全体終了する。step 21 時点でコンテナ0はほぼ空
(3個)なのに、詰まったコンテナ1への release(imm score -1.54、最下位圏)を
試みて死亡し、**60個の残り荷物と空コンテナ1基が未使用のまま失われた**。
配分層が存在すれば「空いている側があるのに詰まった側で危険な一手を打つ」
状況は排除できる。これは placed/fill に直結する構造的損失であり、
1コンテナ配布ケースでは原理的に観測できなかった。

## 次の測定(事前登録)

- arm `l3_prefer_empty`: score が帯(既存 Q_imm 帯 0.15 を流用)内で並ぶとき
  残容量(まず体積、次に幾何化 L3-1)の大きいコンテナを辞書式で優先
- arm `l3_risk_route`: release しか無い item は、より空いたコンテナの候補を優先
- 判定: m2-k15 3 repeats で placed/fill が base を上回るか。
  ローカル比較の限界(deadline 依存)は Task C k=1 と同様に注意

## Ablation 第1ラウンド(2026-08-03): 判定不能、ただし天井が見えた

base [18,40,18] vs l3_prefer_empty [18,18,27]。deadline 依存の分散(18↔40)が
arm 差を圧倒し、n=3 では判定不能(task-b-guard-not-reproducible-off-ci と同種)。
tie-break は作動する(11:17 の run あり)。決定的なのは base r1: 殺し手の
release を生き延びた run は placed 40・配分 23:18 に達した。この scene の
損失の本体は配分ではなく「エピソードを終わらせる 1 手」であり、次の測定は
l3_risk_route(release しか無い item を空いた側へ)と、殺し手 step の
リスク項の実測に移す。CI か直列実行での再測定が前提。

## Death-band 辞書式リスクゲート(2026-08-03): 初の陽性

因果鎖(全リンク実測): 死は score −1.5 帯の release の実行 → その手を
モデル自身が P_rot 0.70 と採点 → 空側コンテナに安全手(P_rot 0.03–0.06)が
数百個実在するが score −2.8 で負ける → 加算 rerank は谷 1.4 > 罰上限 1.0 で
逆転不能 → 死番のみ辞書式(settled or P_rot<0.5 → score)。
直列 ablation: base 27/18/27 → death_band **37**/17/**33**。発火 run は
+6〜+10 placed、配分は 19:19 へ均衡(副作用)。既定オフ。
採用条件: 複数 scene 検証 + CI guard。ledger
`death-band-lexicographic-risk-gate-first-positive`。

## 複数scene検証 第1ラウンド(直列 ×2)

| scene | base placed/fill | death_band placed/fill | 発火 |
|---|---|---|---|
| b000-k15 | 17 / 19.31 | 17 / 19.31(同一) | 0 |
| c000-k1 | 23 / 26.10 | 23 / 26.10(同一) | 0 |
| b001-k20 | 22 / 24.59 | **21 / 26.92** | 1 |

非発火sceneは完全no-op(回帰なし)。b001-k20 では発火1回で
placed −1 / fill +2.33 の交換 — 事前基準「placed非悪化」には形式上抵触。
公式重みが不明のため、この交換の採否は判定保留。追加レプリケートと
発火stepの解剖を夜間に継続。

## 第2ラウンド(全7scene累積)

| scene | base placed | death_band placed | 発火 |
|---|---|---|---|
| m2-k15 ×4 | 27/18/27/20 (μ23.0) | **37/17/33/36 (μ30.75)** | 3/0/11/7 |
| b001-k20 | 22 | 21(fill +2.33) | 1 |
| b000-k20 | 19/20 | 12/20 | 0/0 |
| 他4scene | — | 完全同一 | 0 |

m2 は4反復で平均 +7.75 placed に強化(発火 run は全て base 最良超え)。
b000-k20 r0 の 12 は発火ゼロなので gate の swap ではないが、注意:
発火カウントは swap のみで、死帯 release 選択時の P_rot 評価自体は
予算を消費する — deadline 軌跡への timing 副作用は非ゼロ(このscene は
base 自体も 19/20 と不安定)。採否判定は CI 相当の環境での反復が必要。

## 第3ラウンド(6反復)

- **m2-k15: base μ22.0 vs gate μ30.5(+8.5)。** 発火した5run(2〜11回)は
  全て base 最良(27)超え: 29/31/33/36/37。多コンテナでの効果は堅い
- **b000-k20: base μ19.7 vs gate μ18.0、発火ゼロ。** swap なしでも死帯
  release 選択時の P_rot 評価が予算を食う timing 副作用の方向は負
  (ただし 12 の外れ値を除くと範囲は重なる、n=6)。
  緩和案: 残予算が閾値未満なら評価をスキップする deadline-aware 化

採否の現在地: 多コンテナで大勝、単コンテナは no-op〜微負(timing)。
既定オフのため出荷リスクなし。最終判定は CI 反復(default branch 変更が前提)
または b001-k20 型交換の損得判断(公式重み依存)を要する。

## 2mm × death-band 要因実験(2026-08-04)

| m2-k15 | gate OFF | gate ON(発火) |
|---|---|---|
| guard 10mm | 18/18 | **36/30**(3) |
| guard 2mm | 23/18 | **30/30**(6) |

gate の価値は 2mm 下でも保存(+9.5)。2mm 単独は死番構造を消さず、
むしろ発火が倍増(限界 pose の受理増→死帯到達番の増加)。両変更は
併用可能。最強セルは 10mm+gate(n=2、要追試)— 単コンテナ行列で測った
2mm の得は多コンテナでは自明でない。ledger `joint-2mm-x-death-band-factorial`。

## CI 判定(2026-08-04、ubuntu-24.04、3 replicates)

**death-band(6 case × 3):** suite 合計 base 122.3 placed / 110.6 fill →
gate **125.7 / 119.5**(+3.33 / +8.91)。同セッションで測れた雑音床
(1.7 placed / 3.9 fill)の約2倍で、方向は陽性。ただし **per-case はローカルと逆転**:
c000-k1 が最大の得(+4.67 placed / +10.13 fill、ローカルでは発火ゼロ)、
m2-k15 は **−1.67**(ローカルの主戦場)。CPU が速いと死番の出方が変わるため、
どの scene で効くかはハードウェア依存。一般化するのは機構であって per-case の値ではない。

**雑音床の較正(重要):** anchor ablation の `base` と `true_envelope` は
既定 ON 以降 **同一構成**であり、この run は偶然の null pair だった。
同一コードでも placed mean 18.571 vs 18.333、単一 case では c000-k1 が
**−2.333** まで振れる。n=3 で ±2.3 placed 未満の per-case 主張は判定不能。
そして **envelope の Task B guard はこの run では測れていない**(true 対 true)。
box_envelope 腕での再測定が必要。
