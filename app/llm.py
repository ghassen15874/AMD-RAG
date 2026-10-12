"""Unified Multimodal VLM reasoning & vision engine using Qwen2.5-VL.

Dev: Qwen2.5-VL-3B-Instruct (loaded with device_map="auto" for low-VRAM GPUs)
Prod: Qwen2.5-VL-7B-Instruct (strictly loaded with .to(device), NO device_map="auto", NO accelerate)
"""
import hashlib
import json
import os
import sys
import torch
from pathlib import Path
from PIL import Image
from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

if "/app" not in sys.path:
    sys.path.append("/app")

from device import get_device, get_dtype

_SEARCH_ROOTS = [
    Path(os.environ.get("MC3_MODELS_DIR", "models")),
    Path("models"),
    Path("/app/models"),
    Path(os.environ.get("HF_HOME", "/app/models")),
]


def _is_valid_dir(p: Path) -> bool:
    if not (p / "config.json").is_file():
        return False
    try:
        for f in p.iterdir():
            if f.suffix in [".safetensors", ".bin"] and not f.name.endswith(".json"):
                if f.stat().st_size > 10 * 1024 * 1024:
                    return True
    except OSError:
        pass
    return False


def _find_snapshot() -> str:
    profile = os.environ.get("MC3_PROFILE", "dev").lower()
    if profile == "prod":
        target_model = "models--Qwen--Qwen2.5-VL-7B-Instruct"
        for root in _SEARCH_ROOTS:
            for prefix in ["", "hub"]:
                base = root / prefix / target_model if prefix else root / target_model
                snap_dir = base / "snapshots"
                if snap_dir.is_dir():
                    for child in sorted(snap_dir.iterdir(), reverse=True):
                        if _is_valid_dir(child):
                            return str(child)
                if _is_valid_dir(base):
                    return str(base)
        raise FileNotFoundError(
            "Strict Model Selection Error: Production VLM weights for 'Qwen2.5-VL-7B-Instruct' "
            "were not found in /app/models! Automatic fallback is strictly disabled."
        )
    else:
        target_model = "models--Qwen--Qwen2.5-VL-3B-Instruct"
        for root in _SEARCH_ROOTS:
            for prefix in ["", "hub"]:
                base = root / prefix / target_model if prefix else root / target_model
                snap_dir = base / "snapshots"
                if snap_dir.is_dir():
                    for child in sorted(snap_dir.iterdir(), reverse=True):
                        if _is_valid_dir(child):
                            return str(child)
                if _is_valid_dir(base):
                    return str(base)
        raise FileNotFoundError(
            "Strict Model Selection Error: Development VLM weights for 'Qwen2.5-VL-3B-Instruct' "
            "were not found in /app/models! Automatic fallback is disabled."
        )


_vlm_engine = None


def get_vlm_engine():
    global _vlm_engine
    if _vlm_engine is None:
        _vlm_engine = LLMEngine()
    return _vlm_engine


class LLMEngine:
    """Unified Qwen2.5-VL engine for both vision parsing and textual reasoning."""

    SYSTEM_PROMPT = (
        "You are an expert technical assistant. You must answer the user's "
        "question based STRICTLY on the provided context documents.\n\n"
        "Rules:\n"
        "1. If the context does not contain the answer, reply EXACTLY:\n"
        '   No answer in the corpus: {"answer": "", "citations": [], "confidence": 0.0}\n'
        "2. Your answer value must be the bare value only without units or degree signs (e.g. write '94', not '94 C' or '94°C'; write '180', not '180s'). "
        "Qualifiers that are part of the value MUST stay (e.g. write 'Q3 FY27', not 'Q3'; write 'REV-C2', not 'C2').\n"
        "3. Citations rules:\n"
        "   - Return a JSON object with keys: 'answer', 'citations', 'confidence'.\n"
        "   - 'citations' must be a JSON list of strings containing exact file paths, e.g. [\"engineering/meridian_release_notes.txt\"].\n"
        "   - For multi-hop questions (e.g. Doc A logs an event/defect, Doc B provides the fix/part), cite ALL documents in the chain: [Doc A, Doc B]. For 3-hop chains, cite all 3: [Doc A, Doc B, Doc C].\n"
        "   - For single-hop questions, cite the document containing the answer value.\n"
        "   - Copy exact paths from 'Document: <path>' without '../' or './'.\n"
        "4. Return ONLY the JSON object — no prose, no markdown fences.\n"
        "5. If a document is marked WITHDRAWN or SUPERSEDED do NOT use it.\n"
    )

    def __init__(self):
        snapshot = _find_snapshot()
        device = get_device()
        dtype = get_dtype() or torch.float16
        is_prod = os.environ.get("MC3_PROFILE", "dev").lower() == "prod"

        print(f"Loading unified Qwen2.5-VL from {snapshot} (is_prod={is_prod}) ...", flush=True)
        self.processor = AutoProcessor.from_pretrained(
            snapshot, local_files_only=True, use_fast=False
        )

        import resource
        import time

        t0 = time.time()
        if is_prod:
            # Production: strictly loads with torch_dtype=torch.bfloat16 and .to(device), NO device_map="auto", NO accelerate
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                snapshot,
                torch_dtype=torch.bfloat16,
                low_cpu_mem_usage=False,
                local_files_only=True,
            ).to(device)
        else:
            # Development: device_map="auto" to allow offloading on small host GPU (e.g. 4GB RTX 3050)
            self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
                snapshot,
                torch_dtype=dtype,
                device_map="auto",
                local_files_only=True,
            )

        load_time = time.time() - t0
        peak_ram_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
        self.model.eval()
        print(
            f"Unified Qwen2.5-VL model loaded in {load_time:.2f}s | Peak CPU RAM: {peak_ram_mb:.1f} MB (dtype={self.model.dtype})",
            flush=True,
        )

    def _file_hash(self, path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def parse_image(self, path: str) -> list[dict]:
        """Extract text from an image using the VLM."""
        content_hash = self._file_hash(path)
        cache_file = Path(os.environ.get("MC3_INDEX_DIR", "/app/index")) / "vision_cache.json"
        cache = {}
        if cache_file.is_file():
            try:
                with open(cache_file, "r") as f:
                    cache = json.load(f)
                if content_hash in cache:
                    print(f"Loaded cached VLM output for {path} (hash: {content_hash[:12]}...)", flush=True)
                    return cache[content_hash]
            except Exception:
                pass

        image = Image.open(path).convert("RGB")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {
                        "type": "text",
                        "text": (
                            "Extract ALL text visible in this image verbatim. "
                            "Reproduce every label, heading, table cell, number "
                            "and unit exactly as shown. Do not summarise."
                        ),
                    },
                ],
            }
        ]

        text_prompt = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.processor(
            text=[text_prompt],
            images=[image],
            padding=True,
            return_tensors="pt",
        ).to(self.model.device)

        with torch.no_grad():
            generated_ids = self.model.generate(**inputs, max_new_tokens=1024)

        input_len = inputs["input_ids"].shape[1]
        output_ids = generated_ids[:, input_len:]
        output_text = self.processor.batch_decode(
            output_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0].strip()

        print(f"VLM output for {path}:\n{output_text}", flush=True)
        res = [{"text": output_text, "source": "image_vlm"}]
        try:
            cache[content_hash] = res
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w") as f:
                json.dump(cache, f)
        except Exception:
            pass
        return res

    def generate_answer(self, query: str, context_chunks: list[dict]) -> str:
        """Extractive QA text reasoning over context chunks."""
        context_text = "\n\n".join(
            f"Document: {c['file']}" + (" [STATUS: SUPERSEDED/WITHDRAWN - DO NOT CITE]" if c.get("superseded") else "") + f"\n{c['text']}"
            for c in context_chunks
        )

        user_prompt = (
            f"Context:\n{context_text}\n\n"
            f"Question: {query}\n\n"
            "Return the JSON object."
        )

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.processor(
            text=[text],
            padding=True,
            return_tensors="pt",
        ).to(self.model.device)

        with torch.no_grad():
            generated_ids = self.model.generate(
                **inputs, max_new_tokens=96
            )

        input_len = inputs["input_ids"].shape[1]
        output_ids = generated_ids[:, input_len:]
        response = self.processor.batch_decode(
            output_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0].strip()
        return response
