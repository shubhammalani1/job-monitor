from __future__ import annotations

import requests


def send_slack_notification(job: dict, score_result: dict, slack_webhook_url: str) -> None:
    """Posts a Slack notification (to the user's own webhook) for a high-scoring job.
    Logs errors, never raises."""
    try:
        if not slack_webhook_url:
            print(f"WARNING: no slack_webhook_url configured, skipping notification for '{job.get('title')}'")
            return

        above_floor = score_result.get("salary_likely_above_floor")
        salary_text = "✅ Likely" if above_floor else "❓ Uncertain"

        text = (
            f"🎯 *{score_result.get('score')}/100* — {job.get('title')} at {job.get('company_name')}\n"
            f"{score_result.get('reasoning')}\n"
            f"Salary above floor: {salary_text}\n"
            f"📅 Posted: {job.get('date_posted')}\n"
            f"🔗 {job.get('job_url')}"
        )

        response = requests.post(slack_webhook_url, json={"text": text}, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"ERROR: send_slack_notification failed for '{job.get('title')}': {e}")
