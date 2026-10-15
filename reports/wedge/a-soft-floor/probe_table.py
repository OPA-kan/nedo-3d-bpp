"""The soft-floor probe's results as a Markdown table (soft vs the hard control).

    .venv312/bin/python reports/wedge/a-soft-floor/probe_table.py > reports/wedge/a-soft-floor/probe-table.md
"""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def row(name, r, c):
    if "error" in r or not r.get("boxes"):
        return f"| {name} | error | | | | | | |"
    hard = [b for b in r["boxes"] if not b["soft"]]
    soft = [b for b in r["boxes"] if b["soft"]]
    disp = max((s.get("settle_disp", 0.0) for s in r["steps"]), default=0.0)
    tilt = max((b["tilt_deg"] for b in r["boxes"]), default=0.0)
    pen = max((b["floor_pen"] for b in soft if b["floor_pen"] is not None), default=0.0)
    sink = max((b["sink"] for b in hard), default=0.0)
    top = max(b["top"] for b in r["boxes"])
    fail = ""
    if r["placed"] < r["planned"]:
        f = [s for s in r["steps"] if not s["ok"]][0]
        st = f["status"]
        fail = " (" + ("transport" if not st.get("is_valid", True) else "settle") + f" at {f['sku']} on {f['commanded_bottom']:.2f})"
    ctl = f"{c['placed']}/{c['planned']}, {c['shake_topples']}" if c and "boxes" in c else "-"
    return (f"| {name} | {r['placed']}/{r['planned']}{fail} | {disp * 100:.1f} | {tilt:.1f} | {pen * 100:.1f} | "
            f"{sink * 100:.1f} | {top:.2f} | {r['shake_topples']} ({r['shake_max_shift'] * 100:.0f} cm) | {ctl} |")


def main():
    soft = json.load(open(HERE / "probe.json"))
    ctl = json.load(open(HERE / "probe-control.json"))
    print("| case | placed | settle disp. max (cm) | tilt max (deg) | soft floor pen. max (cm) | hard sink max (cm) | top (m) | shake topples (max shift) | control: placed, topples |")
    print("|---|---|---:|---:|---:|---:|---:|---|---|")
    for name in soft:
        print(row(name, soft[name], ctl.get(name)))


if __name__ == "__main__":
    main()
