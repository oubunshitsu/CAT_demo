from typing import Dict, List, Any
from functools import lru_cache
import json
from omegaconf import OmegaConf

from ca_practice.models import TemplateCAStructure
import logging
import os
import re
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def _safe_format(text: str, **kwargs) -> str:
    """
    Best-effort .format; if a placeholder is missing we fall back to the raw text.
    """
    try:
        return text.format(**kwargs)
    except KeyError:
        return text


def _template_requires_z(struct_template: TemplateCAStructure) -> bool:
    """
    Heuristically detect whether the template expects a 'z' value.
    """

    text_uses_z = "{z" in (struct_template.template_structure_text or "")
    cq_uses_z = any(
        "{z" in (cq.template_cq_text or "") for cq in struct_template.template_cqs.all()
    )

    return text_uses_z or cq_uses_z


@lru_cache(maxsize=1)
def _load_ia_info():
    try:
        with open(
            "llm_layer/local_predicate_model/static/ia_info.json", "r", encoding="utf-8"
        ) as f:
            return json.loads(f.read())
    except Exception:
        return {}


def _first_point_id(points: dict | None) -> str | None:
    if not isinstance(points, dict) or not points:
        return None
    keys = list(points.keys())
    try:
        return str(sorted(keys, key=lambda k: int(k))[0])
    except Exception:
        return str(keys[0])


def _select_point_id_from_llm(
    initial_argument_id: str,
    initial_argument: str,
    counter_argument: str,
    points: dict,
) -> str | None:
    load_dotenv("../local.env")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or not points:
        return _first_point_id(points)

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return _first_point_id(points)

    points_list = []
    for pid, entry in points.items():
        if not isinstance(entry, dict):
            continue
        essential = (entry.get("essential_ia_logic") or "").strip()
        if essential:
            points_list.append(f"{pid}: {essential}")
    points_block = "\n".join(points_list) or "No points available."

    prompt = (
        "You are selecting which IA point the counter-argument is attacking.\n\n"
        f"Initial argument (IA): {initial_argument}\n"
        f"Counter-argument (CA): {counter_argument}\n\n"
        "IA points (id: essential_ia_logic):\n"
        f"{points_block}\n\n"
        "Return only the point id that best matches the CA."
    )
    # breakpoint()

    try:
        client = OpenAI(api_key=api_key)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_completion_tokens=20,
        )
        raw = resp.choices[0].message.content.strip()
        # breakpoint()
    except Exception:
        return _first_point_id(points)

    logger.info({"point_select_prompt": prompt, "raw_output": raw})

    # Try JSON first
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            pid = str(payload.get("point_id", "")).strip()
            # breakpoint()
            if pid in points:
                return pid
    except Exception:
        pass

    # breakpoint()
    # Direct match
    for pid in points.keys():
        if str(pid) in raw:
            return str(pid)

    # First integer fallback
    m = re.search(r"\d+", raw)
    if m and m.group(0) in points:
        return m.group(0)

    return _first_point_id(points)


@lru_cache(maxsize=1)
def _load_structure_evaluator_prompt() -> str:
    try:
        with open(
            "llm_layer/local_predicate_model/prompts/structure_evaluator.txt",
            "r",
            encoding="utf-8",
        ) as f:
            return f.read()
    except Exception:
        return (
            "You are evaluating whether a logical structure description fits the given arguments.\n"
            "Initial argument (IA): {initial_argument}\n"
            "Counter-argument (CA): {counter_argument}\n"
            "Structure description: {ptn_description}\n\n"
            "Answer with YES if the structure is valid for the IA/CA pair, otherwise NO.\n"
            "Return only YES or NO."
        )


@lru_cache(maxsize=1)
def _load_ptn_descriptions() -> dict:
    try:
        with open(
            "llm_layer/local_predicate_model/static/ptn_desc.json",
            "r",
            encoding="utf-8",
        ) as f:
            return json.loads(f.read())
    except Exception:
        return {}


def _ptn_description_for_eval(
    ptn_id: int | str | None,
    format_ctx: dict,
    fallback_description: str,
) -> str:
    if not ptn_id:
        return fallback_description
    ptn_map = _load_ptn_descriptions()
    try:
        ptn_desc = ptn_map.get(str(ptn_id))
        if not isinstance(ptn_desc, str):
            return fallback_description
        return re.sub(
            r"\{([^{}]+)\}",
            lambda m: str(format_ctx.get(m.group(1), "")),
            ptn_desc,
        )
    except Exception:
        return fallback_description


def _evaluate_structure_validity(
    initial_argument: str, counter_argument: str, ptn_description: str
) -> bool:
    load_dotenv("../local.env")
    if os.environ.get("EVALUATOR_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        return True
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return True

    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return True

    prompt_template = _load_structure_evaluator_prompt()
    prompt = prompt_template.format(
        initial_argument=initial_argument,
        counter_argument=counter_argument,
        ptn_description=ptn_description,
    )

    try:
        client = OpenAI(api_key=api_key)
        model = os.environ.get("OPENAI_EVALUATOR_MODEL") or os.environ.get(
            "OPENAI_MODEL", "gpt-4o-mini"
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_completion_tokens=5,
        )
        raw = resp.choices[0].message.content.strip()
    except Exception:
        return True

    logger.info({"structure_eval_prompt": prompt, "raw_output": raw})

    raw_upper = raw.strip().upper()
    if raw_upper.startswith("YES"):
        return True
    if raw_upper.startswith("NO"):
        return False

    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            val = payload.get("valid")
            if isinstance(val, bool):
                return val
            ans = str(payload.get("answer", "")).strip().lower()
            if ans in {"yes", "y"}:
                return True
            if ans in {"no", "n"}:
                return False
    except Exception:
        pass

    return True


# --- LLM interface (stub) --------------------------------------------


# def call_llm_for_structures(
#     topic: str, initial_argument: str, counter_argument: str
# ) -> Dict[str, Any]:
#     """
#     This is where you call your real LLM.

#     It should return JSON of the form:
#     {
#       "structures": [
#         {"structure_name": "Alternative", "z": "wrongful conviction"},
#         ...
#       ]
#     }

#     For now we return a fixed stub so everything works without a real model.
#     """
#     # Example stub:
#     return {
#         "structures": [
#             {"structure_name": "Alternative", "z": "wrongful conviction"},
#             {"structure_name": "Alternative", "z": "test"},
#         ]
#     }


# --- Local Hugging Face model loader --------------------------------


@lru_cache(maxsize=2)
def call_llm_for_structures_dummy():
    """
    Lazily load a text-generation pipeline from a local fine-tuned model.

    Using an LRU cache avoids re-loading the model on every call while still
    allowing a couple of different model paths to be used during debugging.
    """

    # For now we return a fixed stub so everything works without a real model.

    # Example stub:
    return {
        "structures": [
            {
                "structure_name": "Mitigation",
                "z": "mitigation z",
                "diagram_type": "mitigation",
            },
            {
                "structure_name": "Alternative",
                "z": "wrongful conviction wrongful conviction wrongful conviction wrongful conviction wrongful conviction wrongful conviction wrongful conviction wrongful conviction",
                "diagram_type": "alternative",
            },
            {
                "structure_name": "No evidence",
                "z": "conviction wrongful conviction wrongful conviction wrongful conviction wrongful conviction wrongful conviction wrongful conviction",
                "diagram_type": "no-evidence",
            },
            {
                "structure_name": "Another True Cause",
                "z": "test",
                "diagram_type": "atc",
            },
            {
                "structure_name": "Missing mechanism #1",
                "z": "test",
                "diagram_type": "mm1",
            },
            {
                "structure_name": "Missing mechanism #2",
                "z": "test",
                "diagram_type": "mm2",
            },
            {
                "structure_name": "No need to address",
                "z": "test",
                "diagram_type": "nna",
            },
            {
                "structure_name": "Negative effect due to y #1",
                "z": "test",
                "diagram_type": "neg-eff1",
            },
            {
                "structure_name": "Negative effect due to y #2",
                "z": "test",
                "diagram_type": "neg-eff2",
            },
            {
                "structure_name": "Positive effects of a different perspective from y #1",
                "z": "test",
                "diagram_type": "dif-per1",
            },
            {
                "structure_name": "Positive effects of a different perspective from y #2",
                "z": "test",
                "diagram_type": "dif-per2",
            },
        ]
    }


@lru_cache(maxsize=2)
def call_llm_for_structures_predicates(
    topic, initial_argument_id, counter_argument, ia_point_id
):
    config = OmegaConf.load("llm_layer/local_predicate_model/openai_config.yaml")
    from llm_layer.local_predicate_model.components.execute import Executer

    diagram_types_names = {
        1: {
            "structure_name": "Mitigation",
            "diagram_type": "mitigation",
        },
        2: {
            "structure_name": "Alternative",
            "diagram_type": "alternative",
        },
        3: {
            "structure_name": "No evidence",
            "diagram_type": "no-evidence",
        },
        4: {
            "structure_name": "Another True Cause",
            "diagram_type": "atc",
        },
        5: {
            "structure_name": "Missing mechanism #1",
            "diagram_type": "mm1",
        },
        6: {
            "structure_name": "Missing mechanism #2",
            "diagram_type": "mm2",
        },
        7: {
            "structure_name": "No need to address",
            "diagram_type": "nna",
        },
        81: {
            "structure_name": "Negative effect due to y #1",
            "diagram_type": "neg-eff1",
        },
        82: {
            "structure_name": "Negative effect due to y #2",
            "diagram_type": "neg-eff2",
        },
        9: {
            "structure_name": "Positive effects of a different perspective from y #1",
            "diagram_type": "dif-per1",
        },
        10: {
            "structure_name": "Positive effects of a different perspective from y #2",
            "diagram_type": "dif-per2",
        },
    }
    executer = Executer(
        ia_id=initial_argument_id,
        ia_point_id=ia_point_id,
        ca_essay=counter_argument,
        provider=config.provider,
        model_id=config.model_id,
        generation_args=config.generation_args
        if hasattr(config, "generation_args")
        else None,
        predicates_questions_mapping_path=config.predicates_questions_mapping_path,
        system_prompt_path=config.system_prompt_path,
        user_prompt_path=config.user_prompt_path,
        ia_info_path=config.ia_info_path,
    )
    ptn_results = executer()

    identified_ptns, identified_slots = ptn_results["ptn"], ptn_results["slot"]

    if len(identified_ptns) == 0:
        return None

    final_results = []
    for ptn in identified_ptns:
        structure = dict(diagram_types_names[ptn])
        slot_values = identified_slots.get(ptn) or []
        structure["z"] = slot_values[0] if slot_values else ""
        structure["ptn_id"] = ptn
        final_results.append(structure)

    # breakpoint()
    return {"structures": final_results}


# def call_llm_api_for_structures_predicates(
#     topic, initial_argument_id, counter_argument
# ):
#     with (
#         open(
#             "backend/llm_layer/local_predicate_model/prompts/api_version/system_prompt.txt",
#             "r",
#         ) as f1,
#         open(
#             "backend/llm_layer/local_predicate_model/prompts/api_version/user_prompt.txt"
#         ) as f2,
#     ):
#         system_prompt = json.loads(f1.read())
#         user_prompt_template = json.loads(f2.read())

#     return


# --- Public function used by the view --------------------------------


def run_llm_structures(
    topic: str,
    initial_argument: str,
    counter_argument: str,
    initial_argument_id: str | None = None,
    ia_point_id: str | None = None,
    x: str | None = None,
    y: str | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    1) Ask the LLM which templates apply, with x,y,z for each.
    2) Look up the templates in TemplateCAStructure.
    3) Fill them and return a list of ready-to-display structures.
    """
    # raw = call_llm_for_structures_dummy()
    # raw = {}
    ia_info = (
        _load_ia_info().get(str(initial_argument_id or ""), {})
        if initial_argument_id
        else {}
    )
    points = ia_info.get("points") if isinstance(ia_info, dict) else {}
    selected_point_id = ia_point_id or _select_point_id_from_llm(
        str(initial_argument_id or ""), initial_argument, counter_argument, points or {}
    )
    # selected_point_id = "2"
    point_data = (points or {}).get(str(selected_point_id)) if selected_point_id else {}
    # breakpoint()

    # Prefer point-provided x/y, but allow caller overrides.
    x = x or (point_data.get("x") if isinstance(point_data, dict) else None)
    y = y or (point_data.get("y") if isinstance(point_data, dict) else None)

    raw = (
        call_llm_for_structures_predicates(
            topic, initial_argument_id, counter_argument, selected_point_id
        )
        or {}
    )

    # raw = call_llm_for_structures_dummy()

    # logger.info(f"raw results: {raw}")
    structures: List[Dict[str, Any]] = []

    for s in raw.get("structures", []):
        structure_name = s.get("structure_name") or s.get("template_id")
        if not structure_name:
            continue

        x_val = x or s.get("x")
        y_val = y or s.get("y")
        z = s.get("z", "z")
        s["initial_argument_id"] = initial_argument_id
        s["ia_point_id"] = selected_point_id

        tmpl = (
            TemplateCAStructure.objects.prefetch_related("template_cqs")
            .filter(template_structure_name__iexact=structure_name)
            .first()
        )
        if tmpl is None:
            # Unknown template name → skip or log; for now skip.
            raise Exception("Unknown template name, like not loading the cqs")

        requires_z = _template_requires_z(tmpl)
        if requires_z and not z:
            # Template needs z but model did not provide it; skip to avoid bad rendering.
            continue

        # Prefer IA-provided x,y, but allow LLM-suggested overrides as a fallback.
        x_fmt = x_val or "x"
        y_fmt = y_val or "y"

        description = _safe_format(tmpl.template_structure_text, x=x_fmt, y=y_fmt, z=z)
        format_ctx = {}
        if isinstance(point_data, dict) and point_data:
            format_ctx.update(point_data)
        elif isinstance(ia_info, dict):
            format_ctx.update(ia_info)

        format_ctx.update({
            "x": x_fmt,
            "y": y_fmt,
            "z": z,
        })
        # Default any missing placeholders to empty strings.
        eval_description = _ptn_description_for_eval(
            s.get("ptn_id"), format_ctx, description
        )
        critical_questions = [
            _safe_format(cq.template_cq_text, x=x_fmt, y=y_fmt, z=z)
            for cq in tmpl.template_cqs.all()
        ]

        if not _evaluate_structure_validity(
            initial_argument, counter_argument, eval_description
        ):
            continue

        # Fill diagram metadata; fall back to "alternative" so the page still renders.
        diagram_type = s.get("diagram_type", "alternative")
        diagram_template = s.get(
            "diagram_template", f"ca_practice/diagram_{diagram_type}.html"
        )

        structures.append({
            "id": tmpl.template_structure_id,
            "name": tmpl.template_structure_name,
            "description": description,
            "ia_conclusion": s.get("ia_conclusion", description),
            "ia_premise": s.get("ia_premise", description),
            "ca_premise": s.get("ca_premise", description),
            "x": x_fmt,
            "y": y_fmt,
            "z": z,
            "ptn_id": s.get("ptn_id"),
            "diagram_type": diagram_type,
            "diagram_template": diagram_template,
            "critical_questions": critical_questions,
            "ia_point_id": selected_point_id,
        })

    # logger.info(f"structures: {structures}")
    return {"structures": structures, "selected_point_id": selected_point_id}
