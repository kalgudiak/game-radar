import argparse
import logging
from datetime import date, timedelta
from pathlib import Path

import yaml

from .db import DB
from .pipeline import collect
from .report import write_daily, write_trends


def load_config(path):
    p = Path(path)
    if not p.exists():
        p = Path(__file__).resolve().parent.parent / "config.yaml"
    return yaml.safe_load(p.read_text()) if p.exists() else {}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="radar", description="Daily new-game radar, split by genre")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, hlp in (("daily", "collect, then write today's report and 30-day trends"),
                      ("collect", "only collect and store"),
                      ("report", "only write the report for a day")):
        sp = sub.add_parser(name, help=hlp)
        sp.add_argument("--date", type=date.fromisoformat, default=date.today(),
                        help="run date, YYYY-MM-DD (default: today)")
        if name != "report":
            sp.add_argument("--sources", help="comma list, e.g. steam,itch (default: all enabled)")
            sp.add_argument("--lookback", type=int, help="override lookback_days (use 14+ on first run)")
        if name != "collect":
            sp.add_argument("--basis", choices=["discovered", "released"], default="discovered",
                            help="group by day first seen (default) or by store release date")
    ip = sub.add_parser("import", help="import JSON files exported from a browser session, then report")
    ip.add_argument("files", nargs="+")
    ip.add_argument("--date", type=date.fromisoformat, default=date.today())
    ip.add_argument("--note", default="", help="one line shown under the report headline")
    sp2 = sub.add_parser("site", help="build the dashboard website (site/) from all reports")
    sp2.add_argument("--out", default="site")
    tp = sub.add_parser("trends", help="genre counts over a window vs the window before")
    tp.add_argument("--date", type=date.fromisoformat, default=date.today())
    tp.add_argument("--days", type=int, default=30)
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    cfg = load_config(a.config)
    if getattr(a, "lookback", None):
        cfg["lookback_days"] = a.lookback
    db = DB(cfg.get("db_path", "data/radar.db"))
    reports = cfg.get("reports_dir", "reports")

    if a.cmd in ("daily", "collect"):
        only = set(a.sources.split(",")) if a.sources else None
        summary = collect(cfg, db, a.date, only)
        print("New games stored:", summary)
    if a.cmd == "import":
        from .browser_import import import_files
        print("Imported:", import_files(db, a.files, a.date.isoformat()))
        out, rows = write_daily(db, a.date, reports, "discovered", note=a.note)
        print(f"Report: {out} ({len(rows)} unique games)")
    if a.cmd in ("daily", "report"):
        out, rows = write_daily(db, a.date, reports, a.basis)
        print(f"Report: {out} ({len(rows)} unique games)")
    if a.cmd in ("daily", "site"):
        from .site import build_site
        out, days = build_site(reports, getattr(a, "out", "site"))
        print(f"Dashboard site: {out} ({len(days)} days)")
    if a.cmd in ("daily", "trends"):
        print("Trends:", write_trends(db, a.date, getattr(a, "days", 30), reports))
