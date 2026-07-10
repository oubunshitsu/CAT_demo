#!/usr/bin/env python
"""
Run CALSA+ predicate-model evaluation on calsaplus_dataset.jsonl.

The main metric is any-label recall: an instance is counted as correct when
at least one gold PTN label is present in the predicted PTNs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:

    def load_dotenv(*args: Any, **kwargs: Any) -> bool:
        return False


SCRIPT_DIR = Path(__file__).resolve().parent
MODEL_DIR = SCRIPT_DIR.parent
# Add backend/ to sys.path so imports like llm_layer.local_predicate_model work
# whether this script is run from the repo root or from test_performance/.
BACKEND_DIR = MODEL_DIR.parents[1]
REPO_DIR = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@dataclass
class EvaluationResult:
    total: int
    correct: int
    recall: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate gpt-5.2 on the CALSA+ JSONL dataset."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=SCRIPT_DIR / "calsaplus_dataset.jsonl",
        help="Path to the CALSA+ JSONL dataset.",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.2",
        help="OpenAI model ID to use.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of dataset rows to evaluate.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SCRIPT_DIR / "calsaplus_gpt52_predictions.jsonl",
        help="Path to write per-example predictions.",
    )
    parser.add_argument(
        "--instances-dir",
        type=Path,
        default=SCRIPT_DIR / "calsaplus_gpt52_instance_results",
        help="Directory to write one detailed JSON result per dataset instance.",
    )
    parser.add_argument(
        "--questions-output",
        type=Path,
        default=SCRIPT_DIR / "calsaplus_gpt52_predicate_questions_by_ia.json",
        help="Path to write predicate-level questions grouped by IA ID.",
    )
    parser.add_argument(
        "--slot-output",
        type=Path,
        default=SCRIPT_DIR / "calsaplus_gpt52_slotfiller_metrics.json",
        help="Path to write aggregate slot-filler evaluation metrics.",
    )
    parser.add_argument(
        "--bertscore-lang",
        default="en",
        help="Language passed to bert_score.score.",
    )
    parser.add_argument(
        "--bertscore-model",
        default=None,
        help="Optional BERTScore model_type. If omitted, BERTScore chooses the default for the language.",
    )
    parser.add_argument(
        "--bertscore-rescale",
        action="store_true",
        help="Use BERTScore baseline rescaling.",
    )
    parser.add_argument(
        "--ia-info",
        type=Path,
        default=MODEL_DIR / "static" / "ia_info.json",
        help="Path to ia_info.json.",
    )
    parser.add_argument(
        "--ia-point-id",
        default=None,
        help="Optional IA point ID. Defaults to the first point in ia_info.json.",
    )
    return parser.parse_args()


def load_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path}:{line_number}") from exc
            if limit is not None and len(rows) >= limit:
                break
    return rows


def add_current_template_fields(point_data: dict[str, Any]) -> dict[str, Any]:
    """
    Convert older flat CALSA+ IA metadata to the field names expected by the
    current predicate-question templates.

    This is intentionally local to the performance script so the production
    formatter and static files keep the same behavior as the app.
    """
    aliases = {
        "xy_relation": point_data.get("causal_relation"),
        "xy_relation_reverse": point_data.get("reverse_causal_relation"),
        "zy_relation": point_data.get("causal_relation"),
        "y_polarity": point_data.get("same_polarity"),
        "z_polarity_y_sup_z": point_data.get("same_polarity"),
        "z_polarity_y_pro_z": point_data.get("opposite_polarity"),
        "z_polarity_x_pro_z": point_data.get("polarity_x_pro"),
        "z_polarity_x_sup_z": point_data.get("polarity_x_sup"),
    }
    return {
        **point_data,
        **{
            key: value
            for key, value in aliases.items()
            if key not in point_data and value is not None
        },
    }


def build_evaluation_ia_info(source_path: Path, output_dir: Path) -> Path:
    """
    Prepare IA context for the dataset while preserving the existing app code.

    The current app ultimately passes an ia_id, ia_point_id, and ca_essay into
    Executer. For this dataset, rows provide ia_id and ca_essay but no point id,
    so flat IA entries are exposed as a single point whose prompt IA text is
    essential_ia_logic. Older IA entries also use names such as causal_relation,
    while the current predicate templates expect xy_relation. This temporary
    file bridges that schema difference for evaluation only.
    """
    with source_path.open("r", encoding="utf-8") as f:
        ia_info = json.load(f)

    prepared: dict[str, Any] = {}
    for ia_id, ia_entry in ia_info.items():
        if not isinstance(ia_entry, dict):
            prepared[ia_id] = ia_entry
            continue

        points = ia_entry.get("points")
        if isinstance(points, dict) and points:
            prepared_points = {}
            base_data = {
                key: value for key, value in ia_entry.items() if key != "points"
            }
            for point_id, point_data in points.items():
                if isinstance(point_data, dict):
                    prepared_points[point_id] = add_current_template_fields({
                        **base_data,
                        **point_data,
                    })
                else:
                    prepared_points[point_id] = point_data
            prepared[ia_id] = {**ia_entry, "points": prepared_points}
        else:
            prepared[ia_id] = {
                "essay": ia_entry.get("essay", ""),
                "points": {
                    "1": add_current_template_fields({
                        **ia_entry,
                        "point_text": ia_entry.get("essential_ia_logic", ""),
                    })
                },
            }

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix="_ia_info.json",
        dir=output_dir,
        delete=False,
    )
    with handle:
        json.dump(prepared, handle, ensure_ascii=False, indent=2)
    return Path(handle.name)


def normalize_ptn(ptn: Any) -> int:
    value = int(ptn)
    if value in (81, 82):
        return 8
    return value


def normalize_ptns(ptns: Any) -> set[int]:
    if ptns is None:
        return set()
    if not isinstance(ptns, list):
        raise TypeError(f"Expected PTNs to be a list, got {type(ptns).__name__}")
    return {normalize_ptn(ptn) for ptn in ptns}


def normalize_slot_map(slots: Any) -> dict[int, list[str]]:
    if not isinstance(slots, dict):
        return {}
    normalized: dict[int, list[str]] = {}
    for ptn, values in slots.items():
        normalized_ptn = normalize_ptn(ptn)
        if isinstance(values, list):
            normalized_values = [str(value) for value in values if str(value).strip()]
        elif values is None:
            normalized_values = []
        else:
            normalized_values = [str(values)]
        normalized.setdefault(normalized_ptn, []).extend(normalized_values)
    return normalized


def first_predicted_slots_by_ptn(raw_prediction: dict[str, Any]) -> dict[int, str]:
    raw_slots = raw_prediction.get("slot", {})
    if not isinstance(raw_slots, dict):
        return {}

    first_slots: dict[int, str] = {}
    for raw_ptn in raw_prediction.get("ptn", []):
        normalized_ptn = normalize_ptn(raw_ptn)
        if normalized_ptn in first_slots:
            continue
        slot_values = raw_slots.get(raw_ptn, raw_slots.get(str(raw_ptn), []))
        if isinstance(slot_values, list):
            first_slot = str(slot_values[0]) if slot_values else ""
        elif slot_values is None:
            first_slot = ""
        else:
            first_slot = str(slot_values)
        first_slots[normalized_ptn] = first_slot
    return first_slots


def safe_filename(value: Any) -> str:
    text = str(value or "unknown")
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_")
    return text or "unknown"


def extract_question(conversation: list[dict[str, str]]) -> str:
    for message in conversation:
        if message.get("role") != "user":
            continue
        content = message.get("content", "")
        marker = "\nQuestion:\n"
        if marker in content:
            return content.split(marker, 1)[1].strip()
    return ""


def collect_prompts(executer: Any) -> list[dict[str, Any]]:
    return [
        {
            "predicate": predicate,
            "question": extract_question(conversation),
            "conversation": conversation,
        }
        for predicate, conversation in executer.prompt_formater()
    ]


def add_questions_for_instance(
    questions_by_ia: dict[str, dict[str, dict[str, dict[str, Any]]]],
    prediction: dict[str, Any],
) -> None:
    ia_id = str(prediction.get("ia_id") or "unknown")
    ca_id = prediction.get("ca_id")
    questions_by_ia.setdefault(ia_id, {})
    for prompt in prediction.get("prompts", []):
        predicate = str(prompt.get("predicate") or "unknown")
        question = prompt.get("question", "")
        questions = questions_by_ia[ia_id].setdefault(predicate, {})
        entry = questions.setdefault(
            question,
            {
                "question": question,
                "ca_ids": [],
                "count": 0,
            },
        )
        if ca_id not in entry["ca_ids"]:
            entry["ca_ids"].append(ca_id)
        entry["count"] = len(entry["ca_ids"])


def format_questions_by_ia(
    questions_by_ia: dict[str, dict[str, dict[str, dict[str, Any]]]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {
        ia_id: {
            predicate: sorted(
                questions.values(),
                key=lambda item: (-item["count"], item["question"]),
            )
            for predicate, questions in sorted(predicates.items())
        }
        for ia_id, predicates in sorted(questions_by_ia.items())
    }


def run_example(
    args: argparse.Namespace, row: dict[str, Any], ia_info_path: Path
) -> dict[str, Any]:
    from llm_layer.local_predicate_model.components.execute import Executer

    executer = Executer(
        ia_id=row["ia_id"],
        ia_point_id=args.ia_point_id,
        ca_essay=row["ca_essay"],
        provider="openai",
        model_id=args.model,
        generation_args=None,
        predicates_questions_mapping_path=str(
            MODEL_DIR / "static" / "predicates_questions_mapping.json"
        ),
        system_prompt_path=str(
            MODEL_DIR / "prompts" / "api_version" / "system_prompt.txt"
        ),
        user_prompt_path=str(MODEL_DIR / "prompts" / "api_version" / "user_prompt.txt"),
        ia_info_path=str(ia_info_path),
    )
    prompts = collect_prompts(executer)
    raw_prediction = executer()
    gold_ptns = normalize_ptns(row.get("ptns"))
    gold_slot_fillers = normalize_slot_map(row.get("slots"))
    raw_predicted_ptns = raw_prediction.get("ptn", [])
    predicted_ptns = normalize_ptns(raw_predicted_ptns)
    predicted_slot_fillers = raw_prediction.get("slot", {})
    predicted_slot_fillers_first = first_predicted_slots_by_ptn(raw_prediction)
    matched_ptns = sorted(gold_ptns & predicted_ptns)

    return {
        "ca_id": row.get("ca_id"),
        "ia_id": row.get("ia_id"),
        "ca_essay": row.get("ca_essay"),
        "prompts": prompts,
        "gold_ptns": sorted(gold_ptns),
        "gold_slot_fillers": gold_slot_fillers,
        "predicted_ptns_raw": raw_predicted_ptns,
        "predicted_ptns": sorted(predicted_ptns),
        "predicted_slot_fillers": predicted_slot_fillers,
        "predicted_slot_fillers_first": predicted_slot_fillers_first,
        "matched_ptns": matched_ptns,
        "correct": bool(matched_ptns),
        "raw_prediction": raw_prediction,
    }


def evaluate_slot_fillers(
    predictions: list[dict[str, Any]], args: argparse.Namespace
) -> dict[str, Any]:
    try:
        from bert_score import score as bert_score
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "bert_score is required for slot-filler evaluation. Install the "
            "bert-score package in the environment running this script."
        ) from exc

    comparisons: list[dict[str, Any]] = []
    candidates: list[str] = []
    references: list[str] = []

    for prediction_index, prediction in enumerate(predictions):
        ptn_scores: dict[str, dict[str, Any]] = {}
        for ptn in prediction.get("matched_ptns", []):
            ptn = int(ptn)
            predicted_slot = prediction.get("predicted_slot_fillers_first", {}).get(ptn, "")
            gold_slots = prediction.get("gold_slot_fillers", {}).get(ptn, [])
            ptn_key = str(ptn)
            ptn_scores[ptn_key] = {
                "predicted_slot": predicted_slot,
                "gold_slots": gold_slots,
                "bertscore_f1": 0.0,
            }
            if not predicted_slot or not gold_slots:
                continue
            for gold_slot in gold_slots:
                comparisons.append({
                    "prediction_index": prediction_index,
                    "ptn": ptn_key,
                    "gold_slot": gold_slot,
                })
                candidates.append(predicted_slot)
                references.append(gold_slot)
        prediction["slotfiller_scores_by_ptn"] = ptn_scores

    if comparisons:
        score_kwargs = {
            "cands": candidates,
            "refs": references,
            "lang": args.bertscore_lang,
            "rescale_with_baseline": args.bertscore_rescale,
        }
        if args.bertscore_model:
            score_kwargs["model_type"] = args.bertscore_model
        _, _, f1_scores = bert_score(**score_kwargs)
        for comparison, score_value in zip(comparisons, f1_scores.tolist()):
            prediction = predictions[comparison["prediction_index"]]
            ptn_score = prediction["slotfiller_scores_by_ptn"][comparison["ptn"]]
            current_score = ptn_score["bertscore_f1"]
            if score_value > current_score:
                ptn_score["bertscore_f1"] = float(score_value)
                ptn_score["best_matching_gold_slot"] = comparison["gold_slot"]

    instance_scores = []
    for prediction in predictions:
        ptn_scores = [
            item["bertscore_f1"]
            for item in prediction.get("slotfiller_scores_by_ptn", {}).values()
        ]
        instance_score = sum(ptn_scores) / len(ptn_scores) if ptn_scores else 0.0
        prediction["slotfiller_quality_score"] = instance_score
        instance_scores.append(instance_score)

    overall_score = sum(instance_scores) / len(instance_scores) if instance_scores else 0.0
    return {
        "overall_slotfiller_quality_score": overall_score,
        "total_instances": len(predictions),
        "bertscore_lang": args.bertscore_lang,
        "bertscore_model": args.bertscore_model,
        "bertscore_rescale": args.bertscore_rescale,
        "instance_scores": [
            {
                "ca_id": prediction.get("ca_id"),
                "ia_id": prediction.get("ia_id"),
                "matched_ptns": prediction.get("matched_ptns", []),
                "slotfiller_quality_score": prediction.get("slotfiller_quality_score", 0.0),
                "slotfiller_scores_by_ptn": prediction.get("slotfiller_scores_by_ptn", {}),
            }
            for prediction in predictions
        ],
    }


def ensure_slot_metric_dependencies() -> None:
    try:
        import bert_score  # noqa: F401
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "bert_score is required for slot-filler evaluation. Install the "
            "bert-score package before running this script."
        ) from exc


def evaluate(predictions: list[dict[str, Any]]) -> EvaluationResult:
    total = len(predictions)
    correct = sum(1 for item in predictions if item["correct"])
    recall = correct / total if total else 0.0
    return EvaluationResult(total=total, correct=correct, recall=recall)


def main() -> None:
    load_dotenv(REPO_DIR / "local.env")
    load_dotenv(BACKEND_DIR / ".env")

    args = parse_args()
    rows = load_jsonl(args.dataset, args.limit)

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to local.env, backend/.env, or the environment."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.instances_dir.mkdir(parents=True, exist_ok=True)
    args.questions_output.parent.mkdir(parents=True, exist_ok=True)
    args.slot_output.parent.mkdir(parents=True, exist_ok=True)
    ensure_slot_metric_dependencies()
    evaluation_ia_info_path = build_evaluation_ia_info(args.ia_info, args.output.parent)
    predictions: list[dict[str, Any]] = []
    questions_by_ia: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    try:
        with args.output.open("w", encoding="utf-8") as f:
            for index, row in enumerate(rows, start=1):
                print(
                    f"[{index}/{len(rows)}] running ca_id={row.get('ca_id')} "
                    f"ia_id={row.get('ia_id')}",
                    flush=True,
                )
                prediction = run_example(args, row, evaluation_ia_info_path)
                predictions.append(prediction)
                add_questions_for_instance(questions_by_ia, prediction)
                f.write(json.dumps(prediction, ensure_ascii=False) + "\n")
                f.flush()
                instance_path = (
                    args.instances_dir
                    / f"{index:04d}_{safe_filename(row.get('ca_id'))}.json"
                )
                with instance_path.open("w", encoding="utf-8") as instance_file:
                    json.dump(prediction, instance_file, ensure_ascii=False, indent=2)
                with args.questions_output.open(
                    "w", encoding="utf-8"
                ) as questions_file:
                    json.dump(
                        format_questions_by_ia(questions_by_ia),
                        questions_file,
                        ensure_ascii=False,
                        indent=2,
                    )
    finally:
        try:
            evaluation_ia_info_path.unlink()
        except FileNotFoundError:
            pass

    result = evaluate(predictions)
    slot_metrics = evaluate_slot_fillers(predictions, args)
    with args.slot_output.open("w", encoding="utf-8") as f:
        json.dump(slot_metrics, f, ensure_ascii=False, indent=2)
    with args.output.open("w", encoding="utf-8") as f:
        for prediction in predictions:
            f.write(json.dumps(prediction, ensure_ascii=False) + "\n")
    for index, prediction in enumerate(predictions, start=1):
        instance_path = (
            args.instances_dir
            / f"{index:04d}_{safe_filename(prediction.get('ca_id'))}.json"
        )
        with instance_path.open("w", encoding="utf-8") as instance_file:
            json.dump(prediction, instance_file, ensure_ascii=False, indent=2)

    print("\nCALSA+ performance")
    print(f"model: {args.model}")
    print(f"dataset: {args.dataset}")
    print(f"predictions: {args.output}")
    print(f"per-instance results: {args.instances_dir}")
    print(f"questions by IA: {args.questions_output}")
    print(f"slot-filler metrics: {args.slot_output}")
    print(f"any-label recall: {result.recall:.4f} ({result.correct}/{result.total})")
    print(
        "slot-filler quality: "
        f"{slot_metrics['overall_slotfiller_quality_score']:.4f}"
    )


if __name__ == "__main__":
    main()
