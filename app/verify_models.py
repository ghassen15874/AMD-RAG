#!/usr/bin/env python3
"""Verify that required model weights (.safetensors) exist and are non-empty.

Used during Docker build to fail early if models were not downloaded correctly.
"""
import argparse
import os
import sys
from pathlib import Path

DEFAULT_MODELS = [
    "models--sentence-transformers--all-MiniLM-L6-v2",
    "models--Qwen--Qwen2.5-VL-7B-Instruct",
]


def verify_models(models_dir: Path, expected_models: list[str]) -> bool:
    print(f"Verifying model safetensors in: {models_dir}")
    if not models_dir.exists():
        print(f"FATAL: Models directory {models_dir} does not exist!", file=sys.stderr)
        return False

    all_ok = True
    for model_name in expected_models:
        model_path = models_dir / model_name
        if not model_path.exists():
            print(f"FATAL: Model folder {model_name} not found in {models_dir}!", file=sys.stderr)
            all_ok = False
            continue

        safetensors_files = list(model_path.glob("**/*.safetensors"))
        if not safetensors_files:
            print(f"FATAL: No .safetensors files found for {model_name} in {model_path}!", file=sys.stderr)
            all_ok = False
            continue

        total_size_mb = sum(f.stat().st_size for f in safetensors_files) / (1024 * 1024)
        if total_size_mb < 5.0:
            print(f"FATAL: .safetensors files for {model_name} are suspiciously small ({total_size_mb:.2f} MB)!", file=sys.stderr)
            all_ok = False
            continue

        print(f"  [OK] {model_name}: {len(safetensors_files)} safetensors file(s) ({total_size_mb:.1f} MB total)")

    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Verify downloaded safetensors models.")
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path(os.environ.get("MC3_MODELS_DIR", os.environ.get("HF_HOME", "/app/models"))),
        help="Path to models directory (default: $MC3_MODELS_DIR, $HF_HOME, or /app/models)",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="List of model folder names to check (defaults to production models)",
    )
    args = parser.parse_args()

    models_to_check = args.models if args.models else DEFAULT_MODELS
    if not verify_models(args.models_dir, models_to_check):
        sys.exit(1)

    print("All required models verified successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()
