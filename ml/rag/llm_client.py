import torch
from config.settings import get_settings
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline


class HuggingFaceLLM:
    def __init__(self):
        self.settings = get_settings()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.settings.HF_MODEL_ID,
            token=self.settings.HF_TOKEN
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            self.settings.HF_MODEL_ID,
            token=self.settings.HF_TOKEN,
            device_map="auto",
            torch_dtype=torch.float16
        )

        self.pipeline = pipeline(
            "text-generation",
            model=self.model,
            tokenizer=self.tokenizer,
            device=0 if self.device == "cuda" else -1
        )

    def generate(self, prompt: str, max_length: int = 512) -> str:
        """Générer une réponse"""
        outputs = self.pipeline(
            prompt,
            max_length=max_length,
            num_return_sequences=1,
            temperature=0.7,
            top_p=0.95,
            do_sample=True
        )
        return outputs[0]["generated_text"]
