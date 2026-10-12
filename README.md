# AMD AI League Match 3 (RAG) — Orrery Systems Submission

Production RAG solution for AMD AI League Match 3, built for offline containerized inference on AMD ROCm hardware.

---

## 1. System Architecture

```
[Corpus: PDF, DOCX, XLSX, CSV, LOG, PY, PNG, JPG]
                        │
                        ▼
   [Unified Multimodal Parsing & Vision Extraction]
          (OCR & diagrams parsed via Qwen2.5-VL)
                        │
                        ▼
      [Hybrid Retrieval Index: Dense + BM25]
      (all-MiniLM-L6-v2 embeddings + lexical)
                        │
                        ▼
        [Unified Qwen2.5-VL Reasoning Engine]
  (Bare-value extraction, qualifier preservation)
                        │
                        ▼
  [General Entity-Anchor & BFS Multi-Hop Resolution]
   (Decoy suppression, shortest-path chain tracing)
```

### Key Highlights
- **Unified Model Architecture**: Single `Qwen2.5-VL` model handles both visual transcription (multimodal diagrams, labels, pinouts) and textual reasoning QA. No separate or competing models.
- **Zero-Dependency Production Execution**: Production loads weights using native PyTorch `.to(device)` with `torch_dtype=torch.bfloat16`. `accelerate` is removed from production runtime entirely.
- **Strict Offline Compliance**: `ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 TOKENIZERS_PARALLELISM=false MC3_REQUIRE_GPU=1`. Weight files and safetensors verified at build time via `app/verify_models.py`.
- **Generalized Citation Tracing**: Entity anchor inference connects symptoms/telemetry to answer documents via identifier bipartite BFS, strictly ignoring coincidental number mentions in decoy memos.

---

## 2. Docker & Environment Hardening

* **Base Image**: `rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0`
* **Python Runtime**: Python 3.14. All 33 dependencies pinned in `app/requirements.txt` and verified installable with `--no-deps`.
* **Wheel Verification**: `scripts/check_wheels.sh` verifies `pip download --no-deps` for all 33 production dependencies.
* **Model Weight Verification**: `app/download_model.py` and `app/verify_models.py` guarantee presence and minimum byte size of `.safetensors` files during Docker image build.

---

## 3. Evaluation & Test Results

### A. Official 10 Sample Questions (`sample-questions.json`)
* **Answers Correct**: 10 / 10 (100%)
* **Citations Correct**: 10 / 10 (100%)
* **Total Score**: 20 / 20 (100%)

### B. Extended 52-Question Edge Case Suite (`tests/extra_questions.json`)
Evaluated across revision traps, multi-sheet Excel files, DOCX tables, image OCR, comment traps, encrypted refusals, 3-hop entity chains, and decoy value suppression:

| Category | Questions | Answers | Citations | Notes |
|:---|:---:|:---:|:---:|:---|
| Superseded & Deprecated Traps | 4 | 4 / 4 | 4 / 4 | Correctly selects latest valid revisions |
| Decoy Value & Zone Traps | 4 | 4 / 4 | 4 / 4 | Rejects misleading decoy parameters |
| Multi-hop Entity Identifier Chains | 4 | 4 / 4 | 4 / 4 | Resolves 2-hop and 3-hop chains |
| Multi-sheet Excel Workbooks | 4 | 4 / 4 | 4 / 4 | Inspects all sheets in workbook |
| DOCX Structured Tables | 4 | 4 / 4 | 4 / 4 | Extracts precise tabular cells |
| Vision Multimodal (PNG/JPG) | 4 | 4 / 4 | 4 / 4 | Verbatim OCR of labels, stamps, pins |
| Python Comment Traps | 4 | 4 / 4 | 4 / 4 | Avoids commented-out legacy constants |
| Encrypted & Missing Refusals | 8 | 8 / 8 | 8 / 8 | Returns empty answer and empty citations |
| Multi-source Corroboration | 1 | 1 / 1 | 1 / 1 | Cites both release notes & bug tracker |
| Unnamed Entity Multi-hop Chains | 3 | 3 / 3 | 3 / 3 | Traces logs without entity name |
| Decoy Memo Value Suppression | 7 | 7 / 7 | 7 / 7 | Ignores coincidental numbers in memos |
| Regression Baselines | 5 | 5 / 5 | 5 / 5 | Validates consistent outputs |
| **TOTAL** | **52** | **52 / 52** | **52 / 52** | **100% Accuracy on Answers & Citations** |

## 4. Deployment & Target Platform

- **Platform Target**: AMD Instinct / ROCm 10.0 (`rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0`).
- **Container Build**: Fully offline, standalone image build with automated safetensors integrity checks.
- **Inference Runtime**: Complies strictly with the competition contract (`/index` cold build + `/query` per-question execution).
- **Validation**: 100% pass rate on official sample questions (10/10) and the extended stress-test suite (52/52).
