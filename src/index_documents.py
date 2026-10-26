import os
import shutil
import sys
from retrieval import build_index
from config import settings

EMBEDDINGS_FOLDER = settings.EMB_FOLDER

if __name__ == "__main__":
    print("[index] Cleaning previous index...")
    try:
        # Remove old index folder if it exists
        if os.path.exists(EMBEDDINGS_FOLDER):
            shutil.rmtree(EMBEDDINGS_FOLDER)
        os.makedirs(EMBEDDINGS_FOLDER, exist_ok=True)
    except Exception as e:
        print(f"[index] Warning: failed to clean embeddings folder: {e}")

    print("[index] Building FAISS index from documents...")
    try:
        # Build the new index from documents in DOCS_FOLDER
        stats = build_index()
        print(f"[index] Done. documents={stats.get('n_docs', 0)} chunks={stats.get('n_chunks', 0)}")
    except Exception as e:
        print(f"[index] ERROR while building index: {e}")
        sys.exit(1)
