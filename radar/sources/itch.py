"""itch.io: per-genre 'newest' RSS feeds. High volume, lots of jam games, great for
spotting fresh mechanics early."""
import re
import xml.etree.ElementTree as ET

from ..dates import parse_date
from ..models import Game
from ..taxonomy import norm_platform
from .base import Source, log

FEED = "https://itch.io/games/newest/genre-{g}.xml"
FEED_ALL = "https://itch.io/games/newest.xml"
GENRES = ["action", "adventure", "card-game", "educational", "fighting", "interactive-fiction",
          "platformer", "puzzle", "racing", "rhythm", "role-playing", "shooter", "simulation",
          "sports", "strategy", "survival", "visual-novel", "other"]
_BRACKETS = re.compile(r"\s*\[[^\]]*\]")
_SLUG_NAME = {"card-game": "Card Game", "interactive-fiction": "Interactive Fiction",
              "role-playing": "Role-playing", "visual-novel": "Visual Novel"}


def parse_feed(xml_text, genre_slug=None):
    root = ET.fromstring(xml_text)
    games = []
    for it in root.iter("item"):
        t = lambda tag: (it.findtext(tag) or "").strip()
        link = t("link")
        title = t("plainTitle") or _BRACKETS.sub("", t("title"))
        if not link or not title:
            continue
        plats = []
        pnode = it.find("platforms")
        if pnode is not None:
            plats = [norm_platform(c.tag) for c in pnode if (c.text or "").strip().lower() in ("yes", "true", "1")]
        rd = parse_date(t("createDate")) or parse_date(t("pubDate"))
        price_txt = t("price").replace("$", "")
        try:
            price = float(price_txt) if price_txt else None
        except ValueError:
            price = None
        desc = re.sub(r"<[^>]+>", " ", t("description"))
        games.append(Game(
            source="itch", source_id=link.split("?")[0].rstrip("/"), title=title,
            release_date=rd.isoformat() if rd else None, platforms=sorted(set(plats)) or ["Web"],
            raw_genres=[_SLUG_NAME.get(genre_slug, genre_slug.title())] if genre_slug and genre_slug != "other" else [],
            price=price, currency=t("currency") or None, is_free=(price in (None, 0.0)),
            description=" ".join(desc.split()), url=link, icon_url=t("imageurl"), links={"itch.io": link},
            developer=link.split("//")[-1].split(".itch.io")[0] if ".itch.io" in link else None,
        ))
    return games


class ItchSource(Source):
    name = "itch"

    def fetch(self, start, end):
        merged = {}
        first_pages = {}   # slug -> frozenset of ids on page 1, to catch feeds whose genre filter was ignored
        max_pages = int(self.cfg.get("max_pages", 3))
        for slug in self.cfg.get("genres", GENRES) + [None]:
            for page in range(1, max_pages + 1):
                url = FEED.format(g=slug) if slug else FEED_ALL
                try:
                    games = parse_feed(self.http.get(url, params={"page": page} if page > 1 else None).text, slug)
                except Exception as e:
                    log.debug("itch %s p%d: %s", slug, page, e)
                    break
                if not games:
                    break
                if page == 1 and slug:
                    ids = frozenset(g.source_id for g in games)
                    dupes = [s for s, other in first_pages.items() if other == ids]
                    first_pages[slug] = ids
                    if dupes:
                        log.warning("itch: genre feed %s returned the same games as %s; ignoring its genre label", slug, dupes)
                        for g in games:
                            g.raw_genres = []
                        for s in dupes:
                            for m in merged.values():
                                m.raw_genres = [x for x in m.raw_genres if x != _SLUG_NAME.get(s, s.title())]
                for g in games:
                    if g.source_id in self.skip:
                        continue
                    if g.source_id in merged:  # same game in several genre feeds
                        merged[g.source_id].raw_genres = sorted(set(merged[g.source_id].raw_genres + g.raw_genres))
                    else:
                        merged[g.source_id] = g
                dates = [parse_date(g.release_date) for g in games if g.release_date]
                if dates and max(dates) < start:
                    break
        yield from merged.values()
