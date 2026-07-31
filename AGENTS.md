# ここは凍結されたdefault branchです — このまま読み進めないこと

この`main`はlive trunkから約50コミット遅れて凍結されています。
このbranchには本物の`AGENTS.md`（開始手順）、`HANDOFF.md`（現在地）、
`scripts/context.py`（context router）が**ありません**。
ここにあるコードやREADMEについて推論しないでください。

## 正しい開始手順（これだけ実行する）

```bash
git fetch --all --prune
git status --short --branch
git switch --track origin/experiment/anchor-recall-oracle
cat AGENTS.md   # switch後は必ず明示的に読み直す（自動再読込は保証されない）
```

- 既にローカルにそのbranchがあるなら `git switch experiment/anchor-recall-oracle`
- **worktreeがdirtyならswitchしない。** 別worktreeを**ローカルbranch付きで**
  切る（branch無しだとdetached HEADになり、commit/pushの作業導線として危険）:

```bash
git worktree add -b work-<topic> ../nedo-trunk \
  origin/experiment/anchor-recall-oracle
cd ../nedo-trunk
cat AGENTS.md
```

切り替え後は、そのbranchの`AGENTS.md`の手順に従う。コマンドは`python3`を
使う（`python`がPATHに無いsandboxが実在する）。Windowsは`python`に
読み替えてよいが、**正式な検証環境はLinux（CI）**である。

> リポジトリ管理者へ: GitHubのdefault branchを
> `experiment/anchor-recall-oracle`に変更すれば（Settings → General →
> Default branch）、このファイルは不要になり、新規cloneが直接live trunkに
> 着地します。それがこの導線問題の恒久解です。
