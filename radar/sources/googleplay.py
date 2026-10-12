"""Google Play. Play has no public 'new releases' listing, so new games are discovered
through AppBrain, which tracks every Play app and publishes, for each of the 17 game
categories, the most-installed and trending games released in the past 30 days. Each
game's release date, installs, ratings and price then come from Google Play itself
(google-play-scraper). Optional genre-seeded Play searches can add more, but in practice
they mostly return established games."""
import re

from ..dates import parse_date
from ..links import add_link
from ..models import Game
from .base import Source, SourceUnavailable, log

APPBRAIN = "https://www.appbrain.com/apps/{sort}/{cat}/new"
APPBRAIN_CATS = ["games", "action", "adventure", "arcade", "board-games", "card-games", "casino", "casual",
                 "educational", "music-games", "puzzle", "racing", "role-playing", "simulation",
                 "sports-games", "strategy", "trivia", "word-games"]
APPBRAIN_SORTS = ["popular", "trending"]
_AB_TAG = re.compile(r'<a\b[^>]*\bclass="[^"]*\bbrowse-app\b[^"]*"[^>]*>', re.S)
_AB_HREF = re.compile(r'href="/app/[^"/]*/([\w.]+)"')


def parse_appbrain(html):
    """Package ids from an AppBrain list page, in list order (main list only, not sidebars)."""
    out = []
    for tag in _AB_TAG.findall(html or ""):
        m = _AB_HREF.search(tag)
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


DEFAULT_QUERIES = [
    "new game", "new puzzle game", "merge game", "match 3", "idle game", "idle rpg",
    "runner game", "arcade game", "casual game", "hyper casual", "strategy game",
    "tower defense", "rpg game", "action game", "roguelike", "survivor game", "simulation game",
    "tycoon", "racing game", "sports game", "card game", "board game", "word game",
    "trivia game", "casino game", "shooter game", "adventure game", "music game", "kids game",
]


def parse_app(d, cc):
    if not str(d.get("genreId") or "").startswith("GAME"):
        return None
    rd = parse_date(d.get("released"))
    cats = [c.get("name") for c in d.get("categories") or [] if c.get("name")] or [d.get("genre")]
    score = d.get("score")
    return Game(
        source="googleplay", source_id=d["appId"], title=d.get("title", ""),
        release_date=rd.isoformat() if rd else None, platforms=["Android"],
        raw_genres=[c for c in cats if c], developer=d.get("developer"),
        price=d.get("price"), currency=d.get("currency"), is_free=d.get("free"),
        has_iap=d.get("offersIAP"), rating=round(score * 20, 1) if score else None,
        rating_count=d.get("ratings"), installs=d.get("realInstalls") or d.get("minInstalls"),
        description=d.get("description") or "", url=d.get("url") or "", icon_url=d.get("icon") or "",
        content_rating=d.get("contentRating"),
        links=add_link(add_link({}, d.get("url") or f"https://play.google.com/store/apps/details?id={d['appId']}", "Google Play"),
                       d.get("developerWebsite"), "Website"),
        extra={"storefront": cc, "genre_id": d.get("genreId"), "installs_label": d.get("installs"),
               "ads": d.get("adSupported"), "last_update": d.get("updated")},
    )


class GooglePlaySource(Source):
    name = "googleplay"

    def _lib(self):
        try:
            from google_play_scraper import app, search
            return app, search
        except ImportError as e:
            raise SourceUnavailable("pip install google-play-scraper to enable Google Play") from e

    def discover_appbrain(self, day=None):
        """AppBrain refuses (HTTP 429) after ~18-20 pages per visit, so by default each run reads
        one list type (most installed / trending) for all 18 categories, alternating by day.
        Both lists cover the past 30 days, so alternating loses nothing."""
        found = {}
        sorts = self.cfg.get("appbrain_sorts", APPBRAIN_SORTS)
        if self.cfg.get("appbrain_alternate", True) and day is not None and len(sorts) > 1:
            sorts = [sorts[day.toordinal() % len(sorts)]]
        for sort in sorts:
            for cat in self.cfg.get("appbrain_categories", APPBRAIN_CATS):
                try:
                    ids = parse_appbrain(self.http.get(APPBRAIN.format(sort=sort, cat=cat)).text)
                except Exception as e:
                    log.warning("appbrain %s/%s failed: %s", sort, cat, e)
                    continue
                for rank, aid in enumerate(ids, 1):
                    found.setdefault(aid, []).append(f"{sort}/{cat}#{rank}")
        log.info("googleplay: AppBrain %s lists: %d games released in the past 30 days", "+".join(sorts), len(found))
        return found

    def fetch(self, start, end):
        app, search = self._lib()
        lang = self.cfg.get("lang", "en")
        cc = self.cfg.get("countries", ["us"])[0]
        found = self.discover_appbrain(end) if self.cfg.get("appbrain", True) else {}
        if self.cfg.get("search", False):
            n = int(self.cfg.get("hits_per_query", 30))
            for q in self.cfg.get("queries", DEFAULT_QUERIES):
                try:
                    for h in search(q, lang=lang, country=cc, n_hits=n):
                        if h.get("appId"):
                            found.setdefault(h["appId"], [])
                except Exception as e:
                    log.debug("play search %r: %s", q, e)
        todo = [a for a in found if a not in self.skip]
        log.info("googleplay: %d not seen before, fetching details from Google Play", len(todo))
        for aid in todo:
            try:
                g = parse_app(app(aid, lang=lang, country=cc), cc)
            except Exception as e:
                log.debug("play app %s: %s", aid, e)
                continue
            if g:
                if found[aid]:
                    g.extra["appbrain"] = found[aid]
                yield g

    def refresh(self, ids):
        app, _ = self._lib()
        cc = self.cfg.get("countries", ["us"])[0]
        for aid in ids:
            try:
                g = parse_app(app(aid, lang=self.cfg.get("lang", "en"), country=cc), cc)
                if g:
                    yield g
            except Exception as e:
                log.debug("play refresh %s: %s", aid, e)
