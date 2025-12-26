import os
import tempfile
import time
from pathlib import Path

from python.runfiles import runfiles


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def get_test_pdf() -> str:
    r = runfiles.Create()
    pdf_path = r.Rlocation("outloud/bazel.pdf")
    if not pdf_path or not Path(pdf_path).exists():
        raise FileNotFoundError("bazel.pdf not found in runfiles")
    return pdf_path


def test_pdf_extraction():
    log("Starting PDF extraction test...")
    from extractor import extract_from_pdf_simple

    pdf_path = get_test_pdf()
    log(f"Extracting first page from: {pdf_path}")

    start = time.time()
    title, text = extract_from_pdf_simple(pdf_path, max_pages=1)
    elapsed = time.time() - start

    log(f"Extracted {len(text)} characters in {elapsed:.1f}s")
    log(f"Title: {title}")

    assert title, "Title should not be empty"
    assert len(text) > 100, "Extracted text should have substantial content"
    assert (
        "bazel" in text.lower() or "build" in text.lower()
    ), "Text should contain relevant content"
    log("PDF extraction test passed")


def test_tts_generation():
    log("Starting TTS generation test...")
    log("Loading Kokoro TTS model...")
    from tts import generate_audio, get_available_voices

    voices = get_available_voices()
    log(f"Found {len(voices)} available voices")
    assert len(voices) > 0, "Should have available voices"

    voice = voices[0]["id"]
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "test_output.mp3")
        log(f"Generating short audio clip with voice '{voice}'...")

        start = time.time()
        result = generate_audio(
            "Hello, this is a test of the text to speech system.",
            output_path,
            voice=voice,
            speed=1.0,
        )
        elapsed = time.time() - start

        file_size = Path(result).stat().st_size
        log(f"Generated {file_size} bytes in {elapsed:.1f}s")

        assert Path(result).exists(), "Output file should exist"
        assert file_size > 1000, "Output file should have content"
    log("TTS generation test passed")


def test_end_to_end_pdf_to_audio():
    log("Starting end-to-end PDF to audio test...")
    from extractor import extract_from_pdf_simple
    from tts import generate_audio_chunked, get_available_voices

    pdf_path = get_test_pdf()
    log("Extracting first page from PDF...")

    start = time.time()
    title, text = extract_from_pdf_simple(pdf_path, max_pages=1)
    log(f"Extracted {len(text)} chars, title: {title}")

    short_text = text[:500]
    log("Using first 500 characters for audio generation...")

    def progress(current, total, status):
        log(f"  [{current}/{total}] {status}")

    voice = get_available_voices()[0]["id"]
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "e2e_test.mp3")
        result = generate_audio_chunked(
            short_text,
            output_path,
            voice=voice,
            speed=1.2,
            progress_callback=progress,
        )
        elapsed = time.time() - start

        file_size = Path(result).stat().st_size
        log(f"Generated {file_size} bytes total in {elapsed:.1f}s")

        assert Path(result).exists(), "Should generate audio file"
        assert file_size > 5000, "Audio file should have substantial content"
    log("End-to-end test passed")


if __name__ == "__main__":
    log("=" * 50)
    log("OutLoud End-to-End Tests")
    log("=" * 50)

    test_pdf_extraction()
    print()

    test_tts_generation()
    print()

    test_end_to_end_pdf_to_audio()

    print()
    log("=" * 50)
    log("All tests passed!")
    log("=" * 50)
