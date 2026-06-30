from __future__ import annotations

import datetime
import json
import os

from config import (
    get_active_users,
    get_active_phrases,
    get_active_companies,
    get_supabase,
    get_app_settings,
    get_effective_jsearch_key,
    reset_jsearch_usage_if_due,
    increment_jsearch_usage,
    mark_phrase_run,
    mark_company_run,
    get_recent_company_posting_count,
)
from fetch import fetch_jobs_for_phrase
from careers import scrape_company_careers, discover_company_ats
from sources import fetch_remoteok_jobs, fetch_wwr_jobs, fetch_hn_whos_hiring, matches_any_target_role
from dedupe import filter_new_jobs, save_jobs
from score import score_job
from notify import send_slack_notification
from feedback import get_feedback_examples
from extract import enrich_description_if_thin
from verify import filter_dead_links

SCORE_THRESHOLD = 70
AUTO_TRACK_SCORE_THRESHOLD = 65


def create_run_log(user_id: str) -> str | None:
    try:
        supabase = get_supabase()
        response = (
            supabase.table("run_logs")
            .insert({"status": "running", "user_id": user_id})
            .execute()
        )
        return response.data[0]["id"]
    except Exception as e:
        print(f"ERROR: failed to create run log for user {user_id}: {e}")
        return None


def update_run_log(run_id: str | None, **fields) -> None:
    if not run_id:
        return
    try:
        supabase = get_supabase()
        supabase.table("run_logs").update(fields).eq("id", run_id).execute()
    except Exception as e:
        print(f"ERROR: failed to update run log {run_id}: {e}")


def _is_scheduled_run_time(run_times: list[str]) -> bool:
    """True if the current UTC hour matches one of the configured run times.
    The cron heartbeat fires every hour, so matching on the hour is enough granularity."""
    current_hour = datetime.datetime.now(datetime.timezone.utc).hour
    configured_hours = set()
    for t in run_times or []:
        try:
            configured_hours.add(int(t.split(":")[0]))
        except (ValueError, IndexError):
            continue
    return current_hour in configured_hours


def run_for_user(
    user: dict,
    app_settings: dict,
    jsearch_budget: dict,
    phrase_ids: list[str] | None,
    company_ids: list[str] | None,
    phrases_due: bool,
    is_on_demand: bool,
) -> None:
    user_id = user["id"]
    profile = user.get("profile") or {}
    anthropic_api_key = user.get("anthropic_api_key") or app_settings.get("anthropic_api_key")
    slack_webhook_url = user.get("slack_webhook_url")
    jsearch_api_key = get_effective_jsearch_key(app_settings)
    default_company_run_times = app_settings.get("company_run_times")

    run_id = create_run_log(user_id)
    print(f"--- Run started for user '{user.get('name')}' ({user_id}), run_id={run_id} ---")

    phrases_run = 0
    companies_checked = 0

    try:
        phrases = get_active_phrases(user_id, phrase_ids)
        companies = get_active_companies(user_id, company_ids)
        print(f"Loaded {len(phrases)} active phrases, {len(companies)} active companies")

        # Fetch phase
        all_jobs = []
        target_roles = profile.get("target_roles") or []

        for phrase_row in phrases:
            phrase_run_times = phrase_row.get("run_times")
            phrase_due = is_on_demand or (
                _is_scheduled_run_time(phrase_run_times) if phrase_run_times else phrases_due
            )
            if not phrase_due:
                continue

            if jsearch_budget["remaining"] <= 0:
                print(
                    f"WARNING: JSearch quota cap reached ({app_settings.get('jsearch_quota_limit')} "
                    f"requests this period) - skipping remaining phrase fetches"
                )
                break

            phrase = phrase_row.get("phrase")
            location = phrase_row.get("location") or "Dubai, UAE"
            print(f"Fetching jobs for phrase: '{phrase}' in '{location}'")
            jobs = fetch_jobs_for_phrase(phrase, location, jsearch_api_key)
            for job in jobs:
                job["search_phrase_id"] = phrase_row.get("id")
            all_jobs.extend(jobs)
            phrases_run += 1
            jsearch_budget["remaining"] -= 1
            increment_jsearch_usage(1)
            mark_phrase_run(phrase_row.get("id"), phrase_row.get("times_run") or 0)

        for company_row in companies:
            company_run_times = company_row.get("run_times") or default_company_run_times
            company_due = is_on_demand or _is_scheduled_run_time(company_run_times)
            if not company_due:
                continue

            company_name = company_row.get("name")
            careers_url = company_row.get("careers_url")
            print(f"Checking careers page for: {company_name}")
            all_company_jobs, detected_platform = scrape_company_careers(company_name, careers_url)

            # A company's careers feed returns every open role, not just ones relevant to
            # this candidate - a 300-person AI company posts plenty of Sales/Finance/Eng
            # roles alongside the rare PM one. Filtering by target_roles here (same as the
            # aggregator sources) keeps us from spending a link-check, an enrich fetch, and
            # a paid Claude call on hundreds of postings that were never going to be relevant.
            jobs = (
                [j for j in all_company_jobs if matches_any_target_role(j.get("title"), target_roles)]
                if target_roles
                else all_company_jobs
            )
            if len(all_company_jobs) != len(jobs):
                print(
                    f"{company_name}: {len(all_company_jobs)} open roles, "
                    f"{len(jobs)} match target roles"
                )

            recent_activity = get_recent_company_posting_count(company_row.get("id")) if jobs else 0
            for job in jobs:
                job["company_id"] = company_row.get("id")
                job["company_hiring_signal"] = recent_activity
            all_jobs.extend(jobs)
            companies_checked += 1
            mark_company_run(company_row.get("id"), company_row.get("times_run") or 0, detected_platform)

        # Aggregator sources - not tied to any phrase/company row, so they run once per
        # user on the same schedule as phrases rather than per-phrase. No JSearch quota
        # cost (separate free APIs), so they're not gated by jsearch_budget.
        if phrases_due and target_roles:
            for source_name, fetch_source in (
                ("RemoteOK", fetch_remoteok_jobs),
                ("We Work Remotely", fetch_wwr_jobs),
                ("HN Who's Hiring", fetch_hn_whos_hiring),
            ):
                print(f"Checking aggregator source: {source_name}")
                jobs = fetch_source(target_roles)
                all_jobs.extend(jobs)
                print(f"{source_name}: {len(jobs)} jobs matched target roles")

        total_found = len(all_jobs)

        # Dedup phase
        new_jobs, dupes = filter_new_jobs(all_jobs, user_id)
        new_jobs_found = len(new_jobs)
        print(f"Found {total_found} jobs, {new_jobs_found} new, {dupes} already seen")

        # Verify phase - drop dead/broken links before spending an enrich fetch or a
        # scoring call on a posting the candidate can't actually open.
        new_jobs, dead_links = filter_dead_links(new_jobs)
        print(f"Link check: {len(new_jobs)} alive, {dead_links} dead/broken dropped")

        # Enrich phase - fetch full descriptions for jobs whose source only gave a thin one,
        # so scoring (and future feedback) works off real content, not a title alone.
        for job in new_jobs:
            enrich_description_if_thin(job)

        # Score phase
        if not anthropic_api_key:
            print(f"WARNING: user '{user.get('name')}' has no anthropic_api_key configured - jobs will not be scored")

        feedback = get_feedback_examples(user_id)
        print(f"Loaded feedback: {len(feedback['liked'])} liked, {len(feedback['disliked'])} disliked past jobs")

        for job in new_jobs:
            result = score_job(job, profile, anthropic_api_key, feedback)
            job["claude_score"] = result["score"]
            job["claude_reasoning"] = result["reasoning"]
            job["salary_likely_above_floor"] = result["salary_likely_above_floor"]
            job["technical_match"] = result["technical_match"]
            job["ai_relevance"] = result["ai_relevance"]
            job["remote_fit"] = result["remote_fit"]
            job["career_growth"] = result["career_growth"]
            print(f"Scored: {job.get('title')} at {job.get('company_name')} → {result['score']}/100")

        # Auto-discovery phase - a job scoring well from an aggregator source (JSearch,
        # RemoteOK, etc) proves that company is relevant. Probe its name directly against
        # the supported ATS platforms; on a hit, start tracking its careers page going
        # forward, so future runs catch roles that company never syndicates to aggregators
        # at all. This is how the companies list grows - not by hand-picking guesses.
        known_company_names = {(c.get("name") or "").lower() for c in companies}
        for job in new_jobs:
            if (job.get("claude_score") or 0) < AUTO_TRACK_SCORE_THRESHOLD:
                continue
            if job.get("company_id"):
                continue  # already a directly-tracked company, nothing new to discover
            company_name = job.get("company_name")
            if not company_name or company_name.lower() in known_company_names:
                continue
            known_company_names.add(company_name.lower())  # don't re-probe twice in one run

            discovered_url = discover_company_ats(company_name)
            if not discovered_url:
                continue
            try:
                get_supabase().table("companies").insert(
                    {
                        "user_id": user_id,
                        "name": company_name,
                        "careers_url": discovered_url,
                        "active": True,
                        "source": "auto-discovered",
                    }
                ).execute()
                print(f"Auto-discovered direct careers page for '{company_name}': {discovered_url} - now tracking")
            except Exception as e:
                print(f"ERROR: failed to save auto-discovered company '{company_name}': {e}")

        # Notify phase
        notified_count = 0
        for job in new_jobs:
            if job.get("claude_score", 0) >= SCORE_THRESHOLD:
                send_slack_notification(
                    job,
                    {
                        "score": job["claude_score"],
                        "reasoning": job["claude_reasoning"],
                        "salary_likely_above_floor": job["salary_likely_above_floor"],
                    },
                    slack_webhook_url,
                )
                job["notified_at"] = datetime.datetime.utcnow().isoformat()
                notified_count += 1
        print(f"Notified: {notified_count} jobs")

        # Save phase
        save_jobs(new_jobs, user_id)

        update_run_log(
            run_id,
            completed_at=datetime.datetime.utcnow().isoformat(),
            phrases_run=phrases_run,
            companies_checked=companies_checked,
            new_jobs_found=new_jobs_found,
            jobs_notified=notified_count,
            status="completed",
        )

        print(f"--- Run summary for user '{user.get('name')}' ---")
        print(f"Phrases run: {phrases_run}, companies checked: {companies_checked}")
        print(f"Total jobs found: {total_found}, new: {new_jobs_found} (duplicates: {dupes})")
        print(f"Jobs notified: {notified_count}")

    except Exception as e:
        print(f"ERROR: run failed for user '{user.get('name')}' ({user_id}): {e}")
        update_run_log(
            run_id,
            completed_at=datetime.datetime.utcnow().isoformat(),
            status="failed",
            errors=json.dumps({"error": str(e)}),
        )


def main():
    target_user_id = os.environ.get("TARGET_USER_ID") or None
    phrase_ids_raw = os.environ.get("TARGET_PHRASE_IDS") or ""
    company_ids_raw = os.environ.get("TARGET_COMPANY_IDS") or ""
    phrase_ids = [p.strip() for p in phrase_ids_raw.split(",") if p.strip()] or None
    company_ids = [c.strip() for c in company_ids_raw.split(",") if c.strip()] or None
    is_on_demand = bool(target_user_id or phrase_ids or company_ids)

    print("=== Job monitor run started ===" + (f" (target user: {target_user_id})" if target_user_id else ""))

    app_settings = get_app_settings()
    app_settings = reset_jsearch_usage_if_due(app_settings)

    if app_settings.get("paused") and not is_on_demand:
        print("Pipeline is paused (platform setting) - skipping this scheduled run")
        return

    phrases_due = is_on_demand or _is_scheduled_run_time(app_settings.get("run_times"))
    if not phrases_due:
        print(
            f"Not a configured phrase run time (run_times={app_settings.get('run_times')}) - "
            f"will still check any companies due this hour"
        )

    quota_limit = app_settings.get("jsearch_quota_limit") or 200
    calls_used = app_settings.get("jsearch_calls_this_period") or 0
    jsearch_budget = {"remaining": max(quota_limit - calls_used, 0)}
    print(f"JSearch quota: {calls_used}/{quota_limit} used this period, {jsearch_budget['remaining']} remaining")

    users = get_active_users(target_user_id)
    print(f"Loaded {len(users)} active users")

    for user in users:
        run_for_user(user, app_settings, jsearch_budget, phrase_ids, company_ids, phrases_due, is_on_demand)

    print("=== Job monitor run completed for all users ===")


if __name__ == "__main__":
    main()
