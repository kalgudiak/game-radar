"""iOS App Store. Apple has no 'everything released today' API, so this sweeps the
public chart feeds (new + top free/paid/grossing) for every Games sub-category in each
storefront, keeps apps whose release date is recent, and enriches them via iTunes Lookup.
Result: every *new game that is visible on a chart*, tagged with where it charted.
That is the commercially interesting slice; for exhaustive coverage see README."""
from ..dates import parse_date
from ..links import add_link
from ..models import Game
from .base import Source, chunks, log

RSS = "https://itunes.apple.com/{cc}/rss/{feed}/limit=200/genre={gid}/json"
LOOKUP = "https://itunes.apple.com/lookup"
DEFAULT_FEEDS = ["newfreeapplications", "newpaidapplications", "topfreeapplications",
                 "topgrossingapplications", "toppaidapplications"]
DEFAULT_GENRES = [6014] + list(range(7001, 7020))   # 6014 = Games, 7001-7019 = sub-categories


def parse_rss(data):
    entries = ((data or {}).get("feed") or {}).get("entry") or []
    if isinstance(entries, dict):
        entries = [entries]
    out = []
    for e in entries:
        app_id = ((e.get("id") or {}).get("attributes") or {}).get("im:id")
        rel = parse_date((e.get("im:releaseDate") or {}).get("label"))
        if app_id:
            out.append((app_id, rel))
    return out


def parse_lookup(r, cc):
    if r.get("kind") != "software":
        return None
    genres = r.get("genres") or []
    if "Games" not in genres and r.get("primaryGenreName") != "Games":
        return None
    rd = parse_date(r.get("releaseDate"))
    price = r.get("price")
    avg = r.get("averageUserRating")
    size = r.get("fileSizeBytes")
    return Game(
        source="appstore", source_id=str(r["trackId"]), title=r.get("trackName", ""),
        release_date=rd.isoformat() if rd else None, platforms=["iOS"],
        raw_genres=[g for g in genres if g not in ("Games", "Entertainment")],
        developer=r.get("artistName"), publisher=r.get("sellerName"),
        price=price, currency=r.get("currency"), is_free=(price == 0) if price is not None else None,
        rating=round(avg * 20, 1) if avg else None, rating_count=r.get("userRatingCount"),
        description=r.get("description") or "", url=r.get("trackViewUrl") or "",
        icon_url=r.get("artworkUrl512") or r.get("artworkUrl100") or "",
        content_rating=r.get("contentAdvisoryRating"), languages=r.get("languageCodesISO2A") or [],
        links=add_link(add_link({}, r.get("trackViewUrl"), "App Store"), r.get("sellerUrl"), "Website"),
        extra={"storefront": cc, "version": r.get("version"), "min_os": r.get("minimumOsVersion"),
               "size_mb": round(int(size) / 1e6, 1) if size else None,
               "last_update": r.get("currentVersionReleaseDate")},
    )


class AppStoreSource(Source):
    name = "appstore"

    def fetch(self, start, end):
        countries = self.cfg.get("countries", ["us"])
        feeds = self.cfg.get("feeds", DEFAULT_FEEDS)
        genre_ids = self.cfg.get("genre_ids", DEFAULT_GENRES)
        yielded = set()
        for cc in countries:
            charts = {}
            for feed in feeds:
                for gid in genre_ids:
                    try:
                        rows = parse_rss(self.http.get(RSS.format(cc=cc, feed=feed, gid=gid)).json())
                    except Exception as e:
                        log.debug("appstore feed %s/%s/%s: %s", cc, feed, gid, e)
                        continue
                    for rank, (app_id, rel) in enumerate(rows, 1):
                        if (rel and rel < start) or app_id in self.skip or app_id in yielded:
                            continue
                        charts.setdefault(app_id, []).append(f"{cc}/{feed}/{gid}#{rank}")
            log.info("appstore[%s]: %d recent chart entries to look up", cc, len(charts))
            for batch in chunks(charts, 100):
                try:
                    res = self.http.get(LOOKUP, params={"id": ",".join(batch), "country": cc}).json()
                except Exception as e:
                    log.warning("appstore lookup failed: %s", e)
                    continue
                for r in res.get("results", []):
                    g = parse_lookup(r, cc)
                    if g:
                        g.extra["charts"] = charts.get(g.source_id, [])
                        yielded.add(g.source_id)
                        yield g

    def refresh(self, ids):
        cc = self.cfg.get("countries", ["us"])[0]
        for batch in chunks(ids, 100):
            try:
                for r in self.http.get(LOOKUP, params={"id": ",".join(batch), "country": cc}).json().get("results", []):
                    g = parse_lookup(r, cc)
                    if g:
                        yield g
            except Exception as e:
                log.debug("appstore refresh: %s", e)
