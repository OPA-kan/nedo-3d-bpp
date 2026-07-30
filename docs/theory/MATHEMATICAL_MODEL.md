# 数学モデルの根幹

## 0. 原問題

荷物全体を

\[
E=\{1,\ldots,n\}
\]

とする。最初の問いは、荷物の部分集合が直方体などの局所図形を構成できるとき、

\[
\boxed{
\text{どの候補部分集合族を作り、その中から何を選べば、最終目的関数が最大になるか}
}
\]

である。

この問いは、次の二層に分ける必要がある。

1. 実現可能な局所構造の候補族をどう生成するか
2. 与えられた候補族上で、競合しない候補をどう選択・配置するか

## 1. ブロック族と資源競合

同じ荷物集合でも異なる外形や内部配置を作れるため、基本対象は集合だけではない。最小形は

\[
b=(S_b,d_b)
\]

である。

- \(S_b\subseteq E\): 使用する荷物ID集合
- \(d_b\): 実現する外形

全実現可能ブロック族を \(\mathcal B^*\) とする。荷物IDは有限資源なので、外形だけへの商

\[
(S_b,d_b)\mapsto d_b
\]

は一般に不可能である。

選択変数 \(x_b\in\{0,1\}\) に対して、

\[
\sum_{b:i\in S_b}x_b\le1
\qquad(\forall i\in E)
\]

が必要になる。これは荷物を頂点、ブロックを超辺とするハイパーグラフ

\[
\mathcal H=(E,\mathcal B)
\]

上の集合パッキング制約である。

概念的なブロック選択問題は

\[
\max_x \sum_{b\in\mathcal B}w_bx_b
\]

subject to

\[
\sum_{b:i\in S_b}x_b\le1,
\qquad
\operatorname{Packable}(\{d_b:x_b=1\})=1.
\]

ただし実装では \(\mathcal B^*\) を列挙せず、現在状態から生成する

\[
\mathcal B_{\mathrm{local}}(s)\subsetneq\mathcal B^*
\]

だけを使う。

候補族そのものの設計は、計算予算 \(C\) の下で

\[
\mathcal B'^{*}
=
\arg\max_{\substack{\mathcal B'\subseteq\mathcal B^*\\
\operatorname{Cost}(\mathcal B')\le C}}
\left[
\max_{X\in\mathcal I(\mathcal B')}J(X)
\right]
\]

という上位問題として書ける。\(\mathcal I(\mathcal B')\) は資源競合、幾何、支持、搬入制約を満たす選択族である。

## 2. 完全ブロックとソフトブロック

内部充填率を

\[
\eta_b=
\frac{\sum_{i\in S_b}v_i}
{\operatorname{vol}(d_b)}
\]

とする。

- \(\eta_b=1\): 完全ブロック
- \(\eta_b\ge\tau\): 高密度なソフトブロック

完全充填は内部状態を捨てやすくする十分条件だが、状態圧縮の必要条件ではない。後から到達不能な閉空洞は将来の配置可能性に影響しないため、ソフトブロックでも圧縮できる。

## 3. 状態、行動、原始遷移

時刻 \(t\) の状態を

\[
s_t=(P_t,U_t)
\]

とする。

- \(P_t\): settle後の実姿勢を含む配置済み状態
- \(U_t\): 未配置荷物

単品行動は

\[
a=(i,k,p,o)
\]

で、荷物、コンテナ、位置、姿勢を指定する。原始状態遷移系は

\[
\mathcal M=(\mathcal S,\mathcal A,T,R)
\]

である。

\(T\) には内包判定、棚・荷物との非交差、Y→X搬入掃引、8 cm落下開始、物理settle、観測クォータニオンからの実AABB再構成を含める。

実装のcandidate generatorが返す生の集合には物理的な偽陽性も含み得る。
そのうち共通物理検証を通った集合を
\(\widehat{\mathcal A}_{\mathrm{phys}}(s,i)\) とすると、候補ゼロから直ちに
\(\mathcal A(s,i)=\varnothing\)とは結論できない。anchor生成、支持面表現、
release生成、搬入近似による偽陰性をoracleで分離し、

\[
\widehat{\mathcal A}_{\mathrm{phys}}(s,i)
\subseteq
\mathcal A(s,i)
\]

のrecallを測る必要がある。

## 4. 逐次実行可能性付きブロック

重力と一方向搬入があるため、同じ \(S_b\) でも内部順序によって実現可能性が変わる。現在の基本対象は

\[
\boxed{
b=(S_b,\pi_b,\rho_b,d_b,\sigma_b)
}
\]

である。

- \(\pi_b=(i_1,\ldots,i_k)\): 実行可能な内部順序
- \(\rho_b\): アンカーから見た相対配置・姿勢
- \(\sigma_b\): 完成後の外部署名

探索上は

\[
s\xRightarrow{b}s'
\]

というマクロだが、実行時には

\[
s=s_0\xrightarrow{a_1}s_1
\xrightarrow{a_2}\cdots
\xrightarrow{a_k}s_k=s'
\]

と共通配置コアで逐次再生する。

同じ完成構造に複数の実行可能順序がある場合、

\[
\Pi_b=\{\pi_b^{(1)},\ldots,\pi_b^{(q)}\},
\qquad
k!\longrightarrow q,\quad q\ll k!
\]

として保持する。

## 5. Open-loopテンプレートからClosed-loop Optionへ

固定列

\[
\pi_b=[(i_1,p_1,o_1),\ldots,(i_k,p_k,o_k)]
\]

は、settleによる位置・姿勢ずれへ適応できない。最終形はOption

\[
o=(I_o,\pi_o,\beta_o)
\]

として扱う。

- \(I_o\): 開始可能状態
- \(\pi_o(h_j)\): 観測履歴に応じた内部方策
- \(\beta_o\): 成功・失敗を含む終了条件

例えば、

\[
a_1=\pi_o(s_0),\qquad
s_1=T(s_0,a_1),\qquad
a_2=\pi_o(s_1)
\]

とし、1個目のsettle後中心、クォータニオン、実AABB、支持状態、搬入可能領域を観測して2個目を再計画する。

Option失敗時は、成功済みの途中状態を保持してprimitive actionへ戻す。

固定fallback \([0,0,0.25]\) は観測状態から再計画されないopen-loop actionであり、
Closed-loop Optionの代替ではない。Case 000ではitem 27の候補ゼロ後にこのfallbackが
衝突して終了した。fallbackは診断用の最終安全網として区別し、実行可能なincumbent
または観測後に再生成したactionがない限り、継続可能性を保証しない。

## 6. 未来から見た状態同値と署名

\[
\operatorname{Cont}(p)=\operatorname{Cont}(q)
\]

は継続言語の同値性であり、厳密なbisimulationそのものではない。

価値を保存する厳密な状態集約には、任意の次荷物 \(i\) と行動 \(a\) に対して、

\[
\mathcal A(p,i)=\mathcal A(q,i),
\]

\[
r(p,i,a)=r(q,i,a),
\]

\[
\sigma(T(p,i,a))=\sigma(T(q,i,a))
\]

が必要になる。厳密判定は困難なので、実装では

\[
p\approx q
\iff
\hat\sigma(p)\approx\hat\sigma(q)
\]

という近似を使う。

署名は段階的に

\[
\sigma_0=(d),
\quad
\sigma_1=(d,\eta),
\quad
\sigma_2=(d,\eta,H),
\quad
\sigma_3=(d,\eta,H,P),
\quad
\sigma_4=(d,\eta,H,P,C)
\]

と拡張する。

- \(H\): 上面高さプロファイル
- \(P\): 支持可能領域・耐荷重
- \(C\): 外部から到達可能な空隙

署名間の差は、保証付きbisimulation metricではなく、`state similarity score`または`behavioral discrepancy surrogate`としてbeam重複除去、多様性維持、value cacheに限定して使う。

Mode Bでは幾何署名が近くても、可視pool内のどの荷物を救っているかが異なれば、
未来は同値ではない。そこで荷物別可行性署名

\[
\chi_V(s)
=
\left(
\mathbf 1[\mathcal A(s,i)\ne\varnothing]
\right)_{i\in V}
\]

を導入し、

\[
\boxed{
\sigma_B(s,V)
=
\left(
\sigma_{\mathrm{geom}}(s),
\chi_V(s)
\right)
}
\]

とする。異なるpool間を比較するときは荷物indexまたは属性classで成分を対応付ける。
可行荷物数

\[
G(s,V)=\sum_{i\in V}\chi_V(s)_i
\]

はこの署名の粗い集約値として残すが、同じ \(G\) でも救っている荷物が違う状態を
同一視しない。これはMode Bのbeam多様性とvalue cacheへ追加するProposed拡張である。

## 7. 順序圧縮: 静的独立条件とDPOR

状態依存独立関係を

\[
I_s\subseteq\mathcal A\times\mathcal A
\]

とする。行動 \(a,b\) を交換してよいのは、少なくとも

\[
T(T(s,a),b)\approx T(T(s,b),a)
\]

というダイヤモンド条件を満たす場合である。

実装では次を独立性の安全な十分条件として使う。

\[
\operatorname{Sweep}_s(a)\cap\operatorname{Sweep}_s(b)=\varnothing,
\]

\[
\operatorname{SupportDep}_s(a,b)=0,
\]

\[
\operatorname{ContactNeighborhood}_s(a)
\cap
\operatorname{ContactNeighborhood}_s(b)=\varnothing.
\]

固定DAGだけではsettle後に発生する依存を捉えられないため、

\[
\boxed{
\text{静的独立証明による事前削減}
+
\text{干渉観測時の動的backtracking}
}
\]

という簡易DPORを使う。

## 8. LP緩和、双対価格、候補生成

ブロック集合パッキングの完全なLP緩和値は、逐次実行可能性や幾何干渉を無視するため実問題の安全な上界になる。

\[
V^*(s)\le U_{\mathrm{LP}}(s)
\]

一方、制限付き候補族 \(\widehat{\mathcal B}(s)\) のみを使ったRMP値は、未生成列を含まないため安全な上界とは限らない。

双対変数 \(y_i\) から

\[
\operatorname{rc}(b)
=
w_b-\sum_{i\in S_b}y_i
\]

を計算し、有望ブロックのpricing・ランキングに使う。potential-based reward shapingには使わない。

## 9. Task1

Task1では全荷物が既知で、出力は順列

\[
\pi=(\pi_1,\ldots,\pi_n)
\]

である。共通配置コアによる再生結果を \(F(\pi)\) とすると、

\[
\pi^*
=
\arg\max_{\pi\in\mathfrak S_n}
J_{\mathrm{lex}}(F(\pi)).
\]

現在の辞書式目的は

\[
J_{\mathrm{lex}}=(N,V,S,-\bar z)
\]

と整理する。充填率 \(\eta=V/V_C\) は固定コンテナ容量では \(V\) と同値なので、独立キーとしては不要である。

探索行動は

\[
\mathcal A(s)
=
\mathcal A_{\mathrm{single}}(s)
\cup
\mathcal B_K(s)
\]

で、swap、Or-opt、部分列マクロを併用する。

安全な個数上界の一例は

\[
N_{\max}(s)
=
N_{\mathrm{placed}}(s)+k_{\mathrm{vol}}(s)
\]

\[
k_{\mathrm{vol}}(s)
=
\max\left\{
k:
\sum_{j=1}^{k}v_{(j)}
\le V_{\mathrm{remain}}(s)
\right\},
\]

ここで \(v_{(j)}\) は未配置荷物を体積昇順に並べたもの。

## 10. Task2

Task2では到着順が未知である。到着荷物が外から一意に与えられるMode C型では、
最適化対象は方策

\[
\mu:(s_t,i_t)\mapsto a_t
\]

でよい。しかしMode Bでは、可視pool \(V_t\) から荷物自体も選ぶため、行動を

\[
a_t=(i_t,p_t),\qquad i_t\in V_t
\]

とし、方策と価値を

\[
\boxed{
\mu_B:(s_t,V_t)\mapsto(i_t,p_t)
}
\]

\[
\boxed{
V_B(s,V)
}
\]

へ拡張する必要がある。遷移は物理状態だけでなく、選択荷物の除去と新規荷物の
補充によるpool更新も含む。

\[
\mu^*
=
\arg\max_\mu
\mathbb E_\mu
\left[
\sum_{t=0}^{T-1}r(s_t,V_t,i_t,p_t)
+\Phi(s_T,V_T)
\right].
\]

候補評価は概念的に

\[
Q_B(s,V,i,p)
=
r(s,V,i,p)
+\gamma\hat V_B(T(s,i,p),V')
\]

とする。

2026-07-29のTask B proxy実験では、Case 001のitem 0が19step可視で、
15stepに可行候補を持ち、step 14でimmediate top-Kへ入ったにもかかわらず
選ばれず、step 18で候補ゼロになった。これは

\[
\text{置ける間に選ばない}
\longrightarrow
\text{後で不可行になる}
\]

という荷物選択と配置の結合starvationが実在することを示すObserved evidenceである。
したがって即時scoreや可行荷物数だけでなく、荷物別の可行性寿命、待ち時間、
選択しない場合の後悔を候補多様性へ入れる必要がある。

未到着荷物を含むブロックは直接行動にできないため、Task2では

\[
\psi(s)=
(
\text{平坦面},
\text{直方体凹部},
\text{寸法適合性},
\text{支持余力},
\text{搬入可能性}
)
\]

を価値特徴として使う。仮想未来rollout内ではTask1型マクロを再利用できる。

## 11. 五つの圧縮

現在の理論は次の役割分担に整理できる。

| 理論・手法 | 圧縮または役割 |
|---|---|
| EP/EMS | 連続座標候補の圧縮 |
| Closed-loop Options | 時間・探索深さの圧縮 |
| DPOR | 実行順序の圧縮 |
| 署名similarity | 近似状態圧縮 |
| 限定的SMDP準同型 | 証明可能な厳密状態・行動圧縮 |
| LP双対・reduced cost | 候補生成と上界評価 |

核心は、

\[
\boxed{
\text{物理的な逐次実行可能性と将来価値をできるだけ保存しながら、
内部自由度をどこまで捨てられるか}
}
\]

という状態・行動空間設計である。

EP/EMSや支持面anchorによる候補圧縮には、

\[
\boxed{
\text{列挙削減率}
\quad\text{vs.}\quad
\text{物理的candidate recall}
}
\]

のトレードオフがある。anchor recall oracleは、圧縮後の候補集合が無制限列挙の
物理的有効解をどれだけ保持するかを測る。候補ゼロをdead endと判断する前に、
真の \(\mathcal A(s,i)=\varnothing\) とgenerator recall不足を分離する。

## 12. 実装優先順位

### 共通配置・圧縮

1. settle観測へ適応するClosed-loop Option
2. 静的独立証明と小規模DPOR
3. 署名similarityによるbeam管理
4. reduced costによるオンデマンド候補生成
5. 同一タイプ置換など限定的SMDP準同型
6. potential shapingは安全性が整理できるまで保留

### Task2 / Mode B専用

1. candidate recallをfailure stepで計測する
2. class-awareなpriority-ordered探索でdeadline coverageを維持する
3. item lifecycle / starvationを荷物別に記録する
4. \(\chi_V(s)\) によるpool-feasibility署名を導入する
5. regret-aware diversityで可行性寿命の異なる候補をbeamへ残す
6. 解析proxyに勝つことを確認してからpool-aware valueを学習する

1〜3はImplementedである。class-aware探索は各present classから最低1荷物をcapへ
含め、各included itemの先頭unitを先に一巡するが、配置rankingは変更しない。
4〜6はProposedである。Case 000のようなpool 1の
候補ゼロは共通配置・圧縮側、Case 001のような後回し不可行化はMode B側で扱う。

