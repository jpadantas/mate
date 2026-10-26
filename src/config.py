import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    # ---------- LLM ----------
    # Main Ollama endpoint for text generation
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")

    # Ollama endpoint to list installed models (/api/tags)
    OLLAMA_TAGS_URL: str = os.getenv("OLLAMA_TAGS_URL", "http://localhost:11434/api/tags")

    # Default language model (e.g., "mistral-nemo", "llama3.1:8b", "qwen2.5:14b")
    DEFAULT_MODEL: str = os.getenv("OLLAMA_MODEL", "mistral-nemo")

    # Timeout settings (seconds)
    CONNECT_TIMEOUT: int = int(os.getenv("CONNECT_TIMEOUT", "5"))
    READ_TIMEOUT: int = int(os.getenv("READ_TIMEOUT", "300"))

    # Global system prompt — defines the LLM’s role and constraints
    SYSTEM_PROMPT: str = os.getenv(
    "SYSTEM_PROMPT",
    (
        "You are MATE: Mission Assistant for Training and Evaluation. "
        "You are a tactical assistant specialized in air combat operations. "
        "Answer directly and concisely, based strictly on Chapter 5 of 'Fighter Combat: Tactics and Maneuvering'. "
        "Use standard aviation terminology (e.g., leader, wingman, engagement, bracket). "
        "If the question is outside the scope of Chapter 5, state that explicitly."
    ),
)

    # ---------- Retrieval ----------
    # Embedding model used by SentenceTransformers
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")

    # Chunk size and overlap — tuned for dense technical text
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1200"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "250"))

    # Number of top chunks to return from semantic search
    TOP_K: int = int(os.getenv("TOP_K", "5"))

    # Maximum number of characters concatenated into a single context prompt
    MAX_CONTEXT_CHARS: int = int(os.getenv("MAX_CONTEXT_CHARS", "4000"))

    # ---------- Directories ----------
    # Base directory of the project (usually src/)
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))

    # Default folder for documents (.txt, .pdf, .docx)
    DOCS_FOLDER: str = os.getenv(
        "DOCS_FOLDER",
        os.path.join(os.path.dirname(BASE_DIR), "docs"),
    )

    # Folder for vector indexes and embeddings (FAISS, mapping, chunks)
    EMB_FOLDER: str = os.getenv(
        "EMB_FOLDER",
        os.path.join(os.path.dirname(BASE_DIR), "embeddings"),
    )

# Singleton instance of the configuration
settings = Settings()
