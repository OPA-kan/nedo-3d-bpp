"""Render a Self-Play Packing Game trajectory as a standalone HTML replay."""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any


def _item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": row.get("index"),
        "length": float(row.get("length", 0)),
        "width": float(row.get("width", 0)),
        "height": float(row.get("height", 0)),
        "pos": [float(value) for value in (row.get("pos") or [0, 0, 0])],
        "is_soft": bool(row.get("is_soft")),
        "is_prioritized": bool(row.get("is_prioritized")),
    }


def _container(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": int(row.get("index", 0)),
        "length": float(row.get("length", 0)),
        "width": float(row.get("width", 0)),
        "height": float(row.get("height", 0)),
        "cut_x": float(row.get("cut_x", 0)),
        "cut_y": float(row.get("cut_y", 0)),
        "thickness": float(row.get("thickness", 0)),
        "center": [float(value) for value in (row.get("center") or [0, 0, 0])],
        "is_prioritized": bool(row.get("is_prioritized")),
        "has_shelf": bool(row.get("shelf", row.get("require_shelf", False))),
        "items": [_item(item) for item in row.get("packed_items", [])],
    }


def build_payload(manifest_path: pathlib.Path, game_index: int) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    games = list(manifest.get("games", []))
    if not 0 <= game_index < len(games):
        raise ValueError(f"game index {game_index} outside 0..{len(games) - 1}")
    game = games[game_index]
    records = {int(row.get("step", -1)): row for row in game.get("records", [])}
    game_dir = manifest_path.parent / f"game-{game_index:03d}"
    frames = []
    for capture in sorted(game.get("captures", []), key=lambda row: row["step"]):
        step = int(capture["step"])
        snapshot = json.loads(
            (game_dir / capture["snapshot_path"]).read_text(encoding="utf-8")
        )
        context = snapshot.get("self_play_game", {})
        record = records.get(step, {})
        attribute = record.get("attribute_reward", {})
        frames.append({
            "step": step,
            "player": int(context.get("player_to_move", record.get("player", 0))),
            "block_length": int(context.get("block_length", 0)),
            "is_handoff_state": bool(context.get("is_handoff_state")),
            "selected_rank": record.get("selected_rank"),
            "candidate_count": int(record.get("candidate_count", 0)),
            "handoff_after": bool(record.get("handoff")),
            "new_violations": float(attribute.get("new_violations", 0) or 0),
            "containers": [
                _container(row) for row in
                snapshot.get("observation", {}).get("container_list", [])
            ],
        })
    return {
        "title": (
            f"Self-Play Packing · {manifest.get('case_id', 'scenario')} · "
            f"{manifest.get('selection', {}).get('mode')} · game {game_index}"
        ),
        "game": {
            "index": game_index,
            "starting_player": game.get("starting_player"),
            "terminal_reason": game.get("terminal_reason"),
            "rewards": game.get("rewards", [0, 0]),
        },
        "frames": frames,
    }


HTML = r'''<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Self-Play Replay</title>
<style>
:root{color-scheme:dark;font-family:Inter,system-ui,sans-serif}body{margin:0;background:#07111f;color:#eaf2ff;overflow:hidden}
#bar{height:78px;display:flex;align-items:center;gap:12px;padding:0 18px;background:#0d1b2d;border-bottom:1px solid #29415f}
button,select,input{accent-color:#51d6ff;background:#172a43;color:#fff;border:1px solid #385777;border-radius:8px;padding:8px}
button{cursor:pointer}.title{font-weight:800;margin-right:auto}.pill{padding:7px 10px;border-radius:999px;background:#162b45}
#stage{position:relative;height:calc(100vh - 79px)}canvas{width:100%;height:100%;display:block}
#hud{position:absolute;left:18px;top:16px;background:#07111fd9;border:1px solid #29415f;border-radius:12px;padding:12px;min-width:220px;line-height:1.55}
#legend{position:absolute;right:18px;bottom:16px;background:#07111fd9;border:1px solid #29415f;border-radius:12px;padding:10px}
.sw{display:inline-block;width:12px;height:12px;border-radius:3px;margin:0 5px 0 10px}
</style></head><body><div id="bar"><div class="title" id="title"></div><button id="play">▶ Play</button>
<button id="back">◀</button><input id="step" type="range" min="0" value="0"><button id="next">▶</button>
<select id="speed"><option value="1200">0.5×</option><option value="650" selected>1×</option><option value="300">2×</option><option value="140">4×</option></select>
<span class="pill" id="counter"></span></div><div id="stage"><canvas id="view"></canvas><div id="hud"></div>
<div id="legend"><span class="sw" style="background:#49a7ff"></span>normal <span class="sw" style="background:#ff73c7"></span>soft <span class="sw" style="background:#ffd45c"></span>priority <span class="sw" style="background:#ff8a4c"></span>soft+priority</div></div>
<script id="SELF_PLAY_REPLAY" type="application/json">__PAYLOAD__</script><script>
const data=JSON.parse(document.getElementById('SELF_PLAY_REPLAY').textContent),cv=document.getElementById('view'),ctx=cv.getContext('2d'),slider=document.getElementById('step');let at=0,timer=null;
slider.max=Math.max(0,data.frames.length-1);document.getElementById('title').textContent=data.title;
function proj(x,y,z,s,ox,oy){return [ox+(x-y)*s*.55,oy-z*s+(x+y)*s*.25]}
function poly(points,fill,stroke){ctx.beginPath();points.forEach((p,i)=>(i?ctx.lineTo(...p):ctx.moveTo(...p)));ctx.closePath();ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle=stroke;ctx.stroke()}
function line(points,stroke,width=1){ctx.beginPath();points.forEach((p,i)=>(i?ctx.lineTo(...p):ctx.moveTo(...p)));ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.stroke()}
function box(x,y,z,l,w,h,color,s,ox,oy){let p=(a,b,c)=>proj(a,b,c,s,ox,oy),A=p(x-l/2,y-w/2,z-h/2),B=p(x+l/2,y-w/2,z-h/2),C=p(x+l/2,y+w/2,z-h/2),D=p(x-l/2,y+w/2,z-h/2),E=p(x-l/2,y-w/2,z+h/2),F=p(x+l/2,y-w/2,z+h/2),G=p(x+l/2,y+w/2,z+h/2),H=p(x-l/2,y+w/2,z+h/2);poly([D,C,G,H],color+'aa','#dff3ff');poly([B,C,G,F],color+'cc','#dff3ff');poly([E,F,G,H],color,'#fff')}
function containerWire(c,s,ox,oy){let x0=-c.length/2,x1=c.length/2,y0=-c.width/2,y1=c.width/2,profile=[[x0+c.cut_x,0],[x1,0],[x1,c.height],[x0,c.height],[x0,c.cut_y]],stroke=c.is_prioritized?'#ffd45c':'#52769a';[y0,y1].forEach(y=>line([...profile,profile[0]].map(q=>proj(q[0],y,q[1],s,ox,oy)),stroke,2));profile.forEach(q=>line([proj(q[0],y0,q[1],s,ox,oy),proj(q[0],y1,q[1],s,ox,oy)],stroke,1));let t=c.thickness||.04;if(c.cut_x>0)box(x0+c.cut_x/2+t,0,c.height/2+t/2,c.cut_x,Math.max(0,c.width-2*t),t,'#b94f5f',s,ox,oy);if(c.has_shelf)box(0,c.width/4,c.height/2+t/2,Math.max(0,c.length-t),Math.max(0,c.width/2-2*t),t,'#355cff',s,ox,oy)}
function render(){let f=data.frames[at];ctx.clearRect(0,0,cv.width,cv.height);if(!f)return;let n=Math.max(1,f.containers.length),panel=cv.width/n,s=Math.min(170,panel/3.2,cv.height/3.4);f.containers.forEach((c,i)=>{let ox=panel*(i+.5),oy=cv.height*.72,cc=c.center||[0,0,0];ctx.fillStyle=c.is_prioritized?'#ffd45c':'#8eb5dc';ctx.font='bold 16px system-ui';ctx.textAlign='center';ctx.fillText(`C${c.index} ${c.is_prioritized?'PRIORITY':'GENERAL'}${c.has_shelf?' + SHELF':''} · ULD CUT PROFILE`,ox,42);containerWire(c,s,ox,oy);[...c.items].sort((a,b)=>a.pos[2]-b.pos[2]).forEach(it=>{let col=it.is_soft&&it.is_prioritized?'#ff8a4c':it.is_soft?'#ff73c7':it.is_prioritized?'#ffd45c':'#49a7ff';box(it.pos[0]-cc[0],it.pos[1]-cc[1],it.pos[2],it.length,it.width,it.height,col,s,ox,oy)})});
document.getElementById('counter').textContent=`${at+1} / ${data.frames.length}`;let terminal=at===data.frames.length-1?`<br><b>terminal: ${data.game.terminal_reason}</b>`:'';let critical=data.critical?`<br><b>critical ${data.critical.score.toFixed(1)}</b>: ${data.critical.reasons.join(' · ')}`:'';document.getElementById('hud').innerHTML=`<b>STEP ${f.step}</b><br>Player <b style="color:${f.player?'#ff73c7':'#51d6ff'}">${f.player}</b> · block ${f.block_length}<br>rank ${f.selected_rank??'terminal'} / candidates ${f.candidate_count}<br>${f.is_handoff_state?'🔁 HANDOFF STATE<br>':''}${f.handoff_after?'handoff after move<br>':''}${f.new_violations?`⚠ attribute violation +${f.new_violations}`:'attribute clean'}${terminal}${critical}`;slider.value=at}
function go(v){at=Math.max(0,Math.min(data.frames.length-1,v));render()}function play(){if(timer){clearInterval(timer);timer=null;document.getElementById('play').textContent='▶ Play'}else{document.getElementById('play').textContent='⏸ Pause';timer=setInterval(()=>go(at+1<data.frames.length?at+1:0),+document.getElementById('speed').value)}}
document.getElementById('play').onclick=play;document.getElementById('back').onclick=()=>go(at-1);document.getElementById('next').onclick=()=>go(at+1);slider.oninput=()=>go(+slider.value);document.getElementById('speed').onchange=()=>{if(timer){play();play()}};
function resize(){cv.width=cv.clientWidth*devicePixelRatio;cv.height=cv.clientHeight*devicePixelRatio;ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);cv.width=cv.clientWidth;cv.height=cv.clientHeight;render()}addEventListener('resize',resize);resize();
</script></body></html>'''


def render_html(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return HTML.replace("__PAYLOAD__", encoded.replace("</", "<\\/"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--game-index", type=int, default=0)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_html(build_payload(args.manifest, args.game_index)), encoding="utf-8"
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
