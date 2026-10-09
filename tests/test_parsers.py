from datetime import date

from radar.sources.appstore import parse_lookup, parse_rss
from radar.sources.googleplay import parse_app
from radar.sources.igdb import parse_game
from radar.sources.itch import parse_feed
from radar.sources.steam import apply_reviews, parse_details, parse_search
from radar.taxonomy import classify

STEAM_HTML = '''
<a href="https://store.steampowered.com/app/111/Merge_Kingdom/" data-ds-appid="111" class="search_result_row">
 <div class="col search_name ellipsis"><span class="title">Merge Kingdom &amp; Co</span></div>
 <div class="col search_released responsive_secondrow">8 Oct, 2026</div></a>
<a href="https://store.steampowered.com/bundle/9/" data-ds-bundleid="9" class="search_result_row">
 <span class="title">Some Bundle</span><div class="col search_released responsive_secondrow"></div></a>
<a href="https://store.steampowered.com/app/222/Old/" data-ds-appid="222" class="search_result_row">
 <span class="title">Old Game</span><div class="col search_released responsive_secondrow">Sep 1, 2026</div></a>'''


def test_steam_search_and_details():
    rows = parse_search(STEAM_HTML)
    assert rows == [("111", "Merge Kingdom & Co", date(2026, 10, 8)), ("222", "Old Game", date(2026, 9, 1))]
    g = parse_details("111", {
        "type": "game", "name": "Merge Kingdom", "release_date": {"coming_soon": False, "date": "8 Oct, 2026"},
        "genres": [{"description": "Casual"}, {"description": "Indie"}],
        "categories": [{"description": "Single-player"}, {"description": "In-App Purchases"}],
        "developers": ["Tiny Co"], "publishers": [""], "is_free": False,
        "price_overview": {"final": 499, "currency": "USD"}, "platforms": {"windows": True, "mac": True, "linux": False},
        "supported_languages": "English<strong>*</strong>, French<br><strong>*</strong>languages with full audio support",
        "short_description": "Merge castles.", "required_age": 0})
    assert g.release_date == "2026-10-08" and g.platforms == ["Mac", "PC"] and g.price == 4.99
    assert g.has_iap and g.publisher is None and g.languages[:2] == ["English", "French"]
    apply_reviews(g, {"query_summary": {"total_reviews": 40, "total_positive": 30, "review_score_desc": "Mostly Positive"}})
    assert g.rating == 75.0 and g.rating_count == 40
    classify(g)
    assert g.genre == "Puzzle" and "Merge" in g.subgenres
    assert parse_details("1", {"type": "dlc"}) is None


def test_appstore():
    feed = {"feed": {"entry": [
        {"id": {"attributes": {"im:id": "555"}}, "im:releaseDate": {"label": "2026-10-07T00:00:00-07:00"}},
        {"id": {"attributes": {"im:id": "556"}}}]}}
    assert parse_rss(feed) == [("555", date(2026, 10, 7)), ("556", None)]
    g = parse_lookup({"kind": "software", "trackId": 555, "trackName": "Hero Squad: Idle RPG",
                      "releaseDate": "2026-10-07T07:00:00Z", "genres": ["Games", "Role Playing", "Strategy"],
                      "primaryGenreName": "Games", "price": 0.0, "currency": "USD", "averageUserRating": 4.5,
                      "userRatingCount": 120, "artistName": "Studio", "trackViewUrl": "https://apps.apple.com/x"}, "us")
    assert g.is_free and g.rating == 90.0 and g.raw_genres == ["Role Playing", "Strategy"]
    classify(g)
    assert g.genre == "Idle & Incremental" and "Squad / Idle RPG" in g.subgenres
    assert parse_lookup({"kind": "software", "trackId": 1, "genres": ["Productivity"]}, "us") is None


def test_googleplay():
    g = parse_app({"appId": "com.x.runner", "title": "Turbo Runner 3D", "genreId": "GAME_ARCADE",
                   "genre": "Arcade", "categories": [{"name": "Arcade", "id": "GAME_ARCADE"}],
                   "released": "Oct 6, 2026", "score": 4.1, "ratings": 900, "realInstalls": 52000,
                   "free": True, "offersIAP": True}, "in")
    assert g.release_date == "2026-10-06" and g.installs == 52000 and g.rating == 82.0
    classify(g)
    assert g.genre == "Arcade" and "Runner" in g.subgenres
    assert parse_app({"appId": "a", "genreId": "TOOLS"}, "us") is None


def test_igdb():
    g = parse_game({"id": 9, "name": "Void Keepers", "first_release_date": 1791763200,
                    "game_type": {"type": "Main Game"},
                    "platforms": [{"name": "PC (Microsoft Windows)"}, {"name": "PlayStation 5"}, {"name": "Nintendo Switch 2"}],
                    "genres": [{"name": "Shooter"}, {"name": "Indie"}], "themes": [{"name": "Science fiction"}],
                    "keywords": [{"name": "roguelite"}],
                    "involved_companies": [{"company": {"name": "Dev A"}, "developer": True, "publisher": False},
                                           {"company": {"name": "Pub B"}, "developer": False, "publisher": True}]})
    assert g.developer == "Dev A" and g.publisher == "Pub B" and "Switch 2" in g.platforms
    classify(g)
    assert g.genre == "Roguelike"
    assert parse_game({"id": 1, "name": "x", "game_type": {"type": "DLC / Addon"}}) is None


ITCH = """<?xml version="1.0"?><rss><channel>
<item><title>Tiny Tower Guard [Free] [Strategy] [Windows]</title><plainTitle>Tiny Tower Guard</plainTitle>
<link>https://maker.itch.io/tiny-tower-guard</link><pubDate>Wed, 07 Oct 2026 10:00:00 GMT</pubDate>
<createDate>Wed, 07 Oct 2026 09:00:00 GMT</createDate><price>$0.00</price>
<platforms><windows>yes</windows><osx>no</osx></platforms>
<description>&lt;p&gt;A tower defense game&lt;/p&gt;</description></item>
</channel></rss>"""


def test_itch():
    [g] = parse_feed(ITCH, "strategy")
    assert g.title == "Tiny Tower Guard" and g.platforms == ["PC"] and g.developer == "maker"
    assert g.release_date == "2026-10-07" and g.is_free
    classify(g)
    assert g.genre == "Strategy" and "Tower Defense" in g.subgenres


def test_description_noise_is_ignored():
    from radar.models import Game
    g = classify(Game(source="t", source_id="1", title="Calm Lake", raw_genres=["Adventure"],
                      description="You will never sit idle on this lake."))
    assert g.genre == "Adventure" and "Idle" not in g.subgenres
