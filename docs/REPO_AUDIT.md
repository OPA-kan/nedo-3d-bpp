# リポジトリ内部監査 — 2026-08-06

対象は**成果物ではなく整理**である。「何が正しいか」ではなく「次に来た者が
何を正本だと信じるか」を見た。実測はすべて `claude/l3-l4-allocation-ordering`
の tip（`e61ac01`）で取っている。

修正済みのものは §で「修正済み」と書く。修正していないものは**なぜ独断で
やらなかったか**を書く。

---

## A. 正本 branch が分裂している — 未修正・最優先

`AGENTS.md` Step 0 は新規 clone をこう誘導する。

```
git switch --track origin/experiment/anchor-recall-oracle
```

そして「`main` は正本ではない、live trunk は `experiment/anchor-recall-oracle`」
と明記している。**その記述は 2026-08-04 時点で古い。**

| branch | tip | `agent/agent.py` | HEAD から見て | `ANCHOR_TRUE_ENVELOPE` |
|---|---|---:|---|---:|
| `main` | 2026-07-31 | 1,867 行 | 417 遅れ / 2 進み | 0 箇所 |
| `experiment/anchor-recall-oracle`（宣言上の trunk） | 2026-08-04 | 7,160 行 | 130 遅れ | **0 箇所** |
| `claude/l3-l4-allocation-ordering`（実際の作業先） | 2026-08-06 | 7,847 行 | — | 5 箇所 |

`ANCHOR_TRUE_ENVELOPE` は**公式最高スコア 35.375 を出した提出**
（`submissiontrueenvelope`, `docs/OFFICIAL_SCORE_LOG.md`）の実装である。
`docs/BLOCKED_WORK.md` §0 の較正も、`reports/task-c/true-envelope/` の判定も、
`context/optimizer_fingerprint.json` の `behaviour_sha256 = a92092c2` も、
すべてこの実装を前提にしている。

**したがって `AGENTS.md` の手順どおりに clone した者は、最高スコアの agent が
存在しない木の上で作業を始める。** これは仮説ではなく、`AGENTS.md` 自身が
「実際にその事故が起きている」と書いている事故の、次の版である。

**独断で直さなかった理由:** trunk をどれにするかは merge 方針の決定であり、
`experiment/anchor-recall-oracle` へ 130 コミットを流すか、`claude/l3-l4-*`
を trunk と宣言するかで、他の 12 本の branch の扱いが変わる。監査係が黙って
選ぶ範囲を超える。**判断が要る唯一の項目がこれである。**

---

## B. 撤回されたレポートに撤回の印が無かった — 修正済み

`reports/hazard/dominated-choices.md` は「17 手中 10 手で厳密に優越する代替が
あった」と書いており、その全数値は隣のファイル
`dominated-choices-retracted.md` で撤回されている。**撤回側を先に開かない限り
気付けなかった。** 撤回済みの主張が知見として読める状態は、文書の不備では
なく正確性の欠陥である。

- 冒頭に撤回 banner を追加（何がなぜ誤りか、どこを読むか）。
- `reports/INDEX.md` を新設。**手書きではなく生成物**である
  （`scripts/index_reports.py`）。状態は `context/evidence.json` から導出する:
  active な主張が1件でも紐付けば `active`、全て superseded なら
  `superseded`、1件も紐付かないなら `uncited`。台帳を追記したら再生成する。

手書きの索引にしなかったのは、このリポジトリが既に**維持されている索引1つに
つき古い索引1つ**を抱えているからである（§A がその一例）。

`uncited` を「古い」と読ませない注記を索引本文に入れてある。生出力である・
台帳より前に書かれた・撤回されたまま置き換えられていない、の3つを索引は
区別できない。

---

## C. 証拠台帳が2日遅れていた — 修正済み

監査開始時点で `context/evidence.json` は 148 件、最新が `2026-08-04`。その
間に**8つの反証・5つの撤回・8つの計測器不具合の修正**が起きていて、1行も
書かれていなかった。遅れた台帳は「同じ実験を二度やる」ことを止められない。

12 件追記して 160 件（active 133 / superseded 26 / historical 1）。
`afterstate-features-are-one-axis-fullness` は**編集ではなく supersede** した
— 観測は実在し、読み方だけが誤っていたので、本文を残して前を向かせる。

---

## D. 192 MB のトレースは clone コストではなかった — 私の初期見積りの訂正

監査の第一稿は「229 MB のリポジトリの 84% が `policy-trace.jsonl`」と書いて、
削除を提案しかけた。**測ったら間違いだった。**

```
追跡ファイル合計          226.1 MB / 1,204 ファイル
  reports/               223.0 MB / 1,000
  それ以外（コード・文書・テスト）  3.1 MB /   204
policy-trace.jsonl       191.6 MB /    92

.git/objects/pack          7.8 MB      ← clone が運ぶ実体
.git 全体                   21 MB
```

JSONL は反復が激しく、pack 後は 7.8 MB に落ちる。**clone 帯域の問題は最初から
存在しない。** 実コストは checkout 後のディスク 223 MB だけで、これは
`.gitignore` が「大容量・派生物は Drive に置く」と書いている方針
（`docs/DRIVE_SOURCES.md`、25 MB の CSV を対象外にしている）と形式上は
矛盾するが、**その方針が想定した害は発生していない。**

そして削除できない実質的理由がある: これらは死んだログではなく**入力データ**
である。

| ディレクトリ | 読む側 |
|---|---|
| `reports/board-receptivity/` (102.7 MB) | `scripts/fit_hazard_model.py` |
| `reports/first-pass-depth/` (50.8 MB) | `scripts/analyze_first_pass_depth.py` |
| `reports/stability-tradeoff/` (37.0 MB) | `scripts/analyze_stability_tradeoff.py` |

後者2つは既定引数がこのパスを指している。消せば、再生成に物理シミュレータの
長時間実行が要る解析が、fresh checkout で動かなくなる。

**結論: 触らない。** 本当の問題は容量ではなく**索引の不在**で、それは §B で
直した。`reports/INDEX.md` の「生の計測出力」節がこの3ディレクトリを
「人ではなく解析器が読むもの」として明示する。

---

## E. 公開済み判定の数値が、退役した床規則で書かれていた — 修正済み

`scripts/summarize_ablation.py` の対照規則は会期中に修正されている（旧:
`base_null` を基準に `|base − base_null|` を床とする → 新: `base` と
`base_null` を**プール**して中心と幅を取る）。旧規則は同じ2観測を二重に
使うので、`item_cap16` が同じ挙動のまま一度は `+6.000 CLEARS`、次は
`−5.000 within` と出た。

**修正はコードにだけ入り、既に公開されていた2本のレポートは旧規則の数字の
まま残っていた。** 再生成して差し替えた。

- `reports/stowage/zone-order-verdict.md`
- `reports/stowage/attr-guard-verdict.md`

**判定の向きと CLEARS/within の印は、1箇所を除いて全て不変。** 例外は
zone-order の `dual-shelf-mixed` の `fill` で、旧規則では「床を越えた」と
書いていたが、プール規則では **within** である。過大主張1件を撤回した。
両レポートに改訂 note と再生成コマンドを入れてある。

---

## F. 公開済みの結果がリポジトリから再現できなかった — 修正済み

2件、原因は別々。

**F-1. 要約器が読めないレイアウト。** `summarize_ablation.py` は
`**/rows.jsonl` しか glob していなかった。`run_queue.py` はその形で書くが、
直列アドホック実行は `<scenario>-<arm>-r<n>.jsonl` を平置きする。**コミット
されている生データは後者**なので、レポートに印刷されている再生成コマンドは
空の表を返していた。両方読むようにした。

**F-2. 生データがそもそもリポジトリに無かった。** 台帳エントリ
`local-proxies-have-validated-directions`（§G で述べる較正）の根拠 48 本の
`rows.jsonl` は、コンテナが回収すれば消える scratchpad にしか存在しなかった。
388 KB しかないので `reports/stowage/calibration/` に取り込み、再実行して
公開済み JSON と**完全一致**することを確認した。散文が無かったので
`reports/stowage/proxy-calibration.md` を起こした。

同じ場所にもう一つ、arm の**許可リストがハードコード**されている欠陥があった。
知らない arm は**エラーにならず表から消える**ので、「実験が走らなかった」と
読める。arm はデータから読むようにし、ソースに名前を残すのは対照2つだけに
した。

---

## G. `BLOCKED_WORK.md` §0 は部分的に外れた — 更新済み

§0 は「4成分がローカルに存在しないことが、すべての採否判断を止めている
根本原因」と書き、外し方を「未実施」としていた。**実施した。** 逆を向いた
代理は7つ中1つも無い。§0 は「根本原因」から「**方向は既知・交換レートは
未知**」へ降格する。詳細は `reports/stowage/proxy-calibration.md`。

残る制約は正直に書いてある: 3点は方向を反証できるが重みを当てはめられない
ので、`placed` を落として `priority_covered_by_other` を稼ぐような**成分間の
取引は依然として決着不能**である。

---

## H. どこからも参照されていないスクリプト11本 — 削除せず、記録した

70 本中 11 本が、自分以外のどの追跡ファイルからも名前を参照されていない。

```
2026-07-31  analyze_loss_structure.py        公式 safe 判定 × 回転量
2026-08-05  generate_selfplay.py             物理無し afterstate の自己対戦生成
2026-08-05  make_stowage_page.py             断面ページの入口（パスが固定・要修正）
2026-08-05  measure_corridor_shadow.py       搬入経路が潰す空間
2026-08-05  measure_lambda_needed.py         致命手を覆すリスク重み
2026-08-05  measure_packing_gaps.py          荷物間の横隙間 × 強制クリアランス
2026-08-05  measure_zone_order.py            ゾーン順序（設計ごと破棄）
2026-08-05  probe_fatal_step.py              終端手に安全な代替はあったか
2026-08-05  probe_supply_trace.py            律速は空間か供給か
2026-08-05  probe_terminal_slots.py          終端盤面に何が残っているか
2026-08-05  probe_undershelf_ordering.py     棚下は now-or-never か
```

**消していない。** 中身を読むと、どれも docstring に問い・手法・失敗した先行版
までを書いた計測器で、雑ではない。消せば同じものが書き直される — 会期中に
実際に3回起きている（`measure_zone_order.py` は充填器を3回書き直して3回とも
別のものを測り、設計ごと捨てた、と自分で書いている）。参照されていないのは
**索引が無いからで、価値が無いからではない。**

`make_stowage_page.py` だけは実害があったので直した。入力 JSON のパスを
`scripts/packing-*.json` に固定していて、そこに dump は書かれない —
**公開済みの断面図は、作った本人を含め誰にも再描画できなかった。** 引数化し、
存在しないパスは exit 1 にした。dump 3本（68 KB）はやはり scratchpad にしか
無かったので `reports/stowage/dumps/` に保全し、再生成が公開版とバイト単位で
同じ 384,881 B になることを確認した。再生成手順は
`reports/stowage/section-audit.md` 末尾。

---

## I. `coverage_report.py` の4警報 — 未変化

```
rollout:        ノブ5・登録された問い0     — 仮説なき計装
physics:        ノブ3・登録された問い0     — 同上
state_shaping:  問い1・ノブ0              — この軸の仮説は構造的に検証不能
state_shaping:  active な知見5・ノブ0     — 観測のみ。「出荷待ち」と読むな
```

会期中に1件も動いていない。`state_shaping` の2件は
`docs/BLOCKED_WORK.md` §2 の `graded-state-value-helps` と同根で、**推定器が
存在しない**ことが障害である。会期中の3つの試み（Φ / MC rollout /
ハザードモデル）はすべて否定または限定付きに終わり、最後のものは
`reports/hazard/step-confound.md` で**特徴が盤面の充填度ではなく手数を
測っていた**ことが示された。

---

## この監査で変えたファイル

| ファイル | 変更 |
|---|---|
| `context/evidence.json` | 12件追記（148→160）、1件を supersede |
| `reports/INDEX.md` | **新規・生成物** |
| `scripts/index_reports.py` | **新規**。台帳から索引を導出する |
| `reports/hazard/dominated-choices.md` | 撤回 banner |
| `reports/stowage/zone-order-verdict.md` | 数値をプール規則で再生成、過大主張1件を撤回 |
| `reports/stowage/attr-guard-verdict.md` | 同上（印は不変） |
| `reports/stowage/proxy-calibration.md` | **新規**。JSON しか無かった結果に散文を付けた |
| `reports/stowage/calibration/` | **新規・388 KB**。消える場所にあった生データを保全 |
| `scripts/summarize_ablation.py` | 両レイアウトを読む／arm 許可リスト撤廃／末尾の説明が実装と食い違っていたのを修正 |
| `scripts/make_stowage_page.py` | 固定パスを引数化。実行できない入口だった |
| `reports/stowage/dumps/` | **新規・68 KB**。断面図の入力を保全 |
| `reports/stowage/section-audit.md` | 再生成手順を追記 |
| `docs/BLOCKED_WORK.md` | §0 を「実施済み・降格」へ更新 |

**agent の挙動は1バイトも変えていない。** `behaviour_sha256` は
`a92092c2…` のまま、すなわち 35.375 を出した build と同一である。

## 次に来た者へ、優先順位つきで

1. **§A を決める。** trunk がどれかを決めない限り、他の全部が誤った木の上に
   積まれる。監査係の権限外。**未解決はこれ1件だけである。**
2. §G の第4点（`submission22`, 17.581）を較正に足す。成分間の取引を
   決着させる唯一の道で、`attr-guard` はそこで止まっている。
3. §I の `rollout` / `physics` は、問いを登録するかノブを畳むか。放置は
   「仮説なき計装」のまま。
