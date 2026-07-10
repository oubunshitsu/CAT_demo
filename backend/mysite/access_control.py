import os

from django.conf import settings
from django.shortcuts import render


def _parse_users(value: str) -> set[str]:
    return {item.strip().lower() for item in (value or "").split(",") if item.strip()}


class AppAccessControlMiddleware:
    """
    Restrict authenticated users to main app and/or control-group app paths.

    Env vars:
    - CA_PRACTICE_MAIN_APP_ALLOWED_USERS: comma-separated usernames
    - CA_PRACTICE_CG_APP_ALLOWED_USERS: comma-separated usernames
    - CA_PRACTICE_MAIN_APP_GROUP: django group name for main-app access
    - CA_PRACTICE_CG_APP_GROUP: django group name for control-group access
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.base_path = (getattr(settings, "BASE_PATH", "") or "").rstrip("/")
        if not self.base_path:
            self.base_path = ""

    def __call__(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)
        if user.is_superuser or user.is_staff:
            return self.get_response(request)

        path = request.path or ""
        base = self.base_path
        if base:
            main_prefix = f"{base}/"
            cg_prefix = f"{base}/cggf/"
            exempt_prefixes = (
                f"{base}/accounts/",
                f"{base}/admin/",
                f"{base}/static/",
            )
            exempt_exact = {
                f"{base}/logout/",
                f"{base}/cggf/logout/",
            }
        else:
            main_prefix = "/"
            cg_prefix = "/cggf/"
            exempt_prefixes = ("/accounts/", "/admin/", "/static/")
            exempt_exact = {"/logout/", "/cggf/logout/"}

        if path in exempt_exact or any(path.startswith(p) for p in exempt_prefixes):
            return self.get_response(request)

        main_users = _parse_users(os.environ.get("CA_PRACTICE_MAIN_APP_ALLOWED_USERS", ""))
        cg_users = _parse_users(os.environ.get("CA_PRACTICE_CG_APP_ALLOWED_USERS", ""))
        username = (user.username or "").strip().lower()
        main_group = (os.environ.get("CA_PRACTICE_MAIN_APP_GROUP", "") or "").strip()
        cg_group = (os.environ.get("CA_PRACTICE_CG_APP_GROUP", "") or "").strip()

        if main_group:
            can_main = user.groups.filter(name=main_group).exists()
        else:
            can_main = (not main_users) or (username in main_users)
        if cg_group:
            can_cg = user.groups.filter(name=cg_group).exists()
        else:
            can_cg = (not cg_users) or (username in cg_users)

        context = {
            "base_path": base or "",
            "can_main": can_main,
            "can_cggf": can_cg,
            "denied_area": "",
        }

        if path.startswith(cg_prefix):
            if not can_cg:
                context["denied_area"] = "control-group app"
                return render(
                    request,
                    "registration/access_denied.html",
                    context,
                    status=403,
                )
            return self.get_response(request)

        # Main app area under BASE_PATH excluding cggf/admin/accounts/static.
        if path.startswith(main_prefix):
            if not can_main:
                context["denied_area"] = "main app"
                return render(
                    request,
                    "registration/access_denied.html",
                    context,
                    status=403,
                )

        return self.get_response(request)
