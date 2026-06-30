from __future__ import annotations

import time

DEFAULT_COUNTRIES = ["AE", "IN", "GB", "DE", "NL"]
RESULTS_LIMIT = 20
MAX_AGE_DAYS = 2
CALL_DELAY_SECONDS = 1


def _build_raw_data(job) -> dict:
    employment_type = "Remote" if getattr(job, "remote", False) else (
        getattr(job, "short_location", None) or getattr(job, "location", None)
    )
    return {
        "job_description": getattr(job, "description", None),
        "job_seniority": getattr(job, "seniority", None),
        "job_employment_type": employment_type,
    }


def _normalize(job) -> dict:
    date_posted = getattr(job, "date_posted", None)
    return {
        "external_job_id": f"jobspipe-{job.id}",
        "title": job.job_title,
        "company_name": job.company,
        "source_platform": "jobspipe",
        "date_posted": str(date_posted) if date_posted else None,
        "job_url": getattr(job, "url", None) or getattr(job, "final_url", None),
        "raw_data": _build_raw_data(job),
    }


def fetch_jobs_jobspipe(
    phrase: str,
    jobspipe_api_key: str | None,
    countries: list[str] | None = None,
    remote: bool | None = None,
) -> list[dict]:
    """Calls the JobsPipe API for a phrase, normalized to the same job dict shape
    fetch.py (JSearch) and the other source modules already use. Returns [] on any
    failure, including a missing API key - JobsPipe is optional, unlike JSearch,
    since this is an additional source layered on top of an already-working
    pipeline, not a replacement for it. Treating it as required would break every
    existing user's runs the moment this ships, before anyone has actually
    configured a JobsPipe key. The caller resolves the effective key (app_settings,
    falling back to the GitHub Actions secret) via config.get_effective_jobspipe_key,
    same pattern as fetch_jobs_for_phrase takes jsearch_api_key."""
    if not jobspipe_api_key:
        return []

    try:
        import jobspipe
    except ImportError:
        print("WARNING: fetch_jobs_jobspipe called but the jobspipe package isn't installed")
        return []

    try:
        client = jobspipe.Jobspipe(api_key=jobspipe_api_key)
        response = client.jobs.search(
            description_or=[phrase],
            job_country_code_or=countries if countries is not None else DEFAULT_COUNTRIES,
            posted_at_max_age_days=MAX_AGE_DAYS,
            limit=RESULTS_LIMIT,
            **({"remote": True} if remote else {}),
        )
        # JobSearchResponse.data holds the job list (confirmed against the installed
        # SDK's pydantic model fields - {'metadata', 'data'}).
        jobs = response.data
        return [_normalize(job) for job in jobs]
    except Exception as e:
        print(f"ERROR: fetch_jobs_jobspipe failed for phrase='{phrase}': {e}")
        return []
    finally:
        time.sleep(CALL_DELAY_SECONDS)
