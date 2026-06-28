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


def get_active_phrases(user_id: str) -> list[dict]:
    """Returns list of {phrase, location} dicts for this user's active search phrases."""
    try:
        supabase = get_supabase()
        response = (
            supabase.table("search_phrases")
            .select("phrase, location")
            .eq("user_id", user_id)
            .eq("active", True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"ERROR: failed to load active phrases for user {user_id}: {e}")
        return []


def get_active_companies(user_id: str) -> list[dict]:
    """Returns list of {name, careers_url} dicts for this user's active companies."""
    try:
        supabase = get_supabase()
        response = (
            supabase.table("companies")
            .select("name, careers_url")
            .eq("user_id", user_id)
            .eq("active", True)
            .not_.is_("careers_url", "null")
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"ERROR: failed to load active companies for user {user_id}: {e}")
        return []
