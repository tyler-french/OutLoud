import os
import tempfile

import pytest


@pytest.fixture
def test_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["OUTLOUD_DATA_DIR"] = tmpdir
        import importlib

        import outloud.config
        import outloud.db

        importlib.reload(outloud.config)
        importlib.reload(outloud.db)

        yield outloud.db

        del os.environ["OUTLOUD_DATA_DIR"]


def test_create_and_get_article(test_db):
    article_id = test_db.create_article(
        title="Test Article",
        source_type="url",
        source_path="https://example.com",
        voice="am_adam",
    )

    article = test_db.get_article(article_id)
    assert article is not None
    assert article["title"] == "Test Article"
    assert article["source_type"] == "url"
    assert article["voice"] == "am_adam"
    assert article["processing_stage"] == "queued"


def test_update_article_stage(test_db):
    article_id = test_db.create_article(
        title="Test", source_type="url", source_path="https://example.com"
    )

    test_db.update_article_stage(article_id, "extracting")
    article = test_db.get_article(article_id)
    assert article["processing_stage"] == "extracting"

    test_db.update_article_stage(article_id, "extracted", title="Updated Title")
    article = test_db.get_article(article_id)
    assert article["processing_stage"] == "extracted"
    assert article["title"] == "Updated Title"


def test_update_article_stage_invalid_stage(test_db):
    article_id = test_db.create_article(
        title="Test", source_type="url", source_path="https://example.com"
    )

    with pytest.raises(ValueError, match="Invalid processing stage"):
        test_db.update_article_stage(article_id, "invalid_stage")


def test_get_articles_to_process(test_db):
    test_db.create_article(title="A", source_type="url", source_path="a")
    test_db.create_article(title="B", source_type="url", source_path="b")

    articles = test_db.get_articles_to_process()
    assert len(articles) == 2


def test_set_article_error(test_db):
    article_id = test_db.create_article(
        title="Test", source_type="url", source_path="https://example.com"
    )

    test_db.set_article_error(article_id, "Something went wrong")

    article = test_db.get_article(article_id)
    assert article["processing_stage"] == "error"
    assert article["error"] == "Something went wrong"


def test_delete_article(test_db):
    article_id = test_db.create_article(
        title="Test", source_type="url", source_path="https://example.com"
    )

    test_db.delete_article(article_id)
    assert test_db.get_article(article_id) is None
