# Game Radar

Collects every new game it can find across PC, consoles, iOS, Android and itch.io once a day,
puts each one into a single genre (plus mechanic-level sub-genres such as Merge, Runner,
Survivors-like, Idle RPG, Tower Defense), and writes a daily report.

## Setup

```bash
pip install -r requirements.txt
export TWITCH_CLIENT_ID=...       # free: dev.twitch.tv/console -> register an app (for IGDB)
export TWITCH_CLIENT_SECRET=...
python -m radar daily --lookback 14   # first run: backfill two weeks
python -m radar daily                 # every day after that
```

Other commands: `python -m radar collect --sources steam,itch`, `python -m radar report --date 2026-10-08 --basis released`,
`python -m radar trends --days 30`. Run `python -m pytest` for the parser and pipeline tests.

## What you get each day (`reports/YYYY-MM-DD/`)

| File | Contents |
|---|---|
| `report.html` | Filterable page: genre bands, platform filter, sub-genre filter, search, sortable columns. Each game title opens its main store page, with buttons for every other store and site |
| `summary.md` | Genre x platform count table, sub-genres seen, per-genre lists |
| `games.csv` | One row per store listing with every field, a column per store link (`steam_url`, `appstore_url`, `googleplay_url`, `itch_url`, `epic_url`, `playstation_url`, `xbox_url`, `eshop_url`, `website`) and `all_links` |
| `games.json` | One row per game, cross-store duplicates merged |
| `reports/trends/` | Genre counts by release day, and share/change vs the previous window |

`data/radar.db` (SQLite) keeps every game plus a daily snapshot of rating, rating count, installs
and price for the first 30 days after release, so you can spot breakouts:
`SELECT * FROM snapshots WHERE key='steam:123' ORDER BY day`.

## Sources and coverage

| Source | Platforms | How | Coverage |
|---|---|---|---|
| IGDB | PC, PS, Xbox, Switch, mobile majors, VR | Official API (Twitch auth) | Broad for PC/console; thinner for small mobile titles |
| Steam | PC/Mac/Linux | Newest-releases listing + appdetails + reviews; SteamSpy tags | Near-complete |
| App Store | iOS | Chart feeds for all 20 game categories per storefront + iTunes Lookup | New games that reach any chart (the commercially relevant slice) |
| Google Play | Android | Genre-seeded search + app pages (google-play-scraper) | Partial; Play has no public new-releases list |
| itch.io | PC/Web/Mac/Linux | Per-genre "newest" RSS feeds | Near-complete for recent uploads |

**Exhaustive mobile coverage** (every app published each day) is not available from free sources.
If you need it, add a source class for a paid provider (AppMagic, Sensor Tower, Appfigures,
42matters); each source is one file in `radar/sources/` implementing `fetch(start, end)`.

## Links

Every game carries its store page, plus whatever else the source knows: the developer website
(Steam, App Store, Google Play) and, from IGDB, links to Epic, GOG, PlayStation Store, Xbox, eShop,
Discord, YouTube and so on. When the same game is on several stores, all its links are merged.
Store pages are listed first, then the website, then community pages. Domain labels live in
`radar/links.py`.

## How genre is decided

`radar/taxonomy.py` maps every store's genre names, IGDB themes and Steam community tags to one
list of 26 genres. If a game maps to several, the most specific wins (Roguelike over Action,
Puzzle over Casual). Sub-genres are matched on title, tags and genres; a few noisy ones (Idle,
Runner, Co-op...) are never taken from descriptions. Edit `RAW_MAP`, `SUBGENRES` and the
`GENRES` priority order to fit how you think about the market.

## Behaviour notes

- Each run looks back `lookback_days` (default 3) because stores index late. Reports group by the
  day a game was first discovered by default; use `--basis released` to group by store date.
- Games found to be older than the window are remembered and never fetched again, so daily
  runs get cheaper after the first week. Pre-release titles are retried until launch day.
- A failing source is logged in the `runs` table and skipped; the others still run.
- Requests are rate-limited per host (`radar/http.py`). Steam, Apple and Google Play store pages are
  not official public APIs: keep the volume polite, set a real contact in `user_agent`, check each
  store's terms for your use, and check IGDB's terms for commercial use.
- Same-title games on different stores are merged in the report. Very generic titles
  ("Snake") can merge wrongly; the CSV keeps every listing separately.

## Daily dashboard (GitHub Actions + GitHub Pages)

Every morning at 07:00 IST the workflow collects new games, writes that day's report, rebuilds the
dashboard website and publishes it. The dashboard has the latest day, a day picker for every past
day, a Trends page (new games per day by genre, week-on-week genre and sub-genre changes) and a
CSV download per day. History is kept in `reports/`, so nothing is lost if the cache is cleared.

One-time setup (about 10 minutes):
1. Create a GitHub repository (for example `bomome/game-radar`) and upload everything in this folder,
   including the hidden `.github` folder and the `reports/` folder (it holds the first day of real data).
2. Settings > Pages > Build and deployment > Source: **GitHub Actions**.
3. Optional, for console games: Settings > Secrets and variables > Actions, add `TWITCH_CLIENT_ID` and
   `TWITCH_CLIENT_SECRET` (free app at dev.twitch.tv/console).
4. Actions > game-radar-daily > Run workflow, lookback `14`. The first run takes 30-60 minutes.
5. Your dashboard: `https://<your-account>.github.io/game-radar/`. It updates itself every day after that.

Privacy: a GitHub Pages site is public to anyone with the link (private sites need GitHub Enterprise),
and Pages from a private repository needs a paid GitHub plan. The data is all public store data, but if
you want the dashboard behind a login, deploy the `site/` folder to Cloudflare Pages with Cloudflare
Access instead (free for up to 50 people).

Build the site locally any time with `python -m radar site` and open `site/index.html`.

## Scheduling

On your own server instead of GitHub (then serve the `site/` folder with any web server):
`30 1 * * * cd /opt/game-radar && python -m radar daily >> radar.log 2>&1` (UTC).
