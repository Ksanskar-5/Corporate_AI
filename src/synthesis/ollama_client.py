"""
ollama_client.py — Lightweight Client for Local Ollama LLM
Communicates with local Ollama daemon (gemma3:4b).
Includes automatic unload (keep_alive: 0) to avoid keeping the model in memory.
"""

import json
import urllib.request
import urllib.error

DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "gemma3:4b"


def is_ollama_available(url: str = "http://localhost:11434/api/tags") -> bool:
    """Checks if the local Ollama server is reachable."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def query_ollama(
    prompt: str,
    system_prompt: str = None,
    model: str = DEFAULT_MODEL,
    json_mode: bool = False,
    timeout_sec: int = 60,
    keep_alive: str = "0s",  # Unload from memory immediately after generation
) -> str:
    """
    Sends a generation request to the local Ollama LLM.

    Parameters
    ----------
    prompt : str
        The user query / task.
    system_prompt : str, optional
        System instructions for the model.
    model : str
        Local model name (defaults to 'gemma3:4b').
    json_mode : bool
        If True, forces Ollama to return valid JSON format.
    timeout_sec : int
        Request timeout in seconds.
    keep_alive : str
        Controls how long model stays in RAM. '0s' unloads immediately.

    Returns
    -------
    str
        Generated text response from the model.
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
    }
    if system_prompt:
        payload["system"] = system_prompt
    if json_mode:
        payload["format"] = "json"

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        DEFAULT_OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("response", "")
    except urllib.error.URLError as e:
        raise ConnectionError(f"Failed to connect to local Ollama at {DEFAULT_OLLAMA_URL}: {e}")
