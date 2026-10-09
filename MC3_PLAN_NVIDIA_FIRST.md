# AMD AI League – Match 3 (RAG): NVIDIA-first plan, then migrate to AMD ROCm

Date: 2026-10-09
This replaces the earlier plan's hardware assumption. You build and test on an NVIDIA GPU now, and port to the AMD ROCm base image later. The goal is that migration is a Dockerfile swap plus a re-test, not a rewrite.

> No one can promise a guaranteed 100%: the graded corpus and questions are hidden, and each question is all-or-nothing on answer plus exact citation set. This plan removes every known failure and gives you the tests to catch the rest.

---

## 0. Start from the starter kit (do not build from zero)

Use `mc3-starter-kit/` as the base of the repo:

- `starter/app/app.py` already has the contract plumbing (arguments, output path, whole-file JSON write). Keep it and fill in only `index()` and `answer()`.
- `starter/Dockerfile` and `starter/app/requirements.txt` become the two Dockerfiles below (the `sleep infinity` CMD becomes the daemon start).
- `mc3-corpus/` is the test corpus; run `./setup.sh` first to recreate the empty folder and the unreadable file.
- `sample-questions.json` is the automated test for 10 questions, with notes on each trap.
- `selfcheck.py` is the official pre-submission check; run it after every phase.
- `CONTRACT.md` and `README.txt` are authoritative.

Phase 0 below first builds the unchanged starter and records a baseline score.

---

## 1. What does not change (the contract)

| Item | Value |
|---|---|
| Index call | `python3 /app/app.py --index /app/corpus` (once, charged to the 10-minute startup budget) |
| Query call | `python3 /app/app.py --corpus /app/corpus --query-id query_01 --query "..."` (new process per question) |
| Output | `/app/output/<query-id>_output.json` with `answer` (string), `citations` (list), `confidence` (optional) |
| Scoring | 10 questions x 20 points. Correct answer and exact citation set, or zero |
| Refusal | `{"answer": "", "citations": [], "confidence": 0.0}` |
| Limits | Startup 10 min, 30 s per question, 10 min whole run, VRAM 1–48 GiB, image 60 GiB uncompressed |
| Final submission | Must build on `rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0`, ship weights, no network at grading, real GPU use |

The final graded image must be the AMD one. The NVIDIA image is only a development tool.

---

## 2. Portability rules (what makes the migration cheap)

PyTorch on ROCm exposes the GPU through the same `torch.cuda` API, so `.to("cuda")` and `torch.cuda.is_available()` work on both. The risk is in the libraries around torch.

**Do**

- Keep **all device logic in one file**, `device.py`: pick `cuda` if available, set dtype (bf16), report VRAM with `torch.cuda.mem_get_info()`. Never hardcode `"cuda:0"` elsewhere.
- Use PyTorch **SDPA attention** (`attn_implementation="sdpa"`), which runs on both.
- Use plain Hugging Face `transformers` for the VLM and `sentence-transformers` or plain `transformers` for embeddings.
- Keep **torch out of `requirements.txt`**. torch comes from the base image in the AMD build, and from the NVIDIA image (or pip) in the dev build.
- Install every other package with `pip install --no-deps` in the AMD build, and list the dependencies explicitly.
- Keep models as local files in `/models`, loaded with `local_files_only=True`.
- Pure-Python retrieval (`rank_bm25` or a small own BM25) and `numpy` cosine search for vectors. No GPU vector database is needed for a corpus this size.

**Do not (CUDA-only or fragile on ROCm)**

- `flash-attn`, `xformers`, `bitsandbytes`, `auto-gptq`, `triton` kernels you wrote, `nvidia-smi` calls, `torch.compile` tricks you have not tested on ROCm, `cupy`, TensorRT, or a CUDA-specific vLLM build.
- Any `import` that assumes NVIDIA at module import time.
- Quantization formats that need CUDA kernels. Use plain bf16 weights.

**vLLM:** optional and risky. Start with plain `transformers` generation. Only consider vLLM on ROCm after the whole pipeline works, and only if it installs without replacing torch.

---

## 3. Two Dockerfiles, one codebase

```
repo/
  app/                      # identical for both targets
    app.py                  # thin client
    daemon.py               # model + index holder
    device.py               # the only device-specific code
    ...
  docker/
    Dockerfile.nvidia       # dev image (NVIDIA)
    Dockerfile.amd          # final image (mandated ROCm base)
  models/                   # shipped weights (same files for both)
  tests/
```

### Dockerfile.nvidia (development)

```dockerfile
FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime   # any recent CUDA torch image
WORKDIR /app
COPY models/ /models/
COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app/ /app/
RUN mkdir -p /app/corpus /app/output /app/index
CMD ["python3", "/app/daemon.py"]
```

### Dockerfile.amd (final, mandated)

```dockerfile
FROM rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0
WORKDIR /app
COPY models/ /models/
COPY app/requirements.txt /app/requirements.txt
# --no-deps so pip cannot swap ROCm torch for a CUDA build
RUN pip install --no-cache-dir --no-deps -r /app/requirements.txt \
 && python3 -c "import torch; v=torch.__version__; print(v); assert 'rocm' in v"
COPY app/ /app/
RUN mkdir -p /app/corpus /app/output /app/index
CMD ["python3", "/app/daemon.py"]
```

Because the AMD base uses Python 3.14 and Ubuntu 26.04, some wheels may not exist for it. Find this out early (see section 7, "AMD dry run").

---

## 4. Architecture (same as before)

- `daemon.py` loads the VLM and embedder once, holds the index, listens on a unix socket.
- `app.py` is a thin client (about 50 ms). If the socket is missing, it starts the daemon and waits.
- `--index` asks the daemon to build the index, and also persists it to `/app/index`.
- A 25-second watchdog in the client writes an empty answer if the daemon has not replied, so the output file always exists.
- Output is written whole, never streamed. The container must keep running.

---

## 5. Parsing and indexing

Per-file `try/except`; log and skip failures; never abort the walk.

| Type | Approach |
|---|---|
| PDF | Per page, keep tables. If a page has almost no text, render and have the VLM read it. Detect encryption and skip |
| DOCX | Paragraphs, tables, headers, footers |
| XLSX | All sheets including hidden, merged cells expanded, each row as `header: value` with the sheet name |
| CSV | One chunk per row with headers |
| TXT, LOG | Line chunks with timestamps |
| PY | Whole-file chunks with line numbers, plus extracted constants and defaults (`ast`), and comments naming old values |
| PNG, JPG | VLM transcribes all text and pairs labels with values; keep the image path for query-time re-inspection |
| Unknown, no permission, encrypted | Skip and record |

- **Status tagging:** WITHDRAWN, SUPERSEDED, OBSOLETE, DEPRECATED in filename or text means `superseded`. Excluded unless the question asks about the old revision. Prefer the newest revision.
- **Identifier index:** extract ticket ids, error codes, part numbers, versions and revision codes by regex into an inverted index. This is what makes multi-hop work when ordinary search misses the second row.

---

## 6. Query pipeline

1. Hybrid retrieval: BM25 + embeddings + identifier index, fused with reciprocal rank fusion.
2. Image step: if images rank high or the question is about a label, pin or diagram, give the VLM the image itself with the question.
3. Bounded multi-hop loop (up to 3 hops) using identifiers found in earlier evidence. Record which file supplied each link.
4. Extractive grounding: the answer must appear in the evidence after the grader's normalization (uppercase, remove whitespace and `- . · _`). If not, refuse.
5. Strict refusal gate: refuse if retrieval is weak, or the evidence does not state this exact quantity for this exact product and condition.
6. Citations by ablation: remove each used file and re-ask. If the answer is unchanged and still grounded, drop the file.
7. Format: value only, with qualifiers (`Q3 FY27`, `REV-C2`).
8. Always write the JSON, even on exception or timeout.

Time budget per question: client under 0.2 s, retrieval under 1 s, reasoning under 6 s, ablation under 4 s, watchdog 25 s.

---

## 7. Phased plan (NVIDIA first, then AMD)

| Phase | Hardware | Goal | Done when |
|---|---|---|---|
| 0. Setup | NVIDIA | Unpack kit, run `setup.sh`, copy `starter/` and `mc3-corpus/` into the repo, build the unchanged starter and record the baseline with `selfcheck.py` and `sample-questions.json`, download model weights into `models/` | Starter builds on NVIDIA, GPU visible in container, baseline score recorded |
| 1. Skeleton | NVIDIA | Daemon, thin client, JSON writer, watchdog, `device.py`, refusal-only answers | `selfcheck.py` plumbing passes |
| 2. Parsers | NVIDIA | All types, status tagging, identifier index, trap handling | Index builds on sample corpus, no crash, skipped files logged |
| 3. Vision | NVIDIA | VLM transcription of images and scanned pages | Sample Q7 and Q8 answered |
| 4. Retrieval | NVIDIA | Hybrid retrieval + fusion | Right chunk in top results for all sample questions |
| 5. Reasoning | NVIDIA | Multi-hop, grounding, refusal gate, formatting | Sample Q1–Q10 correct answers |
| 6. Citations | NVIDIA | Ablation, status filtering | Sample Q1–Q10 exact citation sets |
| 7. Hardening | NVIDIA | Own adversarial corpora, timing, VRAM, `--network none`, `--cap-drop DAC_OVERRIDE` | Checklist in section 8 passes |
| 8. **AMD dry run** | CPU or any machine with Docker (no AMD GPU needed) | Build `Dockerfile.amd` and check the install works: every wheel installs with `--no-deps`, imports succeed, torch is still `+rocm` | Image builds, imports pass. (The base image is about 29 GiB; the GPU is not needed to build) |
| 9. **AMD migration** | AMD GPU (AMD Developer Cloud MI300X, or Navi 31) | Run the same tests on ROCm: fix any dtype, attention or library issue; re-measure timing and VRAM | Section 8 checklist passes on AMD |
| 10. Package | AMD | Final image, `--network none` test, selfcheck, size check | Submission-ready image under 60 GiB |

The AMD dry run (phase 8) is worth doing early, even before phase 4. It finds missing wheels for Python 3.14 while it is still cheap to change a dependency.

---

## 8. Validation checklist (run on NVIDIA, then again on AMD)

- [ ] `python3 selfcheck.py your-image:tag mc3-corpus` passes.
- [ ] All 10 sample questions: exact answer and exact citation set (Q9 needs two files, Q10 must be empty).
- [ ] 40–60 extra questions in the same shapes on modified corpora: changed values, swapped withdrawn revision, decoys, 3-hop chains, answers in multi-sheet files, table text and low-quality photos.
- [ ] Refusal tests: unanswerable questions, and a question answerable only from the encrypted file.
- [ ] `docker run --rm --network none --cap-drop DAC_OVERRIDE ...` with an empty subdirectory, a `chmod 000` file, an encrypted PDF and an unknown-type file.
- [ ] Index under 10 minutes including model load, on a corpus larger than the sample.
- [ ] Each query under 30 seconds as a fresh process; whole run under 10 minutes.
- [ ] VRAM peak between 1 and 48 GiB (`nvidia-smi` now, `rocm-smi` on AMD).
- [ ] torch still a ROCm build in the AMD image (`+rocm`).
- [ ] Container still running after all questions.
- [ ] `answer` and `citations` keys always present, even on a crash.
- [ ] Image under 60 GiB uncompressed.

---

## 9. Migration checklist (NVIDIA to AMD)

- [ ] Swap to `Dockerfile.amd`; do not copy CUDA torch into it.
- [ ] Reinstall dependencies with `--no-deps`; add any missing transitive packages explicitly.
- [ ] Confirm no CUDA-only import remains (`grep -R "flash_attn\|xformers\|bitsandbytes\|cupy\|nvidia" app/`).
- [ ] Confirm `device.py` selects the GPU on ROCm and that VRAM use is above 1 GiB during indexing and queries (real model on the GPU, no dummy buffer).
- [ ] Re-run the whole validation checklist and compare answers with the NVIDIA run. Differences point to numeric or library issues.
- [ ] Re-measure indexing and query timings; the AMD GPU may be faster or slower.
- [ ] If vLLM was used, confirm it still runs on ROCm without replacing torch; otherwise fall back to plain `transformers`.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| A package has no wheel for Python 3.14 or Ubuntu 26.04 | AMD dry run early (phase 8); prefer pure-Python packages |
| Code works on CUDA but fails on ROCm | Keep device logic in `device.py`, use SDPA, avoid CUDA-only libraries |
| Numeric differences change an answer | Re-run all tests on AMD; keep generation deterministic (greedy decoding) |
| VLM misreads small text in an image | Re-inspect the image at query time with the question; render at higher resolution |
| Ablation drops a truly needed file | Require the answer to remain grounded in the remaining evidence |
| Hidden question shapes not in the sample | Build varied tests yourself |
| Model too large for the image budget | About 30 GiB is available for weights; choose a 7–8B VLM in bf16 |

---

## 11. Honest limits

- None of this has been built or run yet; timings and VRAM must be measured on real hardware.
- "Never refused" and "100%" are goals to engineer toward, not guarantees.
- The AMD-specific steps (phases 8–10) can only be fully confirmed on an AMD GPU.
