"""Import data collected in a browser session (Steam / App Store / itch.io JSON exports)
into the radar database, so the normal classifier and report builder run on it."""
import json
import re
from pathlib import Path

from .dates import parse_date
from .links import add_link
from .models import Game
from .sources.itch import _SLUG_NAME
from .taxonomy import classify, norm_platform

_COUNT = re.compile(r"([\d,]+)\s+(?:user\s+)?reviews?", re.I)
_PCT = re.compile(r"(\d{1,3})%")


def _steam(g):
    if g.get("type") and g["type"] != "game":
        return None
    if not g.get("name"):
        return None
    rd = parse_date(g.get("rd")) or parse_date(g.get("listed"))
    txt = g.get("revtxt") or ""
    m, p = _COUNT.search(txt), _PCT.search(txt)
    cats = g.get("cats") or []
    links = add_link({"Steam": f"https://store.steampowered.com/app/{g['id']}/"}, g.get("web"), "Website")
    return Game(
        source="steam", source_id=str(g["id"]), title=g["name"], release_date=rd.isoformat() if rd else None,
        platforms=sorted({norm_platform(x) for x in g.get("plat") or ["windows"]}),
        raw_genres=g.get("genres") or [], tags=g.get("tags") or [],
        developer=g.get("dev") or None, publisher=g.get("pub") or None,
        price=g.get("price") if g.get("price") is not None else (0.0 if g.get("free") else None),
        currency=g.get("cur"), is_free=bool(g.get("free")), has_iap="In-App Purchases" in cats,
        rating=float(p.group(1)) if p else None,
        rating_count=int(m.group(1).replace(",", "")) if m else None,
        description=g.get("desc") or "", url=links["Steam"], icon_url=g.get("img") or "", links=links,
        extra={"review_label": g.get("rev") or None, "categories": cats},
    )


def _ios(a):
    rd = parse_date(a.get("rd"))
    links = add_link(add_link({}, a.get("url"), "App Store"), a.get("web"), "Website")
    price = a.get("price")
    return Game(
        source="appstore", source_id=str(a["id"]), title=a["name"], release_date=rd.isoformat() if rd else None,
        platforms=["iOS"], raw_genres=a.get("genres") or [], developer=a.get("dev"),
        price=price, currency=a.get("cur"), is_free=(price == 0) if price is not None else None,
        rating=round(a["rating"] * 20, 1) if a.get("rating") else None, rating_count=a.get("count"),
        description=a.get("desc") or "", url=a.get("url") or "", links=links,
        extra={"charts": a.get("charts") or []},
    )


def clean_itch_genres(games):
    """Drop genre labels whose feed returned exactly the same games as another feed."""
    by_slug = {}
    for g in games:
        for s in g.get("genres") or []:
            by_slug.setdefault(s, set()).add(g["url"])
    sets = list(by_slug.items())
    bogus = {a for a, sa in sets for b, sb in sets if a != b and sa == sb}
    for g in games:
        g["genres"] = [s for s in g.get("genres") or [] if s not in bogus]
    return bogus


def _itch(x):
    rd = parse_date(x.get("date"))
    try:
        price = float((x.get("price") or "").replace("$", "")) if x.get("price") else None
    except ValueError:
        price = None
    genres = [_SLUG_NAME.get(s, s.replace("-", " ").title()) for s in x.get("genres") or [] if s != "other"]
    return Game(
        source="itch", source_id=x["url"], title=x["name"], release_date=rd.isoformat() if rd else None,
        platforms=sorted({norm_platform(p) for p in x.get("plats") or []}) or ["Web"],
        raw_genres=genres, developer=x.get("dev"), price=price, currency="USD",
        is_free=price in (None, 0.0), description=x.get("desc") or "", url=x["url"], links={"itch.io": x["url"]},
    )


PARSERS = {"steam": _steam, "appstore": _ios, "itch": _itch}


def import_files(db, paths, day: str):
    counts = {}
    for p in paths:
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        parse = PARSERS[data["source"]]
        if data["source"] == "itch":
            bogus = clean_itch_genres(data["games"])
            if bogus:
                print("itch: ignored unfiltered genre feeds:", ", ".join(sorted(bogus)))
        n = 0
        for raw in data["games"]:
            g = parse(raw)
            if g and g.release_date:
                db.upsert(classify(g), day)
                n += 1
        counts[data["source"]] = counts.get(data["source"], 0) + n
    db.commit()
    return counts
