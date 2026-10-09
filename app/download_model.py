import os
from transformers import AutoProcessor, AutoModelForCausalLM

os.environ["HF_HOME"] = "/app/models"

model_id = "Qwen/Qwen2-VL-2B-Instruct"
print(f"Downloading {model_id}...")
AutoProcessor.from_pretrained(model_id)
AutoModelForCausalLM.from_pretrained(model_id)
print("Download complete.")
