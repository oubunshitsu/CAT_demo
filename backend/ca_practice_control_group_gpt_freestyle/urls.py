from django.urls import path

from . import views

app_name = "ca_practice_control_group_gpt_freestyle"

urlpatterns = [
    path("", views.entry, name="entry"),
    path("start/", views.start, name="start"),
    path("signup/", views.signup, name="signup"),
    path("instructions/", views.instructions, name="instructions"),
    path("stance/", views.stance, name="stance"),
    path("task/", views.task_session, name="task_session"),
    path("task/<int:idx>/", views.task_index, name="task_index"),
    path("feedback/<int:ca_id>/", views.feedback_chat, name="feedback_chat"),
    path("api/feedback/<int:ca_id>/", views.feedback_chat_api, name="feedback_chat_api"),
    path("revision/<int:ca_id>/", views.counterargument_revision, name="counterargument_revision"),
    path("next/", views.next_task, name="next_task"),
    path("done/", views.done, name="done"),
    path("logout/", views.logout_view, name="logout"),
]
