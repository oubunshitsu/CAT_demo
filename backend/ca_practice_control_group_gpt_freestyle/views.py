import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from django.contrib.auth import login, logout
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import (
    ChatHistory,
    CounterArgument,
    InitialArgument,
    RevisedCounterArgument,
    Topic,
)
from ca_practice.forms import EmailUserCreationForm


FIRST_IDX = 0
_SWISS_TZ = ZoneInfo("Europe/Zurich")


def _swiss_timestamp() -> str:
    return datetime.now(_SWISS_TZ).strftime("%Y-%m-%d,%H:%M:%S")


def _cg_timer_start_key(ca_id: int) -> str:
    return f"cg_chat_started_{ca_id}"


def _ensure_cg_timer(request, ca_id: int) -> None:
    key = _cg_timer_start_key(ca_id)
    if not request.session.get(key):
        request.session[key] = datetime.now(_SWISS_TZ).isoformat()
        request.session.modified = True


def _get_cg_elapsed_seconds(request, ca_id: int) -> int:
    start_raw = request.session.get(_cg_timer_start_key(ca_id))
    if not start_raw:
        return 0
    try:
        start_dt = datetime.fromisoformat(start_raw)
        delta = int((datetime.now(_SWISS_TZ) - start_dt).total_seconds())
    except Exception:
        delta = 0
    return max(0, delta)


def _clear_cg_timer(request, ca_id: int) -> None:
    request.session.pop(_cg_timer_start_key(ca_id), None)
    request.session.modified = True


def entry(request: HttpRequest):
    if request.user.is_authenticated:
        return start(request)
    return redirect("login")


def signup(request: HttpRequest):
    web_signup_enabled = os.environ.get("CA_PRACTICE_ENABLE_WEB_SIGNUP", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if not web_signup_enabled:
        raise Http404("Signup is disabled.")

    if request.user.is_authenticated:
        return redirect("ca_practice_control_group_gpt_freestyle:start")

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
            if cg_group_name:
                cg_group, _ = Group.objects.get_or_create(name=cg_group_name)
                user.groups.add(cg_group)
            if main_group_name:
                user.groups.remove(*Group.objects.filter(name=main_group_name))
            login(request, user)
            return redirect("ca_practice_control_group_gpt_freestyle:start")
    else:
        form = EmailUserCreationForm()

    return render(request, "registration/signup.html", {"form": form})


def _all_tasks():
    selected_topic_id = (
        os.environ.get("CA_PRACTICE_SINGLE_TOPIC_ID")
        or os.environ.get("CA_PRACTICE_CG_TOPIC_ID")
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
    request.session["cg_idx"] = FIRST_IDX
    request.session["cg_seen_instructions"] = False
    request.session["cg_stance_by_topic"] = {}
    return redirect("ca_practice_control_group_gpt_freestyle:instructions")


@login_required
def instructions(request: HttpRequest):
    if request.method == "POST":
        request.session["cg_seen_instructions"] = True
        return redirect("ca_practice_control_group_gpt_freestyle:stance")
    template_name = (
        "ca_practice_control_group_gpt_freestyle/instructions_simple.html"
        if os.environ.get("CA_PRACTICE_SIMPLE_INSTRUCTIONS", "").lower()
        in {"1", "true", "yes"}
        else "ca_practice_control_group_gpt_freestyle/instructions.html"
    )
    return render(request, template_name)


@login_required
def stance(request: HttpRequest):
    if not request.session.get("cg_seen_instructions"):
        return redirect("ca_practice_control_group_gpt_freestyle:instructions")

    topics = _all_tasks()
    if not topics:
        return render(request, "ca_practice_control_group_gpt_freestyle/empty.html")

    idx = int(request.session.get("cg_idx", 0))
    if idx < 0 or idx >= len(topics):
        return redirect("ca_practice_control_group_gpt_freestyle:done")

    topic = topics[idx]

    if request.method == "POST":
        stance_value = _normalize_stance(request.POST.get("stance"))
        if stance_value:
            stance_by_topic = request.session.get("cg_stance_by_topic", {})
            stance_by_topic[str(topic.topic_id)] = stance_value
            request.session["cg_stance_by_topic"] = stance_by_topic
            request.session.modified = True
            return redirect("ca_practice_control_group_gpt_freestyle:task_session")

    progress = {"current": idx + 1, "total": len(topics)}
    return render(
        request,
        "ca_practice_control_group_gpt_freestyle/stance.html",
        {"topic": topic, "progress": progress},
    )


@login_required
def task_session(request: HttpRequest):
    if not request.session.get("cg_seen_instructions"):
        return redirect("ca_practice_control_group_gpt_freestyle:instructions")

    topics = _all_tasks()
    if not topics:
        return render(request, "ca_practice_control_group_gpt_freestyle/empty.html")

    idx = int(request.session.get("cg_idx", 0))
    if idx < 0 or idx >= len(topics):
        return redirect("ca_practice_control_group_gpt_freestyle:done")

    topic = topics[idx]
    stance_by_topic = request.session.get("cg_stance_by_topic", {})
    stance_value = _normalize_stance(stance_by_topic.get(str(topic.topic_id)))
    if not stance_value:
        return redirect("ca_practice_control_group_gpt_freestyle:stance")

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
            extracted = _extract_claims_premises(ca.text)
            request.session[f"cg_cp_{ca.counter_argument_id}"] = extracted
            request.session.modified = True
            return redirect(
                "ca_practice_control_group_gpt_freestyle:feedback_chat",
                ca_id=ca.counter_argument_id,
            )

    progress = {"current": idx + 1, "total": len(topics)}
    allow_copy_paste = os.environ.get("CA_PRACTICE_ALLOW_COPY_PASTE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    return render(
        request,
        "ca_practice_control_group_gpt_freestyle/task.html",
        {"task": task, "progress": progress, "allow_copy_paste": allow_copy_paste},
    )


@login_required
def task_index(request: HttpRequest, idx: int):
    topics = _all_tasks()
    if idx < 0 or idx >= len(topics):
        raise Http404("No such task index")

    topic = topics[idx]
    stance_by_topic = request.session.get("cg_stance_by_topic", {})
    stance_value = _normalize_stance(stance_by_topic.get(str(topic.topic_id)))
    if not stance_value:
        return redirect("ca_practice_control_group_gpt_freestyle:stance")

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
            extracted = _extract_claims_premises(ca.text)
            request.session[f"cg_cp_{ca.counter_argument_id}"] = extracted
            request.session.modified = True
            return redirect(
                "ca_practice_control_group_gpt_freestyle:feedback_chat",
                ca_id=ca.counter_argument_id,
            )

    progress = {"current": idx + 1, "total": len(topics)}
    allow_copy_paste = os.environ.get("CA_PRACTICE_ALLOW_COPY_PASTE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    return render(
        request,
        "ca_practice_control_group_gpt_freestyle/task.html",
        {"task": task, "progress": progress, "allow_copy_paste": allow_copy_paste},
    )


@login_required
def next_task(request: HttpRequest):
    topics = _all_tasks()
    idx = int(request.session.get("cg_idx", 0)) + 1
    request.session["cg_idx"] = idx

    if idx >= len(topics):
        return redirect("ca_practice_control_group_gpt_freestyle:done")

    return redirect("ca_practice_control_group_gpt_freestyle:stance")


@login_required
def done(request: HttpRequest):
    return render(request, "ca_practice_control_group_gpt_freestyle/done.html")


@login_required
def logout_view(request: HttpRequest):
    logout(request)
    return redirect("ca_practice_control_group_gpt_freestyle:entry")


def _persist_chat_history(request, user, ca: CounterArgument, history: list[dict]):
    if not history:
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
        "duration_seconds": _get_cg_elapsed_seconds(request, ca.counter_argument_id),
    }

    ChatHistory.objects.update_or_create(
        user=user,
        counter_argument=ca,
        defaults={"history_text_dict": payload},
    )


def _extract_claims_premises(counter_text: str) -> dict:
    load_dotenv("../local.env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {"claims": [], "premises": []}

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return {"claims": [], "premises": []}

    prompt = (
        "Extract claims and premises from the counter-argument.\n"
        "Only consider the sentences that are actually in the counter-argument without extracting the implicit premises.\n"
        "Return JSON only with keys: claims, premises.\n"
        "Each value should be a list of sentences (strings).\n\n"
        f"Counter-argument:\n{counter_text}\n"
    )

    try:
        client = OpenAI(api_key=api_key)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_completion_tokens=200,
        )
        raw = resp.choices[0].message.content.strip()
    except Exception:
        return {"claims": [], "premises": []}

    try:
        import json

        payload = json.loads(raw)
        claims = payload.get("claims") or []
        premises = payload.get("premises") or []
        claims = [str(x).strip() for x in claims if str(x).strip()]
        premises = [str(x).strip() for x in premises if str(x).strip()]
        return {"claims": claims, "premises": premises}
    except Exception:
        return {"claims": [], "premises": []}


def _initial_message_from_counts(counts: dict) -> str:
    claims = int(counts.get("claims", 0))
    premises = int(counts.get("premises", 0))

    # Dummy rules for now
    if premises == 0:
        return "Good job on the counter-argument. It seems like you do not have any premises to support your claim. Please consider adding more premises."
    # if claims <= 1 and premises <= 1:
    #     return "I see a very concise counter-argument. Let's expand it with clearer claims and support."
    if claims == 0:
        return "Good job on the counter-argument. It seems that you do not have any clear claims. Please consider making your claims clearer"

    if claims > premises:
        return "You made several claims but gave fewer premises. Please consider adding supporting reasons."

    return "Your counter-argument has multiple premises. Let's check if they connect clearly to the main claim."


def _counts_from_extraction(extracted: dict) -> dict:
    claims = extracted.get("claims") or []
    premises = extracted.get("premises") or []
    return {"claims": len(claims), "premises": len(premises)}


def _get_or_extract_claims_premises(request, ca) -> dict:
    session_key = f"cg_cp_{ca.counter_argument_id}"
    cached = request.session.get(session_key)
    if isinstance(cached, dict):
        return cached
    extracted = _extract_claims_premises(ca.text)
    request.session[session_key] = extracted
    request.session.modified = True
    return extracted


def _format_claims_premises_message(extracted: dict) -> str:
    claims = extracted.get("claims") or []
    premises = extracted.get("premises") or []

    num_claims = len(claims)
    num_premises = len(premises)

    if not claims and not premises:
        return (
            "I couldn't clearly separate claims and premises from your counter-argument. "
            "Try splitting it into shorter sentences."
        )

    lines = ["Here is a breakdown of your counter-argument:"]
    if claims:
        lines.append("\nClaims:")
        for idx, c in enumerate(claims, 1):
            lines.append(f"{idx}. {c}")
    if premises:
        lines.append("\nPremises:")
        for idx, p in enumerate(premises, 1):
            lines.append(f"{idx}. {p}")

    lines.append(
        f"\nYou seem to have {num_claims} claim(s) and {num_premises} premise(s)"
    )

    if num_premises == 0:
        lines.append("\nPlease consider adding premises to your claim(s)")
    elif num_claims == 0:
        lines.append(
            "\nI could not find a clear claim in your counter-argument. Please consider making your claim(s) clearer"
        )

    elif num_claims > num_premises:
        lines.append(
            "\nYou made several claims but gave fewer premises. Please consider adding supporting reasons."
        )

    return "\n".join(lines)


def _claim_premise_explainer() -> str:
    return (
        "A claim is the main point or conclusion you are trying to prove. "
        "A premise is a supporting reason or piece of evidence that backs up the claim.\n\n"
        "Example:\n"
        "Claim: The city should add more bike lanes.\n"
        "Premise: Protected bike lanes reduce accidents and make cycling safer."
    )


def _counts_based_improvement_hint(counts: dict) -> str | None:
    load_dotenv("../local.env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None

    client = OpenAI(api_key=api_key)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    claims = int(counts.get("claims", 0))
    premises = int(counts.get("premises", 0))

    prompt = (
        "You are a writing coach. Provide a single short hint (1-2 sentences). "
        "Base it ONLY on the counts below and focus on how to improve the counter-argument.\n\n"
        f"Claims: {claims}\n"
        f"Premises: {premises}\n"
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_completion_tokens=120,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


def _fallback_improvement_hint(counts: dict) -> str:
    claims = int(counts.get("claims", 0))
    premises = int(counts.get("premises", 0))

    if claims == 0:
        return "Try stating one clear claim first, then add support for it."
    if premises == 0:
        return "Add at least one supporting reason or example for your main claim."
    if claims > premises:
        return "You have more claims than support. Add a premise to back up each claim."
    if premises > claims:
        return "Consider connecting each premise more directly to a single clear claim."
    return "Try strengthening the link between your claim and premises with a short example."


def _intent_detection_failure_message() -> str:
    return (
        "My apologies, but I am afraid that I might not be able to answer your request. "
        "I can help you by telling you more details on your counter-argument, giving you some "
        "hints on how to improve your counter-argument, or giving a short explanation about "
        "what a premise/claim is"
    )


def _detect_intent(user_message: str) -> str | None:
    load_dotenv("../local.env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None

    client = OpenAI(api_key=api_key)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    prompt = (
        "Classify the user's intent into one of these labels and return ONLY the label:\n"
        "- more_details (user wants more details on their counter-argument)\n"
        "- improve_hint (user wants hints on how to improve their counter-argument)\n"
        "- claim_premise (user wants an explanation of claim/premise)\n"
        "- none (does not match the three intents)\n\n"
        f"User message: {user_message}"
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_completion_tokens=20,
        )
        label = resp.choices[0].message.content.strip().lower()
    except Exception:
        return None

    if label == "more_details":
        return "More details on my counter-argument"
    if label == "improve_hint":
        return "How should I improve"
    if label == "claim_premise":
        return "What is claim/premise"
    return None


def _llm_improvement_reply(
    task, ca, user_message, history=None, initial_argument_text=None
):
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
    load_dotenv("../local.env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None

    client = OpenAI(api_key=api_key)
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    with open(
        "llm_layer/feedback_agent/prompts/system_prompt_no_structure_identified.txt",
        "r",
    ) as f:
        system_prompt_template = f.read()

    try:
        system_content = system_prompt_template.format(
            topic=getattr(task, "topic_text_value", ""),
            initial_argument=initial_argument_text,
            counter_argument=getattr(
                ca, "text", getattr(ca, "counter_argument_text", "")
            ),
        )
        messages = [{"role": "system", "content": system_content}]

        for turn in history:
            raw_role = turn.get("role", "user")
            api_role = "assistant" if raw_role in ("agent", "assistant") else "user"
            content = turn.get("content", "")
            messages.append({"role": api_role, "content": content})

        user_content = user_message or "Please continue the feedback."
        messages.append({"role": "user", "content": user_content})

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.4,
            max_completion_tokens=300,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


def _cg_flow_steps():
    return [
        {
            "assistant": "Thanks for sharing your counter-argument. What would you like to focus on next?"
        },
        {"assistant": "Noted. Let’s dig deeper. Which part feels weakest right now?"},
        {"assistant": "Try revising one sentence to strengthen that part."},
        {"assistant": "You can now move to the revision page when ready."},
    ]


def _cg_seed_history(ca_id: int, ca, request) -> tuple[list, int]:
    session_key = f"cg_chat_{ca_id}"
    step_key = f"cg_chat_step_{ca_id}"
    history = request.session.get(session_key, [])
    step = int(request.session.get(step_key, 0))
    if not history:
        extracted = _get_or_extract_claims_premises(request, ca)
        counts = _counts_from_extraction(extracted)
        opening = _initial_message_from_counts(counts)
        history = [
            {"role": "assistant", "content": opening, "timestamp": _swiss_timestamp()}
        ]
        request.session[session_key] = history
        request.session[step_key] = 0
        request.session.modified = True
        _persist_chat_history(request, request.user, ca, history)
    return history, step


def _cg_apply_choice(
    request, ca, history, step, choice: str, user_text: str | None = None
) -> tuple[list, int]:
    flow = _cg_flow_steps()
    history.append(
        {
            "role": "user",
            "content": user_text or choice,
            "timestamp": _swiss_timestamp(),
        }
    )
    if choice == "More details on my counter-argument":
        extracted = _get_or_extract_claims_premises(request, ca)
        agent_text = _format_claims_premises_message(extracted)
    elif choice == "How should I improve":
        extracted = _get_or_extract_claims_premises(request, ca)
        counts = _counts_from_extraction(extracted)
        agent_text = _counts_based_improvement_hint(
            counts
        ) or _fallback_improvement_hint(counts)
    elif choice == "What is claim/premise":
        agent_text = _claim_premise_explainer()
    else:
        agent_text = flow[min(step + 1, len(flow) - 1)]["assistant"]
    step = min(step + 1, len(flow) - 1)
    history.append(
        {"role": "assistant", "content": agent_text, "timestamp": _swiss_timestamp()}
    )
    session_key = f"cg_chat_{ca.counter_argument_id}"
    step_key = f"cg_chat_step_{ca.counter_argument_id}"
    request.session[session_key] = history
    request.session[step_key] = step
    request.session.modified = True
    _persist_chat_history(request, request.user, ca, history)
    return history, step


def _cg_apply_user_message(
    request, ca, history, step, user_message: str
) -> tuple[list, int]:
    mapped_choice = _detect_intent(user_message)
    if not mapped_choice:
        history.append(
            {
                "role": "user",
                "content": user_message,
                "timestamp": _swiss_timestamp(),
            }
        )
        history.append({
            "role": "assistant",
            "content": _intent_detection_failure_message(),
            "timestamp": _swiss_timestamp(),
        })
        session_key = f"cg_chat_{ca.counter_argument_id}"
        step_key = f"cg_chat_step_{ca.counter_argument_id}"
        request.session[session_key] = history
        request.session[step_key] = step
        request.session.modified = True
        _persist_chat_history(request, request.user, ca, history)
        return history, step

    return _cg_apply_choice(
        request, ca, history, step, mapped_choice, user_text=user_message
    )


@login_required
def feedback_chat(request: HttpRequest, ca_id: int):
    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task
    _ensure_cg_timer(request, ca_id)
    history, step = _cg_seed_history(ca_id, ca, request)
    allow_copy_paste = os.environ.get("CA_PRACTICE_ALLOW_COPY_PASTE", "").lower() in {
        "1",
        "true",
        "yes",
    }

    if request.method == "POST":
        choice = request.POST.get("choice", "").strip()
        user_message = request.POST.get("user_message", "").strip()
        if user_message:
            history, step = _cg_apply_user_message(
                request, ca, history, step, user_message
            )
        elif choice:
            history, step = _cg_apply_choice(request, ca, history, step, choice)

    choices = [
        "More details on my counter-argument",
        "How should I improve",
        "What is claim/premise",
    ]

    return render(
        request,
        "ca_practice_control_group_gpt_freestyle/feedback_chat.html",
        {
            "task": task,
        "counter_argument": ca,
        "history": history,
        "choices": choices,
        "allow_copy_paste": allow_copy_paste,
    },
    )


@login_required
def feedback_chat_api(request: HttpRequest, ca_id: int):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    _ensure_cg_timer(request, ca_id)
    history, step = _cg_seed_history(ca_id, ca, request)

    choice = request.POST.get("choice", "").strip()
    user_message = request.POST.get("user_message", "").strip()
    if user_message:
        history, step = _cg_apply_user_message(request, ca, history, step, user_message)
    elif choice:
        history, step = _cg_apply_choice(request, ca, history, step, choice)
    else:
        return JsonResponse({"ok": False, "error": "Empty choice"}, status=400)
    return JsonResponse({"ok": True, "history": history})


@login_required
def counterargument_revision(request: HttpRequest, ca_id: int):
    ca = get_object_or_404(
        CounterArgument, counter_argument_id=ca_id, user=request.user
    )
    task = ca.task
    history = request.session.get(f"cg_chat_{ca_id}", [])
    if history:
        _persist_chat_history(request, request.user, ca, history)
    _clear_cg_timer(request, ca_id)

    if request.method == "POST":
        revision_text = request.POST.get("revision_text", "").strip()
        original_text = (ca.text or "").strip()
        if revision_text and revision_text != original_text:
            RevisedCounterArgument.objects.update_or_create(
                counter_argument=ca,
                defaults={"revision_text": revision_text},
            )
            return redirect("ca_practice_control_group_gpt_freestyle:next_task")
        error_message = "Please revise your counter-argument before submitting."
        allow_copy_paste = os.environ.get("CA_PRACTICE_ALLOW_COPY_PASTE", "").lower() in {
            "1",
            "true",
            "yes",
        }
        return render(
            request,
            "ca_practice_control_group_gpt_freestyle/counterargument_revision.html",
            {
                "task": task,
                "counter_argument": ca,
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
        "ca_practice_control_group_gpt_freestyle/counterargument_revision.html",
        {
            "task": task,
            "counter_argument": ca,
            "allow_copy_paste": allow_copy_paste,
        },
    )
