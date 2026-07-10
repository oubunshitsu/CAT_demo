from django.db import models
from django.contrib.auth import get_user_model
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

    # Convenience accessors
    @property
    def topic_text_value(self):
        return self.topic.topic_text

    @property
    def initial_argument_value(self):
        return self.initial_argument_text


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
        related_name="counter_arguments_control",
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

    def __str__(self):
        return f"CA {self.counter_argument_id} by User {self.user_id}"

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
        return (
            f"CA Revision {self.revised_counter_argument_id} "
            f"(CA {self.counter_argument_id})"
        )


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
        if v not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")
        return v


class ChatHistorySchema(BaseModel):
    version: int = 1
    messages: list[ChatMessage]


class ChatHistory(models.Model):
    """
    Stores one full chat transcript for a (user, CA).
    """

    chat_history_id = models.AutoField(primary_key=True)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="chat_histories_control",
    )

    counter_argument = models.ForeignKey(
        CounterArgument,
        on_delete=models.CASCADE,
        db_column="counter_argument_id",
        related_name="chat_histories",
    )

    history_text_dict = models.JSONField()

    class Meta:
        unique_together = ("user", "counter_argument")
