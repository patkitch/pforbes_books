# jobber_sync/services/jobber_client.py
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests
from django.conf import settings
from jobber_sync.services.jobber_oauth import get_valid_access_token




class JobberAPIError(Exception):
    pass


@dataclass
class JobberResponse:
    data: Optional[dict]
    errors: Optional[list]
    extensions: Optional[dict]
    raw: dict


from jobber_sync.models import JobberToken

def _headers() -> Dict[str, str]:
    token = get_valid_access_token()
    version = getattr(settings, "JOBBER_API_VERSION", "2025-04-16")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-JOBBER-GRAPHQL-VERSION": version,
        "User-Agent": "pforbes_books/1.0",
    }



def execute_jobber_gql(
    query: str,
    variables: Optional[dict] = None,
    *,
    timeout_seconds: int = 30,
    max_retries: int = 3,
    retry_sleep_seconds: float = 1.0,
) -> JobberResponse:
    """
    Execute a GraphQL query against Jobber.

    - Raises JobberAPIError for transport issues
    - Returns JobberResponse containing data/errors/extensions
    - Retries on HTTP 429 / throttling-like failures (best effort)
    """
    url = getattr(settings, "JOBBER_API_URL", "https://api.getjobber.com/api/graphql")
    payload = {"query": query, "variables": variables or {}}

    last_exc: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            # Use json= so requests sets Content-Type properly
            session = requests.Session()
            session.trust_env = False  # IMPORTANT: ignore system proxy env vars

            r = session.post(
                url,
                headers=_headers(),
                json=payload,                 # use json= instead of data=
                timeout=timeout_seconds,
            )
            print("JOBBER DEBUG:", r.status_code, r.headers.get("Content-Type"), "len=", len(r.content))
            print("JOBBER DEBUG first200 repr:", repr((r.text or "")[:200]))

        except Exception as e:
            last_exc = e
            if attempt < max_retries:
                time.sleep(retry_sleep_seconds * attempt)
                continue
            raise JobberAPIError(f"Jobber request failed: {e}") from e

        # Retry on 429 (rate limit) BEFORE generic non-ok handling
        if r.status_code == 429 and attempt < max_retries:
            time.sleep(retry_sleep_seconds * attempt)
            continue

        # Any other HTTP error
        if r.status_code >= 400:
            content_type = r.headers.get("Content-Type", "")
            preview = (r.text or "")[:2000]
            raise JobberAPIError(
                "Jobber HTTP error.\n"
                f"URL: {r.url}\n"
                f"HTTP: {r.status_code}\n"
                f"Content-Type: {content_type}\n"
                f"Body preview:\n{preview}"
            )

        # Try JSON parse; if it isn't JSON, raise a helpful error
        content_type = r.headers.get("Content-Type", "")
        try:
            body = r.json()
        except Exception:
            text = r.text or ""
            preview = text[:2000]
            raise JobberAPIError(
                "Jobber returned a non-JSON response.\n"
                f"URL: {r.url}\n"
                f"HTTP: {r.status_code}\n"
                f"Content-Type: {content_type}\n"
                f"Response length: {len(text)} chars\n"
                f"First 2000 chars (repr): {preview!r}\n"
                f"History: {[h.status_code for h in r.history]}\n"
                f"Final URL after redirects: {r.url}\n"
            )


        # If Jobber returns THROTTLED in GraphQL errors, backoff and retry
        errors = body.get("errors") or None
        if errors:
            throttled = any((e.get("extensions", {}) or {}).get("code") == "THROTTLED" for e in errors)
            if throttled and attempt < max_retries:
                time.sleep(retry_sleep_seconds * attempt)
                continue

        return JobberResponse(
            data=body.get("data"),
            errors=body.get("errors"),
            extensions=body.get("extensions"),
            raw=body,
        )

    raise JobberAPIError(f"Jobber request failed after retries: {last_exc}")

