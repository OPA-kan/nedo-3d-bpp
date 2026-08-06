"""
Which reports still stand, and which have been overtaken?

`reports/` holds 34 experiment directories and about a thousand files, and
nothing in it says which conclusions are still load-bearing. A reader
arriving at `reports/hazard/dominated-choices.md` has no way to learn that
the file next to it retracts every number in it. That is not a documentation
gap, it is a correctness hazard: the retracted claim reads as a finding.

A hand-written index would acquire the same defect within a week -- this
repository already has one stale index for every maintained one. So the
index is DERIVED, from two sources that are already kept current:

  * `context/evidence.json`, whose entries carry `status` and cite the
    report their claim rests on. A report cited only by superseded entries
    is overtaken; a report cited by no entry at all made no claim that
    survived into the ledger.
  * the filesystem, for the run directories that hold raw measurement
    output and no prose at all.

The status column therefore never disagrees with the ledger, because it is
the ledger. Re-run this after appending evidence:

    python scripts/index_reports.py --write
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
LEDGER = ROOT / "context" / "evidence.json"
OUTPUT = REPORTS / "INDEX.md"

REPORT_PATH = re.compile(r"reports/[A-Za-z0-9._/-]+\.md")

# Directories whose contents are raw measurement output rather than a
# conclusion. They are listed with their size and left unsummarised: reading
# them is the job of the analyser named beside them, not of a person.
RAW_PRODUCERS = {
    "board-receptivity": "scripts/fit_hazard_model.py",
    "first-pass-depth": "scripts/analyze_first_pass_depth.py",
    "first-pass-depth-taskA": "scripts/analyze_first_pass_depth.py",
    "stability-tradeoff": "scripts/analyze_stability_tradeoff.py",
    "attribute-placement": "scripts/fit_hazard_model.py",
    "merge-taskA": "scripts/fit_hazard_model.py",
}


def ledger_entries():
    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    return payload["entries"] if isinstance(payload, dict) else payload


def citations(entries):
    """report path -> [(evidence id, status)], in ledger order."""
    out = collections.defaultdict(list)
    for entry in entries:
        blob = json.dumps(entry, ensure_ascii=False)
        for path in dict.fromkeys(REPORT_PATH.findall(blob)):
            out[path].append(
                (entry.get("id", "?"), entry.get("status", "active"))
            )
    return out


def status_of(cites):
    """
    A report's standing, read off the claims that rest on it.

    `uncited` is deliberately not called "stale". A report can be uncited
    because it is raw output, because it predates the ledger, or because its
    claim was withdrawn and never replaced -- three different things that
    only a reader can tell apart. The index reports the fact and does not
    guess the reason.
    """
    if not cites:
        return "uncited"
    if any(status == "active" for _id, status in cites):
        return "active"
    return "superseded"


def tracked_report_files():
    listing = subprocess.run(
        ["git", "ls-files", "reports"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return [pathlib.Path(p) for p in listing]


def last_touched(path):
    return subprocess.run(
        ["git", "log", "-1", "--format=%ad", "--date=short", "--", str(path)],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip() or "-"


def first_heading(path):
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.name


def render():
    entries = ledger_entries()
    cites = citations(entries)
    tracked = tracked_report_files()

    prose = [p for p in tracked if p.suffix == ".md" and p.name != "INDEX.md"]
    sizes = collections.Counter()
    counts = collections.Counter()
    for path in tracked:
        full = ROOT / path
        if full.exists():
            top = path.parts[1] if len(path.parts) > 1 else "(root)"
            sizes[top] += full.stat().st_size
            counts[top] += 1

    lines = [
        "# reports/ index",
        "",
        "**このファイルは生成物である。** 手で編集しない。",
        "`python scripts/index_reports.py --write` で再生成する。",
        "",
        "状態は `context/evidence.json` から導出している。台帳に active な主張が",
        "1件でも紐付いていれば `active`、紐付く主張が全て superseded なら",
        "`superseded`、1件も紐付かないなら `uncited`。**`uncited` は「古い」の",
        "意味ではない** — 生出力である・台帳より前に書かれた・主張が撤回され",
        "たまま置き換えられていない、の3つを索引は区別できないので、事実だけ",
        "を出して理由は推定しない。",
        "",
        "## 結論を書いたレポート",
        "",
        "| 状態 | 最終更新 | ファイル | 根拠となっている台帳エントリ |",
        "|---|---|---|---|",
    ]

    rank = {"active": 0, "superseded": 1, "uncited": 2}
    rows = []
    for path in prose:
        key = path.as_posix()
        cite = cites.get(key, [])
        state = status_of(cite)
        ids = ", ".join(
            f"`{i}`" + ("" if s == "active" else f" ({s})") for i, s in cite
        ) or "—"
        rows.append((rank[state], key, state, last_touched(path), ids))
    for _r, key, state, date, ids in sorted(rows):
        lines.append(f"| {state} | {date} | `{key}` | {ids} |")

    lines += [
        "",
        "## 生の計測出力（散文なし）",
        "",
        "以下は結論ではなく入力データである。読むのは人ではなく右の解析器。",
        "",
        "| ディレクトリ | 追跡ファイル数 | 容量 | 読む側 |",
        "|---|---:|---:|---|",
    ]
    for name, reader in sorted(RAW_PRODUCERS.items()):
        if name in counts:
            lines.append(
                f"| `reports/{name}/` | {counts[name]} | "
                f"{sizes[name] / 1048576:.1f} MB | `{reader}` |"
            )

    total_mb = sum(sizes.values()) / 1048576
    lines += [
        "",
        f"追跡下の `reports/` 全体: {sum(counts.values())} ファイル / "
        f"{total_mb:.1f} MB。"
        "内訳と、これが clone コストではない理由は `docs/REPO_AUDIT.md` §D。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true", help=f"overwrite {OUTPUT}"
    )
    args = parser.parse_args()
    text = render()
    if args.write:
        OUTPUT.write_text(text, encoding="utf-8")
        print(f"wrote {OUTPUT}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
