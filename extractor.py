import re
from pathlib import Path
from urllib.parse import urlparse

import trafilatura

_marker_converter = None


def get_marker_converter():
    global _marker_converter
    if _marker_converter is None:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
        _marker_converter = PdfConverter(artifact_dict=create_model_dict())
    return _marker_converter


def extract_from_url(url: str) -> tuple[str, str]:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        raise ValueError(f"Could not fetch URL: {url}")

    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    if not text:
        raise ValueError(f"Could not extract text from URL: {url}")

    metadata = trafilatura.extract_metadata(downloaded)
    if metadata and metadata.title:
        title = metadata.title
    else:
        parsed = urlparse(url)
        title = parsed.netloc.replace("www.", "")

    return title, text


def extract_from_pdf(pdf_path: str) -> tuple[str, str]: 
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    converter = get_marker_converter()
    rendered = converter(str(path))

    text = rendered.markdown

    if not text or len(text.strip()) < 100:
        raise ValueError(f"Could not extract text from PDF: {pdf_path}")

    text = clean_markdown_for_tts(text)
    title = extract_title_from_text(text) or path.stem
    title = re.sub(r'[_-]+', ' ', title).strip()

    return title, text


def clean_markdown_for_tts(text: str) -> str:
    """Clean markdown text for TTS reading."""
    # Remove image references
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # Remove links but keep text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Remove horizontal rules
    text = re.sub(r'^-{3,}$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\*{3,}$', '', text, flags=re.MULTILINE)
    # Remove code blocks (usually not good for TTS)
    text = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code
    text = re.sub(r'`[^`]+`', '', text)
    # Convert headers to plain text with pause
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\n\1.\n', text, flags=re.MULTILINE)
    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove reference markers like [1], [2,3], etc.
    text = re.sub(r'\[\d+(?:,\s*\d+)*\]', '', text)
    # Remove bullet points
    text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
    return text.strip()


def extract_title_from_text(text: str) -> str | None:
    lines = text.strip().split('\n')
    for line in lines[:5]:
        line = line.strip()
        if len(line) > 10 and len(line) < 200:
            title = re.sub(r'^#+\s*', '', line)
            title = re.sub(r'\*+', '', title)
            if title:
                return title
    return None


def save_text(text: str, output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return str(path)
