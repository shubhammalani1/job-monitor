from __future__ import annotations

import re
from difflib import SequenceMatcher

from config import get_supabase

FUZZY_TITLE_SIMILARITY_THRESHOLD = 0.88

# Direct company-careers scrapes link straight to the employer's own application page.
# Aggregators (JSearch, RemoteOK, etc) often link to a mirror that can lag, redirect, or
# 404 sooner. When the same job (by fingerprint) shows up from both, prefer the direct one.
DIRECT_SOURCE_PLATFORMS = {"greenhouse", "lever", "ashby", "smartrecruiters", "workable", "attrax"}


def _source_authority(job: dict) -> int:
    return 1 if job.get("source_platform") in DIRECT_SOURCE_PLATFORMS else 0


def _normalize(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def generate_fingerprint(title: str, company_name: str) -> str:
    """Normalizes title + company_name and returns first 64 chars as a fingerprint."""
    combined = f"{_normalize(title)}|{_normalize(company_name)}"
    return combined[:64]


def _title_similarity(title_a: str, title_b: str) -> float:
    return SequenceMatcher(None, _normalize(title_a), _normalize(title_b)).ratio()


def _is_fuzzy_duplicate(job: dict, against: list[dict]) -> bool:
    """True if job's title is a near-match (same normalized company, similar title)
    to anything in `against`. Catches the same posting re-titled slightly across
    platforms (e.g. 'Sr. Product Manager' vs 'Senior Product Manager, Growth') that
    the exact-fingerprint check misses."""
    job_company = _normalize(job.get("company_name"))
    job_title = job.get("title") or ""
    for other in against:
        if _normalize(other.get("company_name")) != job_company:
            continue
        if _title_similarity(job_title, other.get("title") or "") >= FUZZY_TITLE_SIMILARITY_THRESHOLD:
            return True
    return False


def filter_new_jobs(jobs_list: list[dict], user_id: str) -> tuple[list[dict], int]:
    """Returns (new_jobs, seen_count) by checking fingerprints against this user's seen_jobs rows.

    Also collapses duplicate fingerprints within jobs_list itself (e.g. the same posting
    surfaced by two overlapping search phrases in the same run) - otherwise the same job
    would get scored by Claude more than once before the save step ever sees it.

    After the exact-fingerprint pass, also runs a fuzzy title-similarity pass (same
    company, near-identical title) against both the remaining batch and this user's
    existing seen_jobs, to catch near-duplicate postings that differ only in minor
    title wording across platforms.
    """
    if not jobs_list:
        return [], 0

    for job in jobs_list:
        job["fingerprint"] = generate_fingerprint(job.get("title"), job.get("company_name"))

    deduped_within_batch = {}
    intra_batch_dupes = 0
    for job in jobs_list:
        fp = job["fingerprint"]
        if fp in deduped_within_batch:
            intra_batch_dupes += 1
            if _source_authority(job) > _source_authority(deduped_within_batch[fp]):
                deduped_within_batch[fp] = job
        else:
            deduped_within_batch[fp] = job
    unique_jobs = list(deduped_within_batch.values())

    fingerprints = list(deduped_within_batch.keys())

    try:
        supabase = get_supabase()
        response = (
            supabase.table("seen_jobs")
            .select("id, fingerprint, job_url, source_platform")
            .eq("user_id", user_id)
            .in_("fingerprint", fingerprints)
            .execute()
        )
        existing_rows = {row["fingerprint"]: row for row in (response.data or [])}
    except Exception as e:
        print(f"ERROR: filter_new_jobs failed to query seen_jobs for user {user_id}: {e}")
        existing_rows = {}

    after_exact = []
    url_upgrades = 0
    for job in unique_jobs:
        existing = existing_rows.get(job["fingerprint"])
        if not existing:
            after_exact.append(job)
            continue
        # Already seen in a prior run - not new content, but if this run found the same
        # job via a more authoritative source, upgrade the stored link in place so the
        # user doesn't end up clicking through an aggregator mirror when a direct
        # apply link is available.
        if _source_authority(job) > _source_authority(existing):
            try:
                supabase.table("seen_jobs").update(
                    {"job_url": job.get("job_url"), "source_platform": job.get("source_platform")}
                ).eq("id", existing["id"]).execute()
                url_upgrades += 1
            except Exception as e:
                print(f"ERROR: filter_new_jobs failed to upgrade job_url for fingerprint {job['fingerprint']}: {e}")
    exact_dupes = len(unique_jobs) - len(after_exact)
    if url_upgrades:
        print(f"Upgraded {url_upgrades} existing job(s) to a more direct application link")

    try:
        supabase = get_supabase()
        existing_titles_response = (
            supabase.table("seen_jobs")
            .select("title, company_name")
            .eq("user_id", user_id)
            .execute()
        )
        existing_titles = existing_titles_response.data or []
    except Exception as e:
        print(f"ERROR: filter_new_jobs failed to load existing titles for fuzzy check, user {user_id}: {e}")
        existing_titles = []

    new_jobs = []
    fuzzy_dupes = 0
    accepted_so_far = []
    for job in after_exact:
        if _is_fuzzy_duplicate(job, existing_titles) or _is_fuzzy_duplicate(job, accepted_so_far):
            fuzzy_dupes += 1
            continue
        new_jobs.append(job)
        accepted_so_far.append(job)

    seen_count = intra_batch_dupes + exact_dupes + fuzzy_dupes
    return new_jobs, seen_count


def save_jobs(jobs_list: list[dict], user_id: str) -> None:
    """Upserts all jobs to seen_jobs for this user, ignoring conflicts on (fingerprint, user_id)."""
    if not jobs_list:
        return

    rows = []
    for job in jobs_list:
        rows.append(
            {
                "fingerprint": job.get("fingerprint") or generate_fingerprint(
                    job.get("title"), job.get("company_name")
                ),
                "user_id": user_id,
                "external_job_id": job.get("external_job_id"),
                "title": job.get("title"),
                "company_name": job.get("company_name"),
                "source_platform": job.get("source_platform"),
                "date_posted": job.get("date_posted"),
                "claude_score": job.get("claude_score"),
                "claude_reasoning": job.get("claude_reasoning"),
                "salary_likely_above_floor": job.get("salary_likely_above_floor"),
                "technical_match": job.get("technical_match"),
                "ai_relevance": job.get("ai_relevance"),
                "remote_fit": job.get("remote_fit"),
                "career_growth": job.get("career_growth"),
                "job_url": job.get("job_url"),
                "raw_data": job.get("raw_data"),
                "notified_at": job.get("notified_at"),
                "search_phrase_id": job.get("search_phrase_id"),
                "company_id": job.get("company_id"),
            }
        )

    try:
        supabase = get_supabase()
        supabase.table("seen_jobs").upsert(
            rows, on_conflict="fingerprint,user_id", ignore_duplicates=True
        ).execute()
    except Exception as e:
        print(f"ERROR: save_jobs failed to upsert {len(rows)} jobs for user {user_id}: {e}")
