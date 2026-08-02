# 課題C 盤面価値: 独立代替配置とHall型競合

**Status:** Proposed（課題Cの理論本体）。計測器は別目的で一部Implemented、
方策への昇格は未着手。

**Scope:** 課題C（offlineなし、可視pool 1、到着順どおりの逐次配置）。
課題A/Bへの転用は本書の対象外とする。

## 0. 中心命題

将来到着順が未知である積付問題において、良い状態とは空き体積が大きい状態ではなく、
将来荷物型に対する実行可能配置が、少数の共有資源に集中せず、互いに独立な代替経路
として残っている状態である。

\[
\operatorname{Good}(s)
\iff
R_c(s)\text{ が各classで大きく、}
H(s)\text{ が大きい}
\]

「選択肢の数」ではなく「独立な選択肢の数」が中心である。同じ狭い場所に依存する
100個の候補より、互いに資源を共有しない3個の候補の方が将来に強い。

## 1. 情報契約（実装前に固定する）

**課題Cのonline agentは残余荷物リストを受け取らない。**

- `env.get_init_states()` が返すのは `optimize` / `lookahead_k` /
  `container_list` の3つだけである
  （`simulator/src/ground_handling/env.py:172`）。
- 全荷物リストは `env.get_info_for_optimization()` 経由でのみ渡り、その呼び出しは
  `if env.optimize:` の内側にある（`simulator/src/ground_handling/app.py:59`）。
  すなわち**課題A限定**である。
- 課題Cのobservationは pool 1件と container状態だけである。

したがって:

- \(\mathcal C\) は「残余荷物の真の多重集合」ではありえない。**型の事前分布**である。
- \(w_c\) は残個数ではなく事前重みである。
- classの多重度は既知にできない。online側の \(R_c\) は多重度上限なし、または
  事前分布由来の期待多重度で定義する。
- `scripts/measure_residual_capacity.py` の `remaining_classes` は case の
  `item_list` から真の残余を再構成している。**offline計測器としては正しいが、
  online特徴としてそのまま移植すると情報漏洩になる。**同名の概念だが同じ関数では
  ないことを、実装時に必ず分離する。

### 1.1 型集合 \(\mathcal C\) の実体

`simulator/configs/item_params.xlsx` が公開している7型がそのまま \(\mathcal C\)
である。\(m=7\)。

| 型 | L×W×H [m] | mass [kg] | soft | lateralFriction |
|---|---|---:|---|---:|
| スーツケース(大) | 0.75×0.56×0.27 | 18 | no | 0.4 |
| スーツケース(中) | 0.65×0.45×0.25 | 13 | no | 0.4 |
| スーツケース(小) | 0.55×0.40×0.24 | 8 | no | 0.4 |
| ダッフル/ボストン | 0.60×0.30×0.25 | 7 | yes | 0.8 |
| 段ボール | 0.50×0.40×0.40 | 10 | yes | 0.6 |
| 大型リュックサック | 0.65×0.35×0.23 | 12 | yes | 0.8 |
| 小型デイパック | 0.45×0.30×0.20 | 5 | yes | 0.8 |

`is_prioritized` は型ではなく個体属性（各型に TRUE/FALSE 両方がありうる）なので、
priority は \(\mathcal C\) の分割軸ではなく、\(\mathcal O_c(s)\) 側の制約
（優先コンテナ指定、扉側配置）として扱う。同梱 `sample_config.json` の全荷物は
この7型のいずれかに一致する。

\(m=7\) は後述の計算可能性にとって決定的である。

## 2. 実行可能配置と資源

型 \(c\) に対する、状態 \(s\) から安全に実行可能な配置集合を
\(\mathcal O_c(s)\) とし、その元を

\[
o=(x,R,\gamma,\Sigma)
\]

（最終位置、姿勢、搬入経路、支持構造）とする。単なる空間的な空きではなく
「搬入できて、支持され、settle後も安全」までを含む。

契約: \(\mathcal O_c(s)\) の元は**共通配置コアを通ったものだけ**とする
（ABC spec §2）。heightmapや格子表現は高速フィルタであって \(\mathcal O_c\) の
定義ではない。

各配置が使う有限資源集合を \(\rho(o)\) とし、
\(\rho(o)\cap\rho(o')\neq\varnothing\) のとき \(o\sim o'\)（競合）とする。

### 2.1 資源集合 \(\mathcal Z(s)\) は幾何由来で定義する

これは実装契約であって好みの問題ではない。\(|N_s(C')|\) を anchor個数で数えると、
その値は stride と grid密度の関数になる。ABC spec §8 の
「候補点の生個数はgrid密度へ依存するためhard価値にしない」に正面から抵触し、
Stage A で `release_cap_volume` がほぼ全snapshotで 0.113 に張り付いたのと同じ
退化を招く。

したがって \(\mathcal Z(s)\) は、既にコードが幾何から導出している正準オブジェクト
だけで構成する。

| 資源 | 由来 | 実装 |
|---|---|---|
| 支持面成分 | 極大support-plane成分＋床＋棚 | `support_plane_components` (`agent.py:1026`) |
| 搬入corridor | Y→X二段掃引が通る区間 | `transport_sweeps` (`agent.py:1128`) |
| 上方clearance | 天井・切欠き・棚の静的上限 | `container_z_interval` (`agent.py:347`) |
| 占有領域 | settled AABB＋lateral clearance | `anchors_conflict` (`measure_residual_capacity.py:147`) |

これらはいずれも離散化パラメータではなく幾何から決まるので、\(|\mathcal Z|\) は
stride を変えても安定である。現行 `anchors_conflict` は**占有AABBのみ**であり、
しかも z方向に分離していれば競合なしと返す。corridor・支持面・clearance は
未実装であり、理論が要求する \(\rho(o)\) はこれより厳密に広い。

## 3. 受容性 \(A(s)\) は必要条件であって本体ではない

\[
A(s)=\sum_{c\in\mathcal C} w_c\,\mathbf 1[\mathcal O_c(s)\neq\varnothing]
\]

この判断はリポジトリの測定と整合する。`evaluate_visible_pool_feasibility` による
1-ply二値可行性は `residual feasible = 1.000` で飽和し、3つの選択モードを縮退
させた（evidence `three-modes-degenerate-run30340049061`、
`lookahead-modes-degenerate-rich-search`）。\(A\) を本体に置かない、という判断は
既に測られている。

## 4. 独立代替数 \(R_c(s)\)

\[
R_c(s)=\max\left\{|I| : I\subseteq\mathcal O_c(s),\ 
\rho(o)\cap\rho(o')=\varnothing\ \forall o\neq o'\in I\right\}
\]

\(R_c(s)=1\) なら、その唯一の場所を他の荷物に使われた瞬間にその型は行き場を失う。
\(R_c(s)\ge2\) なら一つ失っても代替が残る。

### 4.1 計算可能性と下界契約

最大独立集合はNP困難である。しかし**この用途では下界で十分**であり、下界が正しい
向きでもある。「独立な代替が少なくとも \(k\) 本ある」という保証が欲しいのだから、
過小評価は安全側に外れる。

- 貪欲下界は既に実装がある: `greedy_simultaneous_placements`
  (`measure_residual_capacity.py:169`)。
- 契約: \(\hat R_c\le R_c\) を常に満たすこと。報告時は必ず下界であることを明示し、
  値そのものを目標やscoreとして引用しない（evidence
  `task-a-offline-proxy-is-relative-only` と同じ規律）。

### 4.2 既存実装との差分

現行の貪欲は**全classを横断した1本**の独立集合であり（descriptor
`combined_simultaneous_count`）、class別ベクトルではない。理論が要求するのは
class別の \(R_c\) である。ここが未測定の中心である。

## 5. class間競合 \(H(s)\)

各classが利用可能な資源集合を \(N_s(c)\subseteq\mathcal Z(s)\)、
\(N_s(C')=\bigcup_{c\in C'}N_s(c)\) とする。2つの量を分けて扱う。

**(a) 欠損版（主）**

\[
\operatorname{def}(s)=\max_{C'\subseteq\mathcal C}\bigl(|C'|-|N_s(C')|\bigr)
\]

Hallの欠損定理（Königの系）により、これは

\[
\operatorname{def}(s)=|\mathcal C|-\nu(s)
\]

に等しい。\(\nu(s)\) は二部グラフ \((\mathcal C,\mathcal Z(s))\) の最大マッチング
である。**部分集合列挙は不要で、マッチング1回の多項式時間で厳密に求まる。**
「いま既に詰んでいるか」を測る。

**(b) 比版（副）**

\[
H_{\mathrm{Hall}}(s)=\min_{\varnothing\neq C'\subseteq\mathcal C}
\frac{|N_s(C')|}{|C'|}
\]

これは展開率で、一般にはNP困難だが \(m=7\) なので127部分集合の全列挙で厳密に出る。
コストは無視できる。「どれくらい脆いか」を測る。3classが全て同じ1領域にしか置けない
なら \(H_{\mathrm{Hall}}=1/3\) となり、将来到着順への耐性が低い。

実装は (a) を主、(b) を副とする。

### 5.1 資源には容量が要る（F1実装で判明した修正）

\(N_s(c)\) を「componentの集合」として素朴に定義すると、**Hallが構造的に退化する**。
床は面積 2.9 m² の**単一** support-plane component だからである。全classが床に
届くので \(|N_s(C')|=1\)、したがって \(\operatorname{def}(s)=|\mathcal C|-1=6\) が
盤面によらず常に成立してしまう。これは幾何ではなく数え方が生む定数であり、
§2.1 で避けたはずの退化と同種のものである。

したがって資源は**容量付き**で扱う。resource \(z\) の容量を

\[
\operatorname{cap}(z)=\text{（}z\text{ の上に同時に載る互いに独立な配置の貪欲下界）}
\]

とし、\(\operatorname{def}(s)\) は容量展開した二部グラフ上のマッチングで、
\(H_{\mathrm{Hall}}(s)\) は

\[
\min_{C'}\frac{\sum_{z\in N_s(C')}\operatorname{cap}(z)}{|C'|}
\]

で定義する。容量は \(R_c\) と同じ貪欲下界から導くので、追加の較正は要らない。
`tests/test_measure_board_value.py::test_capacity_is_what_keeps_one_big_floor_from_degenerating`
がこの退化を固定している。

## 6. 損傷 \(D(s,a)\)

配置後の状態を \(T_a(s)\) とする。普通の配置は資源を消費するので絶対量の
\(D>0\) は当然であり、情報が少ない。また utility による正規化は公式重みが
非公開である以上、分母が定義できない。

したがって**最悪class相対損傷を主**とする。

\[
D_\infty(s,a)=\max_c\frac{[R_c(s)-R_c(T_a(s))]_+}{\max(1,R_c(s))}
\]

これは「一種類だけ完全に殺す配置」を直接罰する。

この問題に固有の具体例: HANDOFF不変条件「soft と priority は将来の支持面に
ならない」。広い支持面成分の上に soft を置く配置は、占有体積が小さくても支持面資源
を丸ごと消す。体積ベースの残余指標では見えず、\(D_\infty\) が捉えるべき典型例で
ある。

## 7. 不可逆性 \(U(s)\) は \(\Phi\) に入れない

転倒が即終端であるため、修復距離ではなく不可逆遷移確率が本質である、という判断は
正しい。ただしその担当は**既にライブの risk項**にある。現行の \(Q_{\mathrm{imm}}\)
は

\[
Q_{\mathrm{old}}-1.0\,P_{\mathrm{rot}}(\text{mech-dev-v1})
-0.5\,P_{\mathrm{slide}}(\text{slide-dev-v1})
\]

である（`agent.py:80-96`、`risk_adjusted_score`）。\(U\) を \(\Phi\) に足すと同じ
物理チャンネルを二重計上する。

**\(\Phi\) は選択肢構造だけを測る量として純化する。**物理不可逆性は
\(Q_{\mathrm{imm}}\) が持つ。この分離を保つ限り、両者の寄与を独立に測れる。

## 8. 盤面価値と action評価

\[
\Phi(s)=\sum_{c\in\mathcal C}w_c\log\bigl(1+\hat R_c(s)\bigr)
+\lambda\,H(s)-\mu\,B(s)
\]

\(B(s)\) は単一corridor・単一支持面への集中度。\(U\) は §7 により含めない。
\(\log(1+\hat R_c)\) は \(0\to1\)、\(1\to2\) の改善を大きく、\(15\to16\) を小さく
評価するためである。

\[
Q_C(s,a)=Q_{\mathrm{imm}}(s,a)+\eta\,\Phi(T_a(s))-\kappa\,D_\infty(s,a)
\]

### 8.1 辞書式順序は初版として採用しない

\(\bigl(\text{安全性},\text{実行可能性},\Phi(T_a(s)),Q_{\mathrm{imm}}\bigr)\)
の辞書式は、\(\Phi\) を \(Q_{\mathrm{imm}}\) の**上位キー**に置く。これは既に
失敗した介入より厳密に強い介入である。

visible-pool rollout の enforce は、\(Q_{\mathrm{live}}\) 損失 \(\le0.15\) という
**帯の中でしか** action を変えなかったにもかかわらず、8構成×3反復で
placed 137.667→131.000 / fill 167.881→151.656 と回帰した（evidence
`visible-pool-rollout-enforce-rejected-v1`）。帯なしの上位キーはそれより強い。

昇格手順は ABC spec §10.7（効果が確認できたproxyだけrankingへ昇格）に従う。
§11 の順序を守る。「綺麗な盤面のために現在の安全性を犠牲にしない」という原則は、
運用上は「\(Q_{\mathrm{imm}}\) を上書きしない」と読む。

## 9. 既存実装との対応

| 理論 | 既存実装 | 状態 |
|---|---|---|
| \(\mathcal C\) | `remaining_classes` | offline専用。§1の情報契約に抵触するため online へは移植不可 |
| \(\mathcal O_c(s)\) | `class_anchors` + `iter_cartesian_attempts` | Implemented（stride系統サンプリング＋Horvitz-Thompson推定） |
| \(o\sim o'\) | `anchors_conflict` | 占有AABBのみ。corridor・支持面・clearance は未実装 |
| \(R\)（全class横断） | `greedy_simultaneous_placements` | Implemented（貪欲下界） |
| \(R_c\)（class別） | なし | **新規** |
| \(N_s(c)\), \(H(s)\) | なし | **新規** |
| \(D_\infty(s,a)\) | なし | **新規**（Stage B として予定されていたが未実装） |
| \(A(s)\) | `evaluate_visible_pool_feasibility` ほか | Implemented・飽和 |

## 10. 既存の否定的結果との関係

evidence `stage-a-calibrated-negative` は、\(V_{\mathrm{cap}}\) 記述子が
placed-to-go を説明しないと測っている（LOSO MAE 0.979→1.456、全記述子
\(|\rho|\le0.24\)）。**これは本理論の反証ではない。**対象が3点で異なる。

1. ラベルが placed-to-go だった。同じevidenceが「エピソードは容量枯渇ではなく
   物理失敗で終わる」と結論しているので、そのラベル自体が測るべき対象では
   なかった。
2. class を1本のスカラに畳んでいた。理論の中心である class別ベクトルと class間競合
   は測られていない。
3. 資源が占有AABBのみだった。corridor・支持面・clearance を含む \(\rho(o)\) は
   未測定である。

ただしこれは「未測定だから有望」であって「有効」ではない。§11 を先に通す。

## 11. 反証計画（安い順）

**F1. 飽和チェック（実施済み・2026-08-02・合格）**

43 snapshot、`scripts/measure_board_value.py`。結果は
`reports/replay-analysis/board-value-f1-findings.md`。

- \(A(s)\) は**飽和している**（43中42で全7型が個別に配置可能）。\(A\) を本体に
  置かないという §3 の判断は、仮定ではなく測定になった。
- \(R_c\) と \(H\) は**飽和しない**。Hall欠損は0〜7に散らばり、
  `phi_log_settled` は24通りの値を取る。畳んだスカラが持たない変動を、
  class別ベクトルとclass間競合が持っている。
- ただし**予測力は未確立**である。steps-to-terminal との相関は全て
  \(|\rho|\le0.302\) で符号も揃わない。このデータでは判定できない。理由は
  (i) 課題Bのエピソードである、(ii) replay datasetが終端近傍を意図的に
  過剰抽出しており43中21がto-go 0、(iii) ラベルがStage Aで既に失敗した
  placed-to-go系である。

**F2. ラベルの張り替え（F1とTask Cベースラインを受けて再定義）**

当初は「不可逆失敗まで何step残ったか」を候補にしていたが、これは棄却する。
上記(iii)の通り、エピソードは容量枯渇ではなく物理失敗で終わるので、盤面が
健全なまま終端することがあり、実際にF1でその向きが出た。

代わりに、課題Cベースラインが特定した死因そのものをラベルにする。

\[
Y(s)=\mathbf 1[\text{次に到着した荷物に受理候補が無い}]
\quad(\text{`no\_safe\_action`})
\]

課題Cのエピソードは4/4がこの事象で終わっており
（evidence `task-c-baseline-fallback-is-the-only-death`）、これはstepごとに
直接観測できる。盤面価値が主張しているのは「選択肢が潰れていない状態」なので、
予測対象としてこれ以上に直接的なものはない。終端近傍の過剰抽出にも汚染されない。

強い向きで反証可能である。\(\Phi\) と \(H\) が `no_safe_action` のstepを
それ以外から分離しないなら、盤面価値は課題Cの失敗を記述していないので、
rankingへ入れない。

**F3. 課題Cベースライン上での shadow**

`c000-k1` / `c001-k1` で \(\Phi\) を telemetry としてのみ計算し、選択が変わる頻度、
計算コスト、非退化率を出す。action は変えない。

**F4. Q帯内 tie-break**

ここで初めて action を変える。成功指標は placed と fill の同時非悪化に加えて、
不可逆終了stepが後退すること。

## 12. 計算予算

`POLICY_BUDGET_SECONDS=6.5`。\(\Phi(T_a(s))\) を全候補に対して評価すると
\(|A|\times m\) 回の候補走査になる。visible-pool rollout は3 item・bounded
attempts で 111 ms/step 平均・617 ms 最大だったので、素朴な実装は桁で超過する。

初版の制約:

- \(\Phi\) は top-K（\(K\le3\)）の受理候補にだけ評価する
- class あたりの attempt を bounded にする（Task A の bounded128 と同じ形）
- packed-AABB キャッシュを再利用する

この制約を守れないなら shadow 計測にも載せない。

## 13. 本理論が触らない領域

現行方策のエピソード終了の45%は `unsafe_protocol_fallback`（固定座標
`[0.0, 0.0, 0.25]`）である（evidence `transport-deaths-are-fallback-poison`、
`agent.py:6406`）。\(\Phi\) は「選ぶとき」の質を上げるが、fallback は
「選べないとき」に出る。両者は補完的であり、\(\Phi\) だけを入れてもこの45%は
動かない。課題Cは pool=1 のため退避先itemが存在せず、この経路の重みは課題Bより
大きい。

盤面価値と fallback は別々の実験として進め、片方の改善をもう片方の根拠にしない。
