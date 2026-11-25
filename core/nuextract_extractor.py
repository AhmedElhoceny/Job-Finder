import json
import logging
from threading import Lock
from typing import Optional

from core.models.nuextract_schema import NuExtractResumeData

logger = logging.getLogger(__name__)

NUEXTRACT_BASE_MODEL = "numind/NuExtract-tiny-v1.5"
NUEXTRACT_ADAPTER_MODEL = "nimendraai/NuExtract-tiny-Resume-Data-Extractor"

TEMPLATE = json.dumps(
    {
        "name": "",
        "email": "",
        "phone": "",
        "website": "",
        "skills": [""],
        "experience": [{"title": "", "company": "", "duration": ""}],
        "education": [{"degree": "", "institution": "", "year": ""}],
        "other_details": [""],
    },
    indent=4,
)


def extract_first_json(text: str) -> str:
    """Extracts the first valid JSON block using brace-counting to avoid trailing token errors."""
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if start is None:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                return text[start : i + 1]
    return text


class NuExtractResumeExtractor:
    """Extracts structured resume facts using Hugging Face's nimendraai/NuExtract-tiny-Resume-Data-Extractor."""

    _instance: Optional["NuExtractResumeExtractor"] = None
    _lock: Lock = Lock()

    def __init__(
        self,
        base_model_name: str = NUEXTRACT_BASE_MODEL,
        adapter_model_name: str = NUEXTRACT_ADAPTER_MODEL,
    ):
        self.base_model_name = base_model_name
        self.adapter_model_name = adapter_model_name
        self.tokenizer = None
        self.model = None
        self._is_loaded = False
        self._load_lock = Lock()

    def load_model(self):
        """Loads tokenizer, base model and fine-tuned LoRA weights."""
        with self._load_lock:
            if self._is_loaded:
                return

            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from peft import PeftModel

            logger.info(f"Loading NuExtract tokenizer from '{self.base_model_name}'...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.base_model_name,
                trust_remote_code=True,
            )

            logger.info(f"Loading NuExtract base model from '{self.base_model_name}'...")
            base_model = AutoModelForCausalLM.from_pretrained(
                self.base_model_name,
                dtype=torch.float32,
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            ).eval()

            logger.info(f"Applying LoRA adapter '{self.adapter_model_name}'...")
            self.model = PeftModel.from_pretrained(
                base_model,
                self.adapter_model_name,
            ).eval()

            self._is_loaded = True
            logger.info("NuExtract-tiny-Resume-Data-Extractor successfully initialized!")

    def extract(self, resume_text: str, max_tokens: int = 512) -> NuExtractResumeData:
        """Extracts structured resume data from raw text."""
        import torch

        if not self._is_loaded:
            self.load_model()

        prompt = (
            "<|input|>\n"
            f"### Template:\n{TEMPLATE}\n"
            f"### Text:\n{resume_text.strip()}\n\n"
            "<|output|>"
        )

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=2048,
        )

        with torch.no_grad():
            out = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                do_sample=False,
            )

        decoded = self.tokenizer.decode(out[0], skip_special_tokens=True)
        raw_output = decoded.split("<|output|>")[-1].strip()
        json_str = extract_first_json(raw_output)

        try:
            data = json.loads(json_str)
            # Filter out empty placeholder strings
            if isinstance(data.get("skills"), list):
                data["skills"] = [s for s in data["skills"] if s and s.strip()]
            if isinstance(data.get("other_details"), list):
                data["other_details"] = [o for o in data["other_details"] if o and o.strip()]
            return NuExtractResumeData.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to parse NuExtract output as valid JSON: {e}. Raw: {raw_output[:200]}")
            return NuExtractResumeData()


def get_extractor() -> NuExtractResumeExtractor:
    """Singleton getter for the extractor to avoid re-loading weights in memory."""
    if NuExtractResumeExtractor._instance is None:
        with NuExtractResumeExtractor._lock:
            if NuExtractResumeExtractor._instance is None:
                NuExtractResumeExtractor._instance = NuExtractResumeExtractor()
    return NuExtractResumeExtractor._instance
