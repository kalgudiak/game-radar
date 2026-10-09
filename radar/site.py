"""Builds the dashboard website from the reports folder:
  site/index.html        latest day (with a day picker)
  site/days/<day>.html   every past day
  site/trends.html       genre and sub-genre trends across all days
  site/data/<day>.csv    downloads
History lives in reports/<day>/games.json, so the site can always be rebuilt from scratch."""
import json
import shutil
from collections import Counter
from pathlib import Path

from .report import _genre_colors
from .taxonomy import GENRES


def _days(reports):
    return sorted((p.name for p in Path(reports).iterdir()
                   if p.is_dir() and (p / "report.html").exists() and p.name[:4].isdigit()), reverse=True)


def _nav(days, current, prefix):
    opts = "".join(f'<option value="{prefix}days/{d}.html"{" selected" if d == current else ""}>{d}</option>' for d in days)
    return (f'<nav class="sitenav" aria-label="Dashboard"><label>Day <select onchange="location.href=this.value">{opts}</select></label>'
            f'<a href="{prefix}index.html">Latest</a><a href="{prefix}trends.html">Trends</a>'
            f'<a href="{prefix}data/{current}.csv" download>Download CSV</a></nav>')


def build_site(reports="reports", out="site", window=30):
    reports, out = Path(reports), Path(out)
    days = _days(reports)
    if not days:
        raise SystemExit("No reports yet: run `python -m radar daily` first.")
    if out.exists():
        shutil.rmtree(out)
    (out / "days").mkdir(parents=True)
    (out / "data").mkdir()
    for d in days:
        html = (reports / d / "report.html").read_text(encoding="utf-8")
        (out / "days" / f"{d}.html").write_text(html.replace("<!--NAV-->", _nav(days, d, "../")), encoding="utf-8")
        if (reports / d / "games.csv").exists():
            shutil.copy(reports / d / "games.csv", out / "data" / f"{d}.csv")
    latest = (reports / days[0] / "report.html").read_text(encoding="utf-8")
    (out / "index.html").write_text(latest.replace("<!--NAV-->", _nav(days, days[0], "")), encoding="utf-8")

    series = []
    for d in sorted(days)[-window:]:
        rows = json.loads((reports / d / "games.json").read_text(encoding="utf-8"))
        series.append({"day": d, "genres": Counter(r["genre"] for r in rows),
                       "subs": Counter(s for r in rows for s in r["subgenres"]), "total": len(rows)})
    data = json.dumps({"series": series, "colors": _genre_colors(), "order": GENRES})
    (out / "trends.html").write_text(TRENDS.replace("__DATA__", data.replace("</", "<\\/"))
                                     .replace("<!--NAV-->", _nav(days, days[0], "")), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    return out, days


TRENDS = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Game Radar: trends</title>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,500..800&family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#E9EDF2;--panel:#FFFFFF;--ink:#17213A;--muted:#5A6680;--rule:#CBD3DF;--focus:#2F6FEB;--row:#EEF1F5;
 box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121826;--panel:#1B2333;--ink:#E6EBF5;--muted:#9AA6BF;--rule:#334058;--focus:#7FA8FF;--row:#243047}}
:root[data-theme="dark"]{--bg:#121826;--panel:#1B2333;--ink:#E6EBF5;--muted:#9AA6BF;--rule:#334058;--focus:#7FA8FF;--row:#243047}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 "Atkinson Hyperlegible",system-ui,sans-serif}
.wrap{padding:0 clamp(16px,4vw,48px) 64px}
h1{font-family:Archivo,"Arial Narrow",sans-serif;font-stretch:78%;font-weight:800;font-size:clamp(34px,6vw,60px);line-height:.95;margin:28px 0 6px}
h2{font-family:Archivo,sans-serif;font-stretch:80%;font-weight:800;font-size:26px;margin:32px 0 8px}
p{color:var(--muted);max-width:66ch;margin:0}
.sitenav{display:flex;flex-wrap:wrap;gap:14px;align-items:center;padding:12px clamp(16px,4vw,48px) 0;font-size:14px}
.sitenav a{color:var(--focus)} select{font:inherit;padding:4px 8px;border:1px solid var(--rule);border-radius:6px;background:var(--panel);color:var(--ink)}
.box{background:var(--panel);border:1px solid var(--rule);border-radius:6px;padding:16px;overflow-x:auto}
svg text{fill:var(--muted);font-size:11px}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:10px;font-size:13px}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px}
table{border-collapse:collapse;width:100%;min-width:520px;font-size:14px}th{text-align:left;color:var(--muted);padding:6px 10px;border-bottom:1px solid var(--rule)}
td{padding:7px 10px;border-bottom:1px solid var(--row)}.num{text-align:right;font-variant-numeric:tabular-nums}
.up{color:#1E8E3E}.down{color:#C5221F}
@media (prefers-color-scheme:dark){.up{color:#6DD58C}.down{color:#F28B82}}
</style></head><body>
<!--NAV-->
<div class="wrap">
<h1>What's being released</h1>
<p id="sub"></p>
<h2>New games per day, by genre</h2>
<div class="box"><svg id="chart" role="img" aria-label="Stacked bar chart of new games per day by genre"></svg><div class="legend" id="legend"></div></div>
<h2>Genres: last 7 days vs the 7 before</h2>
<div class="box"><table id="gtab"></table></div>
<h2>Sub-genres: last 7 days vs the 7 before</h2>
<div class="box"><table id="stab"></table></div>
</div>
<script>
const D=__DATA__,S=D.series;
document.getElementById("sub").textContent=`${S.length} day${S.length>1?"s":""} of data, ${S[0].day} to ${S[S.length-1].day}. ${S.reduce((a,s)=>a+s.total,0).toLocaleString()} games in total.`;
const genres=D.order.filter(g=>S.some(s=>s.genres[g]));
const W=Math.max(640,S.length*34+60),H=300,pad=40,bw=Math.min(26,(W-pad-10)/S.length-6),max=Math.max(...S.map(s=>s.total),1);
const svg=document.getElementById("chart");svg.setAttribute("viewBox",`0 0 ${W} ${H+40}`);svg.setAttribute("width",W);
let h="";for(let i=0;i<=4;i++){const v=Math.round(max*i/4),y=H-(H-20)*i/4;h+=`<line x1="${pad}" x2="${W}" y1="${y}" y2="${y}" stroke="currentColor" opacity=".12"/><text x="${pad-6}" y="${y+4}" text-anchor="end">${v}</text>`}
S.forEach((s,i)=>{let y=H;const x=pad+8+i*((W-pad-10)/S.length);
 genres.forEach(g=>{const n=s.genres[g]||0;if(!n)return;const hh=(H-20)*n/max;y-=hh;h+=`<rect x="${x}" y="${y}" width="${bw}" height="${hh}" fill="${D.colors[g]}"><title>${s.day}: ${g} ${n}</title></rect>`});
 if(S.length<=14||i%Math.ceil(S.length/14)===0)h+=`<text x="${x+bw/2}" y="${H+16}" text-anchor="middle">${s.day.slice(5)}</text>`});
svg.innerHTML=h;svg.style.color="var(--ink)";
document.getElementById("legend").innerHTML=genres.map(g=>`<span><i style="background:${D.colors[g]}"></i>${g}</span>`).join("");
function compare(key,el,limit){const last=S.slice(-7),prev=S.slice(-14,-7),sum=(arr,k)=>arr.reduce((a,s)=>a+(s[key][k]||0),0);
 const keys=[...new Set(S.flatMap(s=>Object.keys(s[key])))];const tot=last.reduce((a,s)=>a+s.total,0)||1;
 const rows=keys.map(k=>({k,n:sum(last,k),p:sum(prev,k)})).filter(r=>r.n||r.p).sort((a,b)=>b.n-a.n).slice(0,limit);
 el.innerHTML=`<thead><tr><th>${key==="genres"?"Genre":"Sub-genre"}</th><th class="num">Last 7 days</th><th class="num">Share</th><th class="num">7 days before</th><th class="num">Change</th></tr></thead><tbody>`+
 rows.map(r=>{const ch=prev.length?(r.p?Math.round((r.n-r.p)/r.p*100):null):undefined;
  const c=ch===undefined?"Needs 2 weeks":ch===null?"New":(ch>0?"+":"")+ch+"%";const cls=ch>0||ch===null?"up":ch<0?"down":"";
  return `<tr><td>${r.k}</td><td class="num">${r.n}</td><td class="num">${(r.n/tot*100).toFixed(1)}%</td><td class="num">${prev.length?r.p:""}</td><td class="num ${ch===undefined?"":cls}">${c}</td></tr>`}).join("")+"</tbody>"}
compare("genres",document.getElementById("gtab"),30);compare("subs",document.getElementById("stab"),20);
</script></body></html>"""
