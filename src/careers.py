from __future__ import annotations

import re
import datetime
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup

GREENHOUSE_PATTERNS = [
    re.compile(r"boards\.greenhouse\.io/([\w-]+)"),
    re.compile(r"job-boards\.greenhouse\.io/([\w-]+)"),
]
LEVER_PATTERN = re.compile(r"jobs\.lever\.co/([\w-]+)")
ATTRAX_MAX_PAGES = 5


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


def _set_page_param(url: str, page: int) -> str:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    params["page"] = [str(page)]
    new_query = urlencode(params, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


def _scrape_attrax_page(base_url: str, page_url: str, company_name: str) -> list[dict]:
    response = requests.get(page_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    tiles = soup.select("div.attrax-vacancy-tile")
    normalized = []
    for tile in tiles:
        job_id = tile.get("data-jobid")
        title_el = tile.select_one("a.attrax-vacancy-tile__title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        href = title_el.get("href") or ""
        job_url = href if href.startswith("http") else f"{base_url}{href}"

        location_el = tile.select_one(".attrax-vacancy-tile__location-freetext .attrax-vacancy-tile__item-value")
        location = location_el.get_text(strip=True) if location_el else None

        normalized.append(
            {
                "external_job_id": f"attrax-{job_id or title}",
                "title": title,
                "company_name": company_name,
                "source_platform": "attrax",
                "date_posted": None,
                "job_url": job_url,
                "raw_data": {
                    "job_description": None,
                    "job_seniority": None,
                    "job_employment_type": location,
                },
            }
        )
    return normalized


def _is_attrax_site(html: str) -> bool:
    return "attrax-vacancy-tile" in html or "attraxAntiforgeryToken" in html


def _scrape_attrax(company_name: str, careers_url: str) -> list[dict]:
    parsed = urlparse(careers_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    first_page = requests.get(careers_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    first_page.raise_for_status()
    if not _is_attrax_site(first_page.text):
        return []

    all_jobs = []
    seen_ids = set()
    for page_num in range(1, ATTRAX_MAX_PAGES + 1):
        page_url = careers_url if page_num == 1 else _set_page_param(careers_url, page_num)
        jobs = _scrape_attrax_page(base_url, page_url, company_name)
        new_jobs = [j for j in jobs if j["external_job_id"] not in seen_ids]
        if not new_jobs:
            break
        for j in new_jobs:
            seen_ids.add(j["external_job_id"])
        all_jobs.extend(new_jobs)

    return all_jobs


def scrape_company_careers(company_name: str, careers_url: str) -> list[dict]:
    """Scrapes a company's careers page for jobs.

    Supports Greenhouse and Lever boards via their public JSON APIs (detected
    from careers_url), and Attrax-based career sites (detected by fetching the
    page and checking for Attrax's markup, since Attrax doesn't have a
    consistent URL pattern - it's white-labelled per company, e.g.
    careers.deliveryhero.com). Any other site falls back to a no-op with a
    log message - add a new branch here for a custom scraper.
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

        attrax_jobs = _scrape_attrax(company_name, careers_url)
        if attrax_jobs:
            return attrax_jobs

        print(f"Careers scraper not yet implemented for {company_name} ({careers_url}) - add manually")
        return []
    except Exception as e:
        print(f"ERROR: scrape_company_careers failed for {company_name}: {e}")
        return []
