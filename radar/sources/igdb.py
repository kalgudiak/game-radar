"""IGDB (Twitch) - the broadest catalogue for PC and console releases, all platforms.
Needs a free Twitch developer app: TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET."""
import os
from datetime import datetime, time, timedelta, timezone

from ..links import add_link
from ..models import Game
from ..taxonomy import norm_platform
from .base import Source, SourceUnavailable, log

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
GAMES_URL = "https://api.igdb.com/v4/games"
FIELDS = (
    "name,slug,url,summary,first_release_date,game_type.type,platforms.name,genres.name,"
    "themes.name,game_modes.name,player_perspectives.name,keywords.name,"
    "involved_companies.company.name,involved_companies.developer,involved_companies.publisher,"
    "total_rating,total_rating_count,hypes,cover.image_id,language_supports.language.name,websites.url"
)
EXCLUDED_TYPES = {"DLC / Addon", "DLC", "Bundle", "Mod", "Episode", "Season", "Update", "Pack / Addon", "Pack"}
PAGE = 500


def _epoch(d):
    return int(datetime.combine(d, time.min, tzinfo=timezone.utc).timestamp())


def parse_game(row):
    gtype = (row.get("game_type") or {}).get("type")
    if gtype in EXCLUDED_TYPES or not row.get("name"):
        return None
    comps = row.get("involved_companies") or []
    devs = [c["company"]["name"] for c in comps if c.get("developer") and c.get("company")]
    pubs = [c["company"]["name"] for c in comps if c.get("publisher") and c.get("company")]
    names = lambda k: [x["name"] for x in row.get(k) or [] if x.get("name")]
    ts = row.get("first_release_date")
    langs = sorted({(l.get("language") or {}).get("name") for l in row.get("language_supports") or []} - {None})
    cover = (row.get("cover") or {}).get("image_id")
    links = {}
    for w in row.get("websites") or []:
        add_link(links, w.get("url"))
    add_link(links, row.get("url"), "IGDB")
    return Game(
        source="igdb", source_id=str(row["id"]), title=row["name"],
        release_date=datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat() if ts else None,
        platforms=sorted({norm_platform(p) for p in names("platforms")}),
        raw_genres=names("genres") + names("themes"),
        tags=names("keywords")[:30] + names("player_perspectives"),
        game_modes=names("game_modes"),
        developer=", ".join(devs) or None, publisher=", ".join(pubs) or None,
        rating=row.get("total_rating"), rating_count=row.get("total_rating_count"),
        description=row.get("summary") or "", url=row.get("url") or "",
        icon_url=f"https://images.igdb.com/igdb/image/upload/t_cover_big/{cover}.jpg" if cover else "",
        languages=langs, links=links, extra={"hypes": row.get("hypes"), "game_type": gtype},
    )


class IGDBSource(Source):
    name = "igdb"

    def _auth(self):
        cid, secret = os.environ.get("TWITCH_CLIENT_ID"), os.environ.get("TWITCH_CLIENT_SECRET")
        if not (cid and secret):
            raise SourceUnavailable("set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET to enable IGDB")
        tok = self.http.post(TOKEN_URL, params={"client_id": cid, "client_secret": secret,
                                                "grant_type": "client_credentials"}).json()
        return {"Client-ID": cid, "Authorization": f"Bearer {tok['access_token']}"}

    def fetch(self, start, end):
        headers = self._auth()
        lo, hi = _epoch(start), _epoch(end + timedelta(days=1))
        offset = 0
        while True:
            q = (f"fields {FIELDS}; where first_release_date >= {lo} & first_release_date < {hi}; "
                 f"sort first_release_date desc; limit {PAGE}; offset {offset};")
            rows = self.http.post(GAMES_URL, data=q, headers=headers).json()
            for row in rows:
                if str(row.get("id")) in self.skip:
                    continue
                g = parse_game(row)
                if g:
                    yield g
            log.info("igdb: page at offset %d -> %d rows", offset, len(rows))
            if len(rows) < PAGE:
                break
            offset += PAGE
