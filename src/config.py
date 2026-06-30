from __future__ import annotations

import os
from supabase import create_client, Client

REQUIRED_ENV_VARS = [
    "JSEARCH_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_KEY",
]


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_env():
    """Validates all required env vars are present, raises clear error if not."""
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )
    return {name: os.environ[name] for name in REQUIRED_ENV_VARS}


JSEARCH_API_KEY = os.environ.get("JSEARCH_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
# Deliberately not in REQUIRED_ENV_VARS - JobsPipe is a second, additive job source on top
# of an already-working pipeline (see fetch_jobspipe.py). Requiring it would break every
# existing run the moment this ships, before the key is actually configured. It self-gates:
# fetch_jobs_jobspipe() reads this directly and no-ops if unset.
JOBSPIPE_API_KEY = os.environ.get("JOBSPIPE_API_KEY")

_supabase_client: Client | None = None


def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _require_env("SUPABASE_URL")
        _require_env("SUPABASE_KEY")
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


def get_active_users(target_user_id: str | None = None) -> list[dict]:
    """Returns list of active user rows: id, name, profile, anthropic_api_key, slack_webhook_url.

    Each user brings their own Anthropic key and Slack webhook - the platform only
    supplies JSearch access and Supabase storage.

    If target_user_id is set, only that user is returned (used for on-demand
    "Run now" triggers so they don't burn every other user's quota).
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("users")
            .select("id, name, profile, anthropic_api_key, slack_webhook_url")
            .eq("active", True)
        )
        if target_user_id:
            query = query.eq("id", target_user_id)
        response = query.execute()
        return response.data or []
    except Exception as e:
        print(f"ERROR: failed to load active users: {e}")
        return []


def get_active_phrases(user_id: str, phrase_ids: list[str] | None = None) -> list[dict]:
    """Returns list of {id, phrase, location, times_run, run_times} dicts for this user's
    active search phrases. run_times is None if the phrase uses the platform-wide default
    schedule instead of its own.

    If phrase_ids is set, restricts to just those (used for targeted "run selected only"
    triggers) without touching the active flag in the database.
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("search_phrases")
            .select("id, phrase, location, times_run, run_times")
            .eq("user_id", user_id)
            .eq("active", True)
        )
        if phrase_ids:
            query = query.in_("id", phrase_ids)
        response = query.execute()
        return response.data or []
    except Exception as e:
        print(f"ERROR: failed to load active phrases for user {user_id}: {e}")
        return []


def get_active_companies(user_id: str, company_ids: list[str] | None = None) -> list[dict]:
    """Returns list of {id, name, careers_url, run_times, times_run} dicts for this
    user's active companies. run_times is None if the company uses the platform-wide
    default schedule instead of its own.

    If company_ids is set, restricts to just those (used for targeted "run selected only"
    triggers) without touching the active flag in the database.
    """
    try:
        supabase = get_supabase()
        query = (
            supabase.table("companies")
            .select("id, name, careers_url, run_times, times_run")
            .eq("user_id", user_id)
            .eq("active", True)
            .not_.is_("careers_url", "null")
        )
        if company_ids:
            query = query.in_("id", company_ids)
        response = query.execute()
        return response.data or []
    except Exception as e:
        print(f"ERROR: failed to load active companies for user {user_id}: {e}")
        return []


def get_recent_company_posting_count(company_id: str, days: int = 7) -> int:
    """Counts how many jobs we've seen from this company in the last `days` days -
    a cheap, honest 'is this company actively expanding right now' signal computed
    from data we already have, rather than a paid funding/headcount-tracking feed."""
    try:
        import datetime

        since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
        supabase = get_supabase()
        response = (
            supabase.table("seen_jobs")
            .select("id", count="exact")
            .eq("company_id", company_id)
            .gte("created_at", since)
            .execute()
        )
        return response.count or 0
    except Exception as e:
        print(f"ERROR: failed to get recent posting count for company {company_id}: {e}")
        return 0


def mark_phrase_run(phrase_id: str, times_run: int) -> None:
    try:
        supabase = get_supabase()
        supabase.table("search_phrases").update(
            {"times_run": times_run + 1, "last_run_at": _now_iso()}
        ).eq("id", phrase_id).execute()
    except Exception as e:
        print(f"ERROR: failed to update run counter for phrase {phrase_id}: {e}")


def mark_company_run(company_id: str, times_run: int, detected_platform: str) -> None:
    try:
        supabase = get_supabase()
        supabase.table("companies").update(
            {
                "times_run": times_run + 1,
                "last_run_at": _now_iso(),
                "detected_platform": detected_platform,
            }
        ).eq("id", company_id).execute()
    except Exception as e:
        print(f"ERROR: failed to update run counter for company {company_id}: {e}")


def _now_iso() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


DEFAULT_APP_SETTINGS = {
    "paused": False,
    "run_times": ["04:00", "09:00", "16:00"],
    "company_run_times": ["09:00"],
    "anthropic_api_key": None,
    "jsearch_api_key": None,
    "jsearch_quota_limit": 200,
    "jsearch_calls_this_period": 0,
    "jsearch_period_reset_at": None,
    "jobspipe_api_key": None,
}


def get_app_settings() -> dict:
    """Returns the single shared platform settings row, with safe defaults on any failure
    so a settings-table problem never blocks the whole pipeline from running."""
    try:
        supabase = get_supabase()
        response = supabase.table("app_settings").select("*").eq("id", 1).single().execute()
        return {**DEFAULT_APP_SETTINGS, **(response.data or {})}
    except Exception as e:
        print(f"ERROR: failed to load app_settings, using defaults: {e}")
        return dict(DEFAULT_APP_SETTINGS)


def get_effective_jsearch_key(settings: dict) -> str | None:
    """Shared JSearch key from app_settings, falling back to the GitHub Actions
    secret env var if the admin hasn't set one via the dashboard yet."""
    return settings.get("jsearch_api_key") or JSEARCH_API_KEY


def get_effective_jobspipe_key(settings: dict) -> str | None:
    """Same pattern as get_effective_jsearch_key - shared JobsPipe key from
    app_settings (dashboard-configurable), falling back to the GitHub Actions
    secret env var. None is a valid result - JobsPipe is optional."""
    return settings.get("jobspipe_api_key") or JOBSPIPE_API_KEY


def reset_jsearch_usage_if_due(settings: dict) -> dict:
    """If the configured reset date has passed, zeroes the usage counter and pushes the
    reset date forward 30 days. Returns the (possibly updated) settings dict."""
    import datetime

    reset_at = settings.get("jsearch_period_reset_at")
    if not reset_at:
        return settings

    try:
        reset_dt = datetime.datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return settings

    if datetime.datetime.now(datetime.timezone.utc) < reset_dt:
        return settings

    new_reset_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat()
    try:
        supabase = get_supabase()
        supabase.table("app_settings").update(
            {"jsearch_calls_this_period": 0, "jsearch_period_reset_at": new_reset_at}
        ).eq("id", 1).execute()
        print(f"JSearch quota period reset. New reset date: {new_reset_at}")
    except Exception as e:
        print(f"ERROR: failed to reset jsearch usage period: {e}")
        return settings

    settings["jsearch_calls_this_period"] = 0
    settings["jsearch_period_reset_at"] = new_reset_at
    return settings


def increment_jsearch_usage(count: int) -> None:
    if count <= 0:
        return
    try:
        supabase = get_supabase()
        current = supabase.table("app_settings").select("jsearch_calls_this_period").eq("id", 1).single().execute()
        new_count = (current.data or {}).get("jsearch_calls_this_period", 0) + count
        supabase.table("app_settings").update({"jsearch_calls_this_period": new_count}).eq("id", 1).execute()
    except Exception as e:
        print(f"ERROR: failed to increment jsearch usage counter: {e}")
