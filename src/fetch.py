from __future__ import annotations

import time
import requests

JSEARCH_URL = "https://api.openwebninja.com/jsearch/search-v2"
PHRASE_DELAY_SECONDS = 2


def fetch_jobs_for_phrase(phrase: str, location: str, jsearch_api_key: str) -> list[dict]:
    """Calls JSearch API for a phrase/location and returns normalized job dicts.
    Returns [] on any error (including a missing api key)."""
    try:
        if not jsearch_api_key:
            raise RuntimeError("no jsearch_api_key configured")

        params = {
            "query": f"{phrase} in {location}",
            "country": "ae",
            "date_posted": "3days",
        }
        headers = {"x-api-key": jsearch_api_key}
        response = requests.get(JSEARCH_URL, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        results = (data.get("data") or {}).get("jobs", [])[:10]
        normalized = []
        for job in results:
            normalized.append(
                {
                    "external_job_id": job.get("job_id"),
                    "title": job.get("job_title"),
                    "company_name": job.get("employer_name"),
                    "source_platform": job.get("job_publisher", "jsearch"),
                    "date_posted": job.get("job_posted_at_datetime_utc"),
                    "job_url": job.get("job_apply_link") or job.get("job_url"),
                    "raw_data": job,
                }
            )
        return normalized
    except Exception as e:
        print(f"ERROR: fetch_jobs_for_phrase failed for phrase='{phrase}', location='{location}': {e}")
        return []
    finally:
        time.sleep(PHRASE_DELAY_SECONDS)
