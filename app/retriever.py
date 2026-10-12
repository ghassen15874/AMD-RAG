import json
import os
import torch
import torch.nn.functional as F
from pathlib import Path
from transformers import AutoTokenizer, AutoModel

_EMBED_CACHE_DIR = "models--sentence-transformers--all-MiniLM-L6-v2"
_SEARCH_ROOTS = [
    Path(os.environ.get("MC3_MODELS_DIR", "models")),
    Path("models"),
    Path("/app/models"),
    Path(os.environ.get("HF_HOME", "/app/models")),
]


def _find_embedder_snapshot() -> str:
    """Locate the first valid snapshot directory for the embedder model."""
    for root in _SEARCH_ROOTS:
        snap_dir = root / _EMBED_CACHE_DIR / "snapshots"
        if snap_dir.is_dir():
            for child in sorted(snap_dir.iterdir()):
                if (child / "config.json").is_file():
                    return str(child)
    raise FileNotFoundError(
        "Embedder weights not found.  Download them:\n"
        "  huggingface-cli download sentence-transformers/all-MiniLM-L6-v2 "
        f"--local-dir models/{_EMBED_CACHE_DIR}/snapshots/main\n"
    )


class Retriever:
    def __init__(self, index_dir=None):
        self.index_dir = index_dir or os.environ.get("MC3_INDEX_DIR", "/app/index")
        self.model_id = _find_embedder_snapshot()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print(f"Loading retriever model from {self.model_id} ...", flush=True)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_id, local_files_only=True)
        self.model = AutoModel.from_pretrained(self.model_id, local_files_only=True).to(self.device)
        self.model.eval()
        print("Retriever model loaded.", flush=True)
        
        self.chunks = []
        self.embeddings = None

    def _mean_pooling(self, model_output, attention_mask):
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    def embed_texts(self, texts):
        encoded_input = self.tokenizer(texts, padding=True, truncation=True, return_tensors='pt', max_length=512).to(self.device)
        with torch.no_grad():
            model_output = self.model(**encoded_input)
        sentence_embeddings = self._mean_pooling(model_output, encoded_input['attention_mask'])
        sentence_embeddings = F.normalize(sentence_embeddings, p=2, dim=1)
        return sentence_embeddings

    def index_corpus(self, index_path):
        # Read the chunks from the index file created by daemon
        with open(index_path, 'r') as f:
            data = json.load(f)
            self.chunks = data.get("chunks", [])
            self.identifiers = data.get("identifiers", {})
        
        if not self.chunks:
            return
            
        print(f"Embedding {len(self.chunks)} chunks...", flush=True)
        texts = [chunk.get("text", "") for chunk in self.chunks]
        
        # Batch processing to avoid OOM
        batch_size = 32
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            emb = self.embed_texts(batch_texts)
            all_embeddings.append(emb)
            
        self.embeddings = torch.cat(all_embeddings, dim=0)
        
        # Save embeddings
        torch.save(self.embeddings, f"{self.index_dir}/embeddings.pt")
        
        # Fit BM25
        from bm25 import BM25
        import re
        self.bm25 = BM25()
        tokenized_corpus = [re.findall(r'\w+', t.lower()) for t in texts]
        self.bm25.fit(tokenized_corpus)
        import pickle
        with open(f"{self.index_dir}/bm25.pkl", "wb") as f:
            pickle.dump(self.bm25, f)
            
        print("Indexing complete.", flush=True)

    def load_index(self, index_path):
        with open(index_path, 'r') as f:
            data = json.load(f)
            self.chunks = data.get("chunks", [])
            self.identifiers = data.get("identifiers", {})
        self.embeddings = torch.load(f"{self.index_dir}/embeddings.pt").to(self.device)
        import pickle
        with open(f"{self.index_dir}/bm25.pkl", "rb") as f:
            self.bm25 = pickle.load(f)

    def retrieve(self, query, top_k=5):
        if not self.chunks:
            return []
            
        # 1. Embeddings Retrieval
        query_emb = self.embed_texts([query])
        similarities = torch.matmul(self.embeddings, query_emb.T).squeeze(1)
        dense_scores = similarities.tolist()
        
        # 2. BM25 Retrieval
        import re
        tokenized_query = re.findall(r'\w+', query.lower())
        bm25_scores = self.bm25.get_scores(tokenized_query)
        
        # 3. Identifier Match Retrieval
        ident_scores = [0] * len(self.chunks)
        for ident, paths in self.identifiers.items():
            if ident.lower() in query.lower():
                for i, chunk in enumerate(self.chunks):
                    if ident.lower() in chunk.get("text", "").lower():
                        ident_scores[i] += 5
                    elif chunk["file"] in paths:
                        ident_scores[i] += 1
                        
        # RRF Fusion
        def rrf_score(scores, k=60, top_n=None):
            ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            rrf = [0] * len(scores)
            limit = top_n if top_n is not None else len(scores)
            for rank, idx in enumerate(ranked[:limit]):
                if scores[idx] > 0:
                    rrf[idx] = 1.0 / (k + rank + 1)
            return rrf
            
        dense_rrf = rrf_score(dense_scores, top_n=10)
        bm25_rrf = rrf_score(bm25_scores, top_n=10)
        ident_rrf = rrf_score(ident_scores)
        
        query_lower = query.lower()
        asks_for_superseded = any(w in query_lower for w in ["superseded", "withdrawn", "obsolete", "deprecated", "previous", "old"])
        
        final_scores = []
        for i in range(len(self.chunks)):
            score = dense_rrf[i] + bm25_rrf[i] + ident_rrf[i] * 2.0
            if self.chunks[i].get("superseded", False):
                if not asks_for_superseded:
                    score = -1.0
                else:
                    score *= 0.1
            final_scores.append(score)
        
        # Get top-k
        top_k = min(top_k, len(self.chunks))
        ranked_indices = [idx for idx in sorted(range(len(final_scores)), key=lambda i: final_scores[i], reverse=True) if final_scores[idx] > 0][:top_k]
        
        results = []
        seen_files = set()
        for idx in ranked_indices:
            chunk = self.chunks[idx].copy()
            chunk['score'] = final_scores[idx]
            results.append(chunk)
            seen_files.add(chunk["file"])

        # Multi-hop identifier expansion:
        # If top chunks mention an identifier that maps to other corpus files, include them
        from parsers.registry import extract_identifiers
        hop_files = set()
        for idx in ranked_indices[:3]:
            if self.chunks[idx].get("superseded", False) and not asks_for_superseded:
                continue
            chunk_idents = extract_identifiers(self.chunks[idx].get("text", ""))
            for ident in chunk_idents:
                for target_file in self.identifiers.get(ident, set()):
                    if target_file not in seen_files:
                        hop_files.add(target_file)

        for hop_file in hop_files:
            for idx in sorted(range(len(self.chunks)), key=lambda i: final_scores[i], reverse=True):
                if self.chunks[idx]["file"] == hop_file:
                    if self.chunks[idx].get("superseded", False) and not asks_for_superseded:
                        continue
                    chunk = self.chunks[idx].copy()
                    chunk['score'] = final_scores[idx]
                    results.append(chunk)
                    seen_files.add(hop_file)
                    break
            
        if not asks_for_superseded:
            results = [r for r in results if not r.get("superseded", False)]
            
        return results
