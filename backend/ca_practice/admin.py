from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils import timezone

from .models import (
    ChatHistory,
    CounterArgument,
    NoStructureChatHistory,
    RevisedCounterArgument,
    UsernamePasswordResetRequest,
    IdentifiedCAStructure,
    InitialArgument,
    IAPoint,
    TemplateCAStructure,
    TemplateCQ,
    Topic,
)

User = get_user_model()


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = DjangoUserAdmin.list_display + ("group_list",)

    @admin.display(description="Groups")
    def group_list(self, obj):
        return ", ".join(obj.groups.values_list("name", flat=True))


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
        "selected_point_id",
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


@admin.register(TemplateCAStructure)
class TemplateCAStructureAdmin(admin.ModelAdmin):
    list_display = (
        "template_structure_id",
        "template_structure_name",
        "template_structure_text",
    )
    search_fields = ("template_structure_name", "template_structure_text")


@admin.register(TemplateCQ)
class TemplateCQAdmin(admin.ModelAdmin):
    list_display = ("template_cq_id", "template_structure", "template_cq_text")
    search_fields = ("template_cq_text", "template_structure__template_structure_name")
    autocomplete_fields = ("template_structure",)


@admin.register(IdentifiedCAStructure)
class IdentifiedCAStructureAdmin(admin.ModelAdmin):
    list_display = (
        "identified_id",
        "user",
        "counter_argument",
        "template_structure",
        "z",
    )
    search_fields = (
        "counter_argument__counter_argument_text",
        "user__username",
        "template_structure__template_structure_name",
        "z",
    )
    autocomplete_fields = ("user", "counter_argument", "template_structure")


@admin.register(IAPoint)
class IAPointAdmin(admin.ModelAdmin):
    list_display = ("ia_point_id", "initial_argument", "point_text")
    search_fields = ("ia_point_id", "point_text", "initial_argument__initial_argument_text")
    autocomplete_fields = ("initial_argument",)


@admin.register(ChatHistory)
class ChatHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "chat_history_id",
        "user",
        "counter_argument",
        "template_structure",
        "template_cq",
        "history_text_dict",
    )
    search_fields = (
        "user__username",
        "counter_argument__counter_argument_text",
        "template_structure__template_structure_name",
        "template_cq__template_cq_text",
    )
    autocomplete_fields = (
        "user",
        "counter_argument",
        "template_structure",
        "template_cq",
    )


@admin.register(NoStructureChatHistory)
class NoStructureChatHistoryAdmin(admin.ModelAdmin):
    list_display = ("chat_history_id", "counter_argument", "history_text_dict")
    search_fields = (
        "counter_argument__counter_argument_text",
        "counter_argument__user__username",
    )
    autocomplete_fields = ("counter_argument",)


@admin.register(UsernamePasswordResetRequest)
class UsernamePasswordResetRequestAdmin(admin.ModelAdmin):
    list_display = (
        "reset_request_id",
        "username",
        "user",
        "status",
        "requested_at",
        "processed_at",
    )
    search_fields = ("username", "user__username", "admin_note")
    list_filter = ("status",)
    autocomplete_fields = ("user",)
    actions = ("mark_approved", "mark_rejected", "mark_done")

    @admin.action(description="Mark selected requests as approved")
    def mark_approved(self, request, queryset):
        queryset.update(
            status=UsernamePasswordResetRequest.STATUS_APPROVED,
            processed_at=timezone.now(),
        )

    @admin.action(description="Mark selected requests as rejected")
    def mark_rejected(self, request, queryset):
        queryset.update(
            status=UsernamePasswordResetRequest.STATUS_REJECTED,
            processed_at=timezone.now(),
        )

    @admin.action(description="Mark selected requests as completed")
    def mark_done(self, request, queryset):
        queryset.update(
            status=UsernamePasswordResetRequest.STATUS_DONE,
            processed_at=timezone.now(),
        )
