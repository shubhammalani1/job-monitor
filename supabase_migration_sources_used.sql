-- Tracks which job sources (jsearch, jobspipe, remoteok, we_work_remotely, hn_whos_hiring)
-- actually returned data on each run, for visibility into source-level coverage as more
-- sources get added over time.

alter table run_logs add column sources_used jsonb;
