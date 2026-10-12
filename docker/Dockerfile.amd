FROM rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0

WORKDIR /app

ENV HF_HOME=/app/models
ENV MC3_PROFILE=prod

COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --no-deps -r /app/requirements.txt \
 && python3 -c "import torch; v=torch.__version__; print('ROCm torch build verified:', v); assert 'rocm' in v, f'Expected ROCm torch, got {v}'" \
 && python3 -c "import transformers, tokenizers, safetensors, huggingface_hub, numpy, yaml, regex, tqdm, lxml, docx, openpyxl, pypdf, PIL; from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration; print('All core modules imported successfully.')"

COPY app/download_model.py /app/download_model.py
COPY app/verify_models.py /app/verify_models.py
RUN python3 /app/download_model.py \
 && python3 /app/verify_models.py

ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false MC3_REQUIRE_GPU=1

COPY app/ /app/
RUN mkdir -p /app/corpus /app/output /app/index

CMD ["python3", "/app/daemon.py"]
