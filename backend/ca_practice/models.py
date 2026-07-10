from django.db import models
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, validator
from datetime import datetime


# ===========================
#  Given (static configuration)
# ===========================


class Topic(models.Model):
    topic_id = models.AutoField(primary_key=True)
    topic_text = models.TextField()

    def __str__(self):
        return f"{self.topic_id}: {self.topic_text[:50]}"


class InitialArgument(models.Model):
    initial_argument_id = models.CharField(primary_key=True, max_length=128)

    # ForeignKey → Topic
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        db_column="topic_id",
        related_name="initial_arguments",
    )

    stance = models.CharField(
        max_length=4,
        choices=(("pro", "Pro"), ("con", "Con")),
        default="pro",
    )
    initial_argument_text = models.TextField(default="")

    def __str__(self):
        return f"IA {self.initial_argument_id} (Topic {self.topic_id})"

    # Convenience accessors for Django templates + LLM calls
    @property
    def topic_text_value(self):
        return self.topic.topic_text

    @property
    def initial_argument_value(self):
        return self.initial_argument_text


class TemplateCAStructure(models.Model):
    template_structure_id = models.AutoField(primary_key=True)
    template_structure_name = models.TextField()  # human-readable
    template_structure_text = models.TextField()  # template / description

    def __str__(self):
        return f"Structure {self.template_structure_id}: {self.template_structure_name}"


class TemplateCQ(models.Model):
    template_cq_id = models.AutoField(primary_key=True)

    # FK → structure template
    template_structure = models.ForeignKey(
        TemplateCAStructure,
        on_delete=models.CASCADE,
        db_column="template_structure_id",
        related_name="template_cqs",
    )

    template_cq_text = models.TextField()

    def __str__(self):
        return f"CQ {self.template_cq_id} (Structure {self.template_structure_id})"


# ===========================
#  Collected User Data
# ===========================

User = get_user_model()


class CounterArgument(models.Model):
    counter_argument_id = models.AutoField(primary_key=True)

    # FK → user
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="counter_arguments",
    )

    # FK → initial argument
    initial_argument = models.ForeignKey(
        InitialArgument,
        on_delete=models.CASCADE,
        db_column="initial_argument_id",
        to_field="initial_argument_id",
        related_name="counter_arguments",
    )

    counter_argument_text = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    stance = models.CharField(
        max_length=4,
        choices=(("pro", "Pro"), ("con", "Con")),
        default="pro",
    )
    selected_point_id = models.CharField(max_length=64, blank=True, default="")

    def __str__(self):
        return f"CA {self.counter_argument_id} by User {self.user_id}"

    # Convenience accessors
    @property
    def text(self):
        return self.counter_argument_text

    @property
    def task(self):
        return self.initial_argument

    @property
    def submitted_at_switzerland(self):
        dt = timezone.localtime(self.submitted_at, ZoneInfo("Europe/Zurich"))
        return dt.strftime("%Y-%m-%d,%H:%M:%S")


class RevisedCounterArgument(models.Model):
    revised_counter_argument_id = models.AutoField(primary_key=True)
    counter_argument = models.ForeignKey(
        CounterArgument,
        on_delete=models.CASCADE,
        db_column="counter_argument_id",
        related_name="revisions",
    )
    revision_text = models.TextField()

    def __str__(self):
        return f"CA Revision {self.revised_counter_argument_id} (CA {self.counter_argument_id})"


class UsernamePasswordResetRequest(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_DONE = "done"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_DONE, "Done"),
    )

    reset_request_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="user_id",
        related_name="username_reset_requests",
    )
    username = models.CharField(max_length=150)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
    )
    admin_note = models.TextField(blank=True, default="")
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"ResetRequest {self.reset_request_id} ({self.username})"


class IdentifiedCAStructure(models.Model):
    """
    One identified logical structure instance for one CA.
    Includes the filled-in `z` value.
    """

    identified_id = models.AutoField(primary_key=True)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="identified_structures",
    )

    counter_argument = models.ForeignKey(
        CounterArgument,
        on_delete=models.CASCADE,
        db_column="counter_argument_id",
        related_name="identified_structures",
    )

    template_structure = models.ForeignKey(
        TemplateCAStructure,
        on_delete=models.CASCADE,
        db_column="template_structure_id",
    )

    z = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("user", "counter_argument", "template_structure", "z")

    def __str__(self):
        return (
            f"Identified Structure {self.template_structure_id} "
            f"for CA {self.counter_argument_id} (User {self.user_id})"
        )


class IAPoint(models.Model):
    """
    One logical point for an InitialArgument.
    """

    id = models.AutoField(primary_key=True)
    ia_point_id = models.CharField(max_length=64)
    initial_argument = models.ForeignKey(
        InitialArgument,
        on_delete=models.CASCADE,
        db_column="initial_argument_id",
        to_field="initial_argument_id",
        related_name="points",
    )
    point_text = models.TextField()

    class Meta:
        unique_together = ("initial_argument", "ia_point_id")

    def __str__(self):
        return f"IA Point {self.ia_point_id} for IA {self.initial_argument_id}"


# ===========================
#  Chat History Validation (Pydantic)
# ===========================


class ChatMessage(BaseModel):
    turn_index: int
    role: str
    content: str
    timestamp: datetime

    @validator("role")
    def role_must_be_valid(cls, v):
        if v not in {"user", "agent"}:
            raise ValueError("role must be 'user' or 'agent'")
        return v


class ChatHistorySchema(BaseModel):
    version: int = 1
    messages: list[ChatMessage]


class ChatHistory(models.Model):
    """
    Stores one full chat transcript for a (user, CA, structure, CQ).
    """

    chat_history_id = models.AutoField(primary_key=True)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="chat_histories",
    )

    counter_argument = models.ForeignKey(
        CounterArgument,
        on_delete=models.CASCADE,
        db_column="counter_argument_id",
        related_name="chat_histories",
    )

    template_structure = models.ForeignKey(
        TemplateCAStructure,
        on_delete=models.CASCADE,
        db_column="template_structure_id",
    )

    template_cq = models.ForeignKey(
        TemplateCQ,
        on_delete=models.CASCADE,
        db_column="template_cq_id",
    )

    history_text_dict = models.JSONField()

    class Meta:
        unique_together = (
            "user",
            "counter_argument",
            "template_structure",
            "template_cq",
        )

    def __str__(self):
        return (
            f"ChatHistory (User {self.user_id}, CA {self.counter_argument_id}, "
            f"Structure {self.template_structure_id}, CQ {self.template_cq_id})"
        )

    def clean(self):
        try:
            ChatHistorySchema(**self.history_text_dict)
        except Exception as e:
            raise ValidationError(f"Invalid chat history format: {e}")


class NoStructureChatHistory(models.Model):
    """
    Stores one full improvement-chat transcript for a CA when no structure is found.
    """

    chat_history_id = models.AutoField(primary_key=True)
    counter_argument = models.ForeignKey(
        CounterArgument,
        on_delete=models.CASCADE,
        db_column="counter_argument_id",
        related_name="no_structure_chat_histories",
    )
    history_text_dict = models.JSONField()

    class Meta:
        unique_together = ("counter_argument",)

    def __str__(self):
        return f"NoStructureChatHistory (CA {self.counter_argument_id})"
