from django.contrib import admin

from .models import (
    ChatHistory,
    CounterArgument,
    InitialArgument,
    RevisedCounterArgument,
    Topic,
)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("topic_id", "topic_text")
    search_fields = ("topic_text",)


@admin.register(InitialArgument)
class InitialArgumentAdmin(admin.ModelAdmin):
    list_display = (
        "initial_argument_id",
        "topic",
        "stance",
        "initial_argument_text",
    )
    search_fields = ("initial_argument_text", "topic__topic_text")
    autocomplete_fields = ("topic",)


@admin.register(CounterArgument)
class CounterArgumentAdmin(admin.ModelAdmin):
    list_display = (
        "counter_argument_id",
        "user",
        "initial_argument",
        "submitted_at",
        "submitted_at_switzerland",
        "counter_argument_text",
        "stance",
    )
    search_fields = (
        "counter_argument_text",
        "user__username",
        "initial_argument__initial_argument_text",
    )
    autocomplete_fields = ("user", "initial_argument")


@admin.register(RevisedCounterArgument)
class RevisedCounterArgumentAdmin(admin.ModelAdmin):
    list_display = ("revised_counter_argument_id", "counter_argument", "revision_text")
    search_fields = (
        "revision_text",
        "counter_argument__counter_argument_text",
        "counter_argument__user__username",
    )
    autocomplete_fields = ("counter_argument",)


@admin.register(ChatHistory)
class ChatHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "chat_history_id",
        "user",
        "counter_argument",
        "history_text_dict",
    )
    search_fields = (
        "user__username",
        "counter_argument__counter_argument_text",
    )
    autocomplete_fields = ("user", "counter_argument")
