from __future__ import annotations

import re
import datetime

import requests

GREENHOUSE_PATTERNS = [
    re.compile(r"boards\.greenhouse\.io/([\w-]+)"),
    re.compile(r"job-boards\.greenhouse\.io/([\w-]+)"),
]
LEVER_PATTERN = re.compile(r"jobs\.lever\.co/([\w-]+)")


def _scrape_greenhouse(company_name: str, token: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    jobs = response.json().get("jobs", [])

    normalized = []
    for job in jobs:
        normalized.append(
            {
                "external_job_id": f"greenhouse-{job.get('id')}",
                "title": job.get("title"),
                "company_name": company_name,
                "source_platform": "greenhouse",
                "date_posted": job.get("updated_at"),
                "job_url": job.get("absolute_url"),
                "raw_data": {
                    "job_description": job.get("content"),
                    "job_seniority": None,
                    "job_employment_type": (job.get("location") or {}).get("name"),
                },
            }
        )
    return normalized


def _scrape_lever(company_name: str, token: str) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{token}?mode=json"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    jobs = response.json()

    normalized = []
    for job in jobs:
        created_at_ms = job.get("createdAt")
        date_posted = None
        if created_at_ms:
            date_posted = datetime.datetime.utcfromtimestamp(created_at_ms / 1000).isoformat() + "Z"

        categories = job.get("categories") or {}
        normalized.append(
            {
                "external_job_id": f"lever-{job.get('id')}",
                "title": job.get("text"),
                "company_name": company_name,
                "source_platform": "lever",
                "date_posted": date_posted,
                "job_url": job.get("hostedUrl"),
                "raw_data": {
                    "job_description": job.get("descriptionPlain"),
                    "job_seniority": categories.get("commitment"),
                    "job_employment_type": categories.get("location"),
                },
            }
        )
    return normalized


def scrape_company_careers(company_name: str, careers_url: str) -> list[dict]:
    """Scrapes a company's careers page for jobs.

    Supports Greenhouse and Lever boards directly via their public JSON APIs
    (detected from careers_url), since those two ATS platforms cover a large
    share of tech company career pages. Any other URL falls back to a no-op
    with a log message - add a new branch here for a custom scraper.
    """
    try:
        if not careers_url:
            return []

        for pattern in GREENHOUSE_PATTERNS:
            match = pattern.search(careers_url)
            if match:
                return _scrape_greenhouse(company_name, match.group(1))

        lever_match = LEVER_PATTERN.search(careers_url)
        if lever_match:
            return _scrape_lever(company_name, lever_match.group(1))

        print(f"Careers scraper not yet implemented for {company_name} ({careers_url}) - add manually")
        return []
    except Exception as e:
        print(f"ERROR: scrape_company_careers failed for {company_name}: {e}")
        return []
