import textwrap
from typing import Tuple, List, Iterator
import requests
import json

from config import settings

# Centralized configuration
OLLAMA_URL = settings.OLLAMA_URL
DEFAULT_MODEL = settings.DEFAULT_MODEL
DEFAULT_CONNECT_TIMEOUT = settings.CONNECT_TIMEOUT
DEFAULT_READ_TIMEOUT = settings.READ_TIMEOUT
OLLAMA_TAGS_URL = settings.OLLAMA_TAGS_URL


def _format_prompt(question: str, context: str, system_prompt: str | None = None) -> str:
    """
    Builds a structured prompt for the Ollama /api/generate endpoint.
    Since Ollama does not use native role-based formatting,
    we prefix sections with [SYSTEM], [CONTEXT], [USER], and [ASSISTANT].
    """
    sys_txt = (system_prompt or settings.SYSTEM_PROMPT).strip()
    return textwrap.dedent(f"""
    [SYSTEM]
    {sys_txt}

    [CONTEXT]
    {context}

    [USER]
    {question}

    [ASSISTANT]
    """).strip()


def ask_ollama(
    question: str,
    context: str,
    model: str = DEFAULT_MODEL,
    connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: int = DEFAULT_READ_TIMEOUT,
    system_prompt: str | None = None,
) -> str:
    """
    Sends a formatted prompt to Ollama and returns only the text response.
    """
    prompt = _format_prompt(question, context, system_prompt=system_prompt)
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=(connect_timeout, read_timeout),
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data.get("response", "No 'response' field found in Ollama output.")
        return f"Unexpected Ollama response type: {type(data)}"
    except requests.Timeout:
        return f"Error: Ollama timed out after connect={connect_timeout}s, read={read_timeout}s."
    except requests.RequestException as e:
        return f"Error: Failed to communicate with Ollama: {e}"


def ask_ollama_stream(
    question: str,
    context: str,
    model: str = DEFAULT_MODEL,
    connect_timeout: int = DEFAULT_CONNECT_TIMEOUT,
    read_timeout: int = DEFAULT_READ_TIMEOUT,
    system_prompt: str | None = None,
) -> Iterator[str]:
    """
    Streams partial tokens from Ollama as they are generated.
    Yields plain text chunks (no JSON), stopping when 'done' is True.
    """
    prompt = _format_prompt(question, context, system_prompt=system_prompt)
    try:
        with requests.post(
            OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": True},
            timeout=(connect_timeout, read_timeout),
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                # Ollama streams JSON lines, one object per line
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Each line may contain a partial 'response'
                piece = obj.get("response", "")
                if piece:
                    yield piece

                if obj.get("done", False):
                    break
    except requests.Timeout:
        yield f"\n\n[Error] Ollama timed out after connect={connect_timeout}s, read={read_timeout}s."
    except requests.RequestException as e:
        yield f"\n\n[Error] Failed to communicate with Ollama: {e}"


def list_installed_models(connect_timeout: int = 3, read_timeout: int = 5) -> List[str]:
    """
    Retrieves the list of installed models from Ollama via /api/tags.
    Always returns them alphabetically sorted (case-insensitive) and deduplicated.
    Example output: ["codellama:instruct", "gemma:instruct", "llama3:instruct", "mistral:instruct"]
    """
    try:
        resp = requests.get(OLLAMA_TAGS_URL, timeout=(connect_timeout, read_timeout))
        resp.raise_for_status()
        data = resp.json() or {}
        names: List[str] = []
        for item in data.get("models", []):
            name = item.get("name")
            if name:
                names.append(name)
        # Remove duplicates and sort alphabetically (case-insensitive)
        return sorted(set(names), key=str.lower)
    except requests.RequestException:
        return []


def health_check(connect_timeout: int = 2, read_timeout: int = 2) -> Tuple[bool, str]:
    """
    Lightweight health check (kept for backward compatibility).
    """
    return True, "OK"
