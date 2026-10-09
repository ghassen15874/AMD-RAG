#!/usr/bin/env python3
import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
import threading

OUTPUT_DIR = Path(os.environ.get("MC2_OUTPUT_DIR", "/app/output"))
INDEX_DIR = Path(os.environ.get("MC3_INDEX_DIR", "/app/index"))
SOCKET_PATH = "/tmp/mc3_daemon.sock"

def ensure_daemon():
    if not os.path.exists(SOCKET_PATH):
        print("Starting daemon...")
        # Since CMD runs app/daemon.py directly now, it might be running already.
        # But for queries in a new exec, if the daemon crashed, we can restart it.
        # Or wait, the instructions say:
        # "CMD ['python3', '/app/daemon.py']"
        # So the daemon is started by the container's CMD. 
        # But if it's not ready yet, we wait. If socket doesn't exist, we start it as fallback.
        subprocess.Popen([sys.executable, "/app/daemon.py"])
        # Wait for socket
        for _ in range(100):
            if os.path.exists(SOCKET_PATH):
                break
            time.sleep(0.1)

def send_request(payload, timeout=25.0):
    ensure_daemon()
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(SOCKET_PATH)
    client.sendall(json.dumps(payload).encode("utf-8"))
    
    data = b""
    while True:
        chunk = client.recv(65536)
        if not chunk:
            break
        data += chunk
        try:
            resp = json.loads(data.decode("utf-8"))
            client.close()
            return resp
        except json.JSONDecodeError:
            continue
    client.close()
    return json.loads(data.decode("utf-8"))

def index(corpus: Path) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    send_request({"action": "index", "corpus": str(corpus)}, timeout=600.0)

def answer(corpus: Path, query: str) -> tuple[str, list[str], float]:
    result = {"answer": "", "citations": [], "confidence": 0.0}
    
    def worker():
        nonlocal result
        try:
            resp = send_request({"action": "query", "corpus": str(corpus), "query": query}, timeout=23.0)
            if "answer" in resp and "citations" in resp:
                result = resp
        except Exception as e:
            print(f"Error querying daemon: {e}")
            
    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=24.0)
    
    return result.get("answer", ""), result.get("citations", []), result.get("confidence", 0.0)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=Path, help="build the index over this corpus, then exit")
    ap.add_argument("--corpus", type=Path, help="corpus root for a query")
    ap.add_argument("--query-id", help="output stem the harness assigns, e.g. query_01")
    ap.add_argument("--query", help="the question to answer")
    args = ap.parse_args()

    if args.index is not None:
        index(args.index)
        return 0

    if args.corpus is None or args.query is None or not args.query_id:
        ap.error("a query needs --corpus, --query-id and --query")

    try:
        text, citations, confidence = answer(args.corpus, args.query)
    except Exception as e:
        print(f"Watchdog / top-level error: {e}")
        text, citations, confidence = "", [], 0.0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / (args.query_id + "_output.json")
    out.write_text(
        json.dumps(
            {"answer": text, "citations": list(citations), "confidence": confidence},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
