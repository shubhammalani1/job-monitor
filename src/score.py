from __future__ import annotations

import datetime
import json
import re
import time

import anthropic

CLAUDE_MODEL = "claude-sonnet-4-6"
CALL_DELAY_SECONDS = 1


def _safe_int(value) -> int | None:
    """Sub-scores are supporting breakdown, not guaranteed fields - missing or
    unparseable should read as 'not available', not a misleading 0."""
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_json_response(text: str) -> dict:
    """Claude is instructed to return raw JSON, but sometimes wraps it in markdown
    code fences anyway - strip those before parsing instead of failing outright."""
    text = text.strip()
    fence_match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```$", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    return json.loads(text)

SYSTEM_PROMPT = (
    "You are a job relevance scorer. Return ONLY valid JSON, no preamble, no markdown."
)

USER_PROMPT_TEMPLATE = """Score this job posting for {name}, a candidate with this background:
- Current role: {current_role} at {current_company} ({location})
{background_bullets}
Education:
{education_bullets}
- Target market: {target_location}. Open to: {target_roles}
- Hard avoids: {hard_avoids}
- Salary floor: {salary_floor_amount} {salary_floor_currency}/month
{feedback_section}
Job details:
Title: {title}
Company: {company_name}
Description: {description}
Seniority level: {seniority_level}
Work arrangement: {work_arrangement}
Posted: {posted_recency}
{company_hiring_signal_line}

Return JSON exactly like this:
{{
  "score": <integer 0-100, your single holistic judgment - not an average of the fields below>,
  "reasoning": "<one tight sentence: the single strongest reason to apply or pass>",
  "salary_likely_above_floor": <true or false>,
  "title_match": "<strong/partial/weak>",
  "company_type_match": "<strong/partial/weak>",
  "technical_match": <integer 0-100, how well the role uses this candidate's specific technical/domain depth, not just seniority>,
  "ai_relevance": <integer 0-100, how central AI/LLM/agentic work is to the role itself - 0 if the role has nothing to do with AI>,
  "remote_fit": <integer 0-100, how well the work arrangement matches the candidate's target_location (100 if it's remote or based exactly where they want, lower for a location/timezone mismatch)>,
  "career_growth": <integer 0-100, scope/seniority/leadership trajectory this role offers relative to the candidate's current level>
}}

Scoring guide for the overall "score":
90-100: Perfect fit. Senior role squarely in the target functions at a company type
  that matches the candidate's experience. Clear cross-functional scope. Almost
  certainly above salary floor.
70-89: Good fit. Right function but mid-seniority, OR right level but
  slightly adjacent company type. Worth reviewing.
50-69: Partial fit. Transferable but would be a stretch or step sideways.
  Include but don't prioritize.
0-49: Poor fit. Matches a hard avoid, or far too junior/senior. Or irrelevant
  industry with no transferable context.

Salary inference guide (since most postings don't show salary):
Above floor likely if: senior/leadership title + reputable company in the target industry
Above floor uncertain if: mid-level title at an unknown company
Below floor likely if: junior title, or a company type unrelated to the candidate's experience

Freshness ("Posted" above) is a tiebreaker, not a relevance signal - a great-fit role
posted two weeks ago still scores on its merits. Only let freshness nudge the score when
two jobs would otherwise be roughly equivalent; if a job is posted today or yesterday,
you may mention the urgency to apply soon in the one-sentence reasoning, but never use
staleness alone to push a genuinely strong match down into a lower tier.

If a company hiring-activity line is present above, treat multiple recent postings from
the same company as a (mild, secondary) positive signal for career_growth and stability -
an actively expanding team is a reasonable signal worth a passing mention in reasoning,
but it should never be the main reason for a high score.

If a "Past feedback" section is present above, treat it as the candidate's revealed
preferences and weigh it alongside the stated profile - if this job closely resembles
something they liked, that supports a higher score; if it closely resembles something
they skipped, that supports a lower score, even if the stated profile alone would have
scored it differently. Don't overweight a single example, but a consistent pattern across
several liked or skipped jobs should meaningfully move the score.
"""


def _days_ago(created_at: str | None) -> str:
    if not created_at:
        return ""
    try:
        created = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        days = (datetime.datetime.now(datetime.timezone.utc) - created).days
        if days <= 0:
            return " (today)"
        if days == 1:
            return " (1 day ago)"
        return f" ({days} days ago)"
    except (ValueError, TypeError):
        return ""


def _format_feedback_section(feedback: dict | None) -> str:
    if not feedback:
        return ""

    liked = feedback.get("liked") or []
    disliked = feedback.get("disliked") or []
    if not liked and not disliked:
        return ""

    lines = [
        "\nPast feedback from this candidate (most recent first - weigh recent feedback "
        "more heavily than older feedback, since preferences can shift over time):"
    ]
    if liked:
        lines.append("Liked (marked interested/applied):")
        for j in liked:
            recency = _days_ago(j.get("created_at"))
            lines.append(f"- {j.get('title')} at {j.get('company_name')}{recency}")
            snippet = j.get("description_snippet")
            if snippet:
                lines.append(f"  Description excerpt: {snippet}")
    if disliked:
        lines.append("Disliked (marked skip):")
        for j in disliked:
            recency = _days_ago(j.get("created_at"))
            reason = j.get("skip_reason")
            suffix = f" - reason given: {reason}" if reason else ""
            lines.append(f"- {j.get('title')} at {j.get('company_name')}{recency}{suffix}")
            snippet = j.get("description_snippet")
            if snippet:
                lines.append(f"  Description excerpt: {snippet}")
    lines.append("")
    return "\n".join(lines)


def _format_profile_prompt(profile: dict, job: dict, feedback: dict | None = None) -> str:
    background = profile.get("background") or []
    education = profile.get("education") or []
    target_roles = profile.get("target_roles") or []
    hard_avoids = profile.get("hard_avoids") or []
    raw_data = job.get("raw_data") or {}

    posted_recency = _days_ago(job.get("date_posted")).strip(" ()") or "unknown"

    recent_activity = job.get("company_hiring_signal")
    company_hiring_signal_line = (
        f"Company hiring activity: {recent_activity} other new postings from this company in the past 7 days"
        if recent_activity and recent_activity > 1
        else ""
    )

    return USER_PROMPT_TEMPLATE.format(
        name=profile.get("name") or "the candidate",
        current_role=profile.get("current_role") or "Not specified",
        current_company=profile.get("current_company") or "Not specified",
        location=profile.get("location") or "Not specified",
        background_bullets="\n".join(f"- {b}" for b in background) or "- Not specified",
        education_bullets="\n".join(f"- {e}" for e in education) or "- Not specified",
        target_location=profile.get("target_location") or "Not specified",
        target_roles=", ".join(target_roles) or "Not specified",
        hard_avoids=", ".join(hard_avoids) or "None specified",
        salary_floor_amount=profile.get("salary_floor_amount") or "Not specified",
        salary_floor_currency=profile.get("salary_floor_currency") or "",
        feedback_section=_format_feedback_section(feedback),
        title=job.get("title") or "Not provided",
        company_name=job.get("company_name") or "Not provided",
        description=raw_data.get("job_description") or "Not provided",
        seniority_level=raw_data.get("job_seniority") or "Not specified",
        work_arrangement=raw_data.get("job_employment_type") or "Not specified",
        posted_recency=posted_recency,
        company_hiring_signal_line=company_hiring_signal_line,
    )


def score_job(job_dict: dict, profile: dict, anthropic_api_key: str, feedback: dict | None = None) -> dict:
    """Calls Claude (using the user's own API key) to score a job against their profile,
    plus their revealed preferences from past interested/applied/skip actions if provided.
    Returns {score, reasoning, salary_likely_above_floor}. Returns score=0 on any failure."""
    try:
        if not anthropic_api_key:
            raise RuntimeError("user has no anthropic_api_key configured")

        prompt = _format_profile_prompt(profile, job_dict, feedback)
        client = anthropic.Anthropic(api_key=anthropic_api_key, timeout=60.0)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        parsed = _parse_json_response(text)

        return {
            "score": int(parsed.get("score", 0)),
            "reasoning": parsed.get("reasoning", ""),
            "salary_likely_above_floor": bool(parsed.get("salary_likely_above_floor", False)),
            "technical_match": _safe_int(parsed.get("technical_match")),
            "ai_relevance": _safe_int(parsed.get("ai_relevance")),
            "remote_fit": _safe_int(parsed.get("remote_fit")),
            "career_growth": _safe_int(parsed.get("career_growth")),
        }
    except Exception as e:
        print(f"ERROR: score_job failed for '{job_dict.get('title')}' at '{job_dict.get('company_name')}': {e}")
        return {
            "score": 0,
            "reasoning": f"Scoring failed: {e}",
            "salary_likely_above_floor": False,
            "technical_match": None,
            "ai_relevance": None,
            "remote_fit": None,
            "career_growth": None,
        }
    finally:
        time.sleep(CALL_DELAY_SECONDS)
