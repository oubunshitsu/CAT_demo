from llm_layer.local_predicate_model.components.format import (
    OutputFormater,
    PromptFormater,
)
from tqdm import tqdm
from llm_layer.local_predicate_model.components.parse import CAParser
from llm_layer.local_predicate_model.components.utils import InstancePtnAggregator
import logging

logger = logging.getLogger(__name__)


class Executer:
    """
    Takes in a CA, outputs a list of feedback
    """

    def __init__(
        self,
        ia_id,
        ia_point_id,
        ca_essay,
        provider,
        model_id,
        generation_args,
        predicates_questions_mapping_path,
        system_prompt_path,
        user_prompt_path,
        ia_info_path,
    ):
        self.ia_id = ia_id
        # Takes in either a list of conversation or a text prompt (for non-instruct models)
        self.ca_parser = CAParser(
            provider=provider,
            model_id=model_id,
            generation_args=generation_args,
        )
        self.output_formater = OutputFormater(provider)
        self.prompt_formater = PromptFormater(
            ia_id,
            ia_point_id,
            ca_essay,
            predicates_questions_mapping_path,
            system_prompt_path,
            user_prompt_path,
            ia_info_path,
        )
        self.ptn_aggregator = InstancePtnAggregator()

    def __call__(
        self,
    ):
        predicate_results = {}
        # Answer question associated with each predicate
        for predicate, conversation in tqdm(self.prompt_formater(), total=13):
            generated_text = self.ca_parser(conversation)
            formated_outputs = self.output_formater(generated_text)
            predicate_results[predicate] = formated_outputs

            # logger.info(f"generated_text: {generated_text}")
            # logger.info(f"formated_outputs: {formated_outputs}")

            logger.info({
                "predicate": predicate,
                "conversation": conversation,
                "generated_text": generated_text,
                "formated_outputs": formated_outputs,
            })
            # logger.info("\n\n")
            # breakpoint()

        # {'ptn': [9, 10], 'slot': {9: ['every avenue to correct potential mistakes has been explored and exploited'],.....}
        yes_predicates, ptn_results = self.ptn_aggregator(predicate_results)
        # breakpoint()

        return ptn_results
