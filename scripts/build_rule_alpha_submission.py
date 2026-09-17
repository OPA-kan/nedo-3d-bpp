"""Assemble the rule-alpha submission directory and zip it.

    python3 scripts/build_rule_alpha_submission.py [--out dist/submit] [--zip dist/submit.zip]

The directory follows the simulator README (``agent.py`` at its top, other
files beside it) and the zip is ``zip -r submit ./submit`` as the README
says.  ``agent/agent.py`` (the official baseline, untouched) travels as
``rule_alpha/_production_agent.py`` because rule-alpha reuses its geometry
helpers; the stack policy travels as numpy weights (``policy.npz``,
exported from ``policy.pt`` when missing).
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RULE_ALPHA_SKIP = {"visualize.py", "terrain_view.py", "physics.py", "penetration.py", "runner.py",
                   "scenarios.py", "episode.py"}
WEDGE_KEEP = {"__init__.py", "env.py", "stack.py", "option.py", "npolicy.py"}
STACK_POLICY = ROOT / "reports" / "wedge" / "ppo-stack-c1-s0-tower"


def build(out: pathlib.Path, policy_dir: pathlib.Path = STACK_POLICY) -> pathlib.Path:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copy(ROOT / "submission" / "agent.py", out / "agent.py")
    (out / "rule_alpha").mkdir()
    for path in sorted((ROOT / "rule_alpha").glob("*.py")):
        if path.name not in RULE_ALPHA_SKIP:
            shutil.copy(path, out / "rule_alpha" / path.name)
    shutil.copy(ROOT / "agent" / "agent.py", out / "rule_alpha" / "_production_agent.py")
    (out / "wedge_rl").mkdir()
    for name in sorted(WEDGE_KEEP):
        shutil.copy(ROOT / "wedge_rl" / name, out / "wedge_rl" / name)
    weights = out / "weights" / "stack"
    weights.mkdir(parents=True)
    npz = policy_dir / "policy.npz"
    if not npz.exists():
        from wedge_rl.npolicy import export

        export(policy_dir)
    shutil.copy(npz, weights / "policy.npz")
    for extra in ("meta.json", "config.json"):
        if (policy_dir / extra).exists():
            shutil.copy(policy_dir / extra, weights / extra)
    return out


def zip_dir(out: pathlib.Path, archive: pathlib.Path) -> pathlib.Path:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                zf.write(path, arcname=str(pathlib.Path(out.name) / path.relative_to(out)))
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "dist" / "submit")
    parser.add_argument("--zip", type=pathlib.Path, default=ROOT / "dist" / "submit.zip")
    parser.add_argument("--policy", type=pathlib.Path, default=STACK_POLICY)
    args = parser.parse_args()
    out = build(args.out.resolve(), args.policy.resolve())
    archive = zip_dir(out, args.zip.resolve())
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"built: {out} ({size / 1e6:.1f} MB), zip: {archive} ({archive.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
