-- Adds a cooldown timestamp so the dashboard's "Run now" button can't be
-- spammed (each manual run costs the user's own Anthropic quota + your JSearch quota).
alter table users add column last_manual_run_at timestamptz;
