-- Run this entire file in the Supabase SQL editor before the first run.

create extension if not exists pgcrypto;

create table search_phrases (
    id uuid primary key default gen_random_uuid(),
    phrase text not null,
    location text default 'Dubai, UAE',
    active boolean default true,
    created_at timestamptz default now()
);

create table companies (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    careers_url text,
    active boolean default true,
    notes text,
    last_scraped_at timestamptz,
    created_at timestamptz default now()
);

create table seen_jobs (
    id uuid primary key default gen_random_uuid(),
    fingerprint text unique not null,
    external_job_id text,
    title text,
    company_name text,
    source_platform text,
    date_posted timestamptz,
    claude_score integer,
    claude_reasoning text,
    salary_likely_above_floor boolean,
    status text default 'new',
    job_url text,
    raw_data jsonb,
    notified_at timestamptz,
    created_at timestamptz default now()
);

create table run_logs (
    id uuid primary key default gen_random_uuid(),
    started_at timestamptz default now(),
    completed_at timestamptz,
    phrases_run integer default 0,
    companies_checked integer default 0,
    new_jobs_found integer default 0,
    jobs_notified integer default 0,
    errors jsonb,
    status text default 'running'
);

-- Seed data
insert into search_phrases (phrase, location) values
('product manager', 'Dubai, UAE'),
('senior product manager', 'Dubai, UAE'),
('head of product', 'Dubai, UAE'),
('strategy manager', 'Dubai, UAE'),
('chief of staff', 'Dubai, UAE'),
('head of growth', 'UAE');
