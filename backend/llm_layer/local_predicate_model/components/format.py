import json
import re
import logging

logger = logging.getLogger(__name__)


class OutputFormater:
    def __init__(self, provider) -> None:
        if provider == "hf":
            self.formater = HFOutputFormater()
        elif provider == "openai":
            self.formater = OpenAIOutputFormater()
        else:
            raise Exception(f"provider: {provider} not supported")

    def __call__(self, generated_text):
        return self.formater(generated_text)


class OpenAIOutputFormater:
    def __init__(self) -> None:
        pass

    def __call__(self, generated_text):
        results = {}
        regex_patterns = dict(
            zip(
                ["reason", "answer", "slot"],
                [
                    r"<think>(.*?)</think>",
                    r"<answer>(.*?)</answer>",
                    r"<slot>(.*?)</slot>",
                ],
            )
        )
        for key, pattern in regex_patterns.items():
            matched_strings = re.findall(pattern, generated_text[key])
            if len(matched_strings) > 0:
                # results[key] = matched_strings[0].lower()
                target_string = matched_strings[0].lower()
                if key == "slot":
                    # Change '['..']' to "['']"
                    if re.fullmatch(r"'['.*?']'", target_string):
                        target_string[0] = '"'
                        target_string[-1] = '"'
                    # breakpoint()
                    try:
                        target_list = eval(target_string)
                    except Exception:
                        pass
                    else:
                        # Only consider the first slotfiller,
                        # if the generation contains many
                        target_string = target_list[0]
                results[key] = target_string
            else:
                if key == "answer":
                    if "yes" in generated_text.lower():
                        results[key] = "yes"
                    elif "no" in generated_text.lower():
                        results[key] = "no"
        return results


class HFOutputFormater:
    def __init__(self) -> None:
        pass

    def __call__(self, generated_text):
        results = {}
        regex_patterns = dict(
            zip(
                ["evidence", "answer", "slot"],
                [
                    r"<think>(.*?)</think>",
                    r"<answer>(.*?)</answer>",
                    r"<slot>(.*?)</slot>",
                ],
            )
        )
        for key, pattern in regex_patterns.items():
            matched_strings = re.findall(pattern, generated_text)
            if len(matched_strings) > 0:
                # results[key] = matched_strings[0].lower()
                target_string = matched_strings[0].lower()
                if key == "slot":
                    # Change '['..']' to "['']"
                    if re.fullmatch(r"'['.*?']'", target_string):
                        target_string[0] = '"'
                        target_string[-1] = '"'
                    # breakpoint()
                    try:
                        target_list = eval(target_string)
                    except Exception:
                        pass
                    else:
                        # Only consider the first slotfiller,
                        # if the generation contains many
                        target_string = target_list[0]
                results[key] = target_string
            else:
                if key == "answer":
                    if "yes" in generated_text.lower():
                        results[key] = "yes"
                    elif "no" in generated_text.lower():
                        results[key] = "no"
        return results


class PromptFormater:
    def __init__(
        self,
        ia_id,
        ia_point_id,
        ca_essay,
        predicates_questions_mapping_path,
        system_prompt_path,
        user_prompt_path,
        ia_info_path,
    ):
        self.ia_id = ia_id
        self.ia_point_id = ia_point_id
        self.ca_essay = ca_essay
        with (
            open(predicates_questions_mapping_path, "r") as f1,
            open(system_prompt_path, "r") as f2,
            open(user_prompt_path, "r") as f3,
            open(ia_info_path, "r") as f4,
        ):
            self.predicate_questions = json.loads(f1.read())
            self.system_prompt = f2.read()
            self.user_prompt_template = f3.read()
            self.ia_info = json.loads(f4.read())

    def _first_point_id(self, points: dict | None) -> str | None:
        if not isinstance(points, dict) or not points:
            return None
        keys = list(points.keys())
        try:
            return str(sorted(keys, key=lambda k: int(k))[0])
        except Exception:
            return str(keys[0])

    def _point_data(self) -> dict:
        ia_entry = self.ia_info.get(self.ia_id, {})
        points = ia_entry.get("points") if isinstance(ia_entry, dict) else {}
        if not points:
            return ia_entry if isinstance(ia_entry, dict) else {}
        point_id = self.ia_point_id or self._first_point_id(points)
        if point_id is None:
            return {}
        return (points or {}).get(str(point_id), {}) or {}

    def __call__(self):
        point_data = self._point_data()
        for predicate, question in self.predicate_questions.items():
            # print(question)
            # logger.info(f"predicate: {predicate}")
            # logger.info(f"question templ: {question}")

            question = question.format(**point_data)

            # logger.info(f"question: {question}")

            user_prompt = self.user_prompt_template.format(
                question=question,
                ia_essay=point_data.get("essential_ia_logic", ""),
                ca_essay=self.ca_essay,
            )
            conversation = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            yield predicate, conversation


def results_df_format(results_df):
    """
    Format the final results DataFrame, each row contains feedback for one pattern
    """

    def _expand_results(results) -> str:
        if isinstance(results, dict):
            concat_strings_all = []
            for key, value in results.items():
                if isinstance(value, list):
                    concat_value_string = ""
                    for i, fdk in enumerate(value):
                        concat_value_string = concat_value_string + f"{i + 1}): {fdk}"
                        if i < len(value) - 1:
                            concat_value_string = concat_value_string + "\n"
                    value = concat_value_string

                concat_string_per_ptn = str(key) + ":\n" + value
                concat_strings_all.append(concat_string_per_ptn)
            concat_strings_all = "\n\n".join(concat_strings_all)
        elif isinstance(results, list):
            concat_strings_all = "\n\n".join(results)
        else:
            raise Exception("results must be either a dict or a list")
        return concat_strings_all

    for column_name in ["ptn_desc", "ptn_feedback", "predicate_feedback"]:
        results_df[column_name] = results_df[column_name].apply(_expand_results)

    return results_df
