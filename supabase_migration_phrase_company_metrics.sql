-- Adds job attribution (which phrase/company actually found a job), run counters
-- for credit/quality tracking, and per-company schedule overrides.

alter table search_phrases add column times_run integer default 0;
alter table search_phrases add column last_run_at timestamptz;

alter table companies add column times_run integer default 0;
alter table companies add column last_run_at timestamptz;
alter table companies add column detected_platform text;
-- null = use the platform-wide default company schedule (app_settings.company_run_times).
-- set = this company runs on its own schedule instead.
alter table companies add column run_times jsonb;

alter table seen_jobs add column search_phrase_id uuid references search_phrases(id) on delete set null;
alter table seen_jobs add column company_id uuid references companies(id) on delete set null;

create index if not exists seen_jobs_search_phrase_id_idx on seen_jobs(search_phrase_id);
create index if not exists seen_jobs_company_id_idx on seen_jobs(company_id);
create index if not exists seen_jobs_user_id_idx on seen_jobs(user_id);

alter table app_settings add column company_run_times jsonb not null default '["09:00"]'::jsonb;
