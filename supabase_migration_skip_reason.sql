-- Adds an optional free-text reason a user can give when skipping a job,
-- so the feedback loop gets richer negative signal than just "skip".
alter table seen_jobs add column skip_reason text;
