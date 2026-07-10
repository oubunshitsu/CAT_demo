import json
import os
from dotenv import load_dotenv

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth import logout, login
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import DatabaseError
from django.utils import timezone as django_timezone

from .models import (
    InitialArgument,
    CounterArgument,
    RevisedCounterArgument,
    IdentifiedCAStructure,
    TemplateCAStructure,
    TemplateCQ,
    ChatHistory,
    NoStructureChatHistory,
    UsernamePasswordResetRequest,
    Topic,
)
from .llm import run_llm_structures
from .forms import EmailUserCreationForm, UsernameResetRequestForm


FIRST_IDX = 0  # zero-based index
_IA_INFO_CACHE = None
_IA_INFO_MTIME = None
_STRUCTURE_VIEW_DESC_CACHE = None
_STRUCTURE_VIEW_DESC_MTIME = None
_SWISS_TZ = ZoneInfo("Europe/Zurich")


def _swiss_timestamp() -> str:
    return datetime.now(_SWISS_TZ).strftime("%Y-%m-%d,%H:%M:%S")


def _load_ia_info():
    """
    Load ia_info.json if present; return the raw JSON (dict preferred).
    """
    global _IA_INFO_CACHE, _IA_INFO_MTIME

    try:
        ia_path = (
            Path(__file__).resolve().parent.parent
            / "llm_layer"
            / "local_predicate_model"
            / "static"
            / "ia_info.json"
        )
        mtime = ia_path.stat().st_mtime
        if _IA_INFO_CACHE is not None and _IA_INFO_MTIME == mtime:
            return _IA_INFO_CACHE

        data = json.loads(ia_path.read_text(encoding="utf-8"))
        _IA_INFO_CACHE = data
        _IA_INFO_MTIME = mtime
    except (FileNotFoundError, json.JSONDecodeError):
        _IA_INFO_CACHE = {}
        _IA_INFO_MTIME = None

    return _IA_INFO_CACHE


def _match_ia_info_by_id(initial_argument_id: int | str | None) -> dict | None:
    """
    Find an ia_info entry keyed by initial_argument_id (string match).
    """
    if not initial_argument_id and initial_argument_id != 0:
        return None

    key = str(initial_argument_id)
    data = _load_ia_info()

    if isinstance(data, dict):
        # direct key match
        if key in data:
            return data[key]
        # match on embedded id field if present
        for k, entry in data.items():
            if str(entry.get("initial_argument_id", "")) == key:
                return entry
            if str(k) == key:
                return entry
    elif isinstance(data, list):
        for entry in data:
            if str(entry.get("initial_argument_id", "")) == key:
                return entry
    return None


def _first_point_id(points: dict | None) -> str | None:
    if not isinstance(points, dict) or not points:
        return None
    keys = list(points.keys())
    try:
        return str(sorted(keys, key=lambda k: int(k))[0])
    except Exception:
        return str(keys[0])


def _task_context(task: InitialArgument, ca: CounterArgument | None = None) -> dict:
    ia_info = _match_ia_info_by_id(task.initial_argument_id) or {}
    points = ia_info.get("points") if isinstance(ia_info, dict) else {}
    selected_point_id = getattr(ca, "selected_point_id", "") if ca is not None else ""
    if not selected_point_id and ca is None:
        selected_point_id = _first_point_id(points)
    point_data = (
        (points or {}).get(str(selected_point_id)) if selected_point_id else {}
    ) or {}
    x_val = point_data.get("x", "")
    y_val = point_data.get("y", "")
    return {
        "ia_info": ia_info,
        "points": points or {},
        "point_id": str(selected_point_id) if selected_point_id is not None else "",
        "point_data": point_data,
        "x": x_val,
        "y": y_val,
        "initial_argument_id": task.initial_argument_id,
        "initial_argument_text": task.initial_argument_value,
    }


def _apply_ia_info(
    structures: list[dict],
    ia_info: dict | None,
    point_data: dict | None,
    stance: str | None,
):
    if not point_data:
        return structures
    conclusion = point_data.get("conclusion") or (ia_info or {}).get("conclusion")
    if not conclusion and point_data.get("claim_verb"):
        prefix = "should not be" if stance == "con" else "should be"
        conclusion = f"{prefix} {point_data['claim_verb']}"
    for s in structures:
        s.update(point_data)
        if conclusion and not s.get("conclusion"):
            s["conclusion"] = conclusion
    return structures


def _sync_selected_point(
    ca, task: InitialArgument, context: dict, result: dict
) -> dict:
    selected_point_id = (result or {}).get("selected_point_id") or ""
    if selected_point_id and not getattr(ca, "selected_point_id", ""):
        ca.selected_point_id = selected_point_id
        ca.save(update_fields=["selected_point_id"])
        return _task_context(task, ca)
    return context


def entry(request: HttpRequest):
    """
    Entry point: show login at the base URL, or start the flow if authenticated.
    """
    if request.user.is_authenticated:
        return start(request)
    return redirect("login")


def signup(request: HttpRequest):
    """
    Create a new user account.
    """
    web_signup_enabled = os.environ.get("CA_PRACTICE_ENABLE_WEB_SIGNUP", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if not web_signup_enabled:
        raise Http404("Signup is disabled.")

    if request.user.is_authenticated:
        return redirect("ca_practice:start")

    if request.method == "POST":
        form = EmailUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            main_group_name = (
                os.environ.get("CA_PRACTICE_MAIN_APP_GROUP", "") or "ca_main_users"
            ).strip()
            cg_group_name = (
                os.environ.get("CA_PRACTICE_CG_APP_GROUP", "") or "ca_cggf_users"
            ).strip()
            if main_group_name:
                main_group, _ = Group.objects.get_or_create(name=main_group_name)
                user.groups.add(main_group)
            if cg_group_name:
                user.groups.remove(*Group.objects.filter(name=cg_group_name))
            login(request, user)
            return redirect("ca_practice:user_created")
    else:
        form = EmailUserCreationForm()

    return render(request, "registration/signup.html", {"form": form})


def password_reset_by_username(request: HttpRequest):
    """
    Username-only reset flow:
    - 1st successful reset: direct self-reset.
    - 2nd+ resets: require admin approval first.
    """
    if request.method == "POST":
        form = UsernameResetRequestForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data["username"]
            user_model = get_user_model()
            user = user_model.objects.filter(username=username).first()
            if user is None or user.is_superuser:
                form.add_error("username", "Username not found.")
            else:
                done_count = UsernamePasswordResetRequest.objects.filter(
                    user=user,
                    status=UsernamePasswordResetRequest.STATUS_DONE,
                ).count()
                if done_count == 0:
                    reset_request = UsernamePasswordResetRequest.objects.create(
                        user=user,
                        username=user.username,
                        status=UsernamePasswordResetRequest.STATUS_APPROVED,
                        admin_note="Auto-approved first username-only reset.",
                        processed_at=django_timezone.now(),
                    )
                    request.session["reset_user_id"] = user.pk
                    request.session["reset_request_id"] = reset_request.reset_request_id
                    request.session.modified = True
                    return redirect("ca_practice:password_reset_by_username_set")

                approved_request = (
                    UsernamePasswordResetRequest.objects.filter(
                        user=user,
                        status=UsernamePasswordResetRequest.STATUS_APPROVED,
                    )
                    .order_by("-requested_at")
                    .first()
                )
                if approved_request is not None:
                    request.session["reset_user_id"] = user.pk
                    request.session["reset_request_id"] = (
                        approved_request.reset_request_id
                    )
                    request.session.modified = True
                    return redirect("ca_practice:password_reset_by_username_set")

                has_pending = UsernamePasswordResetRequest.objects.filter(
                    user=user,
                    status=UsernamePasswordResetRequest.STATUS_PENDING,
                ).exists()
                if not has_pending:
                    UsernamePasswordResetRequest.objects.create(
                        user=user,
                        username=user.username,
                        status=UsernamePasswordResetRequest.STATUS_PENDING,
                    )
                return redirect("ca_practice:password_reset_request_done")
    else:
        form = UsernameResetRequestForm()

    return render(request, "registration/password_reset_by_username.html", {"form": form})


def password_reset_by_username_set(request: HttpRequest):
    user_id = request.session.get("reset_user_id")
    reset_request_id = request.session.get("reset_request_id")
    if not user_id or not reset_request_id:
        return redirect("ca_practice:password_reset_by_username")

    user_model = get_user_model()
    user = user_model.objects.filter(pk=user_id).first()
    reset_request = UsernamePasswordResetRequest.objects.filter(
        reset_request_id=reset_request_id,
        user=user,
    ).first()
    if (
        user is None
        or user.is_superuser
        or reset_request is None
        or reset_request.status != UsernamePasswordResetRequest.STATUS_APPROVED
    ):
        request.session.pop("reset_user_id", None)
        request.session.pop("reset_request_id", None)
        request.session.modified = True
        return redirect("ca_practice:password_reset_by_username")

    if request.method == "POST":
        form = SetPasswordForm(user=user, data=request.POST)
        if form.is_valid():
            form.save()
            reset_request.status = UsernamePasswordResetRequest.STATUS_DONE
            reset_request.processed_at = django_timezone.now()
            reset_request.save(update_fields=["status", "processed_at"])
            request.session.pop("reset_user_id", None)
            request.session.pop("reset_request_id", None)
            request.session.modified = True
            return redirect("ca_practice:password_reset_by_username_done")
    else:
        form = SetPasswordForm(user=user)

    return render(request, "registration/password_reset_by_username_set.html", {"form": form})


def password_reset_request_done(request: HttpRequest):
    return render(request, "registration/password_reset_request_done.html")


def password_reset_by_username_done(request: HttpRequest):
    return render(request, "registration/password_reset_by_username_done.html")


@login_required
def user_created(request: HttpRequest):
    return render(
        request,
        "registration/user_created.html",
        {"created_username": request.user.username},
    )


def _safe_format(text: str, **kwargs) -> str:
    """
    Best-effort .format; if a placeholder is missing we fall back to the raw text.
    """
    try:
        return text.format(**kwargs)
    except KeyError:
        return text


def _load_structure_view_descriptions() -> dict:
    """
    Load structure_view_descriptions from ptn_desc.json if present.
    """
    global _STRUCTURE_VIEW_DESC_CACHE, _STRUCTURE_VIEW_DESC_MTIME

    try:
        desc_path = (
            Path(__file__).resolve().parent.parent
            / "llm_layer"
            / "local_predicate_model"
            / "static"
            / "ptn_desc.json"
        )
        mtime = desc_path.stat().st_mtime
        if (
            _STRUCTURE_VIEW_DESC_CACHE is not None
            and _STRUCTURE_VIEW_DESC_MTIME == mtime
        ):
            return _STRUCTURE_VIEW_DESC_CACHE

        data = json.loads(desc_path.read_text(encoding="utf-8"))
        _STRUCTURE_VIEW_DESC_CACHE = data.get("structure_view_descriptions", {})
        _STRUCTURE_VIEW_DESC_MTIME = mtime
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        _STRUCTURE_VIEW_DESC_CACHE = {}
        _STRUCTURE_VIEW_DESC_MTIME = None

    return _STRUCTURE_VIEW_DESC_CACHE


def _save_identified_structures(user, ca: CounterArgument, task: InitialArgument):
    """
    Persist identified logical structures for a counter-argument.
    """
    context = _task_context(task, ca)
    result = run_llm_structures(
        topic=task.topic_text_value,
        initial_argument=context["initial_argument_text"],
        counter_argument=ca.text,
        initial_argument_id=context["initial_argument_id"],
        ia_point_id=context["point_id"],
        x=context["x"],
        y=context["y"],
    )
    structures = result.get("structures", [])
    _apply_ia_info(
        structures,
        context["ia_info"],
        context["point_data"],
        getattr(task, "stance", None),
    )

    for s in structures:
        tmpl = None
        template_id = s.get("id")
        name = s.get("name")

        if template_id:
            tmpl = TemplateCAStructure.objects.filter(
                template_structure_id=template_id
            ).first()
        if tmpl is None and name:
            tmpl = TemplateCAStructure.objects.filter(
                template_structure_name__iexact=name
            ).first()

        if tmpl is None:
            continue

        z_val = s.get("z")
        IdentifiedCAStructure.objects.get_or_create(
            user=user,
            counter_argument=ca,
            template_structure=tmpl,
            z=z_val,
        )


def _resolve_template_cq(tmpl: TemplateCAStructure, cq_index: int) -> TemplateCQ | None:
    """
    Return the TemplateCQ at a given index (matching the order used to build critical_questions).
    """
    cqs = list(tmpl.template_cqs.all().order_by("template_cq_id"))
    if cq_index < 0 or cq_index >= len(cqs):
        return None
    return cqs[cq_index]


def _resolve_template_structure(structure: dict) -> TemplateCAStructure | None:
    template_id = structure.get("id")
    name = structure.get("name")
    if template_id:
        tmpl = TemplateCAStructure.objects.filter(
            template_structure_id=template_id
        ).first()
        if tmpl is not None:
            return tmpl
    if name:
        return TemplateCAStructure.objects.filter(
            template_structure_name__iexact=name
        ).first()
    return None


def _persist_chat_history(
    request, ca: CounterArgument, structure: dict, structure_index: int, cq_index: int
):
    """
    Save chat history for a single CQ if present in session.
    """
    session_key = f"feedback_chat_{ca.counter_argument_id}_{structure_index}_{cq_index}"
    history = request.session.get(session_key, [])
    if not history:
        return

    tmpl = _resolve_template_structure(structure)
    if tmpl is None:
        return

    template_cq = _resolve_template_cq(tmpl, cq_index)
    if template_cq is None:
        return

    messages = []
    for turn_idx, item in enumerate(history):
        ts = item.get("timestamp") or _swiss_timestamp()
        messages.append({
            "turn_index": turn_idx,
            "role": item.get("role", ""),
            "content": item.get("content", ""),
            "timestamp": ts,
        })

    payload = {
        "version": 1,
        "messages": messages,
        "duration_seconds": _get_cq_elapsed_seconds(
            request, ca.counter_argument_id, structure_index, cq_index
        ),
    }

    ChatHistory.objects.update_or_create(
        user=request.user,
        counter_argument=ca,
        template_structure=tmpl,
        template_cq=template_cq,
        defaults={"history_text_dict": payload},
    )


def _cq_timer_start_key(ca_id: int, structure_index: int, cq_index: int) -> str:
    return f"feedback_chat_started_{ca_id}_{structure_index}_{cq_index}"


def _cq_timer_elapsed_key(ca_id: int, structure_index: int, cq_index: int) -> str:
    return f"feedback_chat_elapsed_{ca_id}_{structure_index}_{cq_index}"


def _ensure_cq_timer(request, ca_id: int, structure_index: int, cq_index: int) -> None:
    start_key = _cq_timer_start_key(ca_id, structure_index, cq_index)
    if not request.session.get(start_key):
        request.session[start_key] = datetime.now(timezone.utc).isoformat()
        request.session.modified = True


def _pause_cq_timer(request, ca_id: int, structure_index: int, cq_index: int) -> None:
    start_key = _cq_timer_start_key(ca_id, structure_index, cq_index)
    elapsed_key = _cq_timer_elapsed_key(ca_id, structure_index, cq_index)

    start_raw = request.session.get(start_key)
    if not start_raw:
        return
    try:
        start_dt = datetime.fromisoformat(start_raw)
        delta = int((datetime.now(timezone.utc) - start_dt).total_seconds())
        delta = max(0, delta)
    except Exception:
        delta = 0

    prev_elapsed = int(request.session.get(elapsed_key, 0) or 0)
    request.session[elapsed_key] = prev_elapsed + delta
    request.session.pop(start_key, None)
    request.session.modified = True


def _get_cq_elapsed_seconds(
    request, ca_id: int, structure_index: int, cq_index: int
) -> int:
    start_key = _cq_timer_start_key(ca_id, structure_index, cq_index)
    elapsed_key = _cq_timer_elapsed_key(ca_id, structure_index, cq_index)

    elapsed = int(request.session.get(elapsed_key, 0) or 0)
    start_raw = request.session.get(start_key)
    if not start_raw:
        return max(0, elapsed)
    try:
        start_dt = datetime.fromisoformat(start_raw)
        delta = int((datetime.now(timezone.utc) - start_dt).total_seconds())
        delta = max(0, delta)
    except Exception:
        delta = 0
    return max(0, elapsed + delta)


def _clear_cq_timer_state(
    request, ca_id: int, structure_index: int, cq_index: int
) -> None:
    request.session.pop(_cq_timer_start_key(ca_id, structure_index, cq_index), None)
    request.session.pop(_cq_timer_elapsed_key(ca_id, structure_index, cq_index), None)
    request.session.modified = True


def _no_structure_timer_start_key(ca_id: int) -> str:
    return f"no_structure_chat_started_{ca_id}"


def _no_structure_chat_session_key(ca_id: int) -> str:
    return f"improvement_chat_{ca_id}"


def _ensure_no_structure_timer(request, ca_id: int) -> None:
    start_key = _no_structure_timer_start_key(ca_id)
    if not request.session.get(start_key):
        request.session[start_key] = datetime.now(timezone.utc).isoformat()
        request.session.modified = True


def _get_no_structure_elapsed_seconds(request, ca_id: int) -> int:
    start_raw = request.session.get(_no_structure_timer_start_key(ca_id))
    if not start_raw:
        return 0
    try:
        start_dt = datetime.fromisoformat(start_raw)
        delta = int((datetime.now(timezone.utc) - start_dt).total_seconds())
    except Exception:
        delta = 0
    return max(0, delta)


def _clear_no_structure_timer_state(request, ca_id: int) -> None:
    request.session.pop(_no_structure_timer_start_key(ca_id), None)
    request.session.modified = True


def _persist_no_structure_chat_history(
    request, ca: CounterArgument, history: list[dict]
):
    """
    Save no-structure improvement chat transcript for a CA.
    """
    for item in history:
        if not item.get("timestamp"):
            item["timestamp"] = _swiss_timestamp()
    try:
        NoStructureChatHistory.objects.update_or_create(
            counter_argument=ca,
            defaults={
                "history_text_dict": {
                    "version": 1,
                    "messages": history,
                    "duration_seconds": _get_no_structure_elapsed_seconds(
                        request, ca.counter_argument_id
                    ),
                }
            },
        )
    except DatabaseError:
        # If schema is not migrated yet, keep the chat flow working.
        return


def _finalize_no_structure_chat_history(request, ca: CounterArgument) -> None:
    session_key = _no_structure_chat_session_key(ca.counter_argument_id)
    history = request.session.get(session_key, [])
    if history:
        _persist_no_structure_chat_history(request, ca, history)
    request.session.pop(session_key, None)
    _clear_no_structure_timer_state(request, ca.counter_argument_id)


# =======================================
#   Task selection and CA writing
# =======================================


def _all_tasks():
    """
    Retrieve ALL Topics in order.
    """
    selected_topic_id = (
        os.environ.get("CA_PRACTICE_SINGLE_TOPIC_ID")
        or os.environ.get("CA_PRACTICE_TOPIC_ID")
        or ""
    ).strip()
    if selected_topic_id:
        try:
            topic_id = int(selected_topic_id)
        except ValueError:
            return []
        return list(Topic.objects.filter(topic_id=topic_id).order_by("topic_id"))
    return list(Topic.objects.order_by("topic_id"))


def _normalize_stance(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    value = raw_value.strip().lower()
    if value in {"yes", "pro", "agree"}:
        return "pro"
    if value in {"no", "con", "disagree"}:
        return "con"
    return None


def _select_initial_argument(topic: Topic, stance: str) -> InitialArgument:
    task = InitialArgument.objects.filter(topic=topic, stance=stance).first()
    if not task:
        raise Http404("No initial argument for selected topic.")
    return task


@login_required
def start(request: HttpRequest):
    """
    Reset task progress to the first item.
    """
    request.session["idx"] = FIRST_IDX
    request.session["seen_instructions"] = False
    request.session["stance_by_topic"] = {}
    return redirect("ca_practice:instructions")


@login_required
def instructions(request: HttpRequest):
    """
    Show instructions before starting the counter-argument workflow.
    """
    if request.method == "POST":
        request.session["seen_instructions"] = True
        return redirect("ca_practice:stance")
    template_name = (
        "ca_practice/instructions_simple.html"
        if os.environ.get("CA_PRACTICE_SIMPLE_INSTRUCTIONS", "").lower()
        in {"1", "true", "yes"}
        else "ca_practice/instructions.html"
    )
    return render(request, template_name)


@login_required
def stance(request: HttpRequest):
    """
    Ask the user to choose a stance for the current topic.
    """
    if not request.session.get("seen_instructions"):
        return redirect("ca_practice:instructions")

    topics = _all_tasks()
    if not topics:
        return render(request, "ca_practice/empty.html")

    idx = int(request.session.get("idx", 0))
    if idx < 0 or idx >= len(topics):
        return redirect("ca_practice:done")

    topic = topics[idx]

    if request.method == "POST":
        stance_value = _normalize_stance(request.POST.get("stance"))
        if stance_value:
            stance_by_topic = request.session.get("stance_by_topic", {})
            stance_by_topic[str(topic.topic_id)] = stance_value
            request.session["stance_by_topic"] = stance_by_topic
            request.session.modified = True
            return redirect("ca_practice:task_session")

    progress = {"current": idx + 1, "total": len(topics)}
    return render(
        request,
        "ca_practice/stance.html",
        {"topic": topic, "progress": progress},
    )


@login_required
def task_session(request: HttpRequest):
    """
    Main "write a counter-argument" workflow.
    """
    if not request.session.get("seen_instructions"):
        return redirect("ca_practice:instructions")
    topics = _all_tasks()
    if not topics:
        return render(request, "ca_practice/empty.html")

    idx = int(request.session.get("idx", 0))
    if idx < 0 or idx >= len(topics):
        return redirect("ca_practice:done")

    topic = topics[idx]
    stance_by_topic = request.session.get("stance_by_topic", {})
    stance_value = _normalize_stance(stance_by_topic.get(str(topic.topic_id)))
    if not stance_value:
        return redirect("ca_practice:stance")

    task = _select_initial_argument(topic, stance_value)

    if request.method == "POST":
        counter_text = request.POST.get("counter_text", "").strip()
        if counter_text:
            ca = CounterArgument.objects.create(
                user=request.user,
                initial_argument=task,
                counter_argument_text=counter_text,
                stance=stance_value,
            )
            # Defer structure computation to a loading page so we can show progress.
            return redirect(
                "ca_practice:structure_loading", ca_id=ca.counter_argument_id
            )

    progress = {"current": idx + 1, "total": len(topics)}
    allow_copy_paste = os.environ.get("CA_PRACTICE_ALLOW_COPY_PASTE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    return render(
        request,
        "ca_practice/task.html",
        {
            "task": task,
            "progress": progress,
            "allow_copy_paste": allow_copy_paste,
        },
    )


@login_required
def task_index(request: HttpRequest, idx: int):
    """
    Directly access a specific task by index (useful for debugging).
    """
    topics = _all_tasks()
    if idx < 0 or idx >= len(topics):
        raise Http404("No such task index")

    topic = topics[idx]
    stance_by_topic = request.session.get("stance_by_topic", {})
    stance_value = _normalize_stance(stance_by_topic.get(str(topic.topic_id)))
    if not stance_value:
        return redirect("ca_practice:stance")

    task = _select_initial_argument(topic, stance_value)

    if request.method == "POST":
        counter_text = request.POST.get("counter_text", "").strip()
        if counter_text:
            CounterArgument.objects.create(
                user=request.user,
                initial_argument=task,
                counter_argument_text=counter_text,
                stance=stance_value,
            )
        # No redirect here; saving identified structures only happens in task_session.
        next_idx = idx + 1
        if next_idx >= len(topics):
            return redirect("ca_practice:done")
        return redirect("ca_practice:task_index", idx=next_idx)

    progress = {"current": idx + 1, "total": len(topics)}
    allow_copy_paste = os.environ.get("CA_PRACTICE_ALLOW_COPY_PASTE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    return render(
        request,
        "ca_practice/task.html",
        {"task": task, "progress": progress, "allow_copy_paste": allow_copy_paste},
    )


@login_required
def next_task(request):
    """
    Move on to the next task in the sequence.
    """
    topics = _all_tasks()
    idx = int(request.session.get("idx", 0)) + 1
    request.session["idx"] = idx

    if idx >= len(topics):
        return redirect("ca_practice:done")

    return redirect("ca_practice:stance")


# =======================================
#   LLM Structure Page
# =======================================


def logout_view(request: HttpRequest):
    """
    Sign the user out via GET and redirect to login.
    """
    logout(request)
    return redirect("login")


def _cache_key_for_structures(ca_id: int) -> str:
    return f"structures_cache_{ca_id}"


@login_required
def structure_loading(request: HttpRequest, ca_id: int):
    """
    Show a spinner/progress page while structures are computed.
    """
    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    return render(
        request, "ca_practice/structure_loading.html", {"ca_id": ca.counter_argument_id}
    )


@login_required
def prepare_structures(request: HttpRequest, ca_id: int):
    """
    Compute structures and stash them in session for later rendering.
    Intended to be called via fetch from structure_loading.
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task
    context = _task_context(task, ca)

    result = run_llm_structures(
        topic=task.topic_text_value,
        initial_argument=context["initial_argument_text"],
        counter_argument=ca.text,
        initial_argument_id=context["initial_argument_id"],
        ia_point_id=context["point_id"],
        x=context["x"],
        y=context["y"],
    )
    structures = result.get("structures", [])
    context = _sync_selected_point(ca, task, context, result)
    _apply_ia_info(
        structures,
        context["ia_info"],
        context["point_data"],
        getattr(task, "stance", None),
    )

    # Persist identified structures to DB
    for s in structures:
        tmpl = None
        template_id = s.get("id")
        name = s.get("name")
        if template_id:
            tmpl = TemplateCAStructure.objects.filter(
                template_structure_id=template_id
            ).first()
        if tmpl is None and name:
            tmpl = TemplateCAStructure.objects.filter(
                template_structure_name__iexact=name
            ).first()
        if tmpl is None:
            continue
        z_val = s.get("z")
        IdentifiedCAStructure.objects.get_or_create(
            user=request.user,
            counter_argument=ca,
            template_structure=tmpl,
            z=z_val,
        )

    cache_key = _cache_key_for_structures(ca_id)
    request.session[cache_key] = structures
    request.session.modified = True

    return JsonResponse({
        "ok": True,
        "redirect": reverse("ca_practice:structure", args=[ca_id]),
    })


@login_required
def structure_view(request: HttpRequest, ca_id: int):
    """
    Show the logical structures page for a given CounterArgument.
    """
    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task  # InitialArgument through @property
    context = _task_context(task, ca)

    cache_key = _cache_key_for_structures(ca_id)
    cached_structures = request.session.get(cache_key)

    if cached_structures is not None:
        structures = cached_structures
    else:
        result = run_llm_structures(
            topic=task.topic_text_value,
            initial_argument=context["initial_argument_text"],
            counter_argument=ca.text,
            initial_argument_id=context["initial_argument_id"],
            ia_point_id=context["point_id"],
            x=context["x"],
            y=context["y"],
        )
        structures = result.get("structures", [])
        context = _sync_selected_point(ca, task, context, result)

    _apply_ia_info(
        structures,
        context["ia_info"],
        context["point_data"],
        getattr(task, "stance", None),
    )
    if cached_structures is not None:
        request.session[cache_key] = structures
        request.session.modified = True

    # If no structures, render improvement chat on this page.
    improvement_mode = not structures
    history = []
    if improvement_mode:
        session_key = _no_structure_chat_session_key(ca_id)
        history = request.session.get(session_key, [])
        _ensure_no_structure_timer(request, ca_id)
        if not history:
            # Let the model produce the opening assistant turn.
            opening = _llm_improvement_reply(task, ca, None, [])
            history = [
                {
                    "role": "assistant",
                    "content": opening,
                    "timestamp": _swiss_timestamp(),
                }
            ]
            request.session[session_key] = history
            _persist_no_structure_chat_history(request, ca, history)

        if request.method == "POST":
            user_message = request.POST.get("user_message", "").strip()
            if user_message:
                history.append(
                    {
                        "role": "user",
                        "content": user_message,
                        "timestamp": _swiss_timestamp(),
                    }
                )
                agent_reply = _llm_improvement_reply(task, ca, user_message, history)
                history.append(
                    {
                        "role": "assistant",
                        "content": agent_reply,
                        "timestamp": _swiss_timestamp(),
                    }
                )
                request.session[session_key] = history
                _persist_no_structure_chat_history(request, ca, history)

    structure_index = 0
    try:
        structure_index = int(request.GET.get("structure_index", "0"))
    except ValueError:
        structure_index = 0

    num_structures = len(structures)
    if num_structures:
        structure_index = max(0, min(structure_index, num_structures - 1))

    structures_json = json.dumps(structures)
    view_desc_templates = _load_structure_view_descriptions()

    for structure in structures:
        structure_text = _safe_format(structure["description"], **structure)
        structure["description"] = structure_text
        struct_key = structure.get("ptn_id") or structure.get("id")
        if not struct_key:
            diagram_type = structure.get("diagram_type")
            diagram_map = {
                "mitigation": 1,
                "alternative": 2,
                "no-evidence": 3,
                "atc": 4,
                "mm1": 5,
                "mm2": 6,
                "nna": 7,
                "neg-eff": 8,
                "dif-per1": 9,
                "dif-per2": 10,
            }
            struct_key = diagram_map.get(diagram_type)
        view_template = view_desc_templates.get(str(struct_key)) if struct_key else None
        if isinstance(view_template, dict):
            structure["view_descriptions"] = {
                key: _safe_format(value, **structure)
                for key, value in view_template.items()
                if value
            }

    current_structure = structures[structure_index] if structures else None
    has_next_structure = structure_index < num_structures - 1
    has_prev_structure = structure_index > 0

    allow_copy_paste = os.environ.get("CA_PRACTICE_ALLOW_COPY_PASTE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    context = {
        "task": task,
        "counter_argument": ca,
        "structures": structures,
        "current_structure": current_structure,
        "structure_index": structure_index,
        "num_structures": num_structures,
        "has_next_structure": has_next_structure,
        "has_prev_structure": has_prev_structure,
        "structures_json": structures_json,
        "improvement_mode": improvement_mode,
        "improvement_history": history,
        "allow_copy_paste": allow_copy_paste,
    }
    return render(request, "ca_practice/structures.html", context)


# =======================================
#   Final pages
# =======================================


@login_required
def thanks(request: HttpRequest):
    return render(request, "ca_practice/thanks.html")


@login_required
def done(request: HttpRequest):
    return render(request, "ca_practice/done.html")


# =======================================
#   Feedback Chat (session-based)
# =======================================


def _llm_feedback_reply(
    task, ca, structure, current_cq, history, user_message, initial_argument_text
):
    """
    LLM reply generator. Tries OpenAI; falls back to a stub.
    """
    # Try OpenAI first
    reply = _call_openai_feedback(
        task, ca, structure, current_cq, history, user_message, initial_argument_text
    )
    if reply:
        return reply

    # Fallback stub
    structure_name = structure.get("name", "this logical structure")

    prefix = (
        "We are currently discussing the critical question:\n\n"
        f'"{current_cq}"\n\n'
        f'within the logical structure "{structure_name}".\n\n'
    )

    return (
        prefix
        + f'You said: "{user_message}".\n\n'
        + "Think about whether your answer fully addresses this question, "
        "and whether there are hidden assumptions you might clarify."
    )


def _call_openai_feedback(
    task, ca, structure, current_cq, history, user_message, initial_argument_text
):
    """
    Optional OpenAI-based reply. Returns None on failure.
    """
    load_dotenv("../local.env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("api_key not found")
        return None

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        print("openai module not found --> fallback to dummy output")
        return None

    client = OpenAI(api_key=api_key)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    with open("llm_layer/feedback_agent/prompts/system_prompt.txt", "r") as f:
        system_prompt_template = f.read()
    with open("llm_layer/feedback_agent/prompts/user_prompt.txt", "r") as f:
        user_prompt_template = f.read()
    try:
        messages = []
        system_content = system_prompt_template.format(
            topic=getattr(task, "topic_text_value", ""),
            initial_argument=initial_argument_text,
            counter_argument=getattr(
                ca, "text", getattr(ca, "counter_argument_text", "")
            ),
            logical_structure=structure.get("name", ""),
            critical_question=current_cq,
        )
        messages.append({"role": "developer", "content": system_content})
        logical_structure_text = _safe_format(
            structure.get("description", "") or "",
            **(structure or {}),
        ).strip()

        # breakpoint()

        if not logical_structure_text:
            logical_structure_text = structure.get("name", "")

        user_content = user_prompt_template.format(
            topic=getattr(task, "topic_text_value", ""),
            initial_argument=initial_argument_text,
            counter_argument=getattr(
                ca, "text", getattr(ca, "counter_argument_text", "")
            ),
            logical_structure=logical_structure_text,
            critical_question=current_cq,
        )
        messages.append({"role": "user", "content": user_content})
        for turn in history:
            # Skip seeding the CQ itself; keep only real conversational turns.
            if turn.get("role") == "assistant" and turn.get("content") == current_cq:
                continue
            raw_role = turn.get("role", "user")
            role = "assistant" if raw_role in ("assistant", "agent") else "user"
            content = turn.get("content", "")
            messages.append({"role": role, "content": content})

        resp = client.responses.create(
            model=model,
            input=messages,
            temperature=0.4,
            # max_output_tokens=300,
        )
        output_text = getattr(resp, "output_text", None)
        if output_text and output_text.strip():
            return output_text.strip()
        for item in getattr(resp, "output", []) or []:
            if getattr(item, "type", "") != "message":
                continue
            for part in getattr(item, "content", []) or []:
                if getattr(part, "type", "") == "output_text":
                    text = (getattr(part, "text", "") or "").strip()
                    if text:
                        return text
        return None
    except Exception as e:
        print(e)
        return None


def _llm_improvement_reply(
    task, ca, user_message, history=None, initial_argument_text=None
):
    """
    Stub reply when no structures were detected: encourage user to refine CA.
    """
    ia_text = (
        initial_argument_text
        if initial_argument_text is not None
        else getattr(task, "initial_argument_value", "")
    )
    reply = _call_openai_improvement(task, ca, user_message, history or [], ia_text)
    if reply:
        return reply
    return (
        "Thanks for sharing. Let's look for ways to strengthen your counter-argument.\n\n"
        f'You said: "{user_message}".\n\n'
        "Consider whether you can add clearer evidence, tackle likely objections, "
        "or sharpen the causal link between your points."
    )


def _call_openai_improvement(task, ca, user_message, history, initial_argument_text):
    """
    Optional OpenAI-based reply for improvement mode. Returns None on failure.
    """
    load_dotenv("../local.env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("api_key not found")
        return None

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        print("openai module not found --> fallback to dummy output")
        return None

    client = OpenAI(api_key=api_key)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    with open(
        "llm_layer/feedback_agent/prompts/system_prompt_no_structure_identified.txt",
        "r",
    ) as f:
        system_prompt_template = f.read()
    with open(
        "llm_layer/feedback_agent/prompts/user_prompt_no_structure_identified.txt",
        "r",
    ) as f:
        user_prompt_template = f.read()
    try:
        system_content = system_prompt_template.format(
            topic=getattr(task, "topic_text_value", ""),
            initial_argument=initial_argument_text,
            counter_argument=getattr(
                ca, "text", getattr(ca, "counter_argument_text", "")
            ),
        )
        user_content_seed = user_prompt_template.format(
            topic=getattr(task, "topic_text_value", ""),
            initial_argument=initial_argument_text,
            counter_argument=getattr(
                ca, "text", getattr(ca, "counter_argument_text", "")
            ),
        )
        messages = [
            {"role": "developer", "content": system_content},
            {"role": "user", "content": user_content_seed},
        ]

        for turn in history:
            raw_role = turn.get("role", "user")
            api_role = "assistant" if raw_role in ("agent", "assistant") else "user"
            content = turn.get("content", "")
            messages.append({"role": api_role, "content": content})

        user_content = (
            "Please provide an opening suggestion to improve the counter-argument."
            if (not history and not user_message)
            else (user_message or "")
        )
        if user_content:
            last_turn = history[-1] if history else {}
            last_is_same_user_message = (
                last_turn.get("role")
                in ("user", "assistant")  # history uses "user"/"assistant"
                and last_turn.get("role") == "user"
                and (last_turn.get("content") or "") == user_content
            )
            if not last_is_same_user_message:
                messages.append({"role": "user", "content": user_content})

        resp = client.responses.create(
            model=model,
            input=messages,
            temperature=0.4,
            # max_output_tokens=300,
        )
        output_text = getattr(resp, "output_text", None)
        if output_text:
            return output_text.strip()
        for item in getattr(resp, "output", []) or []:
            if item.type != "message":
                continue
            for part in item.content:
                if part.type == "output_text":
                    return part.text.strip()
        return None
    except Exception:
        return None


@login_required
def feedback_chat(request, ca_id: int, structure_index: int, cq_index: int):
    """
    Multi-turn chat interface for structure-specific critical questions.
    """
    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task
    context = _task_context(task, ca)

    cache_key = _cache_key_for_structures(ca_id)
    cached_structures = request.session.get(cache_key)

    if cached_structures is not None:
        structures = cached_structures
    else:
        result = run_llm_structures(
            topic=task.topic_text_value,
            initial_argument=context["initial_argument_text"],
            counter_argument=ca.text,
            initial_argument_id=context["initial_argument_id"],
            ia_point_id=context["point_id"],
            x=context["x"],
            y=context["y"],
        )
        structures = result.get("structures", [])
        context = _sync_selected_point(ca, task, context, result)
        _apply_ia_info(
            structures,
            context["ia_info"],
            context["point_data"],
            getattr(task, "stance", None),
        )
    num_structures = len(structures)
    has_next_structure = structure_index < num_structures - 1
    next_structure_index = (
        structure_index + 1 if has_next_structure else structure_index
    )

    if not structures or structure_index >= len(structures):
        return render(request, "ca_practice/feedback_error.html")

    current_structure = structures[structure_index]
    cqs = current_structure.get("critical_questions", []) or []

    if not cqs:
        cqs = ["What is the main weakness in this counter-argument?"]

    cq_index = max(0, min(cq_index, len(cqs) - 1))
    current_cq = cqs[cq_index]

    current_cq = current_cq.format(**current_structure)

    # Session key for this specific (CA, structure, CQ)
    session_key = f"feedback_chat_{ca_id}_{structure_index}_{cq_index}"
    history = request.session.get(session_key, [])
    _ensure_cq_timer(request, ca_id, structure_index, cq_index)

    # First visit: seed with CQ
    if not history:
        history.append(
            {
                "role": "assistant",
                "content": current_cq,
                "timestamp": _swiss_timestamp(),
            }
        )
        request.session[session_key] = history
        request.session.modified = True
        _persist_chat_history(request, ca, current_structure, structure_index, cq_index)

    # Handle user POST
    if request.method == "POST":
        user_message = request.POST.get("user_message", "").strip()
        if user_message:
            history.append(
                {
                    "role": "user",
                    "content": user_message,
                    "timestamp": _swiss_timestamp(),
                }
            )

            agent_reply = _llm_feedback_reply(
                task,
                ca,
                current_structure,
                current_cq,
                history,
                user_message,
                context["initial_argument_text"],
            )
            history.append(
                {
                    "role": "assistant",
                    "content": agent_reply,
                    "timestamp": _swiss_timestamp(),
                }
            )

            request.session[session_key] = history
            request.session.modified = True
            _persist_chat_history(
                request, ca, current_structure, structure_index, cq_index
            )

    # Navigation
    num_cqs = len(cqs)
    has_prev_cq = cq_index > 0
    has_next_cq = cq_index < num_cqs - 1

    prev_cq_index = cq_index - 1 if has_prev_cq else 0
    next_cq_index = cq_index + 1 if has_next_cq else num_cqs - 1

    user_turns = sum(1 for turn in history if turn.get("role") == "user")
    can_advance = user_turns >= 3
    turns_remaining = max(0, 3 - user_turns)

    allow_copy_paste = os.environ.get("CA_PRACTICE_ALLOW_COPY_PASTE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    context = {
        "task": task,
        "counter_argument": ca,
        "history": history,
        "structure": current_structure,
        "structure_index": structure_index,
        "num_structures": num_structures,
        "has_next_structure": has_next_structure,
        "next_structure_index": next_structure_index,
        "cq_index": cq_index,
        "num_cqs": num_cqs,
        "has_prev_cq": cq_index > 0,
        "has_next_cq": cq_index < num_cqs - 1,
        "prev_cq_index": prev_cq_index,
        "next_cq_index": next_cq_index,
        "current_cq": current_cq,
        "can_advance": can_advance,
        "turns_remaining": turns_remaining,
        "allow_copy_paste": allow_copy_paste,
    }
    return render(request, "ca_practice/feedback_chat.html", context)


@login_required
def feedback_chat_api(request, ca_id: int, structure_index: int, cq_index: int):
    """
    AJAX endpoint to append a chat turn without reloading the page.
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task
    context = _task_context(task, ca)

    cache_key = _cache_key_for_structures(ca_id)
    cached_structures = request.session.get(cache_key)

    if cached_structures is not None:
        structures = cached_structures
    else:
        result = run_llm_structures(
            topic=task.topic_text_value,
            initial_argument=context["initial_argument_text"],
            counter_argument=ca.text,
            initial_argument_id=context["initial_argument_id"],
            ia_point_id=context["point_id"],
            x=context["x"],
            y=context["y"],
        )
        structures = result.get("structures", [])
        context = _sync_selected_point(ca, task, context, result)
        _apply_ia_info(
            structures,
            context["ia_info"],
            context["point_data"],
            getattr(task, "stance", None),
        )

    if not structures or structure_index >= len(structures) or structure_index < 0:
        return JsonResponse({"ok": False, "error": "No structures"}, status=400)

    current_structure = structures[structure_index]
    cqs = current_structure.get("critical_questions", []) or []
    if not cqs:
        cqs = ["What is the main weakness in this counter-argument?"]

    cq_index = max(0, min(cq_index, len(cqs) - 1))
    current_cq = cqs[cq_index]

    current_cq = current_cq.format(**current_structure)

    session_key = f"feedback_chat_{ca_id}_{structure_index}_{cq_index}"
    history = request.session.get(session_key, [])
    _ensure_cq_timer(request, ca_id, structure_index, cq_index)
    if not history:
        history.append(
            {
                "role": "assistant",
                "content": current_cq,
                "timestamp": _swiss_timestamp(),
            }
        )
        request.session[session_key] = history
        request.session.modified = True
        _persist_chat_history(request, ca, current_structure, structure_index, cq_index)

    user_message = request.POST.get("user_message", "").strip()
    if not user_message:
        return JsonResponse({"ok": False, "error": "Empty message"}, status=400)

    history.append(
        {
            "role": "user",
            "content": user_message,
            "timestamp": _swiss_timestamp(),
        }
    )
    agent_reply = _llm_feedback_reply(
        task,
        ca,
        current_structure,
        current_cq,
        history,
        user_message,
        context["initial_argument_text"],
    )
    history.append(
        {
            "role": "assistant",
            "content": agent_reply,
            "timestamp": _swiss_timestamp(),
        }
    )

    request.session[session_key] = history
    request.session.modified = True
    _persist_chat_history(request, ca, current_structure, structure_index, cq_index)

    return JsonResponse({"ok": True, "history": history})


@login_required
def feedback_next_cq(request, ca_id: int, structure_index: int, cq_index: int):
    """
    Persist the current CQ chat history, then advance to the next CQ.
    """
    if request.method != "POST":
        return redirect(
            "ca_practice:feedback_chat",
            ca_id=ca_id,
            structure_index=structure_index,
            cq_index=cq_index,
        )

    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task
    context = _task_context(task, ca)

    cache_key = _cache_key_for_structures(ca_id)
    cached_structures = request.session.get(cache_key)

    if cached_structures is not None:
        structures = cached_structures
    else:
        result = run_llm_structures(
            topic=task.topic_text_value,
            initial_argument=context["initial_argument_text"],
            counter_argument=ca.text,
            initial_argument_id=context["initial_argument_id"],
            ia_point_id=context["point_id"],
            x=context["x"],
            y=context["y"],
        )
        structures = result.get("structures", [])
        context = _sync_selected_point(ca, task, context, result)
        _apply_ia_info(
            structures,
            context["ia_info"],
            context["point_data"],
            getattr(task, "stance", None),
        )

    if not structures or structure_index >= len(structures):
        return redirect(
            "ca_practice:feedback_chat",
            ca_id=ca_id,
            structure_index=structure_index,
            cq_index=cq_index,
        )

    current_structure = structures[structure_index]
    cqs = current_structure.get("critical_questions", []) or []
    if not cqs:
        return redirect(
            "ca_practice:feedback_chat",
            ca_id=ca_id,
            structure_index=structure_index,
            cq_index=cq_index,
        )

    session_key = f"feedback_chat_{ca_id}_{structure_index}_{cq_index}"
    history = request.session.get(session_key, [])
    user_turns = sum(1 for turn in history if turn.get("role") == "user")
    if user_turns < 3:
        messages.warning(
            request,
            "Please complete at least 3 turns with the agent before moving to the next question.",
        )
        return redirect(
            "ca_practice:feedback_chat",
            ca_id=ca_id,
            structure_index=structure_index,
            cq_index=cq_index,
        )

    _persist_chat_history(request, ca, current_structure, structure_index, cq_index)
    _pause_cq_timer(request, ca_id, structure_index, cq_index)

    next_cq_index = min(cq_index + 1, len(cqs) - 1)
    return redirect(
        "ca_practice:feedback_chat",
        ca_id=ca_id,
        structure_index=structure_index,
        cq_index=next_cq_index,
    )


@login_required
def feedback_prev_cq(request, ca_id: int, structure_index: int, cq_index: int):
    """
    Persist the current CQ chat history, then go back to the previous CQ.
    """
    if request.method != "POST":
        return redirect(
            "ca_practice:feedback_chat",
            ca_id=ca_id,
            structure_index=structure_index,
            cq_index=cq_index,
        )

    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task
    context = _task_context(task, ca)

    cache_key = _cache_key_for_structures(ca_id)
    cached_structures = request.session.get(cache_key)

    if cached_structures is not None:
        structures = cached_structures
    else:
        result = run_llm_structures(
            topic=task.topic_text_value,
            initial_argument=context["initial_argument_text"],
            counter_argument=ca.text,
            initial_argument_id=context["initial_argument_id"],
            ia_point_id=context["point_id"],
            x=context["x"],
            y=context["y"],
        )
        structures = result.get("structures", [])
        context = _sync_selected_point(ca, task, context, result)
        _apply_ia_info(
            structures,
            context["ia_info"],
            context["point_data"],
            getattr(task, "stance", None),
        )

    if not structures or structure_index >= len(structures):
        return redirect(
            "ca_practice:feedback_chat",
            ca_id=ca_id,
            structure_index=structure_index,
            cq_index=cq_index,
        )

    current_structure = structures[structure_index]
    cqs = current_structure.get("critical_questions", []) or []
    if not cqs:
        return redirect(
            "ca_practice:feedback_chat",
            ca_id=ca_id,
            structure_index=structure_index,
            cq_index=cq_index,
        )

    _persist_chat_history(request, ca, current_structure, structure_index, cq_index)
    _pause_cq_timer(request, ca_id, structure_index, cq_index)

    prev_cq_index = max(cq_index - 1, 0)
    return redirect(
        "ca_practice:feedback_chat",
        ca_id=ca_id,
        structure_index=structure_index,
        cq_index=prev_cq_index,
    )


@login_required
def improvement_chat_api(request, ca_id: int):
    """
    AJAX endpoint for the improvement chat when no structures exist.
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task
    context = _task_context(task, ca)

    session_key = _no_structure_chat_session_key(ca_id)
    history = request.session.get(session_key, [])
    _ensure_no_structure_timer(request, ca_id)
    if not history:
        history = [
            {
                "role": "assistant",
                "content": "let's try to improve your counter-argument",
                "timestamp": _swiss_timestamp(),
            }
        ]

    user_message = request.POST.get("user_message", "").strip()
    if not user_message:
        return JsonResponse({"ok": False, "error": "Empty message"}, status=400)

    history.append(
        {
            "role": "user",
            "content": user_message,
            "timestamp": _swiss_timestamp(),
        }
    )
    agent_reply = _llm_improvement_reply(
        task, ca, user_message, history, context["initial_argument_text"]
    )
    history.append(
        {
            "role": "assistant",
            "content": agent_reply,
            "timestamp": _swiss_timestamp(),
        }
    )

    request.session[session_key] = history
    request.session.modified = True
    _persist_no_structure_chat_history(request, ca, history)

    return JsonResponse({"ok": True, "history": history})


@login_required
def improvement_chat_complete(request: HttpRequest, ca_id: int):
    """
    Finish no-structure improvement session and return to CA writing page.
    """
    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    _finalize_no_structure_chat_history(request, ca)
    return redirect("ca_practice:task_session")


@login_required
def feedback_complete(request: HttpRequest, ca_id: int):
    """
    Persist chat histories for all structures/CQs of this CA, then advance to next task.
    """
    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task
    context = _task_context(task, ca)
    if request.method == "POST":
        try:
            structure_index = int(request.POST.get("structure_index", "0"))
            cq_index = int(request.POST.get("cq_index", "0"))
        except ValueError:
            structure_index = 0
            cq_index = 0
        session_key = f"feedback_chat_{ca_id}_{structure_index}_{cq_index}"
        history = request.session.get(session_key, [])
        user_turns = sum(1 for turn in history if turn.get("role") == "user")
        if user_turns < 3:
            messages.warning(
                request,
                "Please complete at least 3 turns with the agent before moving on.",
            )
            return redirect(
                "ca_practice:feedback_chat",
                ca_id=ca_id,
                structure_index=structure_index,
                cq_index=cq_index,
            )
        # Best-effort save of the current CQ before persisting all history.
        cache_key = _cache_key_for_structures(ca_id)
        cached_structures = request.session.get(cache_key)
        if cached_structures is not None:
            structures = cached_structures
        else:
            result = run_llm_structures(
                topic=task.topic_text_value,
                initial_argument=context["initial_argument_text"],
                counter_argument=ca.text,
                initial_argument_id=context["initial_argument_id"],
                ia_point_id=context["point_id"],
                x=context["x"],
                y=context["y"],
            )
            structures = result.get("structures", [])
            context = _sync_selected_point(ca, task, context, result)
            _apply_ia_info(
                structures,
                context["ia_info"],
                context["point_data"],
                getattr(task, "stance", None),
            )
        if structures and 0 <= structure_index < len(structures):
            _persist_chat_history(
                request,
                ca,
                structures[structure_index],
                structure_index,
                cq_index,
            )
            _pause_cq_timer(request, ca_id, structure_index, cq_index)

    def persist_for_structure(structures_data, s_idx):
        s = structures_data[s_idx]

        cqs = s.get("critical_questions", []) or []
        for cq_idx, _cq_text in enumerate(cqs):
            session_key = f"feedback_chat_{ca_id}_{s_idx}_{cq_idx}"
            history = request.session.get(session_key, [])
            if not history:
                continue

            _persist_chat_history(request, ca, s, s_idx, cq_idx)
            _pause_cq_timer(request, ca_id, s_idx, cq_idx)

            # Clear the session history once persisted.
            request.session.pop(session_key, None)
            _clear_cq_timer_state(request, ca_id, s_idx, cq_idx)

    result = run_llm_structures(
        topic=task.topic_text_value,
        initial_argument=context["initial_argument_text"],
        counter_argument=ca.text,
        initial_argument_id=context["initial_argument_id"],
        ia_point_id=context["point_id"],
        x=context["x"],
        y=context["y"],
    )
    structures = result.get("structures", [])

    for s_idx in range(len(structures)):
        persist_for_structure(structures, s_idx)

    return redirect("ca_practice:counterargument_revision", ca_id=ca_id)


@login_required
def counterargument_revision(request: HttpRequest, ca_id: int):
    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task
    context = _task_context(task, ca)

    if request.method == "POST":
        revision_text = request.POST.get("revision_text", "").strip()
        original_text = (ca.text or "").strip()
        if revision_text and revision_text != original_text:
            RevisedCounterArgument.objects.update_or_create(
                counter_argument=ca,
                defaults={"revision_text": revision_text},
            )
            return redirect("ca_practice:next_task")
        error_message = "Please revise your counter-argument before submitting."
        allow_copy_paste = os.environ.get(
            "CA_PRACTICE_ALLOW_COPY_PASTE", ""
        ).lower() in {
            "1",
            "true",
            "yes",
        }
        return render(
            request,
            "ca_practice/counterargument_revision.html",
            {
                "task": task,
                "counter_argument": ca,
                "initial_argument_text": context["initial_argument_text"],
                "allow_copy_paste": allow_copy_paste,
                "revision_error": error_message,
            },
        )

    allow_copy_paste = os.environ.get("CA_PRACTICE_ALLOW_COPY_PASTE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    return render(
        request,
        "ca_practice/counterargument_revision.html",
        {
            "task": task,
            "counter_argument": ca,
            "initial_argument_text": context["initial_argument_text"],
            "allow_copy_paste": allow_copy_paste,
        },
    )
