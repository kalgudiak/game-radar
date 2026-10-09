"""Google Play via the open-source google-play-scraper package. Play has no public
'new releases' listing, so we run genre-seeded searches per country, then fetch each
unseen app and keep the recently released ones. Old apps are remembered and never
re-fetched, so the daily cost falls after the first week."""
from ..dates import parse_date
from ..links import add_link
from ..models import Game
from .base import Source, SourceUnavailable, log

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

    def fetch(self, start, end):
        app, search = self._lib()
        lang = self.cfg.get("lang", "en")
        n = int(self.cfg.get("hits_per_query", 30))
        seen = set()
        for cc in self.cfg.get("countries", ["us"]):
            for q in self.cfg.get("queries", DEFAULT_QUERIES):
                try:
                    hits = search(q, lang=lang, country=cc, n_hits=n)
                except Exception as e:
                    log.debug("play search %r: %s", q, e)
                    continue
                for h in hits:
                    aid = h.get("appId")
                    if not aid or aid in self.skip or aid in seen:
                        continue
                    seen.add(aid)
                    try:
                        g = parse_app(app(aid, lang=lang, country=cc), cc)
                    except Exception as e:
                        log.debug("play app %s: %s", aid, e)
                        continue
                    if g:
                        yield g
        log.info("googleplay: checked %d unseen apps", len(seen))

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
