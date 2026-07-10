from django.urls import path

from . import views

app_name = "ca_practice"

urlpatterns = [
    path("", views.entry, name="entry"),
    path("start/", views.start, name="start"),  # resets to first
    path("signup/", views.signup, name="signup"),
    path(
        "accounts/password-reset-by-username/",
        views.password_reset_by_username,
        name="password_reset_by_username",
    ),
    path(
        "accounts/password-reset-by-username/set/",
        views.password_reset_by_username_set,
        name="password_reset_by_username_set",
    ),
    path(
        "accounts/password-reset-request-done/",
        views.password_reset_request_done,
        name="password_reset_request_done",
    ),
    path(
        "accounts/password-reset-by-username/done/",
        views.password_reset_by_username_done,
        name="password_reset_by_username_done",
    ),
    path("user-created/", views.user_created, name="user_created"),
    path("instructions/", views.instructions, name="instructions"),
    path("stance/", views.stance, name="stance"),
    path("task/", views.task_session, name="task_session"),
    path("task/<int:idx>/", views.task_index, name="task_index"),
    path("thanks/", views.thanks, name="thanks"),
    path("next/", views.next_task, name="next_task"),
    path("done/", views.done, name="done"),
    path("structure_loading/<int:ca_id>/", views.structure_loading, name="structure_loading"),
    path("api/prepare_structures/<int:ca_id>/", views.prepare_structures, name="prepare_structures"),
    path("structure/<int:ca_id>/", views.structure_view, name="structure"),
    path("logout/", views.logout_view, name="logout"),
    # feedback chat page
    path(
        "feedback/<int:ca_id>/<int:structure_index>/<int:cq_index>/",
        views.feedback_chat,
        name="feedback_chat",
    ),
    path(
        "api/feedback/<int:ca_id>/<int:structure_index>/<int:cq_index>/",
        views.feedback_chat_api,
        name="feedback_chat_api",
    ),
    path(
        "feedback_next/<int:ca_id>/<int:structure_index>/<int:cq_index>/",
        views.feedback_next_cq,
        name="feedback_next_cq",
    ),
    path(
        "feedback_prev/<int:ca_id>/<int:structure_index>/<int:cq_index>/",
        views.feedback_prev_cq,
        name="feedback_prev_cq",
    ),
    path(
        "api/improvement/<int:ca_id>/",
        views.improvement_chat_api,
        name="improvement_chat_api",
    ),
    path(
        "improvement_complete/<int:ca_id>/",
        views.improvement_chat_complete,
        name="improvement_chat_complete",
    ),
    path(
        "feedback_complete/<int:ca_id>/",
        views.feedback_complete,
        name="feedback_complete",
    ),
    path(
        "revision/<int:ca_id>/",
        views.counterargument_revision,
        name="counterargument_revision",
    ),
]
