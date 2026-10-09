import json
import os
import socket
import sys

SOCKET_PATH = "/tmp/mc3_daemon.sock"

def handle_index(payload):
    corpus_path = payload.get("corpus")
    # TODO: Build index and save to /app/index
    return {"status": "ok"}

def handle_query(payload):
    corpus_path = payload.get("corpus")
    query = payload.get("query")
    # For phase 1, refusal only
    return {"answer": "", "citations": [], "confidence": 0.0}

def serve():
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
    
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(16)
    print("Daemon listening on", SOCKET_PATH)
    
    while True:
        conn, _ = server.accept()
        with conn:
            try:
                # recv and parse the entire payload
                data = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                    # Since we do single request/response per connection, we can try to parse
                    try:
                        payload = json.loads(data.decode("utf-8"))
                        break
                    except json.JSONDecodeError:
                        continue
                
                action = payload.get("action")
                
                if action == "index":
                    result = handle_index(payload)
                elif action == "query":
                    result = handle_query(payload)
                else:
                    result = {"error": "unknown action"}
                    
                conn.sendall(json.dumps(result).encode("utf-8"))
            except Exception as e:
                err = {"error": str(e), "answer": "", "citations": [], "confidence": 0.0}
                conn.sendall(json.dumps(err).encode("utf-8"))

if __name__ == "__main__":
    serve()
