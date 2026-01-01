import tempfile
from pathlib import Path


def test_clean_markdown_for_tts():
    from outloud.extractor import clean_markdown_for_tts

    markdown = """# Title

This is a paragraph with a [link](http://example.com).

Reference [1] and [2,3] should be removed.

`code` should be removed.

```python
def foo():
    pass
```

Email: test@example.com

Figure 1: A caption to remove.
"""

    cleaned = clean_markdown_for_tts(markdown)

    assert "http://example.com" not in cleaned
    assert "[1]" not in cleaned
    assert "[2,3]" not in cleaned
    assert "`code`" not in cleaned
    assert "def foo():" not in cleaned
    assert "test@example.com" not in cleaned
    assert "Figure 1:" not in cleaned
    assert "Title" in cleaned
    assert "paragraph" in cleaned


def test_extract_title_from_text():
    from outloud.extractor import extract_title_from_text

    text = """
Short.

This is a Valid Title for the Document

More content here.
"""
    title = extract_title_from_text(text)
    assert title == "This is a Valid Title for the Document"


def test_extract_title_from_text_with_markdown():
    from outloud.extractor import extract_title_from_text

    text = "## The Article Title\n\nSome content."
    title = extract_title_from_text(text)
    assert title == "The Article Title"


def test_save_text():
    from outloud.extractor import save_text

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "subdir" / "test.txt"
        result = save_text("Hello World", str(output_path))

        assert Path(result).exists()
        assert Path(result).read_text() == "Hello World"
