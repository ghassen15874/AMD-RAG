#!/usr/bin/env python3
"""Run the full MC3 evaluation against sample-questions.json.

Usage (from project root):
    python tests/run_eval.py [--corpus mc3-corpus] [--questions sample-questions.json]

This script runs the daemon in-process (no Docker required) and evaluates
every question, printing per-question pass/fail for answer and citations.
"""
import argparse
import json
import os
import sys
import time
import threading
from pathlib import Path

# Resolve project root
PROJ_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJ_ROOT / "app"

# Add app/ to path
sys.path.insert(0, str(APP_DIR))

# Point HF_HOME to local models
os.environ["HF_HOME"] = str(PROJ_ROOT / "models")
# Ensure we never hit the network
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"


def normalize_answer(text: str) -> str:
    """Normalize an answer for comparison: lowercase, strip whitespace/special chars."""
    import re
    return re.sub(r'[\s\-°]', '', str(text)).lower()


def answer_matches(actual: str, expected: str, aliases: list[str]) -> bool:
    """Check if actual answer matches expected or any alias."""
    if not expected and not actual:
        return True  # Both empty = correct refusal
    if not expected or not actual:
        return False
    norm_actual = normalize_answer(actual)
    norm_expected = normalize_answer(expected)
    if norm_actual == norm_expected:
        return True
    # Check if expected is contained in actual
    if norm_expected in norm_actual:
        return True
    for alias in aliases:
        if normalize_answer(alias) in norm_actual:
            return True
    return False


def citations_match(actual: list[str], expected: list[str]) -> tuple[bool, str]:
    """Check if citations match exactly."""
    actual_set = set(actual)
    expected_set = set(expected)
    if actual_set == expected_set:
        return True, "exact"
    missing = expected_set - actual_set
    extra = actual_set - expected_set
    details = []
    if missing:
        details.append(f"missing: {missing}")
    if extra:
        details.append(f"extra: {extra}")
    return False, "; ".join(details)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=PROJ_ROOT / "mc3-corpus")
    ap.add_argument("--questions", type=Path, default=PROJ_ROOT / "sample-questions.json")
    ap.add_argument("--index-dir", type=Path, default=PROJ_ROOT / "index_mount")
    ap.add_argument("--output-dir", type=Path, default=PROJ_ROOT / "eval_output")
    args = ap.parse_args()

    # Set environment vars that the app code expects
    os.environ["MC3_INDEX_DIR"] = str(args.index_dir)
    os.environ["MC2_OUTPUT_DIR"] = str(args.output_dir)
    args.index_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with open(args.questions) as f:
        data = json.load(f)

    queries = data["queries"]
    corpus = str(args.corpus)

    print("=" * 70)
    print("MC3 Evaluation Runner")
    print(f"Corpus: {corpus}")
    print(f"Questions: {len(queries)}")
    print("=" * 70)
    print()

    # Import the daemon modules directly
    print("Loading models...")
    t0 = time.time()

    from daemon import build_index, handle_query
    import daemon

    # Build the index
    print("\n--- INDEXING ---")
    build_index(corpus)

    # Initialize retriever
    from retriever import Retriever
    daemon.retriever = Retriever(str(args.index_dir))
    daemon.retriever.index_corpus(Path(args.index_dir) / "index.json")

    # Initialize LLM
    from llm import LLMEngine
    daemon.llm_engine = LLMEngine()

    load_time = time.time() - t0
    print(f"\nModels loaded + index built in {load_time:.1f}s\n")

    # Run each query
    print("--- EVALUATION ---\n")
    results = []
    total_correct_answer = 0
    total_correct_citations = 0

    for q in queries:
        n = q["n"]
        query_text = q["query"]
        expected_answer = q["expected_answer"]
        answer_aliases = q.get("answer_aliases", [])
        expected_citations = q["expected_citations"]
        category = q.get("category", "")
        unanswerable = q.get("unanswerable", False)

        print(f"Q{n}: {query_text}")
        print(f"  Category: {category}")

        t0 = time.time()
        try:
            result = handle_query({"corpus": corpus, "query": query_text})
        except Exception as e:
            result = {"answer": "", "citations": [], "confidence": 0.0, "error": str(e)}
        elapsed = time.time() - t0

        actual_answer = result.get("answer", "")
        actual_citations = result.get("citations", [])
        confidence = result.get("confidence", 0.0)

        ans_ok = answer_matches(actual_answer, expected_answer, answer_aliases)
        cit_ok, cit_detail = citations_match(actual_citations, expected_citations)

        if ans_ok:
            total_correct_answer += 1
        if cit_ok:
            total_correct_citations += 1

        status_ans = "✅" if ans_ok else "❌"
        status_cit = "✅" if cit_ok else "❌"

        print(f"  Answer:   {status_ans} got={repr(actual_answer)}, expected={repr(expected_answer)}")
        print(f"  Citation: {status_cit} got={actual_citations}, expected={expected_citations}")
        if not cit_ok:
            print(f"            {cit_detail}")
        print(f"  Confidence: {confidence}, Time: {elapsed:.1f}s")
        if result.get("error"):
            print(f"  ERROR: {result['error']}")
        print()

        results.append({
            "n": n,
            "query": query_text,
            "category": category,
            "expected_answer": expected_answer,
            "actual_answer": actual_answer,
            "answer_correct": ans_ok,
            "expected_citations": expected_citations,
            "actual_citations": actual_citations,
            "citations_correct": cit_ok,
            "confidence": confidence,
            "time_s": round(elapsed, 2),
        })

    # Summary
    print("=" * 70)
    print(f"ANSWERS:   {total_correct_answer}/{len(queries)} correct")
    print(f"CITATIONS: {total_correct_citations}/{len(queries)} correct")
    print(f"SCORE:     {total_correct_answer + total_correct_citations}/{len(queries) * 2}")
    print("=" * 70)

    # Save results
    out_file = args.output_dir / "eval_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed results saved to {out_file}")


if __name__ == "__main__":
    main()
