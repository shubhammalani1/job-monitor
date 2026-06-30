from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT = 20
USER_AGENT = "Mozilla/5.0"

REMOTEOK_API_URL = "https://remoteok.com/api"
WWR_PRODUCT_RSS_URL = "https://weworkremotely.com/categories/remote-product-jobs.rss"
HN_ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search"
HN_ALGOLIA_SEARCH_BY_DATE_URL = "https://hn.algolia.com/api/v1/search_by_date"
HN_MAX_RESULTS_PER_ROLE = 15

_SENIORITY_PREFIX = re.compile(
    r"^(senior|sr\.?|lead|principal|staff|founding|head of|vp of|vp|director of|chief|associate|junior)\s+",
    re.IGNORECASE,
)


def _core_phrase(role: str) -> str:
    """Strips a seniority/qualifier prefix so 'Senior Product Manager' and
    'Product Manager' both reduce to the same core phrase for matching - these
    aggregator sources aren't structured by job title the way an ATS posting is,
    so pre-filtering needs to be generous. False positives are cheap (Claude's real
    scoring catches them); false negatives from being too strict are not."""
    return _SENIORITY_PREFIX.sub("", (role or "").strip()).lower()


def matches_any_target_role(text: str, target_roles: list[str]) -> bool:
    text_lower = (text or "").lower()
    return any(_core_phrase(role) in text_lower for role in target_roles if role)


def _strip_html(html: str | None) -> str | None:
    if not html:
        return None
    text = BeautifulSoup(html, "html.parser").get_text(separator="\n").strip()
    return text or None


def fetch_remoteok_jobs(target_roles: list[str]) -> list[dict]:
    """RemoteOK's public API returns ~100 most recent jobs across all categories
    (no query param support), so filtering by the candidate's target roles happens
    client-side against the title. Index 0 of the response is always a legal/attribution
    notice, not a job - skipped explicitly rather than relying on a try/except to catch it."""
    try:
        response = requests.get(
            REMOTEOK_API_URL, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()
        entries = response.json()

        normalized = []
        for job in entries:
            if "id" not in job:
                continue
            title = job.get("position") or ""
            if not matches_any_target_role(title, target_roles):
                continue

            normalized.append(
                {
                    "external_job_id": f"remoteok-{job.get('id')}",
                    "title": title,
                    "company_name": job.get("company"),
                    "source_platform": "remoteok",
                    "date_posted": job.get("date"),
                    "job_url": job.get("url") or job.get("apply_url"),
                    "raw_data": {
                        "job_description": _strip_html(job.get("description")),
                        "job_seniority": None,
                        "job_employment_type": job.get("location") or "Remote",
                    },
                }
            )
        return normalized
    except Exception as e:
        print(f"ERROR: fetch_remoteok_jobs failed: {e}")
        return []


def fetch_wwr_jobs(target_roles: list[str]) -> list[dict]:
    """We Work Remotely's Product category RSS mixes PM roles with other product-adjacent
    titles (design, etc), so still filters by target_roles client-side. Item titles follow
    the site's own "Company: Job Title" convention."""
    try:
        response = requests.get(
            WWR_PRODUCT_RSS_URL, timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT}
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)

        normalized = []
        for item in root.findall(".//item"):
            raw_title = (item.findtext("title") or "").strip()
            if not matches_any_target_role(raw_title, target_roles):
                continue

            company_name, _, role_title = raw_title.partition(": ")
            if not role_title:
                company_name, role_title = None, raw_title

            link = (item.findtext("link") or "").strip()
            pub_date_raw = item.findtext("pubDate")
            date_posted = None
            if pub_date_raw:
                try:
                    date_posted = parsedate_to_datetime(pub_date_raw).isoformat()
                except (TypeError, ValueError):
                    date_posted = None

            normalized.append(
                {
                    "external_job_id": f"wwr-{link}" if link else None,
                    "title": role_title,
                    "company_name": company_name,
                    "source_platform": "weworkremotely",
                    "date_posted": date_posted,
                    "job_url": link or None,
                    "raw_data": {
                        "job_description": _strip_html(item.findtext("description")),
                        "job_seniority": None,
                        "job_employment_type": item.findtext("type") or "Remote",
                    },
                }
            )
        return normalized
    except Exception as e:
        print(f"ERROR: fetch_wwr_jobs failed: {e}")
        return []


def _latest_whoishiring_story_id() -> int | None:
    response = requests.get(
        HN_ALGOLIA_SEARCH_BY_DATE_URL,
        params={"tags": "story,author_whoishiring", "hitsPerPage": 5},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    hits = response.json().get("hits", [])
    for hit in hits:
        title = (hit.get("title") or "").lower()
        if "who is hiring" in title:
            return int(hit["story_id"]) if hit.get("story_id") else None
    return None


def _first_line_company_and_title(comment_text: str) -> tuple[str | None, str]:
    """HN 'who is hiring' posts are free text, not structured fields - the de facto
    community convention is a first line like 'Company | Location | Type', so this is a
    best-effort split, not a guaranteed-clean title/company the way an ATS gives us.
    The full comment text still goes into job_description either way, so a messy title
    here doesn't affect scoring quality - Claude reads the real content, not just this."""
    first_line = comment_text.strip().split("\n")[0]
    parts = [p.strip() for p in first_line.split("|")]
    if len(parts) >= 2 and len(parts[0]) < 60:
        return parts[0], first_line[:200]
    return None, first_line[:200]


def fetch_hn_whos_hiring(target_roles: list[str]) -> list[dict]:
    """Searches the current month's 'Who is hiring?' thread for comments mentioning
    the candidate's target roles, via HN's official Algolia search API. This is the
    'hidden opportunity discovery' source - companies post directly here, including
    plenty that never appear on a mainstream job board or even have a careers page yet."""
    try:
        story_id = _latest_whoishiring_story_id()
        if not story_id:
            print("WARNING: fetch_hn_whos_hiring couldn't find the current 'who is hiring' thread")
            return []

        seen_ids = set()
        normalized = []
        for role in target_roles:
            core = _core_phrase(role)
            if not core:
                continue

            response = requests.get(
                HN_ALGOLIA_SEARCH_URL,
                params={
                    "query": core,
                    "tags": f"comment,story_{story_id}",
                    "hitsPerPage": HN_MAX_RESULTS_PER_ROLE,
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            for hit in response.json().get("hits", []):
                object_id = hit.get("objectID")
                if not object_id or object_id in seen_ids:
                    continue

                comment_text = _strip_html(hit.get("comment_text"))
                if not comment_text:
                    continue
                # Every real "who is hiring" post follows the thread's own convention of
                # a pipe-delimited first line ("Company | Location | Type"). Off-topic
                # top-level noise - a stray personal message, a "who WANTS to be hired"
                # cross-post - won't have it, so this is a cheap filter for "is this even
                # shaped like a job posting" before spending a Claude call to find out.
                if "|" not in comment_text.split("\n")[0]:
                    continue
                # Algolia's query param does fuzzy/relevance matching, not exact-phrase
                # (e.g. a search for "ai product manager" will surface "AI Staff Engineer"
                # on the shared word "AI") - re-check with the same precise substring
                # matcher the other sources use before accepting the hit.
                if not matches_any_target_role(comment_text, [role]):
                    continue
                company_name, title = _first_line_company_and_title(comment_text)
                seen_ids.add(object_id)

                normalized.append(
                    {
                        "external_job_id": f"hn-{object_id}",
                        "title": title,
                        "company_name": company_name or hit.get("author"),
                        "source_platform": "hackernews",
                        "date_posted": hit.get("created_at"),
                        "job_url": f"https://news.ycombinator.com/item?id={object_id}",
                        "raw_data": {
                            "job_description": comment_text,
                            "job_seniority": None,
                            "job_employment_type": None,
                        },
                    }
                )
        return normalized
    except Exception as e:
        print(f"ERROR: fetch_hn_whos_hiring failed: {e}")
        return []
