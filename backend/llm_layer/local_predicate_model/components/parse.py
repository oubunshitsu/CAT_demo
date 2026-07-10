import os
import torch
from transformers import (
    GenerationConfig,
    AutoModelForCausalLM,
    AutoTokenizer,
)
from dotenv import load_dotenv
from openai import OpenAI
import json


class CAParser:
    def __init__(self, provider, model_id, generation_args) -> None:
        if provider == "hf":
            self.parser = HFCAParser(model_id, generation_args)
        elif provider == "openai":
            self.parser = OpenAIParser(model_id)
        else:
            raise Exception(f"provider: {provider} not supported")

    def __call__(self, prompt):
        return self.parser(prompt)


class OpenAIParser:
    def __init__(self, model_id) -> None:
        self.model_id = model_id

        load_dotenv("../local.env")
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise Exception("api_key not found")

        self.client = OpenAI(api_key=api_key)

    def __call__(self, prompt):
        response = self.client.responses.create(
            model=self.model_id,
            input=prompt,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "ca_logic_analysis",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string"},
                            "answer": {"type": "string"},
                            "slot": {"type": "string"},
                        },
                        "required": ["reason", "answer", "slot"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
        )
        structured_output = json.loads(response.output_text)
        return structured_output


class HFCAParser:
    def __init__(self, model_id, generation_args) -> None:
        self.model_id = model_id
        self.device = "cuda"
        self.model = AutoModelForCausalLM.from_pretrained(model_id, device_map="cuda")
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)

        models_without_pad_token = [
            "meta-llama/Llama-3.1-8B-Instruct",
            "mistralai/Mistral-7B-Instruct-v0.3",
        ]
        if any(
            model_id == model_without_pad_token
            for model_without_pad_token in models_without_pad_token
        ):
            self.tokenizer.pad_token = self.tokenizer.eos_token

        self.generation_config = GenerationConfig(
            max_new_tokens=generation_args.max_new_tokens,
            do_sample=generation_args.do_sample,
            pad_token_id=self.tokenizer.pad_token_id,
            bos_token_id=self.tokenizer.bos_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
            temperature=generation_args.temperature,
            top_p=generation_args.top_p,
            top_k=generation_args.top_k,
            min_p=generation_args.min_p,
            repetition_penalty=generation_args.repetition_penalty,
        )

    def __call__(self, prompt):
        """
        Input: prompt
        Output: generated_text

        """
        # If the model is a instruction-tuned model
        if any(kw in self.model_id.lower() for kw in ["instruct", "chat", "gpt-oss"]):
            # conversation = [
            #     {"role": "system", "content": "You are a helpful assistant"},
            #     {"role": "user", "content": user_prompt},
            # ]
            prompt = self.tokenizer.apply_chat_template(
                prompt,
                continue_final_message=False,
                tokenize=False,
                add_generation_prompt=True,
            )
        # else:
        #     prompt = user_prompt

        prompt_inputs = self.tokenizer(
            text=prompt,
            return_tensors="pt",
            padding=True,
            padding_side="left",
            add_special_tokens=False,
        )
        # print(self.tokenizer.batch_decode(prompt_inputs["input_ids"])[0])
        # breakpoint()
        print(f"Input prompt length: {prompt_inputs['input_ids'].shape[1]}")
        prompt_ids, prompt_mask = (
            prompt_inputs["input_ids"].to(self.device),
            prompt_inputs["attention_mask"].to(self.device),
        )
        with torch.no_grad():
            prompt_completion_ids = self.model.generate(
                prompt_ids,
                attention_mask=prompt_mask,
                generation_config=self.generation_config,
            )
        # Compute prompt length and extract completion ids
        prompt_length = prompt_ids.size(1)
        prompt_ids = prompt_completion_ids[:, :prompt_length]
        completion_ids = prompt_completion_ids[:, prompt_length:]

        print(f"Generation length: {prompt_inputs['input_ids'].shape[1]}")

        completions_text = self.tokenizer.batch_decode(
            completion_ids, skip_special_tokens=True
        )[0]
        # breakpoint()

        # For reasoning models, extract the final answer, discard the thinking part
        # if any(kw in self.model_id.lower() for kw in ["gpt-oss"]):
        #     match = re.search(r"(?<=assistantfinal).*", completions_text, re.DOTALL)
        #     if match:
        #         completions_text = match.group(0)

        return completions_text
