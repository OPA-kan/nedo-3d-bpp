# 戦略・必要な指標・各proxyが支持される理由

いま何をしていて、そのために何が測れている必要があり、既存のproxyはなぜ
proxyとして成立し、softはなぜ成立していなかったのか。

---

## 1. 戦略

公式スコアは6成分の加重平均だが、`num_placed_items` は**他の成分と並ぶ1つ
ではなく、ゲートかつ増幅器**である。

* **ゲート**: 一定数積めないと充填率以外は0
  (`score-cutoff-gate`)。実際に観測されている — placed 0.201 の提出では
  cog/stability/placement/soft が**全部ゼロ**、placed 0.405 以降は非ゼロ
  (`official-score-calibration-point-1`)。**ただし我々はとうに通過側**に
  いるので、現在の低スコアの説明にはならない。
* **増幅器**: placed −2.6% が被ゲート4成分で −20.0%、下向き **7.6倍**・
  上向き **6.7倍** (`num-placed-gate-amplifies-downward-too`)。

したがって戦略は「placed を上げる」に集約される。そして placed を上げる手段
として賭けているのが、**残余空間の価値を学習した proposer**（探索が締切内に
到達できない良候補を、直接提案させる）。死因の57.6%が「候補ゼロで降参」で
あることがその根拠 (`death-budget-is-search-starvation-not-physics`)。

## 2. そのために必要な指標

学習にはラベルが要る。ラベルの形は既に測定で絞り込まれている。

* **短期ラベルは全滅している。** placed-to-go はステップと占有体積に交絡、
  即時settle生存は選択肢数と無関係（符号一致ちょうど0.500）、Q帯の兄弟ペアの
  95.2%が短期指標で引き分ける (`build_branch_labels.py` 冒頭)。
  → **ラベルはエピソードを終わらせて取るしかない。**
* **2成分では足りない。** death-band は placed +2.0 を根拠に出荷して公式
  −15.3% を請求された (`death-band-official-regression-15pct`)。placed と
  fill だけ見ていると、残る4成分の請求書が見えない。
  → **ラベルは6成分ベクトルでなければならない。**

つまり必要なのは「**各公式成分に対応する、方向が公開された、分岐を順位づけ
られるローカル量**」である。

## 3. 各proxyがなぜ支持されるのか

| 成分 | ローカル量 | 支持の根拠 | 既知の限界 |
|---|---|---|---|
| fill | `fill_score` | **proxyではない。** 同梱 `Evaluator.calculate_fill_rate` が公式実装そのもの | 壁密着は fill に計上されない (`wall-flush-fill-exclusion`) |
| placed | `num_placed_items` | **proxyではない。** 同梱評価器が直接出力 | — |
| stability | shake 7指標 | 手順が公式に確定 — 蓋を閉じて重力変動、ずれ・力・運動エネルギーで採点 (`COMPETITION_RULES.md:70-73`)、摩擦が効くことも公式QAが明言 | 大きさ・時間・閾値は非公開。**反復間ノイズが効果を超える**（max_shift 22.7%、peak KE 74.6%）ので、**多数ペアのプール**でしか読めない (`shake-veto-is-inside-its-own-noise-floor`) |
| cog | `com_z` | 公式QAが「荷物は直方体、重心は対角線交点」と確定させたので `z_com = z_rest + h/2` は近似ではなく厳密 (`com-centroid-official`) | 正規化は非公開。**方向のみ**。実例として m2 では com_z が改善したのに公式 cog は落ちた |
| placement (priority) | `priority_*` 違反数 | 規則が**完全公開**され (`simulator/README.md` 評価指標)、物理を要しない。転記が `calculate_attribute_placement` | 違反数→0〜100 の写像は非公開。**スコアとして提示してはならない** (`ATTRIBUTE_PLACEMENT.md`) |
| soft | `soft_*` 違反数 | 同上 | 同上 **＋ 下記の致命的な問題** |

**共通の性質**: どれも「方向は公開されている」。これが proxy を proxy たら
しめている条件であって、値の一致ではない。

## 4. softはなぜproxyとして成立していなかったのか

softの転記は**正しい**。規則は `上方向からの接触判定` と明記されており
(`simulator/README.md` 評価指標)、同梱診断もエージェントもそれを忠実に実装
している。忠実性の問題ではない。

問題は**分散**である。

* ローカル `soft_clean_ratio` は 132エピソードで平均 **0.982**、42盤中34盤が
  完全にクリーン。アーム間でもほとんど動かない（あるwaveで 0.973 対 0.981）。
* 一方で公式 `soft_item_score` は 7.65 → 21.30 と**3倍近く動いている**。
* proxy が 0.98±0.01 でほぼ飽和している間に、スコアは3倍動く。
  **その proxy はスコアについて情報をほとんど持っていない。**

なぜそうなるか。5提出について `g = 公式値 ÷ (ローカル比率×100)` を soft 軸と
placement 軸から**独立に**計算すると、提出ごとにほぼ一致し、placed とともに
急峻に上がる (`attribute-components-are-local-ratio-times-a-placed-scale`)。

| 提出 | placed | soft から g | placement から g |
|---|---:|---:|---:|
| sub1 | 0.434 | 0.078 | 0.059 |
| sub2 | 0.452 | 0.129 | 0.143 |
| deathband | 0.491 | 0.178 | 0.193 |
| quietguard | 0.497 | 0.200 | 0.214 |
| trueenvelope | 0.505 | 0.217 | 0.223 |

つまり **公式属性成分 ≈ ローカル比率 × g(placed)**。我々の soft が 19.65 なのは
規則を破っているからではなく、**placed 0.497 では g がまだ 0.20 しかない**
から。そして proxy はその g を**含んでいない**。

> **一般化**: proxyに必要なのは忠実さではなく**変動**である。飽和した
> proxy は、正しくても制御変数にならない。

同じ検査を priority に当てると、`priority_clean_ratio` は **0.760** で飽和して
いない — 実際に変動がある。だから placement 側の proxy は soft 側より健全で
ある。ただし直し方は測定済みで、`RELEASE_ATTRIBUTE_GUARD` は違反をゼロに
できるが placed を1シナリオあたり約11.5失う (`attribute-guard-trades-placed-for-priority`)。

## 5. 学習ラベルへの帰結

* ラベルは6軸すべてを持つ（`build_branch_labels.py` の `terminal_axes` で
  soft/priority/cog を追加済み。従来は placed と fill のみだった）。
* ただし **soft は現在の運転領域では信号ではなく制約**として扱う。飽和して
  いるので学習の勾配にならないが、proposer が配置分布を変えれば動きうるので、
  「悪化させない」ガードとして持つ。
* 情報を持つ軸は **placed / fill / stability / cog / priority**。
* stability は**プールしてのみ**読む。単一runの shake 差は読まない。
* cog は方向のみ。値の改善を成分の改善と読み替えない。

## 6. この文書が置き換えるもの

soft のズレについて、このセッションで4つの機序が提案され4つとも外れた
（探索飢餓 / post-shake タイミング / stack-aware 解釈 / 積載カットオフ）。
どれも台帳を引かずにその場で組み立てたものだった。5つ目にあたる §4 の説明
だけが、台帳自身が2026-08-04に測っていた増幅構造を再現している。

`AGENTS.md` の情報優先順位は「実行中の公式シミュレータソースと設定」を第1位、
`AGENT_OPERATIONS.md` §0.2 は「導出しない、照会する」と定めている。§4 に到達
するのに必要だったのは新しい実験ではなく、`scripts/context.py evidence
--topic scoring` を一度引くことだった。
