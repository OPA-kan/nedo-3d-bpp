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
各荷物について少なくとも一つ可行配置があるかを調べ、

\[
G(s,V)=
\sum_{i\in V}
\mathbf 1[\mathcal A(s,i)\ne\varnothing]
\]

を離散proxyとして使う。候補点数は数えないため、同一荷物に多数の候補があることを
重複評価しない。

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
4. 連続または格子近似の可行アンカー面積
5. 未知荷物分布に対する期待可行面積
6. sibling rankingによる学習値

最低限、配置個数、体積、物理valid/safe、policy時間、次手dead-end回避数、
pool可行荷物数を比較する。

物理validationが壊れた状態から生成した仮想遷移は教師にも評価にも使えない。
現在のPyBullet不具合を修正するまでは、1～3を単体・代理状態で検証し、成績改善を
主張しない。

## 8. 非目標

- 残余空間やheightmapだけを完全状態とみなさない。
- 分位点フィルタをhard feasibility保証とは呼ばない。
- lookahead自体を新規性として主張しない。
- マクロ、Option、DPORを本理論で置き換えない。
- Gated Iotaを価値学習へ持ち込まない。
