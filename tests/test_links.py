from datetime import date

from radar.db import DB
from radar.links import label_for, ordered
from radar.models import Game
from radar.report import write_daily
from radar.sources.appstore import parse_lookup
from radar.sources.igdb import parse_game
from radar.sources.steam import parse_details
from radar.taxonomy import classify


def test_labels_and_order():
    assert label_for("https://store.steampowered.com/app/1/")[0] == "Steam"
    assert label_for("https://maker.itch.io/game")[0] == "itch.io"
    assert label_for("https://www.nintendo.com/us/store/products/x")[0] == "Nintendo eShop"
    assert label_for("https://mygame.com")[0] == "Website"
    links = {"YouTube": "https://youtube.com/x", "Website": "https://g.com", "IGDB": "https://igdb.com/g", "Steam": "https://store.steampowered.com/app/1/"}
    assert list(ordered(links)) == ["Steam", "Website", "YouTube", "IGDB"]


def test_sources_collect_links():
    g = parse_game({"id": 1, "name": "X", "url": "https://www.igdb.com/games/x",
                    "websites": [{"url": "https://store.steampowered.com/app/9/"}, {"url": "https://store.playstation.com/x"},
                                 {"url": "https://x.com/game"}, {"url": "https://xgame.com"}]})
    assert {"Steam", "PlayStation Store", "Website", "X", "IGDB"} <= set(g.links)
    s = parse_details("9", {"type": "game", "name": "X", "website": "https://xgame.com", "release_date": {"date": "8 Oct, 2026"}})
    assert s.links == {"Steam": "https://store.steampowered.com/app/9/", "Website": "https://xgame.com"}
    a = parse_lookup({"kind": "software", "trackId": 5, "genres": ["Games"], "trackViewUrl": "https://apps.apple.com/app/id5",
                      "sellerUrl": "https://studio.com"}, "us")
    assert a.links == {"App Store": "https://apps.apple.com/app/id5", "Website": "https://studio.com"}


def test_merged_game_shows_every_store(tmp_path):
    db = DB(tmp_path / "r.db")
    day = "2026-10-08"
    for g in (Game(source="steam", source_id="9", title="Star Grid Arena", release_date=day, raw_genres=["Strategy"],
                   links={"Steam": "https://store.steampowered.com/app/9/", "Website": "https://sga.com"}),
              Game(source="googleplay", source_id="com.sga", title="Star Grid Arena", release_date=day, raw_genres=["Strategy"],
                   links={"Google Play": "https://play.google.com/store/apps/details?id=com.sga"})):
        db.upsert(classify(g), day)
    out, rows = write_daily(db, date(2026, 10, 8), tmp_path / "rep")
    assert [l["label"] for l in rows[0]["links"]] == ["Steam", "Google Play", "Website"]
    md = (out / "summary.md").read_text()
    assert "[Star Grid Arena](https://store.steampowered.com/app/9/)" in md and "[Google Play](https://play.google.com" in md
    csv_text = (out / "games.csv").read_text()
    assert "steam_url" in csv_text and "https://sga.com" in csv_text
    assert 'href="https://store.steampowered.com/app/9/"' not in (out / "report.html").read_text()  # data is JSON, rendered by JS
    assert "https://store.steampowered.com/app/9/" in (out / "report.html").read_text()
