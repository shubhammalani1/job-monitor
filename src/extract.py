from __future__ import annotations

import json
import re

import requests
from bs4 import BeautifulSoup

MIN_DESCRIPTION_LENGTH = 200
REQUEST_TIMEOUT = 15


def _strip_html(html: str) -> str:
    text = BeautifulSoup(html, "html.parser").get_text(separator="\n").strip()
    # Some sites double-encode &nbsp; (UTF-8 bytes for U+00A0 re-interpreted as
    # Latin-1), leaving stray "Â" characters in the visible text - clean those up.
    text = text.replace("Â ", " ").replace("Â", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def extract_job_posting_from_page(html: str) -> dict | None:
    """Looks for schema.org JobPosting JSON-LD (used by many job sites for Google
    Jobs indexing - Greenhouse, Attrax, LinkedIn, Indeed, and others all emit this).
    Falls back to og:title/og:description meta tags. Returns None if nothing found."""
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("@type") == "JobPosting":
                title = candidate.get("title")
                description_html = candidate.get("description")
                hiring_org = candidate.get("hiringOrganization") or {}
                company_name = hiring_org.get("name") if isinstance(hiring_org, dict) else None
                return {
                    "title": title,
                    "company_name": company_name,
                    "description": _strip_html(description_html) if description_html else None,
                }

    og_title = soup.find("meta", property="og:title")
    og_description = soup.find("meta", property="og:description")
    og_site_name = soup.find("meta", property="og:site_name")
    if og_title or og_description:
        return {
            "title": og_title.get("content") if og_title else None,
            "company_name": og_site_name.get("content") if og_site_name else None,
            "description": og_description.get("content") if og_description else None,
        }

    return None


def fetch_job_posting(job_url: str) -> dict | None:
    """Fetches a job's own page and extracts title/company/description.
    Returns None on any failure (network error, blocked, no structured data found)."""
    try:
        response = requests.get(
            job_url, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()
        response.encoding = response.encoding or response.apparent_encoding
        return extract_job_posting_from_page(response.text)
    except Exception as e:
        print(f"ERROR: fetch_job_posting failed for {job_url}: {e}")
        return None


def enrich_description_if_thin(job: dict) -> dict:
    """If a job's description is missing or too short to score well, fetches the
    job's own URL and fills it in. Mutates and returns the same job dict. Never raises -
    if enrichment fails, the job just keeps whatever description it already had."""
    raw_data = job.get("raw_data") or {}
    current_description = raw_data.get("job_description") or ""
    job_url = job.get("job_url")

    if len(current_description) >= MIN_DESCRIPTION_LENGTH or not job_url:
        return job

    posting = fetch_job_posting(job_url)
    if posting and posting.get("description"):
        raw_data["job_description"] = posting["description"]
        job["raw_data"] = raw_data

    return job
