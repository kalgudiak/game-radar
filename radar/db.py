import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from .models import Game

SCHEMA = """
CREATE TABLE IF NOT EXISTS games(
  key TEXT PRIMARY KEY, source TEXT, source_id TEXT, title TEXT, title_norm TEXT,
  release_date TEXT, genre TEXT, data TEXT, first_seen TEXT, last_seen TEXT);
CREATE INDEX IF NOT EXISTS ix_games_first_seen ON games(first_seen);
CREATE INDEX IF NOT EXISTS ix_games_release ON games(release_date);
CREATE INDEX IF NOT EXISTS ix_games_title ON games(title_norm);
CREATE TABLE IF NOT EXISTS rejected(source TEXT, source_id TEXT, PRIMARY KEY(source, source_id));
CREATE TABLE IF NOT EXISTS snapshots(
  key TEXT, day TEXT, rating REAL, rating_count INTEGER, installs INTEGER, price REAL,
  PRIMARY KEY(key, day));
CREATE TABLE IF NOT EXISTS runs(
  day TEXT, source TEXT, fetched INTEGER, added INTEGER, status TEXT, message TEXT, at TEXT);
"""


def norm_title(t: str) -> str:
    t = re.sub(r"[™®©℠]", "", t or "")   # strip before NFKD, which turns ™ into "TM"
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\b(the|a|an)\b", " ", t)
    return re.sub(r"[^a-z0-9]+", "", t)


def _merge_list(a, b):
    return list(dict.fromkeys(list(a or []) + list(b or [])))


class DB:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.c = sqlite3.connect(path)
        self.c.row_factory = sqlite3.Row
        self.c.executescript(SCHEMA)

    def known_ids(self, source):
        rows = self.c.execute("SELECT source_id FROM games WHERE source=? UNION "
                              "SELECT source_id FROM rejected WHERE source=?", (source, source))
        return {r[0] for r in rows}

    def reject(self, source, source_id):
        self.c.execute("INSERT OR IGNORE INTO rejected VALUES(?,?)", (source, source_id))

    def upsert(self, g: Game, day: str) -> bool:
        """Returns True if this is a newly discovered game."""
        row = self.c.execute("SELECT data FROM games WHERE key=?", (g.key,)).fetchone()
        if row:
            old = Game.from_dict(json.loads(row["data"]))
            for f in ("platforms", "raw_genres", "tags", "subgenres", "languages"):
                setattr(g, f, _merge_list(getattr(old, f), getattr(g, f)))
            g.links = {**old.links, **g.links}
            g.extra = {**old.extra, **g.extra,
                       "charts": _merge_list(old.extra.get("charts"), g.extra.get("charts"))}
            self.c.execute("UPDATE games SET data=?, genre=?, last_seen=? WHERE key=?",
                           (json.dumps(g.to_dict()), g.genre, day, g.key))
            new = False
        else:
            self.c.execute("INSERT INTO games VALUES(?,?,?,?,?,?,?,?,?,?)", (
                g.key, g.source, g.source_id, g.title, norm_title(g.title), g.release_date,
                g.genre, json.dumps(g.to_dict()), day, day))
            new = True
        self.snapshot(g, day)
        return new

    def snapshot(self, g: Game, day: str):
        self.c.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?,?,?,?,?)",
                       (g.key, day, g.rating, g.rating_count, g.installs, g.price))

    def recent_ids(self, source, since: str):
        return [r[0] for r in self.c.execute(
            "SELECT source_id FROM games WHERE source=? AND release_date>=?", (source, since))]

    def games_first_seen(self, day: str):
        return [Game.from_dict(json.loads(r["data"])) for r in self.c.execute(
            "SELECT data FROM games WHERE first_seen=? ORDER BY genre, title", (day,))]

    def games_released(self, day: str):
        return [Game.from_dict(json.loads(r["data"])) for r in self.c.execute(
            "SELECT data FROM games WHERE release_date=? ORDER BY genre, title", (day,))]

    def genre_counts(self, since: str, until: str):
        return self.c.execute(
            "SELECT release_date AS day, genre, COUNT(DISTINCT title_norm) AS n FROM games "
            "WHERE release_date BETWEEN ? AND ? GROUP BY release_date, genre", (since, until)).fetchall()

    def growth(self, key):
        return self.c.execute("SELECT day, rating, rating_count, installs FROM snapshots "
                              "WHERE key=? ORDER BY day", (key,)).fetchall()

    def log_run(self, day, source, fetched, added, status, message=""):
        self.c.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", (
            day, source, fetched, added, status, message[:500],
            datetime.now(timezone.utc).isoformat(timespec="seconds")))

    def commit(self):
        self.c.commit()
