import re
from pathlib import Path
from urllib.parse import urlparse

import trafilatura
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict

_marker_converter = None


def _get_marker_converter():
    global _marker_converter
    if _marker_converter is None:
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
    """Extract text from PDF using marker-pdf."""
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    converter = _get_marker_converter()
    rendered = converter(str(path))

    text = rendered.markdown

    if not text or len(text.strip()) < 50:
        raise ValueError(f"Could not extract text from PDF: {pdf_path}")

    text = clean_markdown_for_tts(text)
    title = extract_title_from_text(text) or path.stem
    title = re.sub(r"[_-]+", " ", title).strip()

    return title, text


def clean_markdown_for_tts(text: str) -> str:
    # Remove HTML tags and spans
    text = re.sub(r"<[^>]+>", "", text)

    # Remove LaTeX math blocks
    text = re.sub(r"\$\$[\s\S]*?\$\$", "", text)
    text = re.sub(r"\$[^$]+\$", "", text)

    # Remove image references
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

    # Remove markdown links but keep text (handles escaped brackets too)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\\\[([^\]]+)\\\]", r"\1", text)

    # Remove reference markers like [1], [2,3], [\[6\]], etc.
    text = re.sub(r"\[\\?\[?\d+(?:,\s*\d+)*\\?\]?\]", "", text)
    text = re.sub(r"\(#page-\d+-\d+\)", "", text)

    # Remove URLs and email addresses
    text = re.sub(r"https?://[^\s]+", "", text)
    text = re.sub(r"\S+@\S+\.\S+", "", text)

    # Remove DOIs and ISBNs
    text = re.sub(r"doi\.org/[^\s]+", "", text)
    text = re.sub(r"DOI:?\s*[^\s]+", "", text)
    text = re.sub(r"ISBN[:\s]*[\d-]+", "", text)

    # Remove academic paper boilerplate
    text = re.sub(
        r"Permission to make digital or hard copies.*?owner/author\(s\)\.",
        "",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r"©\s*\d{4}.*?(?=\n\n|\Z)", "", text, flags=re.DOTALL)
    text = re.sub(r"ACM ISBN.*?(?=\n)", "", text)
    text = re.sub(r"ACM Reference Format:.*?(?=\n\n)", "", text, flags=re.DOTALL)

    # Remove section labels that don't read well
    text = re.sub(
        r"^(CCS CONCEPTS|KEYWORDS|ABSTRACT)[.\s]*$", "", text, flags=re.MULTILINE
    )
    text = re.sub(r"^Figure \d+:.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^Table \d+:.*$", "", text, flags=re.MULTILINE)

    # Remove horizontal rules
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\*{3,}$", "", text, flags=re.MULTILINE)

    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)

    # Convert headers to plain text with pause
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\n\1.\n", text, flags=re.MULTILINE)

    # Remove bullet points and numbered lists formatting
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)

    # Remove parenthetical asides with just numbers/letters
    text = re.sub(r"\(\d+\)", "", text)
    text = re.sub(r"\([a-z]\)", "", text)

    # Clean up whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)

    return text.strip()


def extract_title_from_text(text: str) -> str | None:
    lines = text.strip().split("\n")
    for line in lines[:5]:
        line = line.strip()
        if len(line) > 10 and len(line) < 200:
            title = re.sub(r"^#+\s*", "", line)
            title = re.sub(r"\*+", "", title)
            if title:
                return title
    return None


def save_text(text: str, output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)
