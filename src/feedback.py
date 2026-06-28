from __future__ import annotations

from config import get_supabase

MAX_EXAMPLES_PER_BUCKET = 15


def get_feedback_examples(user_id: str) -> dict:
    """Returns the user's revealed preferences from past actions in the dashboard:
    {"liked": [{"title", "company_name"}, ...], "disliked": [...]}

    "liked" = jobs marked interested or applied. "disliked" = jobs marked skip.
    Used to feed real signal back into the scoring prompt so it adapts over time,
    instead of only ever scoring against the static profile.
    """
    try:
        supabase = get_supabase()

        liked_response = (
            supabase.table("seen_jobs")
            .select("title, company_name")
            .eq("user_id", user_id)
            .in_("status", ["interested", "applied"])
            .order("created_at", desc=True)
            .limit(MAX_EXAMPLES_PER_BUCKET)
            .execute()
        )
        disliked_response = (
            supabase.table("seen_jobs")
            .select("title, company_name, skip_reason")
            .eq("user_id", user_id)
            .eq("status", "skip")
            .order("created_at", desc=True)
            .limit(MAX_EXAMPLES_PER_BUCKET)
            .execute()
        )

        return {
            "liked": liked_response.data or [],
            "disliked": disliked_response.data or [],
        }
    except Exception as e:
        print(f"ERROR: get_feedback_examples failed for user {user_id}: {e}")
        return {"liked": [], "disliked": []}
