# job-monitor

Automated, multi-tenant job monitoring pipeline. Runs 3x/day via GitHub Actions: fetches
jobs from multiple sources, dedupes against previously seen jobs, scores new jobs against
each candidate's profile using Claude, and notifies via Slack for high-scoring matches.

## Data sources

- **JSearch** (`fetch.py`) - aggregated listings (LinkedIn, Indeed, Glassdoor, and more)
  via per-phrase/location search.
- **JobsPipe** (`fetch_jobspipe.py`) - a second, independent aggregated source layered on
  top of JSearch for the same phrases, plus a separate remote-only pass. Optional - no-ops
  if no key is configured, so it never blocks the pipeline. Same key-resolution pattern as
  JSearch: settable from the dashboard's admin Settings tab, falling back to the
  `JOBSPIPE_API_KEY` GitHub secret if the admin hasn't set one there yet.
- **Company careers pages** (`careers.py`) - direct pulls from a tracked company's own
  Greenhouse, Lever, Ashby, SmartRecruiters, Workable, or Attrax-powered board.
- **RemoteOK, We Work Remotely, Hacker News "Who is hiring"** (`sources.py`) - aggregator
  sources for roles that may never appear on a mainstream job board.

All sources normalize to the same job dict shape before hitting dedup, so adding another
source means writing one more `fetch_*` function with that same `{external_job_id, title,
company_name, source_platform, date_posted, job_url, raw_data}` contract - no changes
needed elsewhere in the pipeline.

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
[`src/careers.py`](src/careers.py) automatically pulls jobs for any company on:
- **Greenhouse** (`boards.greenhouse.io/<token>`), **Lever** (`jobs.lever.co/<token>`),
  **Ashby** (`jobs.ashbyhq.com/<token>`), **SmartRecruiters**
  (`jobs.smartrecruiters.com/<token>`), or **Workable** (`apply.workable.com/<token>`) -
  all via their public JSON APIs
- **Attrax** career sites (white-labelled per company, e.g. `careers.deliveryhero.com`,
  detected by fetching the page and checking for Attrax's markup, then scraped directly)

No per-company code is needed for any of those. Any other careers URL is skipped with a
log message until a custom scraper branch is added for it.

Companies also get added automatically: when a job from an aggregator source scores well,
`discover_company_ats()` probes that company's name directly against the platforms above and
starts tracking its careers page going forward, so the list grows from real signal instead of
needing to be hand-maintained.

## GitHub Actions

The workflow at `.github/workflows/monitor.yml` runs at 4:00, 9:00, and 16:00 UTC
(8am, 1pm, 8pm UAE time) and can also be triggered manually via `workflow_dispatch`.

Add these as repository secrets under Settings → Secrets and variables → Actions:

- `JSEARCH_API_KEY`
- `JOBSPIPE_API_KEY` (optional - get one at [jobspipe.dev](https://jobspipe.dev))
- `ANTHROPIC_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY` (service role key)
- `SLACK_WEBHOOK_URL`

## Pipeline stages

1. **Fetch** — see [Data sources](#data-sources) above; `fetch.py` and `fetch_jobspipe.py`
   query per active search phrase, `careers.py` pulls directly from tracked companies'
   boards, and `sources.py` checks the aggregator sources once per run.
2. **Dedup** — `dedupe.py` fingerprints jobs by normalized title+company and filters out
   anything already in `seen_jobs`.
3. **Score** — `score.py` sends each new job to Claude for a 0-100 relevance score against
   the candidate profile.
4. **Notify** — `notify.py` posts a Slack message for any job scoring 70+.
5. **Save** — all new jobs (regardless of score) are upserted into `seen_jobs`.

Every run is logged in `run_logs` with counts and status (`running`/`completed`/`failed`).
