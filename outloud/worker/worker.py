"""Background worker for processing articles."""

import logging
import threading
import uuid

from outloud import db, extractor, cleaner, tts
from outloud.config import TEXTS_DIR, AUDIO_DIR, UPLOAD_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_worker_thread: threading.Thread | None = None
_wake_event = threading.Event()


def _ensure_ollama_running():
    import os
    import shutil
    import subprocess
    import time
    import requests

    def is_ollama_ready():
        try:
            requests.get("http://localhost:11434/api/tags", timeout=1)
            return True
        except Exception:
            return False

    if is_ollama_ready():
        return

    ollama_paths = [
        shutil.which("ollama"),
        "/usr/local/bin/ollama",
        "/usr/bin/ollama",
        os.path.expanduser("~/.local/bin/ollama"),
        os.path.expanduser("~/bin/ollama"),
    ]
    ollama_bin = next((p for p in ollama_paths if p and os.path.isfile(p)), None)

    if not ollama_bin:
        logger.warning("Ollama not found - text cleanup will be skipped")
        return

    try:
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning(f"Could not start Ollama: {e} - text cleanup will be skipped")
        return

    for _ in range(30):
        time.sleep(0.5)
        if is_ollama_ready():
            logger.info("Ollama started successfully")
            return

    logger.warning(
        "Ollama failed to start within 15 seconds - text cleanup will be skipped"
    )


def _reset_in_progress_articles():
    """Reset articles left in intermediate stages back to queued after restart."""
    try:
        articles = db.get_all_articles()
    except Exception as e:
        logger.exception(f"Failed to load articles for recovery: {e}")
        return

    in_progress_stages = {"extracting", "cleaning", "generating"}
    for article in articles:
        stage = article.get("processing_stage")
        if stage in in_progress_stages:
            article_id = article.get("id")
            if article_id is None:
                continue
            try:
                logger.info(
                    f"Resetting article {article_id} from '{stage}' to 'queued' after restart"
                )
                db.update_article_stage(article_id, "queued")
            except Exception as e:
                logger.exception(f"Failed to reset article {article_id}: {e}")


def start_worker():
    global _worker_thread
    if _worker_thread is not None and _worker_thread.is_alive():
        return

    _ensure_ollama_running()
    _reset_in_progress_articles()
    _scan_uploads_directory()

    _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
    _worker_thread.start()
    logger.info("Background worker started")


def _scan_uploads_directory():
    import hashlib

    if not UPLOAD_DIR.exists():
        return

    tracked = {a["source_path"] for a in db.get_all_articles() if a.get("source_path")}

    for pdf_file in UPLOAD_DIR.glob("*.pdf"):
        if pdf_file.name in tracked:
            continue

        sha256 = hashlib.sha256()
        with open(pdf_file, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        content_hash = sha256.hexdigest()[:16]

        existing = db.get_article_by_hash(content_hash)
        if existing:
            logger.info(f"Skipping duplicate PDF: {pdf_file.name}")
            continue

        filename = pdf_file.name
        if "_" in filename:
            title = filename.split("_", 1)[1].replace(".pdf", "")
        else:
            title = filename.replace(".pdf", "")

        logger.info(f"Found untracked PDF: {filename}, creating article")
        db.create_article(
            title=title,
            source_type="pdf",
            source_path=filename,
            voice="af_heart",
            content_hash=content_hash,
        )


def notify_new_article():
    _wake_event.set()


def _worker_loop():
    while True:
        try:
            articles = db.get_articles_to_process()
            if not articles:
                _wake_event.clear()
                _wake_event.wait(timeout=30)
                continue

            for article in articles:
                _process_article(article)

        except (ConnectionError, TimeoutError, OSError) as e:
            logger.exception(f"Recoverable worker loop error: {e}")
            _wake_event.wait(timeout=5)
        except Exception as e:
            logger.exception(f"Unrecoverable worker loop error: {e}")
            raise


def _process_article(article: dict):
    article_id = article["id"]
    stage = article["processing_stage"]

    try:
        if stage in ("queued", "extracting"):
            _do_extraction(article)

        article = db.get_article(article_id)
        if not article:
            return
        stage = article["processing_stage"]

        if stage in ("extracted", "cleaning"):
            _do_cleaning(article)

        article = db.get_article(article_id)
        if not article:
            return
        stage = article["processing_stage"]

        if stage in ("cleaned", "generating"):
            _do_audio_generation(article)

    except Exception as e:
        logger.exception(f"Error processing article {article_id}: {e}")
        if db.get_article(article_id):
            db.set_article_error(article_id, str(e))


def _do_extraction(article: dict):
    article_id = article["id"]
    source_type = article["source_type"]
    source_path = article["source_path"]
    content_hash = article.get("content_hash") or str(uuid.uuid4())[:16]

    existing_raw = article.get("raw_txt_path")
    if existing_raw and (TEXTS_DIR / existing_raw).exists():
        logger.info(f"Article {article_id} already has raw text, skipping extraction")
        db.update_article_stage(article_id, "extracted")
        return

    db.update_article_stage(article_id, "extracting")
    logger.info(f"Extracting article {article_id} from {source_type}")

    if source_type == "pdf":
        pdf_path = UPLOAD_DIR / source_path
        title, text = extractor.extract_from_pdf(str(pdf_path))
    elif source_type == "url":
        title, text = extractor.extract_from_url(source_path)
    else:
        raise ValueError(f"Unknown source type: {source_type}")

    txt_filename = f"{content_hash}_raw.txt"
    txt_path = TEXTS_DIR / txt_filename
    extractor.save_text(text, str(txt_path))

    db.update_article_stage(
        article_id,
        "extracted",
        title=title,
        txt_path=txt_filename,
        raw_txt_path=txt_filename,
    )
    logger.info(f"Article {article_id} extracted: {title}")


def _do_cleaning(article: dict):
    article_id = article["id"]
    raw_txt_path = article["raw_txt_path"]
    content_hash = article.get("content_hash") or str(uuid.uuid4())[:16]

    if not raw_txt_path:
        raise ValueError(f"Article {article_id} has no raw text to clean")

    cleaned_filename = f"{content_hash}_cleaned.txt"
    cleaned_path = TEXTS_DIR / cleaned_filename
    if cleaned_path.exists():
        logger.info(f"Article {article_id} already has cleaned text, skipping cleanup")
        db.update_article_stage(
            article_id, "cleaned", cleaned_txt_path=cleaned_filename
        )
        return

    txt_path = TEXTS_DIR / raw_txt_path
    text = txt_path.read_text(encoding="utf-8")

    if not cleaner.is_ollama_running():
        logger.info(f"Ollama not running, skipping cleanup for article {article_id}")
        db.update_article_stage(article_id, "cleaned")
        return

    db.update_article_stage(article_id, "cleaning")
    logger.info(f"Cleaning article {article_id}")

    try:
        cleaned = cleaner.cleanup_text_chunked(text)

        cleaned_path.write_text(cleaned, encoding="utf-8")

        db.update_article_stage(
            article_id, "cleaned", cleaned_txt_path=cleaned_filename, was_cleaned=1
        )
        logger.info(f"Article {article_id} cleaned with LLM")

    except Exception as e:
        raise RuntimeError(f"Cleanup failed for article {article_id}: {e}")


def _do_audio_generation(article: dict):
    article_id = article["id"]
    source_txt = article["cleaned_txt_path"] or article["raw_txt_path"]
    voice = article["voice"] or "af_heart"
    content_hash = article.get("content_hash") or str(uuid.uuid4())[:16]

    if not source_txt:
        raise ValueError("No text available for audio generation")

    mp3_filename = f"{content_hash}_{voice}.mp3"
    mp3_path = AUDIO_DIR / mp3_filename

    if mp3_path.exists():
        logger.info(f"Article {article_id} already has audio, skipping generation")
        db.update_article_mp3(article_id, mp3_filename)
        return

    txt_path = TEXTS_DIR / source_txt
    text = txt_path.read_text(encoding="utf-8")

    db.update_article_stage(article_id, "generating")
    logger.info(f"Generating audio for article {article_id}")

    def progress_callback(current, total, status):
        progress_text = f"{current}/{total} chunks"
        db.update_article_progress(article_id, progress_text)

    tts.generate_audio_chunked(
        text, str(mp3_path), voice=voice, progress_callback=progress_callback
    )

    db.update_article_mp3(article_id, mp3_filename)
    logger.info(f"Article {article_id} audio complete")
