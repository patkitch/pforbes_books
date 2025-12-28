from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.views.decorators.http import require_GET

from jobber_sync.models import JobberToken  # <-- ensure name matches
from jobber_sync.services.jobber_oauth import build_authorize_url, exchange_code_for_token, new_state


@require_GET
def jobber_oauth_start(request):
    # store state in session to prevent CSRF-style OAuth attacks
    state = new_state()
    request.session["jobber_oauth_state"] = state
    url = build_authorize_url(state=state)
    return redirect(url)


@require_GET
def jobber_oauth_callback(request):
    code = request.GET.get("code")
    state = request.GET.get("state")

    expected = request.session.get("jobber_oauth_state")
    if not expected or not state or state != expected:
        return HttpResponseBadRequest("Invalid OAuth state. Restart /jobber/oauth/start/.")

    if not code:
        # user denied access OR Jobber sent back without code
        return HttpResponseBadRequest("No code provided. Access likely denied or callback misconfigured.")

    token_result = exchange_code_for_token(code)

    # Upsert single token row
    obj = JobberToken.objects.first()
    if not obj:
        obj = JobberToken()

    obj.access_token = token_result.access_token
    obj.refresh_token = token_result.refresh_token or obj.refresh_token
    obj.token_type = token_result.token_type
    obj.expires_at = token_result.expires_at
    obj.save()

    # Clean session
    request.session.pop("jobber_oauth_state", None)

    return HttpResponse("Jobber OAuth connected. Tokens saved. You can now run the smoke test.")
