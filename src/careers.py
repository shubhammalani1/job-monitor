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
ASHBY_PATTERN = re.compile(r"jobs\.ashbyhq\.com/([\w-]+)")
SMARTRECRUITERS_PATTERN = re.compile(r"jobs\.smartrecruiters\.com/([\w-]+)")
WORKABLE_PATTERN = re.compile(r"apply\.workable\.com/([\w-]+)")
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


def _scrape_ashby(company_name: str, board_name: str) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_name}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    jobs = response.json().get("jobs", [])

    normalized = []
    for job in jobs:
        normalized.append(
            {
                "external_job_id": f"ashby-{job.get('id')}",
                "title": job.get("title"),
                "company_name": company_name,
                "source_platform": "ashby",
                "date_posted": job.get("publishedAt"),
                "job_url": job.get("jobUrl"),
                "raw_data": {
                    "job_description": job.get("descriptionPlain"),
                    "job_seniority": job.get("department"),
                    "job_employment_type": job.get("location"),
                },
            }
        )
    return normalized


def _scrape_smartrecruiters(company_name: str, identifier: str) -> list[dict]:
    """Uses the list endpoint only (not the per-posting detail endpoint) to avoid an
    N+1 call per job - the public posting URL is fully predictable as
    jobs.smartrecruiters.com/{identifier}/{id} (the SEO slug suffix is optional),
    and the main pipeline's enrich phase already fetches each job's own page for a
    full description when the source-provided one is thin, so the omitted detail
    fetch isn't actually lost work."""
    url = f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    jobs = response.json().get("content", [])

    normalized = []
    for job in jobs:
        job_id = job.get("id")
        location = job.get("location") or {}
        normalized.append(
            {
                "external_job_id": f"smartrecruiters-{job_id}",
                "title": job.get("name"),
                "company_name": company_name,
                "source_platform": "smartrecruiters",
                "date_posted": job.get("releasedDate"),
                "job_url": f"https://jobs.smartrecruiters.com/{identifier}/{job_id}" if job_id else None,
                "raw_data": {
                    "job_description": None,
                    "job_seniority": (job.get("experienceLevel") or {}).get("label"),
                    "job_employment_type": location.get("fullLocation"),
                },
            }
        )
    return normalized


def _scrape_workable(company_name: str, account: str) -> list[dict]:
    """details=true gets the full HTML job description in the same call, instead of
    relying on the pipeline's enrich phase to fetch each job's own page afterward."""
    url = f"https://apply.workable.com/api/v1/widget/accounts/{account}?details=true"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    jobs = response.json().get("jobs", [])

    normalized = []
    for job in jobs:
        description_html = job.get("description")
        description = (
            BeautifulSoup(description_html, "html.parser").get_text(separator="\n").strip()
            if description_html
            else None
        )
        location_parts = [job.get("city"), job.get("country")]
        location_str = ", ".join(p for p in location_parts if p) or None

        normalized.append(
            {
                "external_job_id": f"workable-{job.get('shortcode')}",
                "title": job.get("title"),
                "company_name": company_name,
                "source_platform": "workable",
                "date_posted": job.get("published_on"),
                "job_url": job.get("url") or job.get("application_url") or job.get("shortlink"),
                "raw_data": {
                    "job_description": description,
                    "job_seniority": job.get("experience"),
                    "job_employment_type": "Remote" if job.get("telecommuting") else location_str,
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


def _scrape_attrax(company_name: str, careers_url: str) -> tuple[list[dict], bool]:
    """Returns (jobs, is_attrax_site) - is_attrax_site is True even if jobs is empty,
    so the caller can distinguish 'attrax site with zero current postings' from
    'not an attrax site at all' for platform-detection purposes."""
    parsed = urlparse(careers_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    first_page = requests.get(careers_url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    first_page.raise_for_status()
    if not _is_attrax_site(first_page.text):
        return [], False

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

    return all_jobs, True


DISCOVERY_PROBE_TIMEOUT = 8
_CORPORATE_SUFFIXES = (
    " inc.", " inc", " llc", " ltd.", " ltd", " corp.", " corp", " corporation",
    " technologies", " technology", " labs", " ai",
)


def _generate_slug_candidates(company_name: str) -> list[str]:
    """Generates a few plausible board-token guesses from a company's display name -
    'Mistral AI' -> ['mistral-ai', 'mistralai', 'mistral']. Real ATS tokens aren't always
    this guessable (some companies pick something unrelated to their public name), so this
    is intentionally a handful of cheap, high-probability tries, not exhaustive.

    Tries both the original capitalization and lowercase, since board tokens are
    case-sensitive on at least Lever ('Yassir' resolves, 'yassir' 404s)."""
    cleaned_original = re.sub(r"[^\w\s-]", "", (company_name or "")).strip()
    if not cleaned_original:
        return []
    lowered = cleaned_original.lower()

    stripped_lower = lowered
    for suffix in _CORPORATE_SUFFIXES:
        if stripped_lower.endswith(suffix):
            stripped_lower = stripped_lower[: -len(suffix)].strip()
            break

    candidates = []
    for variant in (cleaned_original, lowered, stripped_lower):
        no_spaces = re.sub(r"\s+", "", variant)
        hyphenated = re.sub(r"\s+", "-", variant)
        for c in (no_spaces, hyphenated):
            if c and c not in candidates:
                candidates.append(c)
    return candidates[:6]


def discover_company_ats(company_name: str) -> str | None:
    """Probes Ashby/Lever/Greenhouse/SmartRecruiters/Workable directly with guessed
    board tokens for this company name. Returns a working careers_url on the first hit,
    or None if nothing matched - discovery is best-effort, a miss just means we keep
    relying on aggregator sources for that company instead of also watching its own page."""
    candidates = _generate_slug_candidates(company_name)
    if not candidates:
        return None

    # Each validator confirms the slug maps to a *real, active* board, not just a 200 -
    # SmartRecruiters in particular returns 200 with an empty result set for literally
    # any company id, valid or not, so status code alone would false-match every guess.
    def _has_jobs(resp) -> bool:
        return len(resp.json().get("jobs", [])) > 0

    probes = [
        ("https://api.ashbyhq.com/posting-api/job-board/{}", "https://jobs.ashbyhq.com/{}", _has_jobs),
        (
            "https://api.lever.co/v0/postings/{}?mode=json",
            "https://jobs.lever.co/{}",
            lambda resp: isinstance(resp.json(), list) and len(resp.json()) > 0,
        ),
        ("https://boards-api.greenhouse.io/v1/boards/{}/jobs", "https://boards.greenhouse.io/{}", _has_jobs),
        (
            "https://api.smartrecruiters.com/v1/companies/{}/postings",
            "https://jobs.smartrecruiters.com/{}",
            lambda resp: resp.json().get("totalFound", 0) > 0,
        ),
        ("https://apply.workable.com/api/v1/widget/accounts/{}", "https://apply.workable.com/{}", _has_jobs),
    ]

    for slug in candidates:
        for api_template, public_url_template, has_real_postings in probes:
            try:
                response = requests.get(api_template.format(slug), timeout=DISCOVERY_PROBE_TIMEOUT)
                if response.status_code == 200 and has_real_postings(response):
                    return public_url_template.format(slug)
            except (requests.RequestException, ValueError):
                continue
    return None


def scrape_company_careers(company_name: str, careers_url: str) -> tuple[list[dict], str]:
    """Scrapes a company's careers page for jobs.

    Returns (jobs, detected_platform). detected_platform is one of
    "greenhouse", "lever", "ashby", "smartrecruiters", "workable", "attrax", or
    "unsupported" - used to show a status badge in the dashboard so it's clear
    which companies are actually working.

    Supports Greenhouse, Lever, Ashby, SmartRecruiters, and Workable boards via
    their public JSON APIs (detected from careers_url), and Attrax-based career
    sites (detected by fetching the page and checking for Attrax's markup, since
    Attrax doesn't have a consistent URL pattern - it's white-labelled per
    company, e.g. careers.deliveryhero.com). Any other site falls back to a
    no-op with a log message - add a new branch here for a custom scraper.
    """
    try:
        if not careers_url:
            return [], "unsupported"

        for pattern in GREENHOUSE_PATTERNS:
            match = pattern.search(careers_url)
            if match:
                return _scrape_greenhouse(company_name, match.group(1)), "greenhouse"

        lever_match = LEVER_PATTERN.search(careers_url)
        if lever_match:
            return _scrape_lever(company_name, lever_match.group(1)), "lever"

        ashby_match = ASHBY_PATTERN.search(careers_url)
        if ashby_match:
            return _scrape_ashby(company_name, ashby_match.group(1)), "ashby"

        smartrecruiters_match = SMARTRECRUITERS_PATTERN.search(careers_url)
        if smartrecruiters_match:
            return _scrape_smartrecruiters(company_name, smartrecruiters_match.group(1)), "smartrecruiters"

        workable_match = WORKABLE_PATTERN.search(careers_url)
        if workable_match:
            return _scrape_workable(company_name, workable_match.group(1)), "workable"

        attrax_jobs, is_attrax = _scrape_attrax(company_name, careers_url)
        if is_attrax:
            return attrax_jobs, "attrax"

        print(f"Careers scraper not yet implemented for {company_name} ({careers_url}) - add manually")
        return [], "unsupported"
    except Exception as e:
        print(f"ERROR: scrape_company_careers failed for {company_name}: {e}")
        return [], "unsupported"
