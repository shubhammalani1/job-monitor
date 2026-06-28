from __future__ import annotations

from config import get_supabase

MAX_EXAMPLES_PER_BUCKET = 8
DESCRIPTION_SNIPPET_LENGTH = 400


def _snippet(job_dict: dict) -> str | None:
    raw_data = job_dict.get("raw_data") or {}
    description = raw_data.get("job_description")
    if not description:
        return None
    return description[:DESCRIPTION_SNIPPET_LENGTH]


def get_feedback_examples(user_id: str) -> dict:
    """Returns the user's revealed preferences from past actions in the dashboard:
    {"liked": [{"title", "company_name", "description_snippet", "created_at"}, ...],
     "disliked": [..., "skip_reason"]}

    "liked" = jobs marked interested or applied. "disliked" = jobs marked skip.
    Includes a snippet of the job's actual description (not just title) and when the
    feedback was given, so scoring can weigh real content and recent signal more heavily.
    Capped at MAX_EXAMPLES_PER_BUCKET most recent each, to keep prompt size bounded now
    that full descriptions are included.
    """
    try:
        supabase = get_supabase()

        liked_response = (
            supabase.table("seen_jobs")
            .select("title, company_name, raw_data, created_at")
            .eq("user_id", user_id)
            .in_("status", ["interested", "applied"])
            .order("created_at", desc=True)
            .limit(MAX_EXAMPLES_PER_BUCKET)
            .execute()
        )
        disliked_response = (
            supabase.table("seen_jobs")
            .select("title, company_name, skip_reason, raw_data, created_at")
            .eq("user_id", user_id)
            .eq("status", "skip")
            .order("created_at", desc=True)
            .limit(MAX_EXAMPLES_PER_BUCKET)
            .execute()
        )

        liked = []
        for row in liked_response.data or []:
            liked.append(
                {
                    "title": row.get("title"),
                    "company_name": row.get("company_name"),
                    "description_snippet": _snippet(row),
                    "created_at": row.get("created_at"),
                }
            )

        disliked = []
        for row in disliked_response.data or []:
            disliked.append(
                {
                    "title": row.get("title"),
                    "company_name": row.get("company_name"),
                    "skip_reason": row.get("skip_reason"),
                    "description_snippet": _snippet(row),
                    "created_at": row.get("created_at"),
                }
            )

        return {"liked": liked, "disliked": disliked}
    except Exception as e:
        print(f"ERROR: get_feedback_examples failed for user {user_id}: {e}")
        return {"liked": [], "disliked": []}
