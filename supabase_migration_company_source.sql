-- Tracks how each company entered the list - manually added by the user, part of the
-- initial curated seed, or auto-discovered from a high-scoring job lead (see
-- discover_company_ats in careers.py). Surfaced in the dashboard so a long, growing
-- company list stays self-explanatory instead of looking like an opaque pile.

alter table companies add column source text not null default 'manual';
