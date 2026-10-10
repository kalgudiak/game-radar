"""Steam: the 'newest releases' search listing, then appdetails + review summary per new app.
Optional SteamSpy enrichment adds community tags, which drive much better genre splits."""
import html as htmllib
import re

from ..dates import parse_date
from ..links import add_link
from ..models import Game
from ..taxonomy import norm_platform
from .base import Source, log

SEARCH = "https://store.steampowered.com/search/results/"
DETAILS = "https://store.steampowered.com/api/appdetails"
REVIEWS = "https://store.steampowered.com/appreviews/{}"
SPY = "https://steamspy.com/api.php"
HOVER = "https://store.steampowered.com/apphoverpublic/{}"
_HOVER_TAG = re.compile(r'class="app_tag"[^>]*>\s*([^<]+?)\s*<')

_ROW = re.compile(r'<a[^>]+data-ds-appid="(\d+)"[^>]*>(.*?)</a>', re.S)
_TITLE = re.compile(r'<span class="title">(.*?)</span>', re.S)
_RELEASED = re.compile(r'class="[^"]*search_released[^"]*"[^>]*>\s*([^<]*?)\s*</div>', re.S)
_TAG = re.compile(r"<[^>]+>")
_MODES = {"Single-player", "Multi-player", "PvP", "Online PvP", "Shared/Split Screen PvP", "Co-op",
          "Online Co-op", "Shared/Split Screen Co-op", "MMO", "Cross-Platform Multiplayer"}


def parse_search(results_html):
    out = []
    for appid, inner in _ROW.findall(results_html or ""):
        t = _TITLE.search(inner)
        r = _RELEASED.search(inner)
        out.append((appid, htmllib.unescape(t.group(1).strip()) if t else "",
                    parse_date(r.group(1)) if r else None))
    return out


def parse_details(appid, d):
    if d.get("type") != "game":
        return None
    rd = d.get("release_date") or {}
    if rd.get("coming_soon"):
        return None
    rdate = parse_date(rd.get("date"))
    po = d.get("price_overview") or {}
    cats = [c.get("description") for c in d.get("categories") or []]
    langs = [x.strip() for x in _TAG.sub("", d.get("supported_languages") or "").replace("*", "").split(",") if x.strip()]
    langs = [l.split("languages with full audio")[0].strip() for l in langs if l]
    links = add_link({"Steam": f"https://store.steampowered.com/app/{appid}/"}, d.get("website"), "Website")
    plats = [norm_platform(p) for p, ok in (d.get("platforms") or {}).items() if ok]
    return Game(
        source="steam", source_id=str(appid), title=d.get("name", ""),
        release_date=rdate.isoformat() if rdate else None,
        platforms=sorted(set(plats)) or ["PC"],
        raw_genres=[g["description"] for g in d.get("genres") or []],
        game_modes=[c for c in cats if c in _MODES],
        developer=", ".join(d.get("developers") or []) or None,
        publisher=", ".join(p for p in d.get("publishers") or [] if p) or None,
        price=(po.get("final") / 100) if po.get("final") is not None else (0.0 if d.get("is_free") else None),
        currency=po.get("currency"), is_free=bool(d.get("is_free")),
        has_iap="In-App Purchases" in cats,
        description=d.get("short_description") or "",
        url=f"https://store.steampowered.com/app/{appid}/", icon_url=d.get("header_image") or "",
        content_rating=str(d["required_age"]) + "+" if str(d.get("required_age", "0")) not in ("0", "") else None,
        languages=langs[:40], links=links,
        extra={"categories": cats, "controller": d.get("controller_support"),
               "recommendations": (d.get("recommendations") or {}).get("total")},
    )


def parse_hover_tags(html_text):
    """Community tags from Steam's own store hover card (works where SteamSpy is blocked)."""
    return [htmllib.unescape(t) for t in _HOVER_TAG.findall(html_text or "")][:20]


def fetch_tags(http, appid):
    try:
        return parse_hover_tags(http.get(HOVER.format(appid), params={"l": "english"}).text)
    except Exception as e:
        log.debug("steam hover %s: %s", appid, e)
        return []


def apply_reviews(game, payload):
    qs = (payload or {}).get("query_summary") or {}
    total = qs.get("total_reviews")
    if total:
        game.rating_count = total
        game.rating = round(100 * qs.get("total_positive", 0) / total, 1)
        game.extra["review_label"] = qs.get("review_score_desc")


class SteamSource(Source):
    name = "steam"

    def fetch(self, start, end):
        cc, max_pages = self.cfg.get("cc", "us"), int(self.cfg.get("max_pages", 15))
        candidates = []
        for page in range(max_pages):
            data = self.http.get(SEARCH, params={
                "sort_by": "Released_DESC", "category1": 998, "infinite": 1, "start": page * 100,
                "count": 100, "cc": cc, "l": "english", "ndl": 1}).json()
            rows = parse_search(data.get("results_html", ""))
            if not rows:
                break
            candidates += [a for a, _, d in rows if d and start <= d <= end and a not in self.skip]
            dated = [d for _, _, d in rows if d]
            if dated and max(dated) < start:
                break
        candidates = list(dict.fromkeys(candidates))
        log.info("steam: %d new candidate apps to detail", len(candidates))
        for appid in candidates:
            try:
                node = (self.http.get(DETAILS, params={"appids": appid, "cc": cc, "l": "english"}).json() or {}).get(appid) or {}
                if not node.get("success"):
                    continue
                g = parse_details(appid, node["data"])
                if g:
                    self._enrich(g)
                    yield g
            except Exception as e:  # one bad app shouldn't kill the run
                log.warning("steam: app %s failed: %s", appid, e)

    def _enrich(self, g):
        try:
            apply_reviews(g, self.http.get(REVIEWS.format(g.source_id), params={
                "json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0}).json())
        except Exception as e:
            log.debug("steam reviews %s: %s", g.source_id, e)
        g.tags = fetch_tags(self.http, g.source_id)
        if not g.tags and self.cfg.get("steamspy_tags", True):
            try:
                tags = (self.http.get(SPY, params={"request": "appdetails", "appid": g.source_id}).json() or {}).get("tags") or {}
                if isinstance(tags, dict):
                    g.tags = [t for t, _ in sorted(tags.items(), key=lambda kv: -kv[1])][:20]
            except Exception as e:
                log.debug("steamspy %s: %s", g.source_id, e)

    def refresh(self, ids):
        for appid in ids:
            g = Game(source="steam", source_id=appid, title="")
            try:
                apply_reviews(g, self.http.get(REVIEWS.format(appid), params={
                    "json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0}).json())
                yield g
            except Exception as e:
                log.debug("steam refresh %s: %s", appid, e)
