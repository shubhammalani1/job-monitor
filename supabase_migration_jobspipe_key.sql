-- Shared JobsPipe key, configurable from the admin Settings UI the same way
-- anthropic_api_key and jsearch_api_key already are - falls back to the
-- JOBSPIPE_API_KEY GitHub Actions secret if the admin hasn't set one via the dashboard.

alter table app_settings add column jobspipe_api_key text;
