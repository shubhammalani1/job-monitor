-- Adds structured sub-scores alongside the existing overall claude_score (technical
-- fit, AI relevance, remote/location fit, career growth) so the dashboard can show a
-- real breakdown instead of just one number, and backs the per-company "new postings
-- this week" radar signal with an index on (company_id, created_at).

alter table seen_jobs add column technical_match integer;
alter table seen_jobs add column ai_relevance integer;
alter table seen_jobs add column remote_fit integer;
alter table seen_jobs add column career_growth integer;

create index if not exists seen_jobs_company_id_created_at_idx on seen_jobs(company_id, created_at);
