import os
import sys
import tempfile
from pathlib import Path

import pytest
from python.runfiles import runfiles

from app import app
from extractor import extract_from_pdf_simple
from tts import (
    generate_audio,
    generate_audio_chunked,
    generate_preview,
    get_available_voices,
    get_kokoro,
)


@pytest.fixture(scope="module")
def test_pdf() -> str:
    r = runfiles.Create()
    pdf_path = r.Rlocation("outloud/bazel.pdf")
    if not pdf_path or not Path(pdf_path).exists():
        raise FileNotFoundError("bazel.pdf not found in runfiles")
    return pdf_path


@pytest.fixture(scope="module")
def kokoro():
    return get_kokoro()


class TestPDFExtraction:
    def test_extract_from_pdf(self, test_pdf):
        title, text = extract_from_pdf_simple(test_pdf, max_pages=1)

        assert title, "Title should not be empty"
        assert len(text) > 100, "Extracted text should have substantial content"
        assert (
            "bazel" in text.lower() or "build" in text.lower()
        ), "Text should contain relevant content"


class TestTTS:
    def test_get_available_voices(self):
        voices = get_available_voices()

        assert len(voices) > 0, "Should have available voices"
        assert all("id" in v for v in voices), "Each voice should have an id"
        assert all("name" in v for v in voices), "Each voice should have a name"

    def test_generate_audio(self, kokoro):
        voice = get_available_voices()[0]["id"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_output.mp3")

            result = generate_audio(
                "Hello, this is a test.",
                output_path,
                voice=voice,
                speed=1.0,
            )

            assert Path(result).exists(), "Output file should exist"
            assert Path(result).stat().st_size > 1000, "Output file should have content"

    def test_generate_audio_chunked(self, kokoro, test_pdf):
        _, text = extract_from_pdf_simple(test_pdf, max_pages=1)
        short_text = text[:500]

        progress_calls = []

        def progress_callback(current, total, status):
            progress_calls.append((current, total, status))

        voice = get_available_voices()[0]["id"]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "chunked_test.mp3")

            result = generate_audio_chunked(
                short_text,
                output_path,
                voice=voice,
                speed=1.2,
                progress_callback=progress_callback,
            )

            assert Path(result).exists(), "Should generate audio file"
            assert (
                Path(result).stat().st_size > 5000
            ), "Audio file should have substantial content"
            assert len(progress_calls) > 0, "Progress callback should be called"

    def test_generate_preview(self, kokoro):
        voice = get_available_voices()[0]["id"]

        mp3_bytes = generate_preview(voice, speed=1.0)

        assert isinstance(mp3_bytes, bytes), "Should return bytes"
        assert len(mp3_bytes) > 1000, "Preview should have substantial content"
        assert (
            mp3_bytes[:3] == b"ID3" or mp3_bytes[:2] == b"\xff\xfb"
        ), "Should be valid MP3"


class TestPreviewEndpoint:
    @pytest.fixture
    def client(self):
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_preview_valid_voice(self, client, kokoro):
        valid_voice = get_available_voices()[0]["id"]

        response = client.get(f"/preview/voice/{valid_voice}")

        assert response.status_code == 200, "Should return 200 for valid voice"
        assert response.content_type == "audio/mpeg", "Should return audio/mpeg"
        assert len(response.data) > 1000, "Should return audio data"

    def test_preview_invalid_voice(self, client):
        response = client.get("/preview/voice/invalid_voice_id")

        assert response.status_code == 404, "Should return 404 for invalid voice"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
