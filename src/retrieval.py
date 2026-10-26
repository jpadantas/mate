import os
import io
import sys
import pickle
import threading
import logging
from contextlib import contextmanager, redirect_stderr
from typing import List, Dict, Any, Tuple

import torch
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import pdfplumber
import docx

from config import settings

# =============================================================================
# Quiet logging utilities (avoid noisy PDF logs)
# =============================================================================
@contextmanager
def _quiet_logger(name: str = "pdfminer"):
    logger = logging.getLogger(name)
    prev_level = logger.level
    logger.setLevel(logging.ERROR)
    buf = io.StringIO()
    try:
        with redirect_stderr(buf):
            yield
    finally:
        logger.setLevel(prev_level)

# =============================================================================
# Configuration
# =============================================================================
MODEL_NAME = settings.EMBEDDING_MODEL
CHUNK_SIZE = settings.CHUNK_SIZE
CHUNK_OVERLAP = settings.CHUNK_OVERLAP
TOP_K_DEFAULT = settings.TOP_K
USE_COSINE = True  # IndexFlatIP + normalized vectors → cosine similarity

DOCS_FOLDER = settings.DOCS_FOLDER
EMB_FOLDER = settings.EMB_FOLDER
os.makedirs(EMB_FOLDER, exist_ok=True)

PATH_INDEX = os.path.join(EMB_FOLDER, "faiss.index")
PATH_MAP = os.path.join(EMB_FOLDER, "mapping.pkl")
PATH_CHUNKS = os.path.join(EMB_FOLDER, "chunks.pkl")

# Default limit for context length concatenation
MAX_CONTEXT_CHARS = getattr(settings, "MAX_CONTEXT_CHARS", 12000)

# =============================================================================
# Embedding model (loads on GPU if available)
# =============================================================================
_embedding_model: SentenceTransformer | None = None
_embedding_lock = threading.Lock()

def _model() -> SentenceTransformer:
    """
    Loads the SentenceTransformer model on GPU if available.
    Keeps a singleton instance to avoid repeated loads.
    """
    global _embedding_model
    if _embedding_model is None:
        with _embedding_lock:
            if _embedding_model is None:
                device = "cuda" if torch.cuda.is_available() else "cpu"
                m = SentenceTransformer(MODEL_NAME, device=device)
                if device == "cuda":
                    try:
                        # Move model to CUDA and enable matmul optimization
                        m = m.to(torch.device("cuda"))
                        torch.set_float32_matmul_precision("high")
                    except Exception:
                        pass
                _embedding_model = m
    return _embedding_model

# =============================================================================
# Text utilities
# =============================================================================
def _clean_text(s: str) -> str:
    """Removes extra spaces and empty lines."""
    if not s:
        return ""
    lines = [ln.strip() for ln in s.splitlines()]
    return "\n".join([ln for ln in lines if ln]).strip()

def split_text(text: str, max_chars: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Splits text into overlapping chunks (tries to break at spaces when possible).
    """
    text = _clean_text(text)
    if not text:
        return []

    chunks: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + max_chars)
        chunk = text[start:end]
        if end < n:
            # Try to roll back to the nearest space to avoid word cut
            back = 0
            while end - back > start and back < 200 and text[end - back - 1] != " ":
                back += 1
            if back > 0 and (end - back) > start + (max_chars // 2):
                end -= back
                chunk = text[start:end]
        chunks.append(chunk)
        if end >= n:
            break
        # Next start recedes by overlap to maintain sliding window
        start = max(0, end - overlap)
    return chunks

# =============================================================================
# Document reading
# =============================================================================
def pdf_to_text(pdf_path: str) -> str:
    """Extracts text from a PDF using pdfplumber."""
    try:
        with _quiet_logger():
            with pdfplumber.open(pdf_path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
        return _clean_text("\n".join([p for p in pages if p]))
    except Exception as e:
        print(f"[pdf_to_text] Error in {pdf_path}: {e}")
        return ""

def docx_to_text(docx_path: str) -> str:
    """Extracts text from a DOCX file."""
    try:
        d = docx.Document(docx_path)
        paras = [p.text or "" for p in d.paragraphs]
        return _clean_text("\n".join([p for p in paras if p]))
    except Exception as e:
        print(f"[docx_to_text] Error in {docx_path}: {e}")
        return ""

def _convert_to_txt_if_needed() -> None:
    """
    Converts .pdf/.docx files to .txt (once) to speed up indexing.
    """
    for file in os.listdir(DOCS_FOLDER):
        path = os.path.join(DOCS_FOLDER, file)
        if not os.path.isfile(path):
            continue
        name, ext = os.path.splitext(file)
        ext = ext.lower()
        if ext in [".pdf", ".docx"]:
            txt_path = os.path.join(DOCS_FOLDER, f"{name}.txt")
            if os.path.exists(txt_path):
                continue
            print(f"[convert] {file} -> {os.path.basename(txt_path)}")
            text = pdf_to_text(path) if ext == ".pdf" else docx_to_text(path)
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text or "")

# =============================================================================
# Embedding and index creation
# =============================================================================
def _embed_texts(texts: List[str]) -> np.ndarray:
    """
    Encodes text chunks into embeddings using SentenceTransformers on GPU.
    Returns a NumPy array normalized for FAISS.
    """
    model = _model()
    embs = model.encode(
        texts,
        batch_size=96,              # adjust based on GPU VRAM (64/96/128)
        convert_to_tensor=True,
        normalize_embeddings=False,
        show_progress_bar=False
    )
    # Move tensors from GPU → CPU and convert to float32 NumPy
    if hasattr(embs, "device"):
        embs = embs.detach().to("cpu")
    embs = embs.to(dtype=torch.float32).numpy()
    if USE_COSINE:
        faiss.normalize_L2(embs)
    return embs

def build_index() -> Dict[str, int]:
    """
    Reads all .txt files, splits into chunks, encodes them, and builds FAISS index.
    Saves index, mapping, and chunk list to disk.
    """
    _convert_to_txt_if_needed()

    documents: List[Tuple[str, str]] = []
    for file in sorted(os.listdir(DOCS_FOLDER)):
        if not file.lower().endswith(".txt"):
            continue
        p = os.path.join(DOCS_FOLDER, file)
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"[build_index] Error reading {file}: {e}")
            continue
        content = _clean_text(content)
        if content:
            documents.append((file, content))

    if not documents:
        print("[build_index] No documents found.")
        return {"n_docs": 0, "n_chunks": 0}

    all_chunks: List[str] = []
    mapping: List[str] = []
    for fname, text in documents:
        chunks = split_text(text)
        for ch in chunks:
            all_chunks.append(ch)
            mapping.append(fname)

    if not all_chunks:
        return {"n_docs": len(documents), "n_chunks": 0}

    # Encode on GPU
    embs = _embed_texts(all_chunks)
    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim) if USE_COSINE else faiss.IndexFlatL2(dim)
    index.add(embs)

    # Save files
    faiss.write_index(index, PATH_INDEX)
    with open(PATH_MAP, "wb") as f:
        pickle.dump(mapping, f)
    with open(PATH_CHUNKS, "wb") as f:
        pickle.dump(all_chunks, f)

    return {"n_docs": len(documents), "n_chunks": len(all_chunks)}

# =============================================================================
# Index loading and semantic search
# =============================================================================
_index: faiss.Index | None = None
_mapping: List[str] | None = None
_chunks: List[str] | None = None
_lock = threading.Lock()

def _ensure_index_loaded() -> None:
    """Loads FAISS index and associated metadata into memory if not already loaded."""
    global _index, _mapping, _chunks
    with _lock:
        if _index is not None and _mapping is not None and _chunks is not None:
            return
        if not (os.path.exists(PATH_INDEX) and os.path.exists(PATH_MAP) and os.path.exists(PATH_CHUNKS)):
            raise RuntimeError("Index not built. Run `python index_documents.py` first.")
        _index = faiss.read_index(PATH_INDEX)
        with open(PATH_MAP, "rb") as f:
            _mapping = pickle.load(f)
        with open(PATH_CHUNKS, "rb") as f:
            _chunks = pickle.load(f)

def _build_context_from_hits(indices: List[int], max_total_chars: int | None = None) -> str:
    """Concatenates retrieved chunks up to a character limit."""
    if max_total_chars is None:
        max_total_chars = MAX_CONTEXT_CHARS

    assert _chunks is not None
    seen: set[int] = set()
    parts: List[str] = []
    total = 0
    for idx in indices:
        if idx in seen:
            continue
        seen.add(idx)
        chunk = _chunks[idx]
        if not chunk:
            continue
        add = chunk[: max(0, max_total_chars - total)]
        if not add:
            break
        parts.append(add)
        total += len(add)
        if total >= max_total_chars:
            break
    return "\n\n---\n\n".join(parts)

def search_similar(query: str, top_k: int = TOP_K_DEFAULT) -> Dict[str, Any]:
    """
    Performs semantic search over the indexed documents using FAISS.
    Returns both the context and detailed hit list.
    """
    if not query or not query.strip():
        return {"context": "", "hits": []}

    _ensure_index_loaded()
    assert _index is not None and _mapping is not None and _chunks is not None

    q_emb = _embed_texts([query])
    D, I = _index.search(q_emb, top_k)

    hits: List[Dict[str, Any]] = []
    idxs: List[int] = []

    for score, idx in zip(D[0], I[0]):
        if idx < 0 or idx >= len(_mapping):
            continue
        fname = _mapping[idx]
        chunk_text = _chunks[idx]
        hits.append({
            "file": fname,
            "score": float(score),
            "chunk_id": int(idx),
            "preview": (chunk_text[:280] + "…") if len(chunk_text) > 280 else chunk_text
        })
        idxs.append(int(idx))

    context = _build_context_from_hits(idxs)
    return {"context": context, "hits": hits}
