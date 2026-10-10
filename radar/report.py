import csv
import html
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from .db import norm_title
from .links import ordered
from .taxonomy import FAMILIES, GENRES, PRIORITY, platform_family

LINK_COLUMN_LABEL = {"steam_url": "Steam", "appstore_url": "App Store", "googleplay_url": "Google Play",
                     "itch_url": "itch.io", "epic_url": "Epic Games Store", "playstation_url": "PlayStation Store",
                     "xbox_url": "Xbox Store", "eshop_url": "Nintendo eShop", "website": "Website"}
LINK_COLUMNS = list(LINK_COLUMN_LABEL)
SOURCE_RANK = {"igdb": 0, "steam": 1, "appstore": 2, "googleplay": 3, "itch": 4}
STORE_LABEL = {"igdb": "IGDB", "steam": "Steam", "appstore": "App Store", "googleplay": "Google Play", "itch": "itch.io"}


def _merge_links(gs):
    links = {}
    for g in gs:
        own = g.links or ({STORE_LABEL.get(g.source, g.source): g.url} if g.url else {})
        for label, url in own.items():
            links.setdefault(label, url)
    return [{"label": k, "url": v} for k, v in ordered(links).items()]


def cluster(games):
    """Merge the same title seen on several stores into one row."""
    groups = defaultdict(list)
    for g in games:
        groups[norm_title(g.title) or g.key].append(g)
    rows = []
    for gs in groups.values():
        gs.sort(key=lambda g: SOURCE_RANK.get(g.source, 9))
        rep = gs[0]
        plats = sorted({p for g in gs for p in g.platforms})
        best = max(gs, key=lambda g: g.rating_count or 0)
        rows.append({
            "title": rep.title,
            "genre": min((g.genre for g in gs), key=lambda x: PRIORITY.get(x, 99)),
            "subgenres": sorted({s for g in gs for s in g.subgenres}),
            "platforms": plats,
            "families": sorted({platform_family(p) for p in plats}, key=FAMILIES.index),
            "release_date": min((g.release_date for g in gs if g.release_date), default=""),
            "developer": next((g.developer for g in gs if g.developer), ""),
            "publisher": next((g.publisher for g in gs if g.publisher), ""),
            "price": next((g.price for g in gs if g.price is not None), None),
            "currency": next((g.currency for g in gs if g.currency), ""),
            "free": any(g.is_free for g in gs),
            "iap": any(g.has_iap for g in gs),
            "rating": best.rating, "rating_count": best.rating_count,
            "installs": max((g.installs or 0 for g in gs), default=0) or None,
            "charts": sorted({c for g in gs for c in g.extra.get("charts", [])}),
            "links": _merge_links(gs),
            "raw_genres": sorted({x for g in gs for x in g.raw_genres}),
            "tags": list(dict.fromkeys(t for g in gs for t in g.tags))[:12],
            "description": (rep.description or "")[:280],
            "icon": next((g.icon_url for g in gs if g.icon_url), ""),
        })
    rows.sort(key=lambda r: (PRIORITY.get(r["genre"], 99), -(r["rating_count"] or 0),
                             -len(r["charts"]), r["title"].lower()))
    return rows


def write_daily(db, day: date, out_root, basis="discovered", note=""):
    games = db.games_first_seen(day.isoformat()) if basis == "discovered" else db.games_released(day.isoformat())
    rows = cluster(games)
    out = Path(out_root) / day.isoformat()
    out.mkdir(parents=True, exist_ok=True)

    fields = ["source", "source_id", "title", "genre", "subgenres", "release_date", "platforms",
              "raw_genres", "tags", "game_modes", "developer", "publisher", "price", "currency",
              "is_free", "has_iap", "rating", "rating_count", "installs", "content_rating", "url"]
    with open(out / "games.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields + LINK_COLUMNS + ["all_links", "charts"])
        w.writeheader()
        for g in games:
            d = g.to_dict()
            row = {k: ("; ".join(map(str, d[k])) if isinstance(d[k], list) else d[k]) for k in fields}
            for col in LINK_COLUMNS:
                row[col] = g.links.get(LINK_COLUMN_LABEL[col], "")
            row["all_links"] = " | ".join(f"{k}: {v}" for k, v in ordered(g.links).items())
            row["charts"] = "; ".join(g.extra.get("charts", []))
            w.writerow(row)
    (out / "games.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "summary.md").write_text(_markdown(day, rows, basis), encoding="utf-8")
    from .dashboard import aggregate, render, slim
    meta = {"updated": day.strftime("%d %b %Y").lstrip("0"), "csv": "games.csv", "repo": "", "note": note}
    (out / "report.html").write_text(render([slim(r) for r in rows], aggregate(rows), meta), encoding="utf-8")
    return out, rows


def _matrix(rows):
    m = defaultdict(Counter)
    for r in rows:
        for fam in r["families"] or ["Other"]:
            m[r["genre"]][fam] += 1
    return m


def _markdown(day, rows, basis):
    what = "newly discovered" if basis == "discovered" else "released"
    lines = [f"# New games, {day.isoformat()}", "",
             f"{len(rows)} unique games {what} (a game on several stores counts once).", ""]
    m = _matrix(rows)
    fams = [f for f in FAMILIES if any(m[g][f] for g in m)]
    by_genre = Counter(r["genre"] for r in rows)
    lines += ["| Genre | Total | " + " | ".join(fams) + " |", "|---|---:|" + "---:|" * len(fams)]
    for g in sorted(by_genre, key=lambda g: -by_genre[g]):
        lines.append(f"| {g} | {by_genre[g]} | " + " | ".join(str(m[g][f] or "") for f in fams) + " |")
    subs = Counter(s for r in rows for s in r["subgenres"])
    if subs:
        lines += ["", "**Sub-genres seen today:** " + ", ".join(f"{s} ({n})" for s, n in subs.most_common(15))]
    for g in GENRES:
        items = [r for r in rows if r["genre"] == g]
        if not items:
            continue
        lines += ["", f"## {g} ({len(items)})", ""]
        for r in items[:40]:
            bits = [", ".join(r["platforms"])]
            if r["developer"]:
                bits.append(r["developer"])
            if r["subgenres"]:
                bits.append("/".join(r["subgenres"]))
            if r["rating_count"]:
                bits.append(f"{r['rating']:.0f}/100 from {r['rating_count']:,} ratings" if r["rating"] else f"{r['rating_count']:,} ratings")
            if r["charts"]:
                bits.append(f"charting x{len(r['charts'])}")
            main = r["links"][0]["url"] if r["links"] else ""
            title = f"[{r['title']}]({main})" if main else r["title"]
            others = " · ".join(f"[{l['label']}]({l['url']})" for l in r["links"][1:])
            lines.append(f"- **{title}**: " + "; ".join(bits) + (f"  \n  {others}" if others else ""))
        if len(items) > 40:
            lines.append(f"- ...and {len(items) - 40} more in games.csv")
    return "\n".join(lines) + "\n"


def write_trends(db, end: date, days: int, out_root):
    start = end - timedelta(days=days - 1)
    prev_start = start - timedelta(days=days)
    cur = Counter()
    prev = Counter()
    daily = defaultdict(Counter)
    for r in db.genre_counts(prev_start.isoformat(), end.isoformat()):
        d = date.fromisoformat(r["day"])
        if d >= start:
            cur[r["genre"]] += r["n"]
            daily[r["day"]][r["genre"]] += r["n"]
        else:
            prev[r["genre"]] += r["n"]
    out = Path(out_root) / "trends"
    out.mkdir(parents=True, exist_ok=True)
    genres = [g for g in GENRES if cur[g] or prev[g]]
    with open(out / f"genre-by-day-{end.isoformat()}-{days}d.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["release_date"] + genres)
        for d in sorted(daily):
            w.writerow([d] + [daily[d][g] for g in genres])
    total, ptotal = sum(cur.values()) or 1, sum(prev.values())
    lines = [f"# Genre trends: last {days} days to {end.isoformat()}", "",
             "| Genre | Releases | Share | Prior period | Change |", "|---|---:|---:|---:|---:|"]
    for g in sorted(genres, key=lambda g: -cur[g]):
        ch = f"{(cur[g] - prev[g]) / prev[g] * 100:+.0f}%" if prev[g] else "new"
        lines.append(f"| {g} | {cur[g]} | {cur[g] / total * 100:.1f}% | {prev[g]} | {ch if ptotal else 'n/a'} |")
    p = out / f"trends-{end.isoformat()}-{days}d.md"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ------------------------------------------------------------------ HTML report
def _genre_colors():
    # evenly spaced hues, alternating lightness so neighbours stay distinguishable
    return {g: f"hsl({(i * 137.5) % 360:.0f} {58 if i % 2 else 48}% {46 if i % 2 else 40}%)"
            for i, g in enumerate(GENRES)}


def _html(day, rows, basis, note=""):
    colors = _genre_colors()
    counts = Counter(r["genre"] for r in rows)
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    meta = json.dumps({"colors": colors, "order": GENRES})
    what = "Discovered" if basis == "discovered" else "Released"
    return (HTML_TEMPLATE
            .replace("__DAY__", html.escape(day.strftime("%A %d %B %Y")))
            .replace("__COUNT__", str(len(rows)))
            .replace("__GENRES__", str(len(counts)))
            .replace("__NOTE__", html.escape(note) or "Click a genre band to show or hide it. A game on several stores is listed once.")
            .replace("__WHAT__", what)
            .replace("__DATA__", data).replace("__META__", meta))


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>New games: __DAY__</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@75..100,500..800&family=Atkinson+Hyperlegible:wght@400;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#E9EDF2;--panel:#FFFFFF;--ink:#17213A;--muted:#5A6680;--rule:#CBD3DF;--focus:#2F6FEB;--soft:#EEF1F6;--row:#EEF1F5;--storebg:#EAF1FE;--storeline:#BBD0F7;--off:saturate(.15) brightness(1.35);
 box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
html{scroll-padding-top:env(safe-area-inset-top,0px)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121826;--panel:#1B2333;--ink:#E6EBF5;--muted:#9AA6BF;--rule:#334058;--focus:#7FA8FF;--soft:#263149;--row:#243047;--storebg:#1F3256;--storeline:#36528A;--off:saturate(.15) brightness(.55)}}
:root[data-theme="dark"]{--bg:#121826;--panel:#1B2333;--ink:#E6EBF5;--muted:#9AA6BF;--rule:#334058;--focus:#7FA8FF;--soft:#263149;--row:#243047;--storebg:#1F3256;--storeline:#36528A;--off:saturate(.15) brightness(.55)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 "Atkinson Hyperlegible",system-ui,sans-serif}
header{padding:32px clamp(16px,4vw,48px) 8px}
h1{font-family:Archivo,"Arial Narrow",sans-serif;font-stretch:78%;font-weight:800;font-size:clamp(34px,6vw,64px);line-height:.95;margin:0;letter-spacing:-.01em}
.lede{color:var(--muted);margin:10px 0 0;max-width:62ch}
.spectrum{display:flex;height:64px;margin:24px clamp(16px,4vw,48px) 0;border-radius:6px;overflow:hidden;box-shadow:inset 0 0 0 1px rgba(23,33,58,.15)}
.spectrum button{border:0;padding:0 8px;color:#fff;font:700 13px/1.15 Archivo,sans-serif;font-stretch:85%;text-align:left;cursor:pointer;min-width:6px;overflow:hidden;white-space:nowrap;display:flex;flex-direction:column;justify-content:center}
.spectrum button span{font-size:22px;font-weight:800}
.spectrum button[aria-pressed=false]{filter:var(--off)}
.spectrum button:focus-visible,.chip:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:16px clamp(16px,4vw,48px)}
.chip{border:1px solid var(--rule);background:var(--panel);color:var(--ink);border-radius:999px;padding:5px 12px;font:inherit;font-size:14px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
input,select{font:inherit;font-size:14px;padding:6px 10px;border:1px solid var(--rule);border-radius:6px;background:var(--panel);color:var(--ink)}
input{min-width:220px}
.reset{background:none;border:0;color:var(--focus);font:inherit;font-size:14px;cursor:pointer;text-decoration:underline}
main{padding:0 clamp(16px,4vw,48px) 64px}
section{margin-top:28px}
h2{font-family:Archivo,sans-serif;font-stretch:80%;font-weight:800;font-size:28px;margin:0 0 8px;display:flex;align-items:baseline;gap:10px;border-bottom:4px solid var(--c);padding-bottom:4px}
h2 small{font:400 15px "Atkinson Hyperlegible",sans-serif;color:var(--muted)}
.grid{overflow-x:auto;background:var(--panel);border-radius:6px;border:1px solid var(--rule)}
table{border-collapse:collapse;width:100%;min-width:760px;font-size:14px}
th{text-align:left;font-weight:700;color:var(--muted);padding:8px 10px;border-bottom:1px solid var(--rule);cursor:pointer;white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid var(--row);vertical-align:top}
tr:last-child td{border-bottom:0}
td.t{min-width:240px}
td.t b{display:block;font-size:15px}
td.t b a{color:var(--ink);text-decoration:none}
td.t b a:hover{text-decoration:underline}
.links{display:flex;flex-wrap:wrap;gap:4px;margin:4px 0}
.links a{font-size:12px;border:1px solid var(--rule);border-radius:4px;padding:1px 7px;text-decoration:none;white-space:nowrap}
.links a.store{background:var(--storebg);border-color:var(--storeline)}
.links a:hover{border-color:var(--focus)}
td.t .d{color:var(--muted);font-size:13px;max-width:60ch}
.tag{display:inline-block;background:var(--soft);border-radius:4px;padding:1px 6px;margin:2px 4px 0 0;font-size:12px}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
a{color:var(--focus)}
.empty{padding:40px 0;color:var(--muted)}
.sitenav{display:flex;flex-wrap:wrap;gap:14px;align-items:center;padding:12px clamp(16px,4vw,48px) 0;font-size:14px}
.sitenav a{color:var(--focus)}
@media (prefers-reduced-motion:no-preference){.spectrum button{transition:filter .15s}}
</style></head><body>
<header><h1>__COUNT__ new games across __GENRES__ genres</h1>
<p class="lede">__WHAT__ on __DAY__. __NOTE__</p></header>
<!--NAV-->
<nav class="spectrum" id="spectrum" aria-label="Genres"></nav>
<div class="controls" id="controls">
 <span id="fams"></span>
 <select id="sub" aria-label="Sub-genre"><option value="">All sub-genres</option></select>
 <input id="q" type="search" placeholder="Search title, developer, tag" aria-label="Search">
 <label><input type="checkbox" id="charting" style="min-width:0"> Charting only</label>
 <button class="reset" id="reset">Show everything</button>
</div>
<main id="out"></main>
<script>
const ROWS=__DATA__, META=__META__;
const STORES=new Set(["Steam","App Store","Google Play","itch.io","Epic Games Store","GOG","PlayStation Store","Xbox Store","Microsoft Store","Nintendo eShop","Meta Quest Store","TapTap","CrazyGames","Poki"]);
const state={off:new Set(),fam:null,sub:"",q:"",charting:false,sort:{}};
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const counts={};ROWS.forEach(r=>counts[r.genre]=(counts[r.genre]||0)+1);
const genres=META.order.filter(g=>counts[g]);
const spec=document.getElementById("spectrum");
genres.forEach(g=>{const b=document.createElement("button");b.style.background=META.colors[g];
 b.style.flex=counts[g];b.title=`${g}: ${counts[g]}`;b.setAttribute("aria-pressed","true");
 b.innerHTML=`<span>${counts[g]}</span>${esc(g)}`;b.onclick=()=>{state.off.has(g)?state.off.delete(g):state.off.add(g);render()};spec.appendChild(b)});
const fams=[...new Set(ROWS.flatMap(r=>r.families))];
const fe=document.getElementById("fams");
["All",...fams].forEach(f=>{const b=document.createElement("button");b.className="chip";b.textContent=f==="All"?"All platforms":f;
 b.onclick=()=>{state.fam=f==="All"?null:f;render()};b.dataset.f=f;fe.appendChild(b);fe.append(" ")});
const subs={};ROWS.forEach(r=>r.subgenres.forEach(s=>subs[s]=(subs[s]||0)+1));
const sel=document.getElementById("sub");Object.entries(subs).sort((a,b)=>b[1]-a[1]).forEach(([s,n])=>sel.add(new Option(`${s} (${n})`,s)));
sel.onchange=e=>{state.sub=e.target.value;render()};
document.getElementById("q").oninput=e=>{state.q=e.target.value.toLowerCase();render()};
document.getElementById("charting").onchange=e=>{state.charting=e.target.checked;render()};
document.getElementById("reset").onclick=()=>{state.off.clear();state.fam=null;state.sub="";state.q="";state.charting=false;
 sel.value="";document.getElementById("q").value="";document.getElementById("charting").checked=false;render()};
const cols=[["title","Game"],["platforms","Platforms"],["subgenres","Sub-genres"],["price","Price"],["rating","Rating"],["rating_count","Ratings"],["installs","Installs"],["charts","Charts"],["release_date","Released"]];
function val(r,k){return k==="charts"?r.charts.length:Array.isArray(r[k])?r[k].join(","):r[k]}
function cell(r,k){
 if(k==="title"){const L=r.links||[],main=L[0];
  const pills=L.map(l=>`<a class="${STORES.has(l.label)?"store":""}" href="${esc(l.url)}" target="_blank" rel="noopener" title="${esc(l.url)}">${esc(l.label)}</a>`).join("");
  const name=main?`<a href="${esc(main.url)}" target="_blank" rel="noopener">${esc(r.title)}</a>`:esc(r.title);
  return `<td class="t"><b>${name}</b>${r.developer?esc(r.developer):""}${pills?`<div class="links">${pills}</div>`:""}<div class="d">${esc(r.description)}</div></td>`}
 if(k==="platforms")return `<td>${r.platforms.map(p=>`<span class="tag">${esc(p)}</span>`).join("")}</td>`;
 if(k==="subgenres")return `<td>${r.subgenres.map(p=>`<span class="tag">${esc(p)}</span>`).join("")}</td>`;
 if(k==="price")return `<td class="num">${r.free||r.price===0?"Free":r.price!=null?esc(r.currency+" "+r.price):""}${r.iap?" + IAP":""}</td>`;
 if(k==="rating")return `<td class="num">${r.rating!=null?Math.round(r.rating):""}</td>`;
 if(k==="rating_count"||k==="installs")return `<td class="num">${r[k]?Number(r[k]).toLocaleString():""}</td>`;
 if(k==="charts")return `<td class="num" title="${esc(r.charts.join("\n"))}">${r.charts.length||""}</td>`;
 return `<td class="num">${esc(r[k])}</td>`}
function render(){
 [...spec.children].forEach((b,i)=>b.setAttribute("aria-pressed",String(!state.off.has(genres[i]))));
 [...fe.querySelectorAll(".chip")].forEach(b=>b.setAttribute("aria-pressed",String((b.dataset.f==="All"&&!state.fam)||b.dataset.f===state.fam)));
 const keep=r=>!state.off.has(r.genre)&&(!state.fam||r.families.includes(state.fam))&&(!state.sub||r.subgenres.includes(state.sub))
  &&(!state.charting||r.charts.length)&&(!state.q||(r.title+" "+r.developer+" "+r.links.map(l=>l.label).join(" ")+" "+r.tags.join(" ")+" "+r.raw_genres.join(" ")).toLowerCase().includes(state.q));
 let html="";
 genres.forEach(g=>{let rs=ROWS.filter(r=>r.genre===g&&keep(r));if(!rs.length)return;
  const s=state.sort[g];if(s){rs=[...rs].sort((a,b)=>{const x=val(a,s.k),y=val(b,s.k);return (x>y?1:x<y?-1:0)*s.d})}
  html+=`<section style="--c:${META.colors[g]}"><h2>${esc(g)} <small>${rs.length} game${rs.length>1?"s":""}</small></h2><div class="grid"><table><thead><tr>${cols.map(([k,l])=>`<th data-g="${esc(g)}" data-k="${k}">${l}${s&&s.k===k?(s.d>0?" ▲":" ▼"):""}</th>`).join("")}</tr></thead><tbody>${rs.map(r=>`<tr>${cols.map(([k])=>cell(r,k)).join("")}</tr>`).join("")}</tbody></table></div></section>`});
 const out=document.getElementById("out");
 out.innerHTML=html||`<p class="empty">No games match these filters. Use "Show everything" to clear them.</p>`;
 out.querySelectorAll("th").forEach(th=>th.onclick=()=>{const g=th.dataset.g,k=th.dataset.k,c=state.sort[g];
  state.sort[g]={k,d:c&&c.k===k?-c.d:(["title","platforms","subgenres","release_date"].includes(k)?1:-1)};render()});
}
render();
</script></body></html>"""
