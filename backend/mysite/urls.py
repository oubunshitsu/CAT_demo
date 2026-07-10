"""
URL configuration for mysite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path, include
from django.views.generic import RedirectView
from .auth_views import GroupRedirectLoginView, auth_status_view

base_path = (getattr(settings, "BASE_PATH", "") or "").strip("/")
base_prefix = f"{base_path}/" if base_path else ""

urlpatterns = [
    # Mount app under APP_BASE_PATH.
    path(f"{base_prefix}admin/", admin.site.urls),
    path(
        f"{base_prefix}accounts/login/",
        GroupRedirectLoginView.as_view(),
        name="login",
    ),
    path(
        f"{base_prefix}accounts/auth-status/",
        auth_status_view,
        name="auth_status",
    ),
    path(f"{base_prefix}accounts/", include("django.contrib.auth.urls")),
    path(base_prefix, include("ca_practice.urls")),
    path(
        f"{base_prefix}cggf/",
        include("ca_practice_control_group_gpt_freestyle.urls"),
    ),
]

if base_path:
    urlpatterns.append(
        path("", RedirectView.as_view(url=f"/{base_path}/", permanent=False))
    )

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
