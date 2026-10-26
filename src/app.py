# app.py
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import settings
from llm_interface import ask_ollama, ask_ollama_stream, list_installed_models, health_check
from retrieval import search_similar, build_index, _model


class AskRequest(BaseModel):
    question: str
    top_k: Optional[int] = None
    model: Optional[str] = None
    system_prompt: Optional[str] = None
    max_context_chars: Optional[int] = None


class IndexResponse(BaseModel):
    n_docs: int
    n_chunks: int


app = FastAPI(
    title="MATE API",
    description="Lightweight Retrieval-Augmented Generation API (FAISS + SentenceTransformers + Ollama)",
    version="1.0.0",
)


@app.on_event("startup")
def _warmup() -> None:
    try:
        _ = _model()
        ok, msg = health_check()
        print("[startup]", "OK" if ok else f"LLM warning: {msg}")
    except Exception as e:
        print(f"[startup] Warm-up failed (continuing): {e}")


@app.get("/health")
def health() -> Dict[str, Any]:
    ok, msg = health_check()
    return {"status": "ok" if ok else "warning", "llm_message": msg, "embedding_model": settings.EMBEDDING_MODEL}


@app.get("/models")
def models() -> Dict[str, Any]:
    try:
        names = list_installed_models()
        return {"models": names}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not list models: {e}")


@app.post("/reindex", response_model=IndexResponse)
def reindex() -> IndexResponse:
    try:
        stats = build_index()
        return IndexResponse(n_docs=stats.get("n_docs", 0), n_chunks=stats.get("n_chunks", 0))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rebuild index: {e}")


@app.post("/ask")
def ask(req: AskRequest) -> Dict[str, Any]:
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question text is required.")
    try:
        result = search_similar(q, top_k=req.top_k or settings.TOP_K)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

    context = result.get("context", "")
    hits = result.get("hits", [])

    try:
        answer = ask_ollama(
            question=q,
            context=context,
            model=req.model or settings.DEFAULT_MODEL,
            system_prompt=req.system_prompt or settings.SYSTEM_PROMPT,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ollama request failed: {e}")

    return {"question": q, "answer": answer, "context_length": len(context), "num_hits": len(hits), "hits": hits}


@app.post("/ask_stream")
def ask_stream(req: AskRequest):
    """
    Streaming version. Sends the answer incrementally as plain text.
    Anti-buffering headers help with proxies such as NGINX.
    """
    q = (req.question or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question text is required.")

    try:
        result = search_similar(q, top_k=req.top_k or settings.TOP_K)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")

    context = result.get("context", "")

    def _gen():
        # Empty first chunk so the client unblocks immediately
        yield ""
        for piece in ask_ollama_stream(
            question=q,
            context=context,
            model=req.model or settings.DEFAULT_MODEL,
            system_prompt=req.system_prompt or settings.SYSTEM_PROMPT,
        ):
            yield piece

    return StreamingResponse(
        _gen(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",   # nginx
        },
    )


@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "MATE API is running. Use /ask, /ask_stream, /reindex, /models."}
