import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Optional, Tuple

import requests
from django.conf import settings
from django.utils import timezone

from jobber_sync.models import JobberToken
from dataclasses import dataclass
from urllib.parse import urlencode



JOBBER_OAUTH_AUTHORIZE_URL = "https://api.getjobber.com/oauth/authorize"
JOBBER_OAUTH_TOKEN_URL = "https://api.getjobber.com/api/oauth/token"

@dataclass
class TokenResult:
    access_token: str
    refresh_token: Optional[str]
    token_type: str
    expires_at: timezone.datetime

def build_state() -> str:
    """
    CSRF protection: state = random + signature
    """
    raw = secrets.token_urlsafe(24)
    secret = getattr(settings, "JOBBER_OAUTH_STATE_SECRET", "")
    sig = hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_state(state: str) -> bool:
    try:
        raw, sig = state.split(".", 1)
    except ValueError:
        return False
    secret = getattr(settings, "JOBBER_OAUTH_STATE_SECRET", "")
    expected = hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def build_authorize_url(*, state: str) -> str:
    base = getattr(settings, "JOBBER_OAUTH_AUTHORIZE_URL", "https://api.getjobber.com/api/oauth/authorize")
    redirect_uri = getattr(settings, "JOBBER_OAUTH_REDIRECT_URI", "https://pforbes-books-uuad7.ondigitalocean.app/jobber/oauth/callback/")
    if not redirect_uri:
        raise RuntimeError("JOBBER_OAUTH_REDIRECT_URI missing in settings/env.")

    params = {
        "response_type": "code",
        "client_id": getattr(settings, "JOBBER_CLIENT_ID", ""),
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{base}?{urlencode(params)}"


def _basic_auth_header() -> str:
    cid = getattr(settings, "JOBBER_CLIENT_ID", "")
    csec = getattr(settings, "JOBBER_CLIENT_SECRET", "")
    if not cid or not csec:
        raise RuntimeError("JOBBER_CLIENT_ID / JOBBER_CLIENT_SECRET missing in settings/env.")
    raw = f"{cid}:{csec}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("utf-8")


def exchange_code_for_token(code: str) -> TokenResult:
    token_url = getattr(settings, "JOBBER_OAUTH_TOKEN_URL", "https://api.getjobber.com/api/oauth/token")
    redirect_uri = getattr(settings, "JOBBER_OAUTH_REDIRECT_URI", "")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    headers = {
        "Authorization": _basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    r = requests.post(token_url, data=data, headers=headers, timeout=30)
    # helpful error body
    if r.status_code >= 400:
        raise RuntimeError(f"Jobber token exchange failed. HTTP {r.status_code}. Body: {r.text}")

    body = r.json()
    expires_in = int(body.get("expires_in", 3600))
    expires_at = timezone.now() + timedelta(seconds=expires_in)

    return TokenResult(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token"),
        token_type=body.get("token_type", "Bearer"),
        expires_at=expires_at,
    )

def refresh_access_token() -> JobberToken:
    token = JobberToken.objects.first()
    if not token or not token.refresh_token:
        raise RuntimeError("No refresh token stored. Reconnect via /jobber/oauth/start/.")

    token_url = getattr(settings, "JOBBER_OAUTH_TOKEN_URL", "https://api.getjobber.com/api/oauth/token")

    data = {
        "grant_type": "refresh_token",
        "refresh_token": token.refresh_token,
    }

    headers = {
        "Authorization": _basic_auth_header(),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    r = requests.post(token_url, data=data, headers=headers, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Jobber refresh failed. HTTP {r.status_code}. Body: {r.text}")

    body = r.json()
    expires_in = int(body.get("expires_in", 3600))
    token.access_token = body["access_token"]

    # Jobber may rotate refresh token
    if body.get("refresh_token"):
        token.refresh_token = body["refresh_token"]

    token.token_type = body.get("token_type", token.token_type or "Bearer")
    token.expires_at = timezone.now() + timedelta(seconds=expires_in)
    token.save()
    return token



def get_valid_access_token() -> str:
    token = JobberToken.objects.first()
    if not token:
        raise RuntimeError("No JobberToken record exists. Connect via /jobber/oauth/start/.")
    if token.is_expired:
        token = refresh_access_token()
    return token.access_token

def new_state() -> str:
    return secrets.token_urlsafe(24)
