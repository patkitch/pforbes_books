"""Keep P. Forbes app routes private while preserving the password-gated gallery portal."""

from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse


class PrivateAppAccessMiddleware:
    """Require a Django superuser everywhere except the member/admin portal entry points."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        # Gallery sign-up views enforce their own separate member/admin permissions.
        if path.startswith("/gallery-signups/") or path.startswith("/static/"):
            return self.get_response(request)

        # Allow the built-in login form so the app owner can authenticate.
        if path == reverse("admin:login"):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.is_superuser:
            return self.get_response(request)

        login_url = reverse("admin:login")
        return redirect(f"{login_url}?{urlencode({'next': request.get_full_path()})}")
