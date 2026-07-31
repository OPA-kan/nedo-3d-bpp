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
```

- 既にローカルにそのbranchがあるなら `git switch experiment/anchor-recall-oracle`
- **worktreeがdirtyならswitchしない。** 別worktreeで作業する:

```bash
git worktree add ../nedo-trunk origin/experiment/anchor-recall-oracle
cd ../nedo-trunk
```

切り替えたら、そのbranchの`AGENTS.md`から開始する（Codex等はswitch後に
自動で読み直す）。コマンドは`python3`を使う（`python`がPATHに無い
sandboxが実在する）。

> リポジトリ管理者へ: GitHubのdefault branchを
> `experiment/anchor-recall-oracle`に変更すれば（Settings → General →
> Default branch）、このファイルは不要になり、新規cloneが直接live trunkに
> 着地します。それがこの導線問題の恒久解です。
