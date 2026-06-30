from __future__ import annotations

import time
import requests

JSEARCH_URL = "https://api.openwebninja.com/jsearch/search-v2"
PHRASE_DELAY_SECONDS = 2

# Maps keywords found in a location string to a JSearch country code. This used to be
# hardcoded to "ae" for every search regardless of location - fine when this tool only
# searched Dubai/UAE, actively wrong once other users started adding locations like
# "Bangalore" (JSearch would be told "find Bangalore jobs but restrict to the UAE region",
# a direct contradiction that produces few/irrelevant results). Unrecognized or remote
# locations omit the country filter entirely and let JSearch infer purely from the
# "<phrase> in <location>" query text.
LOCATION_COUNTRY_KEYWORDS = {
    "ae": ["dubai", "abu dhabi", "sharjah", "uae", "united arab emirates"],
    "in": ["bangalore", "bengaluru", "mumbai", "delhi", "pune", "hyderabad", "chennai", "india", "gurugram", "gurgaon", "noida"],
    "us": ["usa", "united states", "new york", "san francisco", "seattle", "austin", "chicago", "boston"],
    "gb": ["uk", "united kingdom", "london", "manchester"],
    "sg": ["singapore"],
    "sa": ["saudi arabia", "riyadh", "jeddah"],
    "qa": ["qatar", "doha"],
    "de": ["germany", "berlin", "munich", "deutschland"],
    "fr": ["france", "paris"],
    "nl": ["netherlands", "amsterdam", "the netherlands"],
    "es": ["spain", "madrid", "barcelona"],
    "ie": ["ireland", "dublin"],
    "ch": ["switzerland", "zurich", "zug"],
    "se": ["sweden", "stockholm"],
    "pt": ["portugal", "lisbon"],
    "it": ["italy", "milan", "rome"],
    "pl": ["poland", "warsaw"],
}


def _resolve_country_code(location: str) -> str | None:
    location_lower = (location or "").lower()
    if "remote" in location_lower:
        return None
    for code, keywords in LOCATION_COUNTRY_KEYWORDS.items():
        if any(keyword in location_lower for keyword in keywords):
            return code
    return None


def _is_remote_location(location: str) -> bool:
    return "remote" in (location or "").lower()


def fetch_jobs_for_phrase(phrase: str, location: str, jsearch_api_key: str) -> list[dict]:
    """Calls JSearch API for a phrase/location and returns normalized job dicts.
    Returns [] on any error (including a missing api key)."""
    try:
        if not jsearch_api_key:
            raise RuntimeError("no jsearch_api_key configured")

        params = {
            "query": f"{phrase} in {location}",
            "date_posted": "3days",
        }
        country_code = _resolve_country_code(location)
        if country_code:
            params["country"] = country_code
        elif _is_remote_location(location):
            # Belt-and-suspenders alongside the "in Remote" query text - guarantees
            # only actually-remote roles come back instead of relying purely on JSearch's
            # text interpretation of the query (which, in testing, was usually but not
            # always reliable on its own).
            params["work_from_home"] = "true"

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
