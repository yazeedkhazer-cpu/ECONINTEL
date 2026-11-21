# ECONINTEL v1.2 — Live Official Data Infrastructure

**Upgrade of ECONINTEL v1.1 (not a replacement).** The Arabic RTL dashboard, its 34 labor indicators, browser-only archive, JSON/CSV export, and original design remain intact. This version introduces official data pipelines and website refresh logic.

## Operating status — important

- **Ready for deployment; not yet deployed online.** The repository must be pushed to GitHub and GitHub Pages configured.
- **Tests are deterministic/offline.** This distribution does not claim any live BLS/FRED reading was fetched: source API connectivity was unavailable while producing it. Initial seed figures are historical reference snapshots only.
- After deployment, a server-side GitHub Actions task downloads official data and publishes `data/official-latest.json`. Browser re-checks that JSON on open, every 5 minutes when the tab is visible, and via the `↻ التحقق الآن` button.
- Actual changes depend on the **source publication schedule**, API availability, and how soon the scheduled Action runs. No second-by-second feed is implied.
- Never put API keys in front-end HTML/JavaScript or source code. Store them only as GitHub Actions Secrets.

## What updates automatically?

**22/34 indicators** from the U.S. Bureau of Labor Statistics (BLS public data API), including derived metrics:
NFP, private payrolls, U-3, U-6, participation, employment/population, prime age participation, total hourly earnings and MoM/YoY wage changes, hours, temp help, JOLTS job openings, hires, quits, layoffs, long-term unemployed, involuntary part-time, vacancy/unemployment ratio, the 3M/12M payroll averages, and long-term unemployed share.

**Another 8/34** with a FREE optional `FRED_API_KEY` via the Federal Reserve Bank of St. Louis, with data originally sourced from BLS/ETA:
- Initial claims `ICSA` and 4-week average (consecutive weekly observations only)
- Continuing claims `CCSA`
- ECI `ECIALLCIV`: quarter-over-quarter and year-over-year changes from seasonally adjusted index values
- Productivity `OPHNFB`, and unit labor costs `ULCNFB`: quarterly annualized rates, derived from index levels
- Sahm recession indicator `SAHMREALTIME`

**Not yet automatically updated (4/34):** BLS employment diffusion series, ADP, ISM Manufacturing Employment, and ISM Services Employment. These are marked as reference rather than pretending to be live. Sector bars are also a separately labeled archived snapshot and are not part of the 34 count.

## Sources, units, revisions

| Pipeline | Source | Frequency | Behavior |
|---|---|---|---|
| BLS | <https://www.bls.gov/developers/> | monthly | v1 unregistered; v2 when `BLS_API_KEY` set |
| JOLTS | BLS Public API | monthly, often later than NFP | Last *individual* release period, never aligned by guessing |
| Weekly claims | DOL / ETA through FRED | weekly | Actual Saturday week-ending date; 4-week mean requires four consecutive weeks |
| ECI, productivity, unit labor costs | BLS through FRED | quarterly | Quarterly index conversion with correct percentage basis |
| Sahm | FRED | monthly | Most recent available period |

`generatedAt` is **the fetch timestamp, not an original data release timestamp**. `observedAt` tracks the fetch timestamp for each metric. Periods are shown separately (2026-10, 2026-11-07, 2026-Q3). Older providers retain their last observation timestamp and can display stale badges. The initial BLS/FRED values are *latest-revised vintages*; they are **not** suitable for event-date backtests without ALFRED or stored as-released versions and actual release timestamps. `data/snapshots/` will archive changed server-side snapshots with a `capturedAt` time, which is not the same as original publication time.

## How to publish online (GitHub Pages)

1. Create a **new** GitHub repository named `econintel` (do not overwrite another project).
2. Push the **CONTENTS** of this `us-economic-intelligence` folder to the repository root, branch `main`. Keep `.github/workflows/update-data.yml` as-is.
3. In GitHub repository go to **Settings → Pages → Build and deployment → Source: GitHub Actions**.
4. In **Settings → Secrets and variables → Actions**, create the secret `FRED_API_KEY` (free key from <https://fred.stlouisfed.org/docs/api/api_key.html>). You may optionally create `BLS_API_KEY` (free registration at <https://data.bls.gov/registrationEngine/>), but the BLS v1 endpoint is usable without a key at its lower limits.
5. Open **Actions → Update ECONINTEL and publish website → Run workflow**. Check that unit tests pass and the `Download official data` step succeeds, then the `Deploy` step succeeds.
6. Website URL will be `https://YOUR-GITHUB-USERNAME.github.io/econintel/` (or the URL shown in the Pages deployment). It will refresh server data at scheduled checks.
7. GitHub's schedule is **best effort**; a provider outage retains the most recent available snapshot. Inspect Actions logs if data are stale, and use the manual `Run workflow` action when appropriate.

The schedule runs hourly on weekdays during U.S. release hours, and once per weekend day. The no-key BLS version has daily query limits: manually triggering excessively may hit them. The browser's 5-minute polling makes *no direct API requests* to BLS/FRED; it only reads the published JSON.

### From Windows Terminal / CMD (Git installed)

First create your empty repo on GitHub. Then unzip and run in CMD (change username):

```bat
cd C:\path\to\us-economic-intelligence
git init
git add .
git commit -m "ECONINTEL v1.2 live official data"
git branch -M main
git remote add origin https://github.com/YOUR-GITHUB-USERNAME/econintel.git
git push -u origin main
```

If `git` is not installed, use GitHub Desktop to add and publish the directory. **Do not upload just the ZIP to GitHub**: GitHub doesn't automatically unpack it.

## Local view and checks

- Open `index.html` to view the seed offline. Auto-fetch requires hosted HTTP(S) site or localhost server.
- `python -m http.server 8000` and `http://localhost:8000/` will display the site, but live JSON will appear only after executing updater successfully.
- `python scripts/update_all.py` fetches validated official BLS readings and FRED if configured; creates `data/official-latest.json` and `assets/official-data.js` atomically and records changed snapshots.
- `python -m unittest discover -s tests -v` runs synthetic validation tests.
- `node --check assets/app.js` checks JavaScript syntax.
- `scripts/update_bls.py` is preserved for compatibility, but the deployed pipeline calls the newer `scripts/update_all.py`.

## Limitations and next phases

- Next: authoritative diffusion index ID and licensed/approved ADP and ISM feeds; do not scrape protected pages and call that an official API.
- Source freshness and release times are different. A once-downloaded revision cannot reconstruct what investors knew at a given historical timestamp.
- Price data (XAUUSD), CPI/PCE, Fed/FOMC modules, actual-vs-consensus surprises, and as-of backtesting are **not implemented in this release**. These are separate future milestones.
- GitHub Actions secrets are never exposed to the browser.
