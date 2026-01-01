import hashlib
import logging
from urllib.parse import urlparse

from flask import Flask, render_template, request, jsonify, send_file, Response
from werkzeug.utils import secure_filename

from outloud import db, tts, worker
from outloud.config import TEXTS_DIR, AUDIO_DIR, UPLOAD_DIR


def compute_file_hash(file_storage) -> str:
    """Compute SHA256 hash of uploaded file."""
    sha256 = hashlib.sha256()
    file_storage.seek(0)
    for chunk in iter(lambda: file_storage.read(8192), b""):
        sha256.update(chunk)
    file_storage.seek(0)
    return sha256.hexdigest()[:16]


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


class StatusEndpointFilter(logging.Filter):
    def filter(self, record):
        return "/articles/status" not in record.getMessage()


logging.getLogger("werkzeug").addFilter(StatusEndpointFilter())


_valid_voices = None


def _get_valid_voices():
    global _valid_voices
    if _valid_voices is None:
        _valid_voices = {v["id"] for v in tts.get_available_voices()}
    return _valid_voices


@app.route("/")
def index():
    articles = db.get_all_articles()
    voices = tts.get_available_voices()
    return render_template("index.html", articles=articles, voices=voices)


@app.route("/process/url", methods=["POST"])
def process_url():
    data = request.get_json()
    url = data.get("url", "").strip()
    voice = data.get("voice", "af_heart")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    if voice not in _get_valid_voices():
        return jsonify({"error": f"Invalid voice ID: {voice}"}), 400

    if len(url) > 2048:
        return jsonify({"error": "URL too long"}), 400

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return jsonify({"error": "Invalid URL - must be HTTP or HTTPS"}), 400

    title = url if len(url) <= 50 else url[:47] + "..."

    article_id = db.create_article(
        title=title,
        source_type="url",
        source_path=url,
        voice=voice,
    )

    worker.notify_new_article()
    return jsonify({"article_id": article_id})


@app.route("/process/text", methods=["POST"])
def process_text():
    data = request.get_json()
    text = data.get("text", "").strip()
    title = data.get("title", "").strip() or "Pasted Text"
    voice = data.get("voice", "af_heart")

    if not text:
        return jsonify({"error": "Text is required"}), 400

    if voice not in _get_valid_voices():
        return jsonify({"error": f"Invalid voice ID: {voice}"}), 400

    if len(text) < 10:
        return jsonify({"error": "Text too short"}), 400

    content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

    txt_filename = f"{content_hash}_raw.txt"
    txt_path = TEXTS_DIR / txt_filename
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.write_text(text, encoding="utf-8")

    article_id = db.create_article(
        title=title[:100],
        source_type="text",
        source_path="",
        txt_path=txt_filename,
        voice=voice,
        content_hash=content_hash,
    )

    db.update_article_stage(article_id, "extracted", raw_txt_path=txt_filename)

    worker.notify_new_article()
    return jsonify({"article_id": article_id})


@app.route("/process/pdf", methods=["POST"])
def process_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    voice = request.form.get("voice", "af_heart")

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if voice not in _get_valid_voices():
        return jsonify({"error": f"Invalid voice ID: {voice}"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "File must be a PDF"}), 400

    content_hash = compute_file_hash(file)
    existing = db.get_article_by_hash(content_hash)
    if existing:
        return jsonify({"article_id": existing["id"], "duplicate": True})

    filename = secure_filename(file.filename)
    pdf_filename = f"{content_hash}_{filename}"
    pdf_path = UPLOAD_DIR / pdf_filename
    file.save(str(pdf_path))

    article_id = db.create_article(
        title=filename.replace(".pdf", ""),
        source_type="pdf",
        source_path=pdf_filename,
        voice=voice,
        content_hash=content_hash,
    )

    worker.notify_new_article()
    return jsonify({"article_id": article_id})


@app.route("/import/pdfs", methods=["POST"])
def import_pdfs():
    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    voice = request.form.get("voice", "af_heart")

    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "No files selected"}), 400

    if voice not in _get_valid_voices():
        return jsonify({"error": f"Invalid voice ID: {voice}"}), 400

    article_ids = []
    duplicates = []
    for file in files:
        if file.filename == "" or not file.filename.lower().endswith(".pdf"):
            continue

        content_hash = compute_file_hash(file)
        existing = db.get_article_by_hash(content_hash)
        if existing:
            duplicates.append(existing["id"])
            continue

        filename = secure_filename(file.filename)
        pdf_filename = f"{content_hash}_{filename}"
        pdf_path = UPLOAD_DIR / pdf_filename
        file.save(str(pdf_path))

        article_id = db.create_article(
            title=filename.replace(".pdf", ""),
            source_type="pdf",
            source_path=pdf_filename,
            voice=voice,
            content_hash=content_hash,
        )
        article_ids.append(article_id)

    if article_ids:
        worker.notify_new_article()

    return jsonify(
        {
            "article_ids": article_ids,
            "count": len(article_ids),
            "duplicates": duplicates,
        }
    )


@app.route("/article/<int:article_id>/reprocess", methods=["POST"])
def reprocess_article(article_id):
    article = db.get_article(article_id)
    if not article:
        return jsonify({"error": "Article not found"}), 404

    db.reset_article_for_reprocessing(article_id)
    worker.notify_new_article()
    return jsonify({"success": True})


@app.route("/article/<int:article_id>/clean", methods=["POST"])
def clean_article(article_id):
    article = db.get_article(article_id)
    if not article:
        return jsonify({"error": "Article not found"}), 404

    if article["processing_stage"] not in ("ready", "completed", "error"):
        return jsonify({"error": "Article is still processing"}), 400

    if not article.get("raw_txt_path"):
        return jsonify({"error": "No raw text available"}), 400

    db.reset_article_for_cleaning(article_id)
    worker.notify_new_article()
    return jsonify({"success": True})


@app.route("/article/<int:article_id>/regenerate", methods=["POST"])
def regenerate_article(article_id):
    article = db.get_article(article_id)
    if not article:
        return jsonify({"error": "Article not found"}), 404

    if article["processing_stage"] not in ("ready", "completed", "error"):
        return jsonify({"error": "Article is still processing"}), 400

    if not article.get("cleaned_txt_path"):
        return jsonify({"error": "No text available"}), 400

    cleaned_txt_path = TEXTS_DIR / article["cleaned_txt_path"]
    if not cleaned_txt_path.exists():
        return jsonify({"error": "Text file not found"}), 400

    data = request.get_json() or {}
    voice = data.get("voice", article.get("voice", "af_heart"))

    if voice not in _get_valid_voices():
        return jsonify({"error": f"Invalid voice ID: {voice}"}), 400

    db.reset_article_for_audio(article_id, voice)
    worker.notify_new_article()
    return jsonify({"success": True})


@app.route("/articles/status")
def articles_status():
    articles = db.get_all_articles()
    return jsonify(articles)


@app.route("/complete/<int:article_id>", methods=["PUT"])
def mark_complete(article_id):
    article = db.get_article(article_id)
    if not article:
        return jsonify({"error": "Article not found"}), 404

    db.mark_article_completed(article_id)
    return jsonify({"success": True})


@app.route("/article/<int:article_id>", methods=["GET", "DELETE"])
def article_endpoint(article_id):
    article = db.get_article(article_id)
    if not article:
        return jsonify({"error": "Article not found"}), 404

    if request.method == "DELETE":
        for txt_field in ["txt_path", "raw_txt_path", "cleaned_txt_path"]:
            if article.get(txt_field):
                txt_path = TEXTS_DIR / article[txt_field]
                if txt_path.exists():
                    txt_path.unlink()

        if article["mp3_path"]:
            mp3_path = AUDIO_DIR / article["mp3_path"]
            if mp3_path.exists():
                mp3_path.unlink()

        if article["source_type"] == "pdf" and article["source_path"]:
            pdf_path = UPLOAD_DIR / article["source_path"]
            if pdf_path.exists():
                pdf_path.unlink()

        db.delete_article(article_id)
        return jsonify({"success": True})

    return jsonify(article)


@app.route("/preview/voice/<voice_id>")
def preview_voice(voice_id):
    voices = {v["id"]: v for v in tts.get_available_voices()}
    if voice_id not in voices:
        return jsonify({"error": "Voice not found"}), 404

    try:
        mp3_bytes = tts.generate_preview(voice_id)
        return Response(
            mp3_bytes,
            mimetype="audio/mpeg",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/audio/<int:article_id>")
def serve_audio(article_id):
    article = db.get_article(article_id)
    if not article or not article["mp3_path"]:
        return jsonify({"error": "Audio not found"}), 404

    mp3_path = AUDIO_DIR / article["mp3_path"]
    if not mp3_path.exists():
        return jsonify({"error": "Audio file not found"}), 404

    return send_file(str(mp3_path), mimetype="audio/mpeg")


if __name__ == "__main__":
    worker.start_worker()
    app.run(debug=True, port=5001, use_reloader=False)
