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


def test_steam_hover_tags_and_retag(tmp_path, monkeypatch):
    from radar.sources import steam
    html = '<div class="hover_tag_row"><div class="app_tag">Roguelite</div><div class="app_tag">Deckbuilding</div><div class="app_tag">Rock &amp; Roll</div></div>'
    assert steam.parse_hover_tags(html) == ["Roguelite", "Deckbuilding", "Rock & Roll"]
    from radar import pipeline
    db = DB(tmp_path / "r.db")
    g = classify(Game(source="steam", source_id="7", title="Cards of Doom", release_date="2026-10-01", raw_genres=["Action", "Indie"]))
    assert g.genre == "Action"
    db.upsert(g, "2026-10-02"); db.commit()
    monkeypatch.setattr(pipeline, "fetch_tags", lambda http, appid: ["Roguelite", "Deckbuilding"])
    assert pipeline.retag_steam({}, db) == ["2026-10-02"]
    row = db.c.execute("SELECT genre FROM games WHERE key='steam:7'").fetchone()
    assert row["genre"] == "Roguelike"
    assert pipeline.retag_steam({}, db) == []   # nothing left to do


def test_appbrain_parse_and_itch_flag():
    from radar.sources.googleplay import parse_appbrain
    html = ('<div class="sidebar"><a href="/app/x/com.side.bar">Side</a></div>'
            '<a class="browse-app safelink hover-shadow d-block" href="/app/overpeak-action/com.rusergames.overpeak"><h3>OverPeak</h3></a>'
            '<a href="/app/fruit-wins/com.fruitwins" class="browse-app safelink">Fruit</a>'
            '<a class="browse-app" href="/app/overpeak-action/com.rusergames.overpeak">dup</a>')
    assert parse_appbrain(html) == ["com.rusergames.overpeak", "com.fruitwins"]
    from radar.dashboard import aggregate, itch_only
    a = {"release_date": "2026-10-08", "genre": "Puzzle", "subgenres": [], "families": ["Web"], "links": [{"label": "itch.io", "url": "u"}]}
    b = {"release_date": "2026-10-08", "genre": "Puzzle", "subgenres": [], "families": ["Android"], "links": [{"label": "Google Play", "url": "u"}]}
    assert itch_only(a) and not itch_only(b)
    agg = aggregate([a, b])["2026-10-08"]
    assert agg["all"]["n"] == 2 and agg["core"]["n"] == 1


def test_appbrain_alternates_and_path_throttle(monkeypatch):
    from datetime import date
    from radar.sources.googleplay import GooglePlaySource
    seen = []

    class FakeHttp:
        def get(self, url, **kw):
            seen.append(url)
            class R: text = '<a class="browse-app" href="/app/x/com.a.b">x</a>'
            return R()
    src = GooglePlaySource(FakeHttp(), {})
    src.discover_appbrain(date(2026, 10, 12))
    a = {u.split("/")[4] for u in seen}; seen.clear()
    src.discover_appbrain(date(2026, 10, 13))
    b = {u.split("/")[4] for u in seen}
    assert len(a) == 1 and len(b) == 1 and a != b      # one list type per day, alternating
    from radar import http as h
    t = h.Http("x"); sleeps = []
    monkeypatch.setattr(h.time, "sleep", lambda s: sleeps.append(s))
    t._throttle("https://store.steampowered.com/appreviews/1"); t._throttle("https://store.steampowered.com/appreviews/2")
    assert sleeps and max(sleeps) <= 0.4
