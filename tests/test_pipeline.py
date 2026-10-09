from datetime import date

from radar.db import DB
from radar.models import Game
from radar.pipeline import collect
from radar.report import write_daily, write_trends
from radar.sources.base import Source


class Fake(Source):
    def __init__(self, name, games):
        super().__init__(None, {})
        self.name, self.games, self.calls = name, games, 0

    def fetch(self, start, end):
        self.calls += 1
        for g in self.games:
            if g.source_id not in self.skip:
                yield g


def G(src, sid, title, rd, genres, plats):
    return Game(source=src, source_id=sid, title=title, release_date=rd, raw_genres=genres,
                platforms=plats, rating_count=10, url=f"https://x/{sid}")


def test_end_to_end(tmp_path):
    db = DB(tmp_path / "r.db")
    day = date(2026, 10, 8)
    steam = Fake("steam", [G("steam", "1", "Star Grid Arena", "2026-10-08", ["Strategy"], ["PC"]),
                           G("steam", "2", "Ancient Classic", "2019-01-01", ["Action"], ["PC"]),
                           G("steam", "3", "Not Yet Out", "2026-12-01", ["Action"], ["PC"])])
    play = Fake("googleplay", [G("googleplay", "com.a", "Star Grid Arena™", "2026-10-07", ["Strategy"], ["Android"]),
                               G("googleplay", "com.b", "Word Wiz", "2026-10-08", ["Word"], ["Android"])])
    summary = collect({"lookback_days": 3, "track_days": 30}, db, day, sources=[steam, play])
    assert summary == {"steam": 1, "googleplay": 2}
    assert "2" in db.known_ids("steam")           # old game remembered as rejected
    assert "3" not in db.known_ids("steam")       # future game retried later

    out, rows = write_daily(db, day, tmp_path / "reports")
    titles = {r["title"]: r for r in rows}
    assert len(rows) == 2                          # cross-store duplicate merged
    assert titles["Star Grid Arena"]["platforms"] == ["Android", "PC"]
    assert titles["Word Wiz"]["genre"] == "Word & Trivia"
    for f in ("games.csv", "games.json", "summary.md", "report.html"):
        assert (out / f).stat().st_size > 0
    assert "| Strategy | 1 |" in (out / "summary.md").read_text()
    assert write_trends(db, day, 7, tmp_path / "reports").exists()

    # second run: nothing new, nothing re-fetched
    assert collect({"lookback_days": 3}, db, day, sources=[steam, play]) == {"steam": 0, "googleplay": 0}
