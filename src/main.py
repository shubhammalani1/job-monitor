from __future__ import annotations

import datetime
import json
import os

from config import get_active_users, get_active_phrases, get_active_companies, get_supabase
from fetch import fetch_jobs_for_phrase
from careers import scrape_company_careers
from dedupe import filter_new_jobs, save_jobs
from score import score_job
from notify import send_slack_notification
from feedback import get_feedback_examples

SCORE_THRESHOLD = 70


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


def run_for_user(user: dict) -> None:
    user_id = user["id"]
    profile = user.get("profile") or {}
    anthropic_api_key = user.get("anthropic_api_key")
    slack_webhook_url = user.get("slack_webhook_url")

    run_id = create_run_log(user_id)
    print(f"--- Run started for user '{user.get('name')}' ({user_id}), run_id={run_id} ---")

    phrases_run = 0
    companies_checked = 0

    try:
        phrases = get_active_phrases(user_id)
        companies = get_active_companies(user_id)
        print(f"Loaded {len(phrases)} active phrases, {len(companies)} active companies")

        # Fetch phase
        all_jobs = []

        for phrase_row in phrases:
            phrase = phrase_row.get("phrase")
            location = phrase_row.get("location") or "Dubai, UAE"
            print(f"Fetching jobs for phrase: '{phrase}' in '{location}'")
            jobs = fetch_jobs_for_phrase(phrase, location)
            all_jobs.extend(jobs)
            phrases_run += 1

        for company_row in companies:
            company_name = company_row.get("name")
            careers_url = company_row.get("careers_url")
            print(f"Checking careers page for: {company_name}")
            jobs = scrape_company_careers(company_name, careers_url)
            all_jobs.extend(jobs)
            companies_checked += 1

        total_found = len(all_jobs)

        # Dedup phase
        new_jobs, dupes = filter_new_jobs(all_jobs, user_id)
        new_jobs_found = len(new_jobs)
        print(f"Found {total_found} jobs, {new_jobs_found} new, {dupes} already seen")

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
            print(f"Scored: {job.get('title')} at {job.get('company_name')} → {result['score']}/100")

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
    print("=== Job monitor run started ===" + (f" (target user: {target_user_id})" if target_user_id else ""))
    users = get_active_users(target_user_id)
    print(f"Loaded {len(users)} active users")

    for user in users:
        run_for_user(user)

    print("=== Job monitor run completed for all users ===")


if __name__ == "__main__":
    main()
