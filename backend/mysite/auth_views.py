import os

from django.http import HttpResponse
from django.contrib.auth.views import LoginView
from django.urls import reverse
from django.utils.html import escape


class GroupRedirectLoginView(LoginView):
    template_name = "registration/login.html"

    def get_success_url(self):
        user = self.request.user
        if user.is_authenticated and not (user.is_superuser or user.is_staff):
            main_group_name = (
                os.environ.get("CA_PRACTICE_MAIN_APP_GROUP", "") or "ca_main_users"
            ).strip()
            cg_group_name = (
                os.environ.get("CA_PRACTICE_CG_APP_GROUP", "") or "ca_cggf_users"
            ).strip()

            in_main = (
                user.groups.filter(name=main_group_name).exists()
                if main_group_name
                else False
            )
            in_cg = (
                user.groups.filter(name=cg_group_name).exists()
                if cg_group_name
                else False
            )

            if in_main:
                return reverse("ca_practice:start")
            if in_cg:
                return reverse("ca_practice_control_group_gpt_freestyle:start")

        return super().get_success_url()


def auth_status_view(request):
    if request.user.is_authenticated:
        username = escape(request.user.username or "")
        message = f'User is logged in as: <strong>{username}</strong>'
    else:
        message = "User is not logged in yet."
    return HttpResponse(
        (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Login status</title>"
            "<style>"
            "html,body{height:100%;margin:0;font-family:Arial,sans-serif;background:#f3f4f6;}"
            ".wrap{min-height:100%;display:flex;align-items:center;justify-content:center;padding:24px;}"
            ".card{background:#fff;border:1px solid #e5e7eb;border-radius:14px;"
            "box-shadow:0 8px 24px rgba(0,0,0,.08);padding:28px 32px;max-width:680px;text-align:center;}"
            "h1{margin:0 0 12px;font-size:1.4rem;}"
            "p{margin:0;color:#374151;font-size:1.05rem;line-height:1.5;}"
            "</style></head><body>"
            "<div class='wrap'><div class='card'><h1>Login status</h1>"
            f"<p>{message}</p>"
            "</div></div></body></html>"
        ),
        content_type="text/html; charset=utf-8",
    )
