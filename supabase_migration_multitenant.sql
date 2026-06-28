-- Multi-tenant migration. Run this in the Supabase SQL editor AFTER the original
-- supabase_setup.sql has already been run once.
--
-- This converts the single-tenant schema into a multi-tenant one:
--   - adds a `users` table (one row per person using the product)
--   - adds user_id to search_phrases, companies, seen_jobs, run_logs
--   - migrates existing data into a first "Shubham" user row so nothing is lost
--   - changes the seen_jobs uniqueness constraint to be per-user

create extension if not exists pgcrypto;

-- 1. Users table
create table users (
    id uuid primary key default gen_random_uuid(),
    access_token text unique not null default encode(gen_random_bytes(32), 'hex'),
    name text not null,
    email text,
    profile jsonb not null default '{}'::jsonb,
    -- profile shape: {
    --   current_role, current_company, location,
    --   background: [string, ...],
    --   education: [string, ...],
    --   target_roles: [string, ...],
    --   target_location: string,
    --   hard_avoids: [string, ...],
    --   salary_floor_amount: number,
    --   salary_floor_currency: string
    -- }
    anthropic_api_key text,
    slack_webhook_url text,
    active boolean default true,
    created_at timestamptz default now()
);

-- 2. Add user_id to existing tables
alter table search_phrases add column user_id uuid references users(id);
alter table companies add column user_id uuid references users(id);
alter table seen_jobs add column user_id uuid references users(id);
alter table run_logs add column user_id uuid references users(id);

-- 3. Migrate existing data into a first user row (preserves what's already there)
do $$
declare
    shubham_id uuid;
begin
    insert into users (name, email, profile, active)
    values (
        'Shubham',
        'shubham.malani@zomato.com',
        '{
            "current_role": "Senior Manager Strategy & Growth",
            "current_company": "Zomato",
            "location": "Bangalore",
            "background": [
                "6 years experience in strategy, growth, marketplace operations",
                "Currently at Zomato managing Bangalore food delivery marketplace",
                "Previously scaled a healthcare startup (Clinikk Healthcare) from pre-revenue to significant ARR as Head of Growth",
                "Selected in elite 18-person Generalist Program at Zomato",
                "Top 5% in GrowthX product & growth program",
                "Strong in: analytical thinking, cross-functional leadership, 0-to-1 builds, marketplace dynamics, performance marketing, AI tools"
            ],
            "education": [
                "BITS Pilani dual degree (Mechanical Engineering + Mathematics)"
            ],
            "target_roles": ["Strategy", "Special Projects", "Growth", "Product"],
            "target_location": "Dubai/UAE",
            "hard_avoids": ["field ops", "sales targets", "logistics execution roles", "ops-heavy roles"],
            "salary_floor_amount": 20000,
            "salary_floor_currency": "AED"
        }'::jsonb,
        true
    )
    returning id into shubham_id;

    update search_phrases set user_id = shubham_id where user_id is null;
    update companies set user_id = shubham_id where user_id is null;
    update seen_jobs set user_id = shubham_id where user_id is null;
    update run_logs set user_id = shubham_id where user_id is null;
end $$;

-- 4. Make user_id required going forward and scope uniqueness per user
alter table search_phrases alter column user_id set not null;
alter table companies alter column user_id set not null;
alter table seen_jobs alter column user_id set not null;
alter table run_logs alter column user_id set not null;

alter table seen_jobs drop constraint seen_jobs_fingerprint_key;
alter table seen_jobs add constraint seen_jobs_fingerprint_user_unique unique (fingerprint, user_id);
