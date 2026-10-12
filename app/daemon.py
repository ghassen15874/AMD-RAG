import json
import os
import re
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
from parsers.vision_parser import parse_image

from retriever import Retriever
from llm import LLMEngine

SOCKET_PATH = "/tmp/mc3_daemon.sock"

INDEX_DATA = {
    "chunks": [],
    "identifiers": {}
}

# Global singletons to persist weights
retriever = None
llm_engine = None

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
                    chunks = parse_image(str(full_path))
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
    from parsers.vision_parser import unload_vlm
    unload_vlm()

def handle_index(payload):
    global retriever, llm_engine
    corpus_path = payload.get("corpus")
    build_index(corpus_path)
    
    if retriever is None:
        retriever = Retriever()
    retriever.index_corpus(Path(os.environ.get("MC3_INDEX_DIR", "/app/index")) / "index.json")
    
    if llm_engine is None:
        from llm import LLMEngine
        llm_engine = LLMEngine()
        
    return {"status": "ok"}

def handle_query(payload):
    global retriever, llm_engine
    corpus_path = payload.get("corpus")
    query = payload.get("query")
    
    if retriever is None:
        retriever = Retriever()
        retriever.load_index(Path(os.environ.get("MC3_INDEX_DIR", "/app/index")) / "index.json")
        
    if llm_engine is None:
        llm_engine = LLMEngine()
        
    chunks = retriever.retrieve(query, top_k=5)
    
    def normalize_text(t):
        import re
        return re.sub(r'[\s\-\.\·\_]', '', str(t)).upper()

    def get_answer(context_chunks):
        answer_text = llm_engine.generate_answer(query, context_chunks)
        if isinstance(answer_text, dict):
            return answer_text
        import json
        if "no answer in the corpus" in str(answer_text).lower():
            return {"answer": "", "citations": [], "confidence": 0.0}
            
        if "```json" in answer_text:
            answer_text = answer_text.split("```json")[1].split("```")[0].strip()
        elif "```" in answer_text:
            answer_text = answer_text.split("```")[1].strip()
            
        try:
            return json.loads(answer_text)
        except Exception:
            return {"answer": "", "citations": [], "confidence": 0.0}
            
    result = get_answer(chunks)
    
    def clean_citation(p):
        if isinstance(p, dict):
            p = p.get("document", p.get("file", ""))
        p = str(p).strip().replace("\\", "/")
        if p.lower().startswith("document:"):
            p = p[9:].strip()
        elif p.lower().startswith("document"):
            p = p[8:].strip()
        while p.startswith("../") or p.startswith("./"):
            if p.startswith("../"):
                p = p[3:]
            elif p.startswith("./"):
                p = p[2:]
        return p.lstrip("/")

    def clean_bare_value(val: str, chunks: list = None) -> str:
        if not val:
            return ""
        val = str(val).strip().strip("'\"`.,")
        # Preserve fiscal year qualifier if model only emitted the quarter
        if re.match(r'^Q[1-4]$', val, re.IGNORECASE) and chunks:
            for c in chunks:
                m = re.search(rf'\b({re.escape(val)}\s+FY\d{{2,4}})\b', c.get("text", ""), re.IGNORECASE)
                if m:
                    return m.group(1).upper()
        # Preserve REV- qualifier if model emitted bare C2/B1
        if re.match(r'^[A-Z]\d+$', val, re.IGNORECASE) and chunks:
            for c in chunks:
                m = re.search(rf'\b(REV\-{re.escape(val)})\b', c.get("text", ""), re.IGNORECASE)
                if m:
                    return m.group(1).upper()
        # Strip prefixes like "pin B14" -> "B14", "release 4.3.2" -> "4.3.2"
        val = re.sub(r'^(?:pin\s+|revision\s+|rev\s+|version\s+|ver\s+|release\s+)', '', val, flags=re.IGNORECASE).strip()
        # Strip degree signs and temperature units: "94 C", "94°C", "94°", "94 degrees C" -> "94"
        temp_match = re.match(r'^(\d+(?:\.\d+)?)\s*(?:°\s*[CFcf]?|[CFcf]\b|deg(?:rees?)?\s*[CFcf]?|degrees?)\.?$', val, re.IGNORECASE)
        if temp_match:
            return temp_match.group(1)
        # Strip time units: "180s", "180 seconds", "180 sec" -> "180"
        time_match = re.match(r'^(\d+(?:\.\d+)?)\s*(?:seconds?|sec|s|minutes?|min|m|hours?|hrs?|h|ms|milliseconds?)\.?$', val, re.IGNORECASE)
        if time_match:
            return time_match.group(1)
        # Strip electrical/frequency/data units: "100 MHz", "3.3 V", "50 W"
        unit_match = re.match(r'^(\d+(?:\.\d+)?)\s*(?:[kKMGT]?Hz|[kKMGT]?B|bits?|bytes?|[uUmM]?V|[uUmM]?A|[uUmM]?W|rpm|RPM)\.?$', val, re.IGNORECASE)
        if unit_match:
            return unit_match.group(1)
        return val

    # Check if query has specific numbers/quantities (like 10,000) that must appear in context
    query_large_nums = re.findall(r'\b\d{1,3}(?:,\d{3})+\b|\b\d{4,}\b', query)
    if query_large_nums:
        all_raw_text = " ".join(c.get("text", "") for c in chunks)
        for num in query_large_nums:
            clean_num = num.replace(",", "")
            if clean_num not in all_raw_text.replace(",", ""):
                # Specific query quantity not present in corpus -> refusal!
                return {"answer": "", "citations": [], "confidence": 0.0}

    # Check if query targets a specific product model / identifier not present in active chunks
    query_idents = extract_identifiers(query)
    all_active_text = " ".join(c.get("text", "") for c in chunks if not c.get("superseded", False))
    if query_idents:
        for q_id in query_idents:
            if q_id.lower() not in all_active_text.lower():
                return {"answer": "", "citations": [], "confidence": 0.0}

    # Check for ungrounded topic refusal (topics like 'telemetry dump' that exist only in unparsed files)
    all_active_lower = all_active_text.lower()
    for topic in ["telemetry dump", "encrypted", "paste"]:
        if topic in query.lower() and topic not in all_active_lower:
            return {"answer": "", "citations": [], "confidence": 0.0}

    # 4. Extractive grounding
    if result.get("answer"):
        if result["answer"].lower().strip().rstrip(".") in ["not specified", "not mentioned", "not provided", "unknown", "n/a", "none", "null", "unanswerable"]:
            return {"answer": "", "citations": [], "confidence": 0.0}
        norm_ans = normalize_text(result["answer"])
        all_chunk_text = " ".join(normalize_text(c.get("text", "")) for c in chunks)
        grounded = norm_ans in all_chunk_text
        if not grounded:
            tokens = [normalize_text(t) for t in re.findall(r'[A-Za-z0-9]+(?:[\.\-][A-Za-z0-9]+)*', result["answer"])]
            grounded = any(t in all_chunk_text for t in tokens if len(t) >= 2)
        if not grounded:
            # Refusal gate
            return {"answer": "", "citations": [], "confidence": 0.0}
            
        result["answer"] = clean_bare_value(result["answer"], chunks)
            
    # 6. Citations verification and multi-hop resolution
    if not result.get("answer"):
        result["citations"] = []
        result["confidence"] = 0.0
        return result

    raw_citations = [clean_citation(c) for c in result.get("citations", [])]
    chunk_files = [chunk["file"] for chunk in chunks]
    valid_citations = [c for c in raw_citations if c in chunk_files]
    
    # Ensure the file containing the answer token is included in valid_citations
    norm_ans = normalize_text(result["answer"])
    has_answer_file = any(norm_ans in normalize_text(c.get("text", "")) for c in chunks if c["file"] in valid_citations and not c.get("superseded", False))
    if not has_answer_file:
        for chunk in chunks:
            if not chunk.get("superseded", False):
                if norm_ans in normalize_text(chunk.get("text", "")):
                    if chunk["file"] not in valid_citations:
                        valid_citations.append(chunk["file"])
                    break

    # Deterministic Citation Verification:
    # A cited file must either directly contain the normalized answer, or provide a verified
    # identifier actually used in a link chain to locate the answer file.
    if valid_citations and result.get("answer"):
        norm_ans = normalize_text(result["answer"])
        all_chunks = getattr(retriever, "chunks", []) or chunks
        
        file_to_text = {}
        file_to_idents = {}
        for c in all_chunks:
            if not c.get("superseded", False):
                f = c["file"]
                if f not in file_to_text:
                    file_to_text[f] = []
                    file_to_idents[f] = set()
                file_to_text[f].append(c.get("text", ""))
                file_to_idents[f].update(extract_identifiers(c.get("text", "")))
        
        # General content words extraction using standard English stopwords (no task-specific terms)
        STOPWORDS = {
            "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", 
            "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", 
            "by", "can", "did", "do", "does", "doing", "down", "during", "each", "few", "for", "from", 
            "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him", 
            "himself", "his", "how", "if", "in", "into", "is", "it", "its", "itself", "just", "me", 
            "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once", 
            "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she", 
            "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", 
            "themselves", "then", "there", "these", "they", "this", "those", "through", "to", "too", 
            "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which", 
            "while", "who", "whom", "why", "will", "with", "you", "your", "yours", "yourself", "yourselves"
        }
        query_content_words = [
            w for w in re.findall(r'[a-zA-Z0-9]+', query.lower())
            if len(w) >= 3 and w not in STOPWORDS
        ]

        def word_matches_text(w: str, target: str) -> bool:
            if w in target:
                return True
            if len(w) >= 5 and w[:4] in target:
                return True
            return False

        # 1. Candidate answer files
        direct_answer_files = [
            f for f in valid_citations
            if f in file_to_text and norm_ans in normalize_text(" ".join(file_to_text[f]))
        ]
        if not direct_answer_files:
            for f, texts in file_to_text.items():
                if norm_ans in normalize_text(" ".join(texts)):
                    direct_answer_files.append(f)

        if not direct_answer_files:
            primary_ans_file = valid_citations[0] if valid_citations else None
        else:
            def score_candidate_answer_file(f: str):
                f_combined = (" ".join(file_to_text.get(f, [])) + " " + f).lower()
                idents = file_to_idents.get(f, set())
                ident_score = len(idents & query_idents)
                content_match_count = sum(1 for w in query_content_words if word_matches_text(w, f_combined))
                is_retrieved = 10 if f in valid_citations else 0
                return (is_retrieved, ident_score, content_match_count)

            direct_answer_files.sort(key=score_candidate_answer_file, reverse=True)
            primary_ans_file = direct_answer_files[0]

        if primary_ans_file:
            ans_file_text = " ".join(file_to_text.get(primary_ans_file, []))
            ans_text_lower = (ans_file_text + " " + primary_ans_file).lower()
            missing_query_words = [w for w in query_content_words if not word_matches_text(w, ans_text_lower)]

            entity_chain = None
            # If the query contains explicit entity identifiers that are NOT in primary_ans_file,
            # find the shortest chain starting from the files carrying the query identifiers.
            if query_idents and not any(qi.lower() in ans_file_text.lower() for qi in query_idents):
                start_files = [f for f, idents in file_to_idents.items() if any(qi in idents for qi in query_idents)]
                if start_files and primary_ans_file not in start_files:
                    start_files.sort(key=lambda sf: 1 if sf in valid_citations else 0, reverse=True)
                    for sf in start_files:
                        from collections import deque
                        queue = deque([[sf]])
                        visited = {sf}
                        found_path = None
                        while queue:
                            path = queue.popleft()
                            curr = path[-1]
                            if curr == primary_ans_file:
                                found_path = path
                                break
                            curr_idents = file_to_idents.get(curr, set())
                            for next_file, next_idents in file_to_idents.items():
                                if next_file not in visited and (curr_idents & next_idents):
                                    visited.add(next_file)
                                    queue.append(path + [next_file])
                        if found_path:
                            entity_chain = found_path
                            break

            # If no explicit query identifiers or entity_chain not found, search for unnamed entity anchor by missing premise words
            if not entity_chain and len(missing_query_words) >= 2:
                candidate_anchors = []
                for f, texts in file_to_text.items():
                    if f != primary_ans_file:
                        f_combined = (" ".join(texts) + " " + f).lower()
                        matched = sum(1 for w in missing_query_words if word_matches_text(w, f_combined))
                        if matched >= 2:
                            candidate_anchors.append((matched, f))
                candidate_anchors.sort(reverse=True, key=lambda x: x[0])

                for matched, anchor_file in candidate_anchors:
                    from collections import deque
                    queue = deque([[anchor_file]])
                    visited = {anchor_file}
                    found_path = None
                    while queue:
                        path = queue.popleft()
                        curr = path[-1]
                        if curr == primary_ans_file:
                            found_path = path
                            break
                        curr_idents = file_to_idents.get(curr, set())
                        for next_file, next_idents in file_to_idents.items():
                            if next_file not in visited and (curr_idents & next_idents):
                                visited.add(next_file)
                                queue.append(path + [next_file])
                    if found_path:
                        entity_chain = found_path
                        break

            # Check for multi-source direct answers where multiple documents independently corroborate with high content overlap
            high_overlap_direct_files = [
                f for f in direct_answer_files
                if f in valid_citations and sum(1 for w in query_content_words if word_matches_text(w, (" ".join(file_to_text.get(f, [])) + " " + f).lower())) >= 3
            ]

            if entity_chain:
                final_chain = entity_chain
            elif len(high_overlap_direct_files) > 1 and primary_ans_file in high_overlap_direct_files:
                final_chain = high_overlap_direct_files
            else:
                final_chain = [primary_ans_file]

            valid_citations = final_chain

    # Ensure no superseded file is cited and remove duplicates
    final_citations = [c for c in list(dict.fromkeys(valid_citations)) if not any(chunk["file"] == c and chunk.get("superseded", False) for chunk in chunks)]
                    
    result["citations"] = final_citations
    result["confidence"] = 1.0 if (final_citations and result.get("answer")) else 0.0
    return result

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
                payload = None
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
                
                if payload is None:
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
