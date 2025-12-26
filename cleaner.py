import requests

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:1b"

CLEANUP_PROMPT = """You are a text editor preparing content for audio narration.

CRITICAL RULES - You MUST follow these:
1. PRESERVE the author's original language, words, and writing style exactly
2. KEEP all original sentences - do not rewrite or paraphrase
3. ONLY remove content, never modify or rephrase existing text

What to REMOVE:
- Reference markers like "[1]", "[2,3]", "Figure 1", "Table 2"
- Code or symbols like <span or ** or |
- Author affiliations, email addresses, page numbers, headers/footers
- Acknowledgments and funding sections
- Appendices and reference lists
- Anything that doesn't dictate well for TTS narration

What to KEEP (unchanged):
- All substantive content that teaches or informs
- The author's exact words and sentence structure
- The logical flow and narrative structure
- Key examples and explanations

Output ONLY the cleaned text. No explanations or commentary.

Text to clean:
"""


def is_ollama_running() -> bool:
    """Check if Ollama is running."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def cleanup_text(text: str, model: str = DEFAULT_MODEL) -> str:
    """
    Clean up text using a local LLM via Ollama.

    Args:
        text: The text to clean up
        model: The Ollama model to use

    Returns:
        Cleaned text
    """
    if not is_ollama_running():
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={
            "model": model,
            "prompt": CLEANUP_PROMPT + text,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for consistent output
                "num_predict": len(text) + 500,  # Allow enough tokens
            },
        },
        timeout=300,  # 5 minute timeout for long texts
    )

    if response.status_code != 200:
        raise RuntimeError(f"Ollama error: {response.text}")

    result = response.json()
    return result.get("response", "").strip()


def cleanup_text_chunked(
    text: str,
    model: str = DEFAULT_MODEL,
    chunk_size: int = 2000,
    progress_callback=None,
) -> str:
    """
    Clean up text in chunks for longer documents.

    Args:
        text: The text to clean up
        model: The Ollama model to use
        chunk_size: Max characters per chunk
        progress_callback: Function called with (current, total, status)

    Returns:
        Cleaned text
    """
    if not is_ollama_running():
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")

    # Split into paragraphs
    paragraphs = text.split("\n\n")

    # Group paragraphs into chunks
    chunks = []
    current_chunk = ""
    for para in paragraphs:
        if len(current_chunk) + len(para) < chunk_size:
            current_chunk += para + "\n\n"
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = para + "\n\n"
    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    if not chunks:
        chunks = [text]

    # Process each chunk
    cleaned_parts = []
    total = len(chunks)

    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(i + 1, total, f"Cleaning chunk {i + 1}/{total}")

        cleaned = cleanup_text(chunk, model)
        cleaned_parts.append(cleaned)

    if progress_callback:
        progress_callback(total, total, "Cleanup complete")

    return "\n\n".join(cleaned_parts)
