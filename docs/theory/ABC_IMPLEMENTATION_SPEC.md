# NEDO 課題A/B/C 実装spec

**Status:** Proposed architecture / diagnostics and release risk gate implemented

**Scope:** 配布シミュレータ上の候補生成、選択、計測。非公開の最終score重みは含まない。

## 1. 設計原則

1. A/B/Cは同じ厳密配置コアを使う。
2. heightmapなどの格子表現は高速フィルタと特徴量であり、完全状態ではない。
3. hard制約はaction形式、包含、搬入、物理settleなどの実行可能性に限定する。
4. soft/priority、残余、重心、表面は公式重みが不明な間は辞書式またはtie-breakに使う。
5. onlineは最初に可行incumbentを確保し、内部締切まで改善する。
6. 診断では直接測定値とproxyを分離し、単一の擬似総合scoreへ混ぜない。
7. releaseの指令位置・姿勢とsettle後の実現位置・姿勢を分離し、その差を
   物理failureとして測る。

## 2. 共通状態

厳密状態は、settle後の位置・クォータニオン・実AABB、コンテナ平面、棚、
支持面、Y→X搬入、荷物属性、可視poolを含む。

高速表現として次を派生させる。

| 表現 | 用途 | 保証 |
|---|---|---|
| `H[x,y]` | 上面・支持候補・表面粗さ | AABB/格子近似 |
| `Z[x,y]` | 天井・切欠き・棚の静的上限 | 静的幾何 |
| `F[x,z]` | Y方向の前方遮蔽 | Y区間だけの必要条件 |
| `T[x,y]` | 最上面の属性 | soft/priority proxy |
| packed item list | 厳密配置コア | settle観測が正本 |

`F`だけでY→Xの全搬入経路を保証しない。最終候補は必ず共通配置コアの
包含・二段搬入・支持判定を通す。

## 3. 候補空間

`z`は支持面から導出できるが、`y`は一般には消せない。priorityの扉側配置、
支持面整合、切欠き後のX移動、将来空間保存があるためである。

\[
p=(container,x\text{-anchor},y\text{-anchor},orientation,support)
\]

壁、棚、既配置AABB面、extreme point、EMS境界をanchorにする。2 cm格子は
表面・遮蔽特徴には使えるが、15 mm搬入余白より粗いため唯一の候補生成器にしない。

## 4. 搬入とsettle

配布validatorの実行順序を契約とする。

1. 目標座標で包含判定
2. 通常は目標より最大8 cm上でY方向へ移動
3. その後X方向へ移動
4. 床・棚から5 cm以内の直置きでは持上げ量を0にする
5. 天井が近ければ持上げ量を縮める
6. 目標座標へ置き、物理settleする

したがって、常時8 cmのheadroomや鉛直カラム全体の空きをhard制約にしない。

## 5. hard層とranking層

hard層はaction形式、LD3包含、Y→X搬入、最低限の支持・settle安全性へ限定する。
支持率は公式の直接判定ではなく、現行55%はsettle失敗を減らす保守proxyである。

候補比較は概念的に次の順とする。

\[
K(p)=(
\text{physical feasible},
\text{next-pool feasible count},
\text{placed count/volume},
-\text{rule penalty},
\text{residual proxies},
-\text{CoG height},
-\text{surface roughness}
)
\]

soft/priority、残余、重心、表面の公式重みが不明な間は、それらを絶対hard制約へ
格上げしない。

release risk gateは通常rankingとは独立した実験層とする。初版は
`off` / `shadow` / `enforce` を切り替え、support、CoM margin、overhang、
drop、support imbalance、initial poseの固定閾値だけを使う。
`shadow`は棄却予定と特徴を記録するが候補を残し、`enforce`だけがranking前に
危険候補を除外する。gate通過候補のscore式は全モードで同じにする。
オンライン特徴の由来はcommand state / predicted contact stateへ明示的に分け、
settle telemetryはoffline評価時だけ結合する。traceではstatic候補数、gate通過数、
gate棄却数、全棄却、protocol fallbackを別々に数える。

候補が尽きた場合の内部結果は `no_safe_action` とする。共通の状態依存fallback
生成器 \(F(s,i,d)\) はProposedであり、未実装の間に外部APIへ返す固定座標または
random actionは `unsafe_protocol_fallback` として診断する。これを安全な
Task C fallbackや検証済みincumbentと同一視しない。

## 6. 課題C

pool 1では未来荷物が見えないため、共通配置コアによる頑健な貪欲を使う。

1. anchor候補を生成
2. hard層で削減
3. 即時配置数・体積を優先
4. 未知未来に対する残余proxyをtie-break
5. 重心・表面を追加tie-break

この方策を全課題のfallbackにする。

## 7. 課題A

offlineでは順序だけでなく内部配置計画を作成し、同一agent instanceに保持する。
戻り値は競技契約どおり順序index列とする。

onlineでは計画座標を現在のsettle状態で再検証し、有効なら実行、無効なら課題Cへ
fallbackする。計画座標はhintであり、固定open-loop命令ではない。

offlineがtimeoutするとagent processが再起動され内部計画も失われるため、必ず
制限前に返す。完全計画探索は1 dry-runの実測速度を確認してから追加する。

## 8. 課題B

可視pool \(V\) の各荷物について、

\[
f_i(s)=\mathbf 1[\mathcal A(s,i)\ne\varnothing]
\]

を第一の残余proxyとする。候補点の生個数はgrid密度へ依存するためhard価値にしない。
必要なら重複anchorを正規化した受入余裕へ拡張する。

\(f_i=0\)でも、別荷物の配置が新しい支持面を作り、後で可行になる場合がある。
したがって「詰み確定」ではなく緊急信号として扱う。
さらに \(f_i\) とオンライン候補生成は同じ配置コアを共有するため、両者の候補なしは
独立した観測ではない。固定fallbackが成功するなど偽陰性の証拠がある間は、
「proxyが保守的」と結論せず、共有する可行性判定を先に診断する。

現在行動 \(a\) の後は、

\[
G(s^a,V\setminus\{i\})=
\sum_{j\ne i}f_j(s^a)
\]

を測り、即時dead-endを避ける。体積条件や前方遮蔽量は、証明済み上界になるまで
hardフィルタにしない。2コンテナの充填率差そのものにもペナルティを置かない。

## 9. action後の診断指標

### PyBulletから直接測る値

| 指標 | 定義 |
|---|---|
| `placed_count` | settle後に登録された累積荷物数 |
| `placed_volume` | 登録荷物の体積和 |
| `fill_percent_proxy` | 体積和 / 配布container有効体積 |
| `center_of_mass_z` | 質量加重したsettle後中心z |
| `remaining_volume_ratio` | 未使用体積比 |

### 明示的なproxy

| 指標 | 定義・限界 |
|---|---|
| `surface_total_variation` | settle後AABBから作る2 cm heightmapの隣接差平均 |
| `surface_height_std` | 同heightmapの高さ標準偏差 |
| `flat_support_edge_ratio` | 隣接高さ差1 cm以下のedge比率 |
| `predicted_feasible_remaining_ratio` | 選択を仮想適用後、評価した可視pool荷物のうち共通配置コアで可行な割合 |
| `candidate_diagnostics` | 候補試行・受理数と、containment/headroom/static/support/corridor別の棄却数 |
| `depth_occupancy_profile` | 扉側 \(y<0\) から奥側 \(y>0\) まで16分割したAABB体積占有proxy |
| `occupied_depth_center_normalized` | 体積加重した配置中心。-1が扉側、+1が奥側 |
| `front_depth_occupancy_mean` / `back_depth_occupancy_mean` | 深さprofile前半/後半の平均 |

表面指標はAABB・格子近似で、接触力や動的安定性そのものではない。可行率も
仮想settle近似であり、次のPyBullet状態を保証しない。深さprofileもLD3断面形状や
棚体積を厳密に差し引かないため、front-blockingの診断proxyとしてのみ使う。

## 10. 実験順序

1. fallbackを変更せず、最初の物理FAIL actionと直前までの指標列を取得
2. 候補棄却理由と深さprofileから共有可行性判定の偽陰性を特定
3. 最小修正後、素の配置器が比較可能な配置数へ届くことを確認
4. 3方式のaction列と可行率を比較
5. 物理valid/safeを通す
6. proxyが将来の配置数・fillを予測するか相関を見る
7. 効果が確認できたproxyだけrankingへ昇格
8. 完全な訓練scoreが得られた後にCEMや学習価値を検討

初回risk gateアブレーションはcoverage方策を固定し、pool 10/20/40、
`off` / `shadow` / `enforce`、各3反復を同時に取る。`off`と`shadow`は
action command列のSHA-256を比較し、一件でも不一致ならhard gate評価へ進まない。
placed count、fill、gate通過率、全棄却、protocol fallback、gate通過releaseの
物理failure、shadowで棄却予定だったが物理的に安全だった選択候補を集計する。

物理FAIL中のfillは診断値であり、コンペscore改善の根拠にはしない。
