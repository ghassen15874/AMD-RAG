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

def wait_for_daemon():
    if not os.path.exists(SOCKET_PATH):
        daemon_py = Path("/app/daemon.py") if Path("/app/daemon.py").is_file() else Path(__file__).parent / "daemon.py"
        if daemon_py.is_file():
            subprocess.Popen([sys.executable, str(daemon_py)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(600):
        if os.path.exists(SOCKET_PATH):
            try:
                # Try connecting to see if it's actually listening
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.connect(SOCKET_PATH)
                return
            except ConnectionRefusedError:
                pass
        time.sleep(0.1)
    print("Timeout waiting for daemon socket.", file=sys.stderr)

def send_request(payload, timeout=25.0):
    wait_for_daemon()
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
    resp = send_request({"action": "index", "corpus": str(corpus)}, timeout=600.0)
    if "error" in resp:
        print(f"Daemon error during indexing: {resp['error']}", file=sys.stderr)
        sys.exit(1)

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
