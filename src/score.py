from __future__ import annotations

import json
import time

import anthropic

CLAUDE_MODEL = "claude-sonnet-4-6"
CALL_DELAY_SECONDS = 1

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

Return JSON exactly like this:
{{
  "score": <integer 0-100>,
  "reasoning": "<2 sentences explaining the score>",
  "salary_likely_above_floor": <true or false>,
  "title_match": "<strong/partial/weak>",
  "company_type_match": "<strong/partial/weak>"
}}

Scoring guide:
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

If a "Past feedback" section is present above, treat it as the candidate's revealed
preferences and weigh it alongside the stated profile - if this job closely resembles
something they liked, that supports a higher score; if it closely resembles something
they skipped, that supports a lower score, even if the stated profile alone would have
scored it differently. Don't overweight a single example, but a consistent pattern across
several liked or skipped jobs should meaningfully move the score.
"""


def _format_feedback_section(feedback: dict | None) -> str:
    if not feedback:
        return ""

    liked = feedback.get("liked") or []
    disliked = feedback.get("disliked") or []
    if not liked and not disliked:
        return ""

    lines = ["\nPast feedback from this candidate (jobs they've acted on before):"]
    if liked:
        lines.append("Liked (marked interested/applied):")
        for j in liked:
            lines.append(f"- {j.get('title')} at {j.get('company_name')}")
    if disliked:
        lines.append("Disliked (marked skip):")
        for j in disliked:
            lines.append(f"- {j.get('title')} at {j.get('company_name')}")
    lines.append("")
    return "\n".join(lines)


def _format_profile_prompt(profile: dict, job: dict, feedback: dict | None = None) -> str:
    background = profile.get("background") or []
    education = profile.get("education") or []
    target_roles = profile.get("target_roles") or []
    hard_avoids = profile.get("hard_avoids") or []
    raw_data = job.get("raw_data") or {}

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
    )


def score_job(job_dict: dict, profile: dict, anthropic_api_key: str, feedback: dict | None = None) -> dict:
    """Calls Claude (using the user's own API key) to score a job against their profile,
    plus their revealed preferences from past interested/applied/skip actions if provided.
    Returns {score, reasoning, salary_likely_above_floor}. Returns score=0 on any failure."""
    try:
        if not anthropic_api_key:
            raise RuntimeError("user has no anthropic_api_key configured")

        prompt = _format_profile_prompt(profile, job_dict, feedback)
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        parsed = json.loads(text)

        return {
            "score": int(parsed.get("score", 0)),
            "reasoning": parsed.get("reasoning", ""),
            "salary_likely_above_floor": bool(parsed.get("salary_likely_above_floor", False)),
        }
    except Exception as e:
        print(f"ERROR: score_job failed for '{job_dict.get('title')}' at '{job_dict.get('company_name')}': {e}")
        return {"score": 0, "reasoning": f"Scoring failed: {e}", "salary_likely_above_floor": False}
    finally:
        time.sleep(CALL_DELAY_SECONDS)
