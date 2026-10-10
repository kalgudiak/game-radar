"""The Game Radar dashboard: one accessible page that answers 'what launched, in what genres,
and what's getting traction' before showing the full list."""
import json
from collections import Counter, defaultdict

from .taxonomy import GENRES

# Mechanics a hybrid-casual mobile studio watches. Order = display order.
WATCH = ["Merge", "Match-3", "Sort & Organise", "Runner", "Hyper-casual", "Hybrid-casual", "Idle",
         "Squad / Idle RPG", "Survivors-like", "Tower Defense", "Auto-battler", "Gacha / Hero Collector",
         "Tycoon", ".io", "Roguelite", "Deckbuilder"]


CORE_STORES = {"Steam", "App Store", "Google Play", "Epic Games Store", "GOG", "PlayStation Store", "Xbox Store",
               "Microsoft Store", "Nintendo eShop", "Meta Quest Store", "IGDB"}


def itch_only(r):
    labels = {l["label"] for l in r.get("links") or r.get("l") or []}
    return not (labels & CORE_STORES)


def slim(r, seen=None):
    """Only the fields the page needs, to keep it light on phones."""
    return {
        "t": r["title"], "g": r["genre"], "s": r["subgenres"], "p": r["platforms"], "f": r["families"],
        "d": r["release_date"], "dev": r.get("developer") or "", "pr": r.get("price"),
        "cur": r.get("currency") or "", "free": bool(r.get("free")), "iap": bool(r.get("iap")),
        "ra": r.get("rating"), "rc": r.get("rating_count"), "in": r.get("installs"),
        "ch": r.get("charts") or [], "l": r.get("links") or [], "img": r.get("icon") or "",
        "desc": (r.get("description") or "")[:160], "seen": seen,
        "ab": r.get("appbrain") or [], "itch": itch_only(r),
    }


def aggregate(rows):
    """Per release-date counts of genres, sub-genres and platform families, both for all games
    ("all") and excluding itch.io-only uploads ("core")."""
    new = lambda: {"n": 0, "g": Counter(), "s": Counter(), "f": Counter()}
    agg = defaultdict(lambda: {"all": new(), "core": new()})
    for r in rows:
        d = r.get("release_date") or r.get("d")
        if not d:
            continue
        for bucket in (["all"] if itch_only(r) else ["all", "core"]):
            a = agg[d][bucket]
            a["n"] += 1
            a["g"][r.get("genre") or r.get("g")] += 1
            for s in r.get("subgenres") or r.get("s") or []:
                a["s"][s] += 1
            for f in r.get("families") or r.get("f") or []:
                a["f"][f] += 1
    plain = lambda v: {"n": v["n"], "g": dict(v["g"]), "s": dict(v["s"]), "f": dict(v["f"])}
    return {d: {k: plain(v) for k, v in b.items()} for d, b in sorted(agg.items())}


def render(rows, agg, meta):
    """rows: slim() dicts. agg: aggregate() output. meta: dict with updated, latest, csv, note, archive."""
    data = {"rows": rows, "agg": agg, "meta": meta, "genres": GENRES, "watch": WATCH}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return TEMPLATE.replace("__DATA__", payload)


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Game Radar: what launched this week</title>
<meta name="description" content="Daily dashboard of new game releases across Steam, iOS, Google Play and itch.io, by genre.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:ital,wght@0,400;0,700;1,400&family=Archivo:wdth,wght@75..100,600..800&display=swap" rel="stylesheet">
<style>
:root{
 --bg:#F4F5F7;--panel:#FFFFFF;--ink:#14171F;--muted:#505868;--rule:#D5DAE3;--soft:#EEF1F5;
 --accent:#1F4FD1;--accent-ink:#FFFFFF;--accent-soft:#E3EAFB;--bar:#1F4FD1;--bar-off:#B9C6E8;
 --up:#11703A;--down:#B3261E;--focus:#F5B700;--chip:#FFFFFF;
 box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
 --bg:#0F1218;--panel:#181C24;--ink:#EDEFF4;--muted:#A9B1C2;--rule:#2C3240;--soft:#20252F;
 --accent:#8EADFF;--accent-ink:#0F1218;--accent-soft:#1E2A47;--bar:#8EADFF;--bar-off:#3A4560;
 --up:#6FD69A;--down:#FF8F87;--focus:#FFD54A;--chip:#181C24}}
:root[data-theme="dark"]{
 --bg:#0F1218;--panel:#181C24;--ink:#EDEFF4;--muted:#A9B1C2;--rule:#2C3240;--soft:#20252F;
 --accent:#8EADFF;--accent-ink:#0F1218;--accent-soft:#1E2A47;--bar:#8EADFF;--bar-off:#3A4560;
 --up:#6FD69A;--down:#FF8F87;--focus:#FFD54A;--chip:#181C24}
html{scroll-padding-top:env(safe-area-inset-top,0px)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:1rem/1.55 "Atkinson Hyperlegible",system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px;border-radius:4px}
.skip{position:absolute;left:-999px;top:8px;background:var(--panel);color:var(--ink);padding:10px 14px;border-radius:6px;z-index:10}
.skip:focus{left:12px}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.wrap{max-width:1180px;margin:0 auto;padding:0 clamp(14px,3.5vw,32px)}
header.top{padding:28px 0 6px}
.eyebrow{font-weight:700;color:var(--muted);font-size:.9rem;letter-spacing:.02em;margin:0}
h1,h2,h3{font-family:Archivo,"Arial Narrow",system-ui,sans-serif;font-stretch:82%;line-height:1.1;margin:0}
h1{font-size:clamp(2rem,5.2vw,3.4rem);font-weight:800;margin:6px 0 8px;letter-spacing:-.01em}
h2{font-size:1.55rem;font-weight:800;margin-bottom:4px}
h3{font-size:1.15rem;font-weight:700}
.sub{color:var(--muted);margin:0;max-width:70ch}
.range{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 6px;align-items:center}
.range span{font-weight:700;margin-right:4px}
.toggle{display:inline-flex;gap:8px;align-items:center;flex-wrap:wrap;margin:4px 0 0;min-height:44px;cursor:pointer}
.toggle input{width:20px;height:20px;accent-color:var(--accent)}
.seg{border:1px solid var(--rule);background:var(--chip);color:var(--ink);border-radius:999px;padding:9px 16px;font:inherit;font-size:.95rem;cursor:pointer;min-height:44px}
.seg[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:var(--accent-ink);font-weight:700}
section{margin-top:30px}
.panel{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:18px clamp(14px,2.4vw,22px)}
.lede{color:var(--muted);margin:2px 0 14px;font-size:.95rem}
.takeaways{list-style:none;margin:0;padding:0;display:grid;gap:10px}
.takeaways li{padding-left:28px;position:relative;font-size:1.06rem}
.takeaways li::before{content:"";position:absolute;left:6px;top:.62em;width:9px;height:9px;border-radius:2px;background:var(--accent)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.stat{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:14px 16px}
.stat b{display:block;font-family:Archivo,sans-serif;font-stretch:82%;font-size:2.2rem;line-height:1.05}
.stat span{color:var(--muted);font-size:.92rem}
.delta{font-size:.85rem;font-weight:700;display:block;margin-top:4px}
.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--muted)}
.grid2{display:grid;grid-template-columns:1.25fr 1fr;gap:16px}
@media (max-width:860px){.grid2{grid-template-columns:1fr}}
.bars{display:grid;gap:6px;margin:0;padding:0;list-style:none}
.barbtn{all:unset;box-sizing:border-box;display:grid;grid-template-columns:minmax(110px,170px) 1fr 132px;gap:10px;align-items:center;width:100%;padding:6px 6px;border-radius:6px;cursor:pointer;min-height:40px}
.barbtn:hover{background:var(--soft)}
.barbtn:focus-visible{outline:3px solid var(--focus)}
.barbtn[aria-pressed=true]{background:var(--accent-soft)}
.barbtn .name{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.track{height:14px;background:var(--soft);border-radius:4px;overflow:hidden}
.fill{height:100%;background:var(--bar);border-radius:4px}
.barbtn[aria-pressed=false].dim .fill{background:var(--bar-off)}
.num{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap;font-size:.93rem}
.num small{color:var(--muted)}
.chart{width:100%;height:auto;display:block}
.chart text{fill:var(--muted);font:12px "Atkinson Hyperlegible",sans-serif}
.chart .b{fill:var(--bar)}
details.tbl{margin-top:8px}
details summary{cursor:pointer;color:var(--accent);font-weight:700;min-height:32px;display:inline-flex;align-items:center}
table{border-collapse:collapse;width:100%;font-size:.92rem}
th,td{padding:6px 8px;border-bottom:1px solid var(--rule);text-align:left}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1px solid var(--rule);background:var(--chip);color:var(--ink);border-radius:8px;padding:8px 12px;font:inherit;font-size:.95rem;cursor:pointer;min-height:44px;display:inline-flex;gap:8px;align-items:baseline}
.chip b{font-variant-numeric:tabular-nums}
.chip[aria-pressed=true]{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.chip.zero{color:var(--muted)}
.chip .delta{display:inline;margin:0}
.chip[aria-pressed=true] .delta{color:inherit}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--rule);border-radius:10px;overflow:hidden;display:flex;flex-direction:column}
.thumb{aspect-ratio:460/215;background:var(--soft);display:flex;align-items:center;justify-content:center;font:800 2rem Archivo,sans-serif;color:var(--muted);overflow:hidden}
.thumb img{width:100%;height:100%;object-fit:cover;display:block}
.card .body{padding:12px 14px 14px;display:flex;flex-direction:column;gap:6px;flex:1}
.card h3{font-size:1.12rem}
.meta{color:var(--muted);font-size:.9rem}
.why{font-weight:700;font-size:.93rem}
.tags{display:flex;flex-wrap:wrap;gap:4px}
.tag{background:var(--soft);border-radius:4px;padding:1px 7px;font-size:.82rem}
.tag.g{background:var(--accent-soft);font-weight:700}
.links{display:flex;flex-wrap:wrap;gap:6px;margin-top:auto;padding-top:6px}
.links a{border:1px solid var(--rule);border-radius:6px;padding:6px 10px;font-size:.86rem;text-decoration:none;font-weight:700;min-height:36px;display:inline-flex;align-items:center}
.links a:hover{border-color:var(--accent)}
.filters{display:grid;grid-template-columns:2fr repeat(4,1fr) 1fr;gap:10px;align-items:end}
@media (max-width:980px){.filters{grid-template-columns:1fr 1fr}}
@media (max-width:520px){.filters{grid-template-columns:1fr}}
.field label{display:block;font-weight:700;font-size:.88rem;margin-bottom:4px}
.field input,.field select{width:100%;font:inherit;font-size:1rem;padding:9px 10px;border:1px solid var(--rule);border-radius:8px;background:var(--panel);color:var(--ink);min-height:44px}
.status{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:space-between;margin:14px 0 8px}
.status p{margin:0;font-weight:700}
.linkbtn{background:none;border:0;color:var(--accent);font:inherit;font-weight:700;text-decoration:underline;cursor:pointer;padding:6px 2px;min-height:36px}
.list{list-style:none;margin:0;padding:0;display:grid;gap:8px}
.row{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:12px;display:grid;grid-template-columns:120px 1fr auto;gap:14px;align-items:start}
.row .thumb{width:120px;border-radius:6px;font-size:1.4rem}
.row h3{font-size:1.08rem}
.row .right{text-align:right;min-width:150px}
@media (max-width:640px){.row{grid-template-columns:84px 1fr}.row .thumb{width:84px}.row .right{grid-column:1/-1;text-align:left;min-width:0}}
.more{display:block;margin:14px auto 0;font:inherit;font-weight:700;padding:12px 22px;border-radius:8px;border:1px solid var(--accent);background:var(--panel);color:var(--accent);cursor:pointer;min-height:44px}
footer{margin:46px 0 30px;color:var(--muted);font-size:.92rem}
footer h2{color:var(--ink);font-size:1.2rem;margin:20px 0 6px}
footer dl{display:grid;grid-template-columns:max-content 1fr;gap:6px 14px;margin:0}
footer dt{font-weight:700;color:var(--ink)}footer dd{margin:0}
.empty{padding:24px;text-align:center;color:var(--muted)}
@media (prefers-reduced-motion:no-preference){.fill{transition:width .25s ease}}
</style>
</head>
<body>
<a class="skip" href="#games">Skip to the list of games</a>
<div class="wrap">
<header class="top">
  <p class="eyebrow" id="updated"></p>
  <h1 id="headline">New games</h1>
  <p class="sub" id="subhead"></p>
  <div class="range" role="group" aria-label="Release date range"><span>Show games released in:</span></div>
  <label class="toggle"><input type="checkbox" id="itch"> Include itch.io uploads <span class="meta">(indie, game-jam and work-in-progress projects, not store releases)</span></label>
</header>
<main>
  <section aria-labelledby="h-take">
    <h2 id="h-take">The short version</h2>
    <p class="lede" id="take-lede"></p>
    <div class="panel"><ul class="takeaways" id="takeaways"></ul></div>
  </section>

  <section aria-labelledby="h-stats">
    <h2 id="h-stats" class="sr">Key numbers</h2>
    <div class="stats" id="stats"></div>
  </section>

  <section aria-labelledby="h-genres">
    <div class="grid2">
      <div class="panel">
        <h2 id="h-genres">Genres</h2>
        <p class="lede">Ranked by number of releases. Select a genre to filter everything on this page.</p>
        <ul class="bars" id="genre-bars"></ul>
      </div>
      <div class="panel">
        <h2 id="h-days">Releases per day</h2>
        <p class="lede" id="days-lede"></p>
        <svg class="chart" id="days-chart" role="img"></svg>
        <details class="tbl"><summary>Show as a table</summary><div id="days-table"></div></details>
        <h2 id="h-plat" style="margin-top:22px">Platforms</h2>
        <p class="lede">A game on several platforms counts once on each.</p>
        <ul class="bars" id="plat-bars"></ul>
      </div>
    </div>
  </section>

  <section aria-labelledby="h-watch">
    <h2 id="h-watch">Hybrid-casual watch</h2>
    <p class="lede">Mechanics we track for mobile. Count of new games using each one, with the change against the same number of days before. Select one to filter.</p>
    <div class="chips" id="watch" role="group" aria-labelledby="h-watch"></div>
  </section>

  <section aria-labelledby="h-top">
    <h2 id="h-top">Worth a look</h2>
    <p class="lede">New games with the most early traction: player ratings, installs and App Store chart positions.</p>
    <div class="cards" id="top"></div>
  </section>

  <section aria-labelledby="h-all" id="games" tabindex="-1">
    <h2 id="h-all">All new games</h2>
    <div class="panel">
      <div class="filters">
        <div class="field"><label for="q">Search</label><input id="q" type="search" placeholder="Title, developer or mechanic" autocomplete="off"></div>
        <div class="field"><label for="fg">Genre</label><select id="fg"></select></div>
        <div class="field"><label for="fp">Platform</label><select id="fp"></select></div>
        <div class="field"><label for="fs">Mechanic</label><select id="fs"></select></div>
        <div class="field"><label for="fc">Price</label><select id="fc"><option value="">Any price</option><option value="free">Free</option><option value="paid">Paid</option></select></div>
        <div class="field"><label for="so">Sort by</label><select id="so"><option value="traction">Most traction</option><option value="new">Newest</option><option value="az">Name A–Z</option></select></div>
      </div>
    </div>
    <div class="status"><p id="count" aria-live="polite"></p><button class="linkbtn" id="clear" type="button">Clear all filters</button></div>
    <ul class="list" id="list"></ul>
    <button class="more" id="more" type="button">Show more games</button>
  </section>
</main>
<footer>
  <h2>How to read this dashboard</h2>
  <dl>
    <dt>New game</dt><dd>A game whose first release date falls in the chosen range. Updates, DLC and ports are left out.</dd>
    <dt>Genre</dt><dd>Each game gets one main genre. When a game fits several, the most specific wins (Roguelike over Action, Puzzle over Casual). "Unclassified" means the store gave no usable genre.</dd>
    <dt>Mechanic</dt><dd>Mechanics found in the store genres, tags and title, such as Merge, Runner or Idle. A game can have several.</dd>
    <dt>Traction</dt><dd>Early signals: player ratings or reviews, Google Play installs, App Store chart positions, and Google Play new-game rankings by installs and trend (from AppBrain). Very new games often have none yet.</dd>
    <dt>Comparisons</dt><dd>"Up" or "down" compares the chosen range with the same number of days just before it.</dd>
    <dt>Sources</dt><dd>Steam (every new release), App Store (new games on the US, India, UK and Japan charts), Google Play (new games on AppBrain's 30-day new-release lists for all 17 game categories, with dates and installs from Google Play), and consoles through IGDB when its keys are set. itch.io uploads are hidden unless you tick the box, because many are prototypes, jam entries or asset packs. Updated every morning at 07:00 IST.</dd>
  </dl>
  <p id="footer-links"></p>
</footer>
</div>
<script>
const D=__DATA__;
const rows=D.rows, agg=D.agg, meta=D.meta;
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=n=>Number(n).toLocaleString("en-IN");
const DAYS=Object.keys(agg).sort();
const LAST=DAYS[DAYS.length-1]||"";
const day=s=>new Date(s+"T00:00:00Z");
const shift=(s,n)=>{const d=day(s);d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10)};
const nice=s=>day(s).toLocaleDateString("en-GB",{day:"numeric",month:"short",timeZone:"UTC"});
const FEED={topfree:"Top Free",topgrossing:"Top Grossing",toppaid:"Top Paid",newfree:"New Free",newpaid:"New Paid"};
const STORES=new Set(["Steam","App Store","Google Play","itch.io","Epic Games Store","GOG","PlayStation Store","Xbox Store","Microsoft Store","Nintendo eShop","Meta Quest Store"]);
const GN=g=>g==="Other"?"Unclassified":g;
const FAMNAME={PC:"PC",Console:"Console",iOS:"iOS",Android:"Android",Web:"Web / itch.io",VR:"VR",Other:"Other"};

// ---------- traction
function bestChart(r){let best=null;for(const c of r.ch){const m=c.match(/^(\w+)\/(\w+)\/\d+#(\d+)$/);if(!m)continue;const rank=+m[3],f=m[2].replace("applications","");
 if(!best||rank<best.rank)best={rank,cc:m[1].toUpperCase(),feed:FEED[f]||f}}return best}
const ABSORT={popular:"most installed",trending:"trending"};
const ABCAT=c=>c==="games"?"":c.replace(/-games$/,"").replace(/-/g," ")+" ";
function bestAB(r){let best=null;for(const c of r.ab||[]){const m=c.match(/^([\w-]+)\/([\w-]+)#(\d+)$/);if(!m)continue;const rank=+m[3];
 if(!best||rank<best.rank||(rank===best.rank&&m[2]==="games"))best={rank,sort:ABSORT[m[1]]||m[1],cat:m[2]}}return best}
rows.forEach(r=>{r.bc=bestChart(r);r.ba=bestAB(r);
 r.score=Math.log10(1+(r.rc||0))+0.6*Math.log10(1+(r.in||0))+(r.bc?1.5*(3-Math.log10(r.bc.rank)):0)+(r.ba?1.2*(2-Math.log10(r.ba.rank)):0)});
function why(r){const p=[];
 if(r.bc)p.push(`#${r.bc.rank} on App Store ${r.bc.feed} (${r.bc.cc})`);
 if(r.ba)p.push(`#${r.ba.rank} ${r.ba.sort} new ${ABCAT(r.ba.cat)}game on Google Play`);
 const mobile=r.p.includes("iOS")||r.p.includes("Android");
 if(r.rc)p.push(mobile?`${fmt(r.rc)} ratings${r.ra!=null?`, ${(r.ra/20).toFixed(1)} out of 5`:""}`:`${fmt(r.rc)} reviews${r.ra!=null?`, ${Math.round(r.ra)}% positive`:""}`);
 if(r.in)p.push(`${fmt(r.in)} installs`);
 return p.join(" · ")||"No ratings yet"}
function price(r){return r.free||r.pr===0?"Free":r.pr!=null?`${r.cur==="USD"?"$":r.cur+" "}${r.pr}`:""}

// ---------- state
const RANGES=[[1,"Latest day"],[3,"3 days"],[7,"7 days"],[14,"14 days"]];
const st={range:7,genre:"",fam:"",sub:"",q:"",price:"",sort:"traction",shown:30,itch:false};
const vis=r=>st.itch||!r.itch;
const avail=DAYS.length?Math.round((day(LAST)-day(DAYS[0]))/864e5)+1:0;

function inRange(d,n,end=LAST){return d&&d<=end&&d>shift(end,-n)}
function filtered(opts={}){return rows.filter(r=>vis(r)&&inRange(r.d,st.range)&&(!st.genre||r.g===st.genre)&&(!st.fam||r.f.includes(st.fam))
 &&(opts.ignoreSub||!st.sub||r.s.includes(st.sub))&&(!st.price||(st.price==="free"?(r.free||r.pr===0):!(r.free||r.pr===0)))
 &&(!st.q||(r.t+" "+r.dev+" "+r.s.join(" ")+" "+r.g).toLowerCase().includes(st.q)))}
// counts from aggregates over a window ending at `end`
function sumAgg(n,end,key,filterGenre=true){const out={};let tot=0;
 for(const d of DAYS){if(!inRange(d,n,end))continue;const a=agg[d][st.itch?"all":"core"];
  if(key==="n"){tot+=a.n;continue}
  for(const[k,v]of Object.entries(a[key]))out[k]=(out[k]||0)+v}
 return key==="n"?tot:out}
function change(cur,prev){if(prev<5&&cur<5)return null;if(!prev)return{txt:"new",cls:"up",word:"new"};
 const pct=Math.round((cur-prev)/prev*100);if(Math.abs(pct)<5)return{txt:"about the same",cls:"flat",word:"flat"};
 return{txt:`${pct>0?"▲ up":"▼ down"} ${Math.abs(pct)}%`,cls:pct>0?"up":"down",word:pct>0?"up":"down",pct}}
const RUNS=meta.runs||1;
const hasPrev=()=>RUNS>=st.range*2&&avail>=st.range*2;

// ---------- header
function header(){
 $("updated").textContent=meta.updated?`Updated ${meta.updated}`:"";
 const list=filtered();
 const rangeTxt=st.range===1?`on ${nice(LAST)}`:`from ${nice(shift(LAST,-st.range+1))} to ${nice(LAST)}`;
 $("headline").textContent=`${fmt(list.length)} new game${list.length===1?"":"s"} ${st.range===1?"on "+nice(LAST):"in "+st.range+" days"}`;
 const bits=[];if(st.genre)bits.push(GN(st.genre));if(st.fam)bits.push(FAMNAME[st.fam]);if(st.sub)bits.push(st.sub);
 $("subhead").textContent=`Released ${rangeTxt}${bits.length?", filtered to "+bits.join(" + "):""}. ${meta.note||""}`;
}
// ---------- takeaways
function takeaways(){
 const list=filtered(), n=list.length, out=[];
 if(!n){$("takeaways").innerHTML=`<li>No games match these filters.</li>`;return}
 const perDay=n/st.range;
 out.push(`<strong>${fmt(n)}</strong> new games${st.range>1?`, about <strong>${fmt(Math.round(perDay))} a day</strong>`:""}.`);
 const g=Object.entries(count(list,r=>[r.g])).filter(x=>x[0]!=="Other").sort((a,b)=>b[1]-a[1]);
 if(!st.genre&&g.length)out.push(`Biggest genre: <strong>${esc(GN(g[0][0]))}</strong> with ${fmt(g[0][1])} games (${Math.round(g[0][1]/n*100)}%)${g[1]?`, then ${esc(GN(g[1][0]))} (${fmt(g[1][1])})`:""}.`);
 if(hasPrev()&&!st.q&&!st.price&&!st.fam&&!st.sub){
  const cur=sumAgg(st.range,LAST,"g"),prev=sumAgg(st.range,shift(LAST,-st.range),"g");
  const moves=Object.keys({...cur,...prev}).map(k=>({k,c:cur[k]||0,p:prev[k]||0})).filter(x=>x.p>=8||x.c>=8)
   .map(x=>({...x,pct:x.p?Math.round((x.c-x.p)/x.p*100):999})).sort((a,b)=>b.pct-a.pct);
  if(moves.length&&moves[0].pct>=15)out.push(`Rising fastest: <strong>${esc(moves[0].k)}</strong>, up ${moves[0].pct===999?"from zero":moves[0].pct+"%"} on the ${st.range} days before (${moves[0].p} → ${moves[0].c}).`);
  const fall=moves[moves.length-1];if(fall&&fall.pct<=-15)out.push(`Falling most: <strong>${esc(fall.k)}</strong>, down ${Math.abs(fall.pct)}% (${fall.p} → ${fall.c}).`);
 }
 const mob=list.filter(r=>r.f.includes("iOS")||r.f.includes("Android"));
 if(mob.length){const mg=Object.entries(count(mob,r=>[r.g])).filter(x=>x[0]!=="Other").sort((a,b)=>b[1]-a[1])[0];
  if(mg)out.push(`<strong>${fmt(mob.length)}</strong> are on mobile; the most common mobile genre is <strong>${esc(mg[0])}</strong> (${mg[1]}).`)}
 const subs=Object.entries(count(list,r=>r.s.filter(s=>D.watch.includes(s)))).sort((a,b)=>b[1]-a[1]);
 if(subs.length&&!st.sub)out.push(`Most used hybrid-casual mechanic: <strong>${esc(subs[0][0])}</strong> (${subs[0][1]} games)${subs[1]?`, then ${esc(subs[1][0])} (${subs[1][1]})`:""}.`);
 const top=[...list].sort((a,b)=>b.score-a.score)[0];
 if(top&&top.score>0)out.push(`Strongest early traction: <strong>${esc(top.t)}</strong> (${esc(GN(top.g))}): ${esc(why(top))}.`);
 $("takeaways").innerHTML=out.map(x=>`<li>${x}</li>`).join("");
 $("take-lede").textContent=hasPrev()?`Ups and downs compare with the ${st.range} days before.`:`Week-on-week comparisons switch on after ${st.range*2} daily updates (${RUNS} so far), so early backfilled data can't distort them.`;
}
function count(list,fn){const o={};list.forEach(r=>fn(r).forEach(k=>o[k]=(o[k]||0)+1));return o}

// ---------- stats
function stats(){
 const list=filtered(),n=list.length;
 const prevRows=hasPrev()?sumAgg(st.range,shift(LAST,-st.range),"f"):null;
 const curF=count(list,r=>r.f);
 const card=(val,label,cur,prev)=>{let d="";if(prev!=null){const c=change(cur,prev);if(c)d=`<span class="delta ${c.cls}">${c.txt}<span class="sr"> compared with the previous ${st.range} days</span></span>`}
  return `<div class="stat"><b>${fmt(val)}</b><span>${label}</span>${d}</div>`};
 const plain=!st.genre&&!st.q&&!st.price&&!st.sub&&!st.fam;
 const prevTotal=hasPrev()&&plain?sumAgg(st.range,shift(LAST,-st.range),"n"):null;
 const mob=(curF.iOS||0)+(curF.Android||0), pc=(curF.PC||0)+(curF.Console||0);
 $("stats").innerHTML=card(n,"new games",n,prevTotal)
  +card(mob,"on mobile (iOS + Android)",mob,plain&&prevRows?(prevRows.iOS||0)+(prevRows.Android||0):null)
  +card(pc,"on PC or console",pc,plain&&prevRows?(prevRows.PC||0)+(prevRows.Console||0):null)
  +(st.itch?card(curF.Web||0,"web / itch.io",curF.Web||0,plain&&prevRows?(prevRows.Web||0):null):"")
  +card(list.filter(r=>r.bc||r.ba).length,"ranking on new-game charts (App Store, Google Play)",0,null);
}
// ---------- bars
function bars(el,entries,total,selected,onPick,prevMap,labeler=x=>x){
 const max=Math.max(1,...entries.map(e=>e[1]));
 el.innerHTML=entries.map(([k,v])=>{const pct=Math.round(v/total*100);let d="";
  if(prevMap){const c=change(v,prevMap[k]||0);if(c&&c.word!=="flat")d=` <small class="${c.cls}">${c.txt}</small>`}
  const on=selected===k;
  return `<li><button type="button" class="barbtn${selected&&!on?" dim":""}" aria-pressed="${on}" data-k="${esc(k)}" aria-label="${esc(labeler(k))}: ${v} games, ${pct} percent${d?". "+d.replace(/<[^>]+>/g,""):""}. ${on?"Selected, select again to clear":"Select to filter"}">
   <span class="name">${esc(labeler(k))}</span><span class="track" aria-hidden="true"><span class="fill" style="display:block;width:${v/max*100}%"></span></span>
   <span class="num" aria-hidden="true">${fmt(v)} <small>${pct}%</small>${d}</span></button></li>`}).join("");
 el.querySelectorAll("button").forEach(b=>b.onclick=()=>onPick(b.dataset.k));
}
function genreBars(){
 const base=rows.filter(r=>vis(r)&&inRange(r.d,st.range)&&(!st.fam||r.f.includes(st.fam))&&(!st.sub||r.s.includes(st.sub)));
 const c=count(base,r=>[r.g]);const e=Object.entries(c).sort((a,b)=>b[1]-a[1]);
 const plain=!st.fam&&!st.sub;
 bars($("genre-bars"),e,base.length||1,st.genre,k=>{st.genre=st.genre===k?"":k;sync()},hasPrev()&&plain?sumAgg(st.range,shift(LAST,-st.range),"g"):null,GN);
}
function platBars(){
 const base=rows.filter(r=>vis(r)&&inRange(r.d,st.range)&&(!st.genre||r.g===st.genre)&&(!st.sub||r.s.includes(st.sub)));
 const c=count(base,r=>r.f);const e=Object.entries(c).sort((a,b)=>b[1]-a[1]);
 bars($("plat-bars"),e,base.length||1,st.fam,k=>{st.fam=st.fam===k?"":k;sync()},null,k=>FAMNAME[k]||k);
}
// ---------- per-day chart
function daysChart(){
 const n=Math.max(st.range,7), days=[];for(let i=n-1;i>=0;i--)days.push(shift(LAST,-i));
 const list=rows.filter(r=>vis(r)&&(!st.genre||r.g===st.genre)&&(!st.fam||r.f.includes(st.fam))&&(!st.sub||r.s.includes(st.sub)));
 const c={};list.forEach(r=>{if(r.d)c[r.d]=(c[r.d]||0)+1});
 const vals=days.map(d=>c[d]||0),max=Math.max(1,...vals);
 const W=560,H=200,pad=34,bw=(W-pad-8)/days.length;
 let s=`<title id="dt">Releases per day</title><desc id="dd">${days.map((d,i)=>`${nice(d)}: ${vals[i]}`).join(", ")}</desc>`;
 for(let i=0;i<=3;i++){const y=H-((H-20)*i/3),v=Math.round(max*i/3);s+=`<line x1="${pad}" x2="${W}" y1="${y}" y2="${y}" stroke="currentColor" opacity=".15"/><text x="${pad-6}" y="${y+4}" text-anchor="end">${v}</text>`}
 days.forEach((d,i)=>{const h=(H-20)*vals[i]/max,x=pad+4+i*bw,inR=inRange(d,st.range);
  s+=`<rect class="b" x="${x}" y="${H-h}" width="${Math.max(2,bw-4)}" height="${h}" opacity="${inR?1:.35}"><title>${nice(d)}: ${vals[i]}</title></rect>`;
  if(days.length<=14||i%2===0)s+=`<text x="${x+bw/2-2}" y="${H+16}" text-anchor="middle">${day(d).getUTCDate()}</text>`});
 const svg=$("days-chart");svg.setAttribute("viewBox",`0 0 ${W} ${H+24}`);svg.setAttribute("aria-labelledby","dt dd");svg.style.color="var(--ink)";svg.innerHTML=s;
 $("days-lede").textContent=`By store release date${st.genre?", "+st.genre+" only":""}. Faded bars are outside the chosen range. The latest day may still be filling in.`;
 $("days-table").innerHTML=`<table><thead><tr><th scope="col">Date</th><th scope="col" class="n">New games</th></tr></thead><tbody>${days.map((d,i)=>`<tr><td>${nice(d)}</td><td class="n">${vals[i]}</td></tr>`).join("")}</tbody></table>`;
}
// ---------- watch
function watchChips(){
 const base=rows.filter(r=>vis(r)&&inRange(r.d,st.range)&&(!st.genre||r.g===st.genre)&&(!st.fam||r.f.includes(st.fam)));
 const c=count(base,r=>r.s);const prev=hasPrev()&&!st.genre&&!st.fam?sumAgg(st.range,shift(LAST,-st.range),"s"):null;
 $("watch").innerHTML=D.watch.map(k=>{const v=c[k]||0;let d="";if(prev){const ch=change(v,prev[k]||0);if(ch&&ch.word!=="flat")d=`<span class="delta ${ch.cls}">${ch.txt}</span>`}
  return `<button type="button" class="chip${v?"":" zero"}" aria-pressed="${st.sub===k}" data-k="${esc(k)}">${esc(k)} <b>${v}</b>${d}</button>`}).join("");
 $("watch").querySelectorAll("button").forEach(b=>b.onclick=()=>{st.sub=st.sub===b.dataset.k?"":b.dataset.k;sync()});
}
// ---------- cards & list
const initials=t=>esc((t||"?").replace(/[^A-Za-z0-9 ]/g,"").split(/\s+/).filter(Boolean).slice(0,2).map(w=>w[0]).join("").toUpperCase()||"?");
function thumb(r){return `<div class="thumb" aria-hidden="true">${r.img?`<img src="${esc(r.img)}" alt="" loading="lazy" onerror="this.parentNode.textContent='${initials(r.t)}'">`:initials(r.t)}</div>`}
function links(r){const L=r.l.slice(0,4);return `<div class="links">${L.map(l=>`<a href="${esc(l.url)}" target="_blank" rel="noopener" aria-label="${esc(r.t)} on ${esc(l.label)} (opens in a new tab)">${esc(l.label)}</a>`).join("")}</div>`}
function tags(r){return `<div class="tags"><span class="tag g">${esc(GN(r.g))}</span>${r.s.slice(0,3).map(s=>`<span class="tag">${esc(s)}</span>`).join("")}</div>`}
function topPicks(){
 const list=filtered().filter(r=>r.score>0).sort((a,b)=>b.score-a.score).slice(0,8);
 $("top").innerHTML=list.length?list.map(r=>`<article class="card">${thumb(r)}<div class="body"><h3>${esc(r.t)}</h3>
  <p class="meta" style="margin:0">${esc([r.dev,r.p.join(", "),price(r)].filter(Boolean).join(" · "))}</p>${tags(r)}<p class="why" style="margin:0">${esc(why(r))}</p>${links(r)}</div></article>`).join("")
  :`<p class="empty">No traction data yet for these games.</p>`;
}
function sorted(list){const s=st.sort;return [...list].sort(s==="new"?(a,b)=>(b.d||"").localeCompare(a.d||"")||b.score-a.score:s==="az"?(a,b)=>a.t.localeCompare(b.t):(a,b)=>b.score-a.score||(b.d||"").localeCompare(a.d||""))}
function renderList(){
 const all=sorted(filtered()),show=all.slice(0,st.shown);
 $("count").textContent=all.length?`Showing ${fmt(show.length)} of ${fmt(all.length)} games`:"No games match these filters";
 $("list").innerHTML=show.map(r=>`<li class="row">${thumb(r)}<div><h3>${esc(r.t)}</h3>
   <p class="meta" style="margin:2px 0 6px">${esc([r.dev,"Released "+nice(r.d)].filter(Boolean).join(" · "))}</p>${tags(r)}
   ${r.desc?`<p class="meta" style="margin:6px 0 0">${esc(r.desc)}</p>`:""}</div>
   <div class="right"><p class="meta" style="margin:0">${esc(r.p.join(", "))}</p><p style="margin:2px 0;font-weight:700">${esc(price(r))}${r.iap?" + in-app purchases":""}</p>
   <p class="meta" style="margin:0 0 4px">${esc(why(r))}</p>${links(r)}</div></li>`).join("");
 $("more").hidden=all.length<=st.shown;
 $("clear").hidden=!(st.genre||st.fam||st.sub||st.q||st.price);
}
// ---------- controls
function controls(){
 const rg=document.querySelector(".range");
 RANGES.forEach(([n,label])=>{if(n>1&&avail&&n>Math.max(avail,1)&&n!==7)return;const b=document.createElement("button");b.type="button";b.className="seg";b.textContent=label;b.dataset.n=n;
  b.onclick=()=>{st.range=n;st.shown=30;sync()};rg.appendChild(b)});
 const allG=[...new Set(rows.map(r=>r.g))].sort((a,b)=>D.genres.indexOf(a)-D.genres.indexOf(b));
 $("fg").innerHTML=`<option value="">All genres</option>`+allG.map(g=>`<option value="${esc(g)}">${esc(GN(g))}</option>`).join("");
 const fams=[...new Set(rows.flatMap(r=>r.f))];
 $("fp").innerHTML=`<option value="">All platforms</option>`+fams.map(f=>`<option value="${esc(f)}">${esc(FAMNAME[f]||f)}</option>`).join("");
 const subs=Object.entries(count(rows,r=>r.s)).sort((a,b)=>b[1]-a[1]).map(x=>x[0]);
 $("fs").innerHTML=`<option value="">All mechanics</option>`+subs.map(s=>`<option>${esc(s)}</option>`).join("");
 $("fg").onchange=e=>{st.genre=e.target.value;sync()};$("fp").onchange=e=>{st.fam=e.target.value;sync()};
 $("fs").onchange=e=>{st.sub=e.target.value;sync()};$("fc").onchange=e=>{st.price=e.target.value;sync()};
 $("so").onchange=e=>{st.sort=e.target.value;sync()};
 $("itch").onchange=e=>{st.itch=e.target.checked;st.shown=30;sync()};
 let t;$("q").oninput=e=>{clearTimeout(t);t=setTimeout(()=>{st.q=e.target.value.trim().toLowerCase();st.shown=30;sync()},200)};
 $("more").onclick=()=>{const first=st.shown;st.shown+=30;renderList();const li=$("list").children[first];if(li){li.setAttribute("tabindex","-1");li.focus()}};
 $("clear").onclick=()=>{Object.assign(st,{genre:"",fam:"",sub:"",q:"",price:"",shown:30});$("q").value="";sync();$("q").focus()};
 const fl=[];if(meta.csv)fl.push(`<a href="${esc(meta.csv)}" download>Download these games as CSV</a>`);if(meta.repo)fl.push(`<a href="${esc(meta.repo)}">Source and history on GitHub</a>`);
 $("footer-links").innerHTML=fl.join(" · ");
}
function sync(){
 document.querySelectorAll(".seg").forEach(b=>b.setAttribute("aria-pressed",String(+b.dataset.n===st.range)));
 $("fg").value=st.genre;$("fp").value=st.fam;$("fs").value=st.sub;$("fc").value=st.price;$("so").value=st.sort;
 header();takeaways();stats();genreBars();platBars();daysChart();watchChips();topPicks();renderList();
}
if(!rows.length){document.querySelector("main").innerHTML=`<p class="empty">No games collected yet. The first daily run fills this in.</p>`}
else{if(avail<7)st.range=avail>=3?3:1;controls();sync()}
</script>
</body>
</html>"""
