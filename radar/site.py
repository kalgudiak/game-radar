"""Builds the dashboard website from the reports folder.
  site/index.html       the dashboard: every game released in the last `window` days, from all runs
  site/data/<day>.csv   each run's games as a download
History lives in reports/<day>/games.json, so the site can always be rebuilt from scratch."""
import json
import os
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .dashboard import aggregate, render, slim
from .db import norm_title

IST = timezone(timedelta(hours=5, minutes=30))


def _days(reports):
    return sorted(p.name for p in Path(reports).iterdir()
                  if p.is_dir() and (p / "games.json").exists() and p.name[:4].isdigit())


def build_site(reports="reports", out="site", window=14, history_days=60):
    reports, out = Path(reports), Path(out)
    days = _days(reports)
    if not days:
        raise SystemExit("No reports yet: run `python -m radar daily` first.")
    union = {}
    for d in days:  # oldest first, so a later sighting of the same game wins
        for r in json.loads((reports / d / "games.json").read_text(encoding="utf-8")):
            if r.get("release_date"):
                union[(norm_title(r["title"]), r["release_date"])] = (r, d)
    last = max(r["release_date"] for r, _ in union.values())
    last_d = date.fromisoformat(last)
    hist_from = (last_d - timedelta(days=history_days - 1)).isoformat()
    list_from = (last_d - timedelta(days=window - 1)).isoformat()
    full = [r for r, _ in union.values() if r["release_date"] >= hist_from]
    rows = [slim(r, seen) for r, seen in union.values() if list_from <= r["release_date"] <= last]

    if out.exists():
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)
    for d in days:
        if (reports / d / "games.csv").exists():
            shutil.copy(reports / d / "games.csv", out / "data" / f"{d}.csv")
    repo = os.environ.get("GITHUB_REPOSITORY")
    meta = {
        "updated": datetime.now(IST).strftime("%d %b %Y, %H:%M IST").lstrip("0"),
        "csv": f"data/{days[-1]}.csv",
        "repo": f"https://github.com/{repo}" if repo else "",
        "note": "",
        "runs": len(days),
    }
    (out / "index.html").write_text(render(rows, aggregate(full), meta), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    return out, days
