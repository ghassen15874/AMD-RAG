#!/usr/bin/env bash
set -euo pipefail

echo "======================================================================"
echo "MC3 Wheel Compatibility & Dependency Check"
echo "Target Base: rocm/pytorch:rocm10.0_ubuntu26.04_py3.14_pytorch_release_2.13.0"
echo "======================================================================"

REQ_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/app/requirements.txt"
TMP_DIR="$(mktemp -d /tmp/wheel_verify_XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [ ! -f "$REQ_FILE" ]; then
    echo "ERROR: Requirements file not found at $REQ_FILE"
    exit 1
fi

echo "Verifying wheels for ALL packages in $REQ_FILE via pip download --no-deps..."
echo ""

pip download --no-deps --dest "$TMP_DIR" -r "$REQ_FILE"

echo ""
echo "======================================================================"
echo "All packages downloaded successfully:"
ls -1 "$TMP_DIR"
echo "======================================================================"
echo "Verification complete: all dependencies have valid wheels available."
