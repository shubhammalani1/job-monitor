-- Per-phrase schedule override, mirroring the existing per-company one (companies.run_times,
-- added in supabase_migration_phrase_company_metrics.sql). null = use the platform-wide
-- default phrase schedule (app_settings.run_times). set = this phrase runs on its own
-- schedule instead - added so a phrase can run less often than the shared default without
-- affecting every other phrase's cadence.

alter table search_phrases add column run_times jsonb;
