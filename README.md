# job-monitor

Automated job monitoring pipeline for the Dubai/UAE market. Runs 3x/day via GitHub Actions:
fetches jobs from JSearch, dedupes against previously seen jobs, scores new jobs against
a candidate profile using Claude, and notifies via Slack for high-scoring matches.

## Setup

1. Run [`supabase_setup.sql`](supabase_setup.sql) in the Supabase SQL editor to create tables
   and seed the initial search phrases.
2. Copy `.env.example` to `.env` and fill in values for local runs:
   ```
   cp .env.example .env
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run locally:
   ```
   python src/main.py
   ```

## Adding target companies

Add a company through the dashboard (or insert a row into `companies` with a `careers_url`).
[`src/careers.py`](src/careers.py) automatically pulls jobs for any company on a **Greenhouse**
(`boards.greenhouse.io/<token>`) or **Lever** (`jobs.lever.co/<token>`) board via their public
JSON APIs - no per-company code needed for those. Any other careers URL is skipped with a log
message until a custom scraper branch is added for it.

## GitHub Actions

The workflow at `.github/workflows/monitor.yml` runs at 4:00, 9:00, and 16:00 UTC
(8am, 1pm, 8pm UAE time) and can also be triggered manually via `workflow_dispatch`.

Add these as repository secrets under Settings → Secrets and variables → Actions:

- `JSEARCH_API_KEY`
- `ANTHROPIC_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY` (service role key)
- `SLACK_WEBHOOK_URL`

## Pipeline stages

1. **Fetch** — `fetch.py` queries JSearch per active search phrase; `careers.py` pulls
   directly from Greenhouse/Lever boards for tracked companies on those platforms.
2. **Dedup** — `dedupe.py` fingerprints jobs by normalized title+company and filters out
   anything already in `seen_jobs`.
3. **Score** — `score.py` sends each new job to Claude for a 0-100 relevance score against
   the candidate profile.
4. **Notify** — `notify.py` posts a Slack message for any job scoring 70+.
5. **Save** — all new jobs (regardless of score) are upserted into `seen_jobs`.

Every run is logged in `run_logs` with counts and status (`running`/`completed`/`failed`).
