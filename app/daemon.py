import json
import os
import socket
import sys
from pathlib import Path

# Add app directory to sys.path if not there
if "/app" not in sys.path:
    sys.path.append("/app")

from parsers.registry import is_superseded, extract_identifiers
from parsers.pdf_parser import parse_pdf
from parsers.docx_parser import parse_docx
from parsers.xlsx_parser import parse_xlsx
from parsers.csv_parser import parse_csv
from parsers.txt_parser import parse_txt
from parsers.py_parser import parse_py

SOCKET_PATH = "/tmp/mc3_daemon.sock"

INDEX_DATA = {
    "chunks": [],
    "identifiers": {}
}

def build_index(corpus_path):
    global INDEX_DATA
    INDEX_DATA = {"chunks": [], "identifiers": {}}
    
    corpus = Path(corpus_path)
    for root, dirs, files in os.walk(corpus):
        for file in files:
            full_path = Path(root) / file
            rel_path = full_path.relative_to(corpus).as_posix()
            
            ext = full_path.suffix.lower()
            chunks = []
            try:
                if ext == ".pdf":
                    chunks = parse_pdf(str(full_path))
                elif ext == ".docx":
                    chunks = parse_docx(str(full_path))
                elif ext == ".xlsx":
                    chunks = parse_xlsx(str(full_path))
                elif ext == ".csv":
                    chunks = parse_csv(str(full_path))
                elif ext in [".txt", ".log"]:
                    chunks = parse_txt(str(full_path))
                elif ext == ".py":
                    chunks = parse_py(str(full_path))
                elif ext in [".png", ".jpg", ".jpeg"]:
                    chunks = [{"text": f"Image at {rel_path}", "is_image": True}]
                else:
                    print(f"Skipping unknown file type: {rel_path}", flush=True)
                    continue
            except PermissionError:
                print(f"Permission denied: {rel_path}", flush=True)
                continue
            except Exception as e:
                print(f"Error processing {rel_path}: {e}", flush=True)
                continue
            
            file_content_for_tagging = "\n".join([c.get("text", "") for c in chunks])
            superseded = is_superseded(file, file_content_for_tagging)
            
            # Extract identifiers
            file_idents = extract_identifiers(file_content_for_tagging)
            for ident in file_idents:
                if ident not in INDEX_DATA["identifiers"]:
                    INDEX_DATA["identifiers"][ident] = set()
                INDEX_DATA["identifiers"][ident].add(rel_path)
                
            for chunk in chunks:
                chunk["file"] = rel_path
                chunk["superseded"] = superseded
                INDEX_DATA["chunks"].append(chunk)

    for k in INDEX_DATA["identifiers"]:
        INDEX_DATA["identifiers"][k] = list(INDEX_DATA["identifiers"][k])
        
    INDEX_DIR = Path(os.environ.get("MC3_INDEX_DIR", "/app/index"))
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(INDEX_DIR / "index.json", "w", encoding="utf-8") as f:
        json.dump(INDEX_DATA, f)
    
    print(f"Index built: {len(INDEX_DATA['chunks'])} chunks, {len(INDEX_DATA['identifiers'])} identifiers", flush=True)

def handle_index(payload):
    corpus_path = payload.get("corpus")
    build_index(corpus_path)
    return {"status": "ok"}

def handle_query(payload):
    corpus_path = payload.get("corpus")
    query = payload.get("query")
    return {"answer": "", "citations": [], "confidence": 0.0}

def serve():
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
    
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(16)
    print("Daemon listening on", SOCKET_PATH, flush=True)
    
    while True:
        conn, _ = server.accept()
        with conn:
            try:
                data = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
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
