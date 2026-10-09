import os
import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForCausalLM

import sys
if "/app" not in sys.path:
    sys.path.append("/app")

from device import get_device, get_dtype

_vlm_processor = None
_vlm_model = None

def get_vlm():
    global _vlm_processor, _vlm_model
    if _vlm_model is None:
        model_id = "Qwen/Qwen2-VL-2B-Instruct"
        print("Loading VLM...", flush=True)
        device = get_device()
        dtype = get_dtype()
        _vlm_processor = AutoProcessor.from_pretrained(model_id)
        _vlm_model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=dtype if dtype else torch.float32, device_map=device
        )
        print("VLM loaded.", flush=True)
    return _vlm_processor, _vlm_model

def parse_image(path):
    chunks = []
    try:
        processor, model = get_vlm()
        image = Image.open(path).convert("RGB")
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": "Extract all text from this image. Specifically transcribe and format all tables, specifications, and key-value pairs clearly."},
                ],
            }
        ]
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        from qwen_vl_utils import process_vision_info
        image_inputs, video_inputs = process_vision_info(messages)
        
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(model.device)
        
        with torch.no_grad():
            generated_ids = model.generate(**inputs, max_new_tokens=512)
            
        generated_ids_trimmed = [
            out_ids[len(in_ids) :] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        
        output_text = processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        
        print(f"VLM output for {path}: {output_text}", flush=True)
        chunks.append({"text": output_text, "source": "image_vlm"})
        
    except Exception as e:
        print(f"Error parsing image {path}: {e}", flush=True)
        chunks.append({"text": f"Image at {path} (VLM failed)", "is_image": True})
    
    return chunks
