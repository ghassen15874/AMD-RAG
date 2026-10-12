#!/usr/bin/env python3
"""
Run container evaluation for Phase 7 Requirement 4:
- Starts container with --network none --cap-drop DAC_OVERRIDE
- Runs index pass
- Invokes each question from sample-questions.json as a separate process
- Measures exact latency from process start to JSON written
"""
import json
import subprocess
import time
from pathlib import Path

CONTAINER_NAME = "mc3-phase7-eval"
IMAGE = "mc3-rag:test"
CORPUS_DIR = Path("mc3-corpus")
QUESTIONS_FILE = Path("sample-questions.json")

def run(cmd, timeout=300):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def main():
    print("=" * 70)
    print("Phase 7 Item 4: Real Container Per-Question Evaluation")
    print(f"Image: {IMAGE}")
    print("Security: --network none --cap-drop DAC_OVERRIDE")
    print("=" * 70)

    # 1. Cleanup any previous instance
    subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)

    # 2. Start container with --network none --cap-drop DAC_OVERRIDE
    print("\nStarting container...")
    start_cmd = [
        "docker", "run", "-d",
        "--network", "none",
        "--cap-drop", "DAC_OVERRIDE",
        "--name", CONTAINER_NAME,
        IMAGE
    ]
    res = run(start_cmd)
    if res.returncode != 0:
        print(f"Failed to start container: {res.stderr}")
        return

    try:
        # 3. Setup app code, corpus and output directory
        print("Preparing app code and corpus inside container...")
        run(["docker", "exec", CONTAINER_NAME, "mkdir", "-p", "/app/corpus", "/app/output", "/app/index"])
        run(["docker", "cp", "app/.", f"{CONTAINER_NAME}:/app/"])
        run(["docker", "exec", CONTAINER_NAME, "pkill", "-f", "daemon.py"])
        cp_res = run(["docker", "cp", f"{CORPUS_DIR}/.", f"{CONTAINER_NAME}:/app/corpus"])
        if cp_res.returncode != 0:
            print(f"Failed to copy corpus: {cp_res.stderr}")
            return

        # 4. Run index pass
        print("Running cold index pass...")
        t_index0 = time.time()
        idx_res = run(["docker", "exec", CONTAINER_NAME, "python3", "/app/app.py", "--index", "/app/corpus"], timeout=600)
        t_index = time.time() - t_index0
        print(f"Index pass complete in {t_index:.2f}s (Output: {idx_res.stdout.strip()})")

        # 5. Load questions
        with open(QUESTIONS_FILE) as f:
            q_data = json.load(f)
        queries = q_data.get("queries", [])

        print(f"\nEvaluating {len(queries)} questions (each as a fresh process)...")
        print("-" * 70)
        
        results = []
        for q in queries:
            qid = f"q{q['n']}"
            qtext = q["query"]
            expected_ans = q["expected_answer"]
            expected_cits = q["expected_citations"]

            # Measure latency from process start to JSON written
            t0 = time.time()
            proc = run([
                "docker", "exec", CONTAINER_NAME,
                "python3", "/app/app.py",
                "--corpus", "/app/corpus",
                "--query-id", qid,
                "--query", qtext
            ], timeout=60)
            latency = time.time() - t0

            # Read output JSON
            cat_res = run(["docker", "exec", CONTAINER_NAME, "cat", f"/app/output/{qid}_output.json"])
            out_json = {}
            if cat_res.returncode == 0 and cat_res.stdout.strip():
                try:
                    out_json = json.loads(cat_res.stdout)
                except Exception:
                    pass

            ans = out_json.get("answer", "")
            cits = out_json.get("citations", [])

            print(f"Q{q['n']} ({qid}):")
            print(f"  Latency:    {latency:.3f}s")
            print(f"  Answer:     {repr(ans)} (expected: {repr(expected_ans)})")
            print(f"  Citations:  {cits} (expected: {expected_cits})")
            if proc.returncode != 0:
                print(f"  STDERR:     {proc.stderr.strip()[:200]}")
            print()

            results.append({
                "n": q["n"],
                "query": qtext,
                "latency_s": round(latency, 3),
                "answer": ans,
                "expected_answer": expected_ans,
                "citations": cits,
                "expected_citations": expected_cits
            })

        avg_lat = sum(r["latency_s"] for r in results) / len(results)
        print("=" * 70)
        print(f"Mean Per-Question Latency: {avg_lat:.3f}s")
        print("=" * 70)

    finally:
        print("\nStopping container...")
        subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)

if __name__ == "__main__":
    main()
