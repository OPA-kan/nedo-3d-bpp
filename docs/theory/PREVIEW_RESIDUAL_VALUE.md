# Preview-aware residual value

**Status:** Proposed theory / selectable proxy implemented

**Default behavior:** unchanged (`weighted`)

**Implementation:** `agent/agent.py`

## 1. 役割

既存の統一理論は、EP/EMS、部分列マクロ、Option、DPOR、状態署名によって
探索空間を圧縮する。本資料はそれらを置き換えず、生成済みのオンライン候補を
どの評価則で比較するかを定める。

中心仮説は次である。

\[
\boxed{
\text{現在の即時scoreだけでなく、配置後に残る可視poolの実行可能性を保存する}
}
\]

## 2. 完全状態と残余表現

残余空間 \(R\) やheightmap \(H\) は有用な特徴だが、完全な物理状態ではない。
状態 \(s\) は少なくとも次を含む。

- settle後の位置、クォータニオン、実AABB
- 支持面、支持率、支持可能な荷物属性
- 搬入掃引とコンテナ境界
- 優先・soft荷物制約
- 可視pool \(V\)

したがって、本資料の可行集合は抽象的なerosionではなく、共通配置コアと
同じ制約を満たす行動集合

\[
\mathcal A(s,i)
\]

で定義する。

## 3. pool-aware depth-2

可視poolを \(V_t\)、現在行動を

\[
a=(i,p),\qquad i\in V_t
\]

とし、仮想遷移後の状態を

\[
s_t^a=T(s_t,a)
\]

とする。

poolに複数荷物がある場合、固定された「次荷物」は存在しない。次手も選択対象
なので、純粋なdepth-2値は

\[
W(a)=
\max_{j\in V_t\setminus\{i\}}
\max_{b\in\mathcal A(s_t^a,j)}
\widehat V(T(s_t^a,b))
\]

となる。次手が存在しなければ、その現在行動はdead endとして扱う。

pool 1かつオフライン順序が既知なら、計画済みの次荷物を \(j\) として固定できる。
順序なし・pool 1ではpreviewがないため、未知荷物分布に対する解析値または学習値が
別途必要になる。

## 4. 可行余裕

連続モデルでの目標は、実物理制約を満たすアンカー集合の面積

\[
N_i(s)=
\mu_2\left(
\operatorname{proj}_{xy}\mathcal A(s,i)
\right)
\]

である。これはpacking numberや最終価値ではなく、荷物 \(i\) を置く自由度だけを
表す。

現実装は連続面積をまだ計算しない。実際の `PlacementCore` で、残った可視poolの
各荷物について少なくとも一つ可行配置があるかを調べ、荷物別可行性署名

\[
\chi_V(s)
=
\left(
\mathbf 1[\mathcal A(s,i)\ne\varnothing]
\right)_{i\in V}
\]

を基本表現とする。現行実装の離散proxy

\[
G(s,V)=\sum_{i\in V}\chi_V(s)_i
\]

は可行荷物数だけを使う粗い射影である。候補点数は数えないため、同一荷物に多数の
候補があることを重複評価しない一方、「どの荷物が可行か」は失う。

2026-07-29のCase 001では、item 0が15stepで候補を持ちながら未選択となり、
最終的に不可行化した。同じ \(G\) でもitem 0を救う状態と救わない状態を区別する
必要があることがObservedとなった。したがって \(G\) はbaselineとして残し、
diversityと将来価値には \(\chi_V\) を使う。

## 5. 実装済みの三モード

環境変数 `LOOKAHEAD_SELECTION_MODE` で選択する。

### weighted

既存互換baseline。

\[
K_{\mathrm{weighted}}(a)
=
\operatorname{score}(a)
+
\gamma\operatorname{score}(b^*)
\]

既定 \(\gamma=0.5\)。既定挙動を維持するため、このモードがdefaultである。

### depth2

異なる尺度を加算せず、

\[
K_{\mathrm{depth2}}(a)
=
(
\mathbf 1[\text{next feasible}],
\operatorname{score}(b^*),
\operatorname{score}(a)
)
\]

を辞書式比較する。

### pool_resilience

poolに残す選択肢を優先し、

\[
K_{\mathrm{resilience}}(a)
=
(
G(s_t^a,V_t\setminus\{i\}),
\operatorname{score}(b^*),
\operatorname{score}(a)
)
\]

を辞書式比較する。

これは可行アンカー面積の最終実装ではなく、pool-awareな最小proxyである。
また、可行荷物のidentityを失うためstarvation回避の十分統計ではない。

## 6. 学習する場合

学習値を導入する場合は、異なる時刻や親状態を直接比較しない。同一親状態から
生成されたsibling候補を、同一未来列 \(\omega\) でrolloutする。

\[
s_{ab}
=
\operatorname{sign}
\left(
Y(s^a;\omega)-Y(s^b;\omega)
\right)
\]

教師の勝敗は追加充填体積だけでなく、現行の辞書式目的

\[
(
\text{placed count},
\text{placed volume},
\text{stability},
-\text{center-of-mass height}
)
\]

から作る。Gated Iotaは使用しない。解析的な期待可行性baselineに勝てない限り、
学習モデルを標準化しない。

## 7. 実験順序

1. 現行 `weighted`
2. `depth2`
3. `pool_resilience`
4. \(\chi_V\) のidentity-aware diversity
5. 待ち時間と可行性消失を使うregret-aware diversity
6. 連続または格子近似の可行アンカー面積
7. 未知荷物分布に対する期待可行面積
8. sibling rankingによる学習値

最低限、配置個数、体積、物理valid/safe、policy時間、次手dead-end回避数、
pool可行荷物数に加え、候補あり未選択step数、top-K未選択回数、不可行化までの
待ち時間、deadlineで探索未開始の荷物数を比較する。

探索coverageは全体およびclass \(c\in\{\mathrm{normal},\mathrm{soft},
\mathrm{priority}\}\) ごとに、

\[
\frac{|\mathrm{included}|}{|\mathrm{visible}|},\qquad
\frac{|\mathrm{search\ started}|}{|\mathrm{included}|},\qquad
\frac{|\mathrm{candidate\ generated}|}{|\mathrm{search\ started}|}
\]

へ分解する。これによりitem cap、deadline配分、候補生成を同一の低coverageへ
混同しない。

物理validationが壊れた状態から生成した仮想遷移は教師にも評価にも使えない。
benchmarkが固定fallbackで終了した状態は教師に使わず、その直前のsettle済み観測を
保存してsibling比較する。1～5はGitHub ActionsのTask B同一config matrixで比較し、
SIGNATE総合scoreの改善とは区別する。

screeningは同一条件3run、採用候補は5runとし、mean、median、sample standard
deviation、min、max、failure mode countを保存する。top-K未選択後のfallbackは
`starvation_signal`として数え、offline物理counterfactualで安全候補だったことを
確認するまでは確定starvationと呼ばない。

## 8. 非目標

- 残余空間やheightmapだけを完全状態とみなさない。
- 分位点フィルタをhard feasibility保証とは呼ばない。
- lookahead自体を新規性として主張しない。
- マクロ、Option、DPORを本理論で置き換えない。
- Gated Iotaを価値学習へ持ち込まない。

## 9. Proposed: 残余受け入れ能力descriptor(2026-07-31)

状態: **Proposed**(未実装の正式契約。段階Aのみ実装対象、μのscore統合は非目標)。

### 9.1 目的と二段階の区別

測るべきは2つで、混同しない。

\[
\boxed{\text{状態が詰まっているか}} = V_{\mathrm{cap}}(s)
\qquad
\boxed{\text{この行動が状態をどれだけ詰まらせるか}} = R_{\mathrm{future}}(s,a)
\]

- **段階A(sanity check)**: 既存snapshotの \(s\) に対する
  \(V_{\mathrm{cap}}(s)\) が、step・占有体積・case・poolのbaselineを超えて
  placed-to-goを説明するかのLOSO検証。これは状態価値の健全性確認であり、
  行動別 \(R_{\mathrm{future}}\) の検証ではない。
- **段階B(正本)**: 各counterfactual候補のsettle後状態
  \(T(s,a)\)(replay行の `x_plus` を packed に追加した解析的状態)へ同じ
  descriptorを計算し、**同一snapshot内の候補間差** を保存する。将来の
  shadow rerank第2項はこちらから作る。

### 9.2 記号

- 残余荷物多重集合 \(U(s)\): configのitem列から、snapshotのpacked
  indexを除いたもの。寸法を丸めた署名で類 \(c\in C(s)\) に量子化し、
  多重度 \(m_c\) を持つ。
- 到達可能可行アンカー集合 \(A_c(s)\): 類 \(c\) の代表itemに対し、
  `CandidateGenerator.iter_cartesian_attempts(attempt_kind="settled")`
  が返す解析的settled候補(inclusion・静的クリアランス・支持・搬送掃引
  モデルを全て通過)。姿勢は `unique_orientations`、類×姿勢ごとに
  上限 \(M\)(既定40)で打ち切り、打ち切りは記録する。
  release候補は含めない(descriptorは「余裕を持って受けられる」領域を測る)。

### 9.3 descriptor定義

1. **到達可能候補数** \(N_c(s)=|A_c(s)|\)、および集約
   \(N(s)=\sum_c \min(N_c, M)\)。生のアンカー数は近傍を二重計上するため、
   **単独では価値指標にしない**(4の下界を主とする)。
2. **最大受け入れ類容量** \(\mathrm{cap}(s)=\max\{\mathrm{vol}(c): N_c(s)\ge 1\}\)。
   置ける最大類の体積。0なら大型類は全滅。
3. **連結構造**: 類 \(c\) のアンカー同士を「footprint AABBが重なる」とき
   隣接とみなすグラフの連結成分。成分数 \(\kappa_c(s)\) と最大成分サイズ。
   軌道分裂 \(\mathcal O\to\mathcal O_L\sqcup\mathcal O_R\) の実装的対応物。
4. **同時配置可能数の下界** \(\Pi(s)\): 占有競合グラフ
   (ノード=(類,アンカー)、辺=side clearance込みの3D AABB干渉、
   類多重度 \(m_c\) 制約付き)上のgreedy independent set。
   greedy順は体積降順→支持率降順で決定的にする。個数版
   \(\Pi_{\#}\) と体積版 \(\Pi_{\mathrm{vol}}\) を併記。
5. **搬送回廊幅の代理**: 類別最大到達奥行き
   \(D_c(s)=\max\{y(a): a\in A_c(s)\}\)。集約は
   「後半 \(y\ge 0\) に到達できる最大類体積」
   \(\mathrm{corr}(s)=\max\{\mathrm{vol}(c): D_c(s)\ge 0\}\)。
   搬送到達性は解析搬送モデル(Y→X掃引、settledクリアランス)に含まれて
   いるため、静的空き空間ではなく到達可能配置空間で測っている。

### 9.4 段階Aの検証プロトコル

- 対象: development + validation snapshot(final_holdoutは開かない)。
- 目的変数: \(\text{placed-to-go}(s_t) = (\text{episode\_steps\_executed}-1)-t\)
  (最終stepは失敗stepなので数えない)。
- baseline特徴: \(t\)、占有体積比、case source(b000/b001)、look_ahead。
- 追加特徴: \(\mathrm{cap}, \Pi_{\#}, \Pi_{\mathrm{vol}}, \mathrm{corr},
  \kappa\)系、\(N\)。
- モデル: OLS(snapshot数が少ないため)。LOSO(snapshot単位)で
  baseline vs baseline+descriptor のMAE / R² を比較。
  n≈24では検出力が低いことを明記し、効果方向と大きさを主に読む。
- 交絡への態度: descriptorがstep・占有体積と強く相関することは前提。
  問うのは**残差への追加説明力**のみ。

### 9.5 計算量と再利用

- 1 snapshotあたり: 類数(~10-20)× 姿勢(≤6)× ベクトル化列挙。
  実測オーダーで1〜5秒/snapshot、24 snapshotで数分。
- 競合グラフ: ノード \(\le \sum_c \min(N_c,M)\)(数百)、辺判定は
  AABBペアのベクトル化で \(O(n^2)\) 許容。
- 再利用: `ContainerGeometry` / `Geometry` / 搬送モデル /
  `iter_cartesian_attempts` / `unique_orientations`(agent本体)、
  state snapshot(observationにpoints/n_vecs込み)、
  `build_task_b_config`(残余荷物の復元)。シミュレータ不要(解析のみ)。
- 段階B: replay行の `x_plus`(settle後pose)をpackedへ追加した観測に
  同じ関数を適用するだけで、追加物理は不要。

### 9.6 非目標(この提案の範囲)

- Rankerやshadow scoreへの \(\mu R_{\mathrm{future}}\) 追加(段階Bの
  同一snapshot内候補間差の検証が通るまで行わない)。
- 厳密な大域対称群・軌道分解(この容器では自明群に退化する。§9は
  互換クラス・競合グラフ・同時配置可能数による近似定式化)。
- 学習モデル化(まず解析descriptorの追加説明力を確認する)。
