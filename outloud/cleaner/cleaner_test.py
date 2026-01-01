from unittest.mock import patch


def test_is_ollama_running_true():
    from outloud.cleaner import is_ollama_running

    with patch("outloud.cleaner.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        assert is_ollama_running() is True


def test_is_ollama_running_false():
    from outloud.cleaner import is_ollama_running

    with patch("outloud.cleaner.requests.get") as mock_get:
        mock_get.side_effect = Exception("Connection refused")
        assert is_ollama_running() is False


def test_cleanup_text_ollama_not_running():
    from outloud.cleaner import cleanup_text
    import pytest

    with patch("outloud.cleaner.is_ollama_running", return_value=False):
        with pytest.raises(RuntimeError, match="Ollama is not running"):
            cleanup_text("test text")


def test_cleanup_text_success():
    from outloud.cleaner import cleanup_text

    with patch("outloud.cleaner.is_ollama_running", return_value=True):
        with patch("outloud.cleaner.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"response": "cleaned text"}

            result = cleanup_text("raw text")
            assert result == "cleaned text"


def test_cleanup_text_chunked():
    from outloud.cleaner import cleanup_text_chunked

    long_text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    progress_calls = []

    with patch("outloud.cleaner.is_ollama_running", return_value=True):
        with patch("outloud.cleaner.cleanup_text") as mock_cleanup:
            mock_cleanup.side_effect = lambda t, m: f"cleaned: {t[:20]}"

            result = cleanup_text_chunked(
                long_text,
                chunk_size=50,
                progress_callback=lambda c, t, s: progress_calls.append((c, t, s)),
            )

            assert "cleaned:" in result
            assert len(progress_calls) > 0
