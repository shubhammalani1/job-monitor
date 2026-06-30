from __future__ import annotations

import requests

REQUEST_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0"

# Confirmed-dead status codes only - the page itself says "this doesn't exist" or
# "this is gone". Everything else (403, 429, 999, 5xx, timeouts) is treated as "can't
# verify, not necessarily dead" rather than dropped: major job sites (LinkedIn, Jooble,
# JobLeads, TheLadders...) routinely block bot-like HEAD/GET requests with exactly those
# codes while the same link opens fine for a human in a browser. Dropping a real job
# because a site doesn't like our User-Agent is a worse failure mode than occasionally
# keeping a link we couldn't positively confirm.
CONFIRMED_DEAD_STATUS_CODES = {404, 410}


def _url_is_alive(url: str) -> bool:
    """False only when we have positive evidence the link is dead (404/410, or a
    connection/DNS failure meaning the host or path structurally doesn't exist).
    Ambiguous responses (bot-blocked, rate-limited, timed out) default to True."""
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.head(
            url, timeout=REQUEST_TIMEOUT, headers=headers, allow_redirects=True
        )
        if response.status_code not in CONFIRMED_DEAD_STATUS_CODES:
            return True
    except requests.exceptions.ConnectionError:
        pass  # DNS/connection failure - fall through to a confirming GET attempt
    except requests.RequestException:
        return True  # timeout, too-many-redirects, etc - ambiguous, not confirmed dead

    try:
        response = requests.get(
            url, timeout=REQUEST_TIMEOUT, headers=headers, allow_redirects=True, stream=True
        )
        return response.status_code not in CONFIRMED_DEAD_STATUS_CODES
    except requests.exceptions.ConnectionError:
        return False  # confirmed: host/path doesn't resolve on two separate attempts
    except requests.RequestException:
        return True


def filter_dead_links(jobs_list: list[dict]) -> tuple[list[dict], int]:
    """Returns (jobs_with_live_links, dropped_count). Jobs with no job_url at all are
    dropped too - a job a candidate can't click through to is useless regardless of
    its score. Runs after dedup (so we never pay this cost on jobs we'd skip anyway)
    and before scoring (so Claude never burns a call on a confirmed-dead posting)."""
    if not jobs_list:
        return [], 0

    alive = []
    dropped = 0
    for job in jobs_list:
        url = job.get("job_url")
        if url and _url_is_alive(url):
            alive.append(job)
        else:
            dropped += 1
            print(f"Dropping dead/missing link: '{job.get('title')}' at '{job.get('company_name')}' -> {url}")

    return alive, dropped
