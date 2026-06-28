-- Platform-wide shared settings, gated by a PIN. Single row (id always 1).
-- Anything in here applies to ALL users, not just one - shared Anthropic/JSearch
-- keys (used as a fallback when a user hasn't set their own), the run schedule,
-- pause state, and the JSearch quota cap.

create table app_settings (
    id integer primary key default 1,
    pin_hash text,
    anthropic_api_key text,
    jsearch_api_key text,
    paused boolean default false,
    run_times jsonb not null default '["04:00", "09:00", "16:00"]'::jsonb,
    jsearch_quota_limit integer default 200,
    jsearch_calls_this_period integer default 0,
    jsearch_period_reset_at timestamptz default (now() + interval '30 days'),
    updated_at timestamptz default now(),
    constraint single_row check (id = 1)
);

insert into app_settings (id) values (1);
