#!/usr/bin/env python3
"""Download pinned model weights for offline inference into models directory.

Downloads:
- sentence-transformers/all-MiniLM-L6-v2 (revision: 1110a243fdf4706b3f48f1d95db1a4f5529b4d41)
- Qwen/Qwen2.5-VL-7B-Instruct (revision: cc594898137f460bfe9f0759e9844b3ce807cfb5)

Saves weights into the exact directory structure expected by HuggingFace snapshot loaders.
Strictly fails with exit code 1 if any .safetensors weight files are missing or incomplete.
"""
import os
import sys
from pathlib import Path
from huggingface_hub import snapshot_download

os.environ["HF_XET_HIGH_PERFORMANCE"] = "1"

PROJ_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = Path(
    os.environ.get("MC3_MODELS_DIR", os.environ.get("HF_HOME", str(PROJ_ROOT / "models")))
).resolve()
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Pinned models and revisions for production
MODELS = [
    (
        "sentence-transformers/all-MiniLM-L6-v2",
        "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        "Retrieval embedding model (~90 MB)",
    ),
    (
        "Qwen/Qwen2.5-VL-7B-Instruct",
        "cc594898137f460bfe9f0759e9844b3ce807cfb5",
        "Unified vision and reasoning VLM (~15 GB)",
    ),
]


def has_valid_safetensors(directory: Path) -> bool:
    """Return True if directory contains config.json and valid .safetensors files (>10MB)."""
    if not (directory / "config.json").is_file():
        return False
    safetensors = list(directory.glob("*.safetensors"))
    if not safetensors:
        return False
    return any(f.stat().st_size > 10 * 1024 * 1024 for f in safetensors)


def download_one(repo_id: str, rev: str, desc: str) -> bool:
    cache_name = f"models--{repo_id.replace('/', '--')}"
    snap_parent = MODELS_DIR / cache_name / "snapshots"
    target_dir = snap_parent / rev

    if target_dir.is_dir() and has_valid_safetensors(target_dir):
        print(f"  [ALREADY PRESENT] {repo_id} ({desc}) at {target_dir}")
        _ensure_main_symlink(snap_parent, rev)
        return True

    print(f"\n>>> Downloading {repo_id} ({desc}) [rev: {rev}] ...")
    print(f"    Target directory: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        snapshot_download(
            repo_id=repo_id,
            revision=rev,
            local_dir=str(target_dir),
            max_workers=8,
        )
        if not has_valid_safetensors(target_dir):
            print(
                f"  [FATAL ERROR] Download completed for {repo_id} but no valid .safetensors weights found in {target_dir}!",
                file=sys.stderr,
            )
            return False

        size_mb = sum(
            f.stat().st_size for f in target_dir.glob("**/*") if f.is_file()
        ) / (1024 * 1024)
        print(f"  [SUCCESS] {repo_id} downloaded and verified ({size_mb:.1f} MB total)")
        _ensure_main_symlink(snap_parent, rev)
        return True
    except Exception as e:
        print(f"  [FAILED] {repo_id}: {e}", file=sys.stderr)
        return False


def _ensure_main_symlink(snap_parent: Path, rev: str):
    main_dir = snap_parent / "main"
    if not main_dir.exists():
        try:
            main_dir.symlink_to(rev, target_is_directory=True)
        except OSError:
            pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Download model weights.")
    parser.add_argument("--minilm-only", action="store_true", help="Download only sentence-transformers/all-MiniLM-L6-v2")
    args = parser.parse_args()

    models_to_download = [MODELS[0]] if args.minilm_only else MODELS

    print("=" * 70)
    print("MC3 Model Downloader — Production Pinned Revisions")
    print(f"Target directory: {MODELS_DIR}")
    print("=" * 70)

    for repo_id, rev, desc in models_to_download:
        success = download_one(repo_id, rev, desc)
        if not success:
            print(
                f"\nFATAL: Model download / verification failed for {repo_id}. Aborting build.",
                file=sys.stderr,
            )
            sys.exit(1)

    print("\n" + "=" * 70)
    print(f"All {len(models_to_download)} selected production models downloaded and verified.")
    print("=" * 70)


if __name__ == "__main__":
    main()
