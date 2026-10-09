import logging
from datetime import date, timedelta

from .dates import parse_date
from .http import Http
from .sources import REGISTRY
from .sources.base import SourceUnavailable
from .taxonomy import classify

log = logging.getLogger("radar")


def build_sources(cfg, http, only=None):
    out = []
    for name, cls in REGISTRY.items():
        scfg = (cfg.get("sources") or {}).get(name) or {}
        if only and name not in only:
            continue
        if not only and not scfg.get("enabled", True):
            continue
        out.append(cls(http, scfg))
    return out


def collect(cfg, db, run_day: date, only=None, sources=None):
    """Discover releases in [run_day - lookback, run_day], classify, store, then
    snapshot metrics for everything released in the last `track_days`."""
    start = run_day - timedelta(days=int(cfg.get("lookback_days", 3)))
    day = run_day.isoformat()
    http = Http(cfg.get("user_agent", "GameRadar/1.0"))
    sources = sources if sources is not None else build_sources(cfg, http, only)
    summary = {}
    for src in sources:
        src.skip = db.known_ids(src.name)
        fetched = added = 0
        try:
            for g in src.fetch(start, run_day):
                fetched += 1
                rd = parse_date(g.release_date)
                if rd is None:
                    continue                      # undated: try again tomorrow
                if rd < start:
                    db.reject(g.source, g.source_id)  # old game: never fetch again
                    continue
                if rd > run_day:
                    continue                      # pre-release; picked up on launch day
                classify(g)
                added += db.upsert(g, day)
            db.log_run(day, src.name, fetched, added, "ok")
            log.info("%s: fetched %d, new %d", src.name, fetched, added)
        except SourceUnavailable as e:
            db.log_run(day, src.name, fetched, added, "skipped", str(e))
            log.warning("%s skipped: %s", src.name, e)
        except Exception as e:
            db.log_run(day, src.name, fetched, added, "error", repr(e))
            log.exception("%s failed after %d items (kept what was stored)", src.name, fetched)
        db.commit()
        summary[src.name] = added

    since = (run_day - timedelta(days=int(cfg.get("track_days", 30)))).isoformat()
    for src in sources:
        ids = db.recent_ids(src.name, since)
        n = 0
        try:
            for g in src.refresh(ids):
                db.snapshot(g, day)
                n += 1
        except SourceUnavailable:
            pass
        except Exception:
            log.exception("%s refresh failed", src.name)
        if n:
            log.info("%s: refreshed metrics for %d tracked games", src.name, n)
        db.commit()
    return summary
