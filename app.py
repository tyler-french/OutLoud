import json
import queue
import threading
import uuid

from flask import Flask, render_template, request, jsonify, send_file, Response
from werkzeug.utils import secure_filename

import db
import extractor
import tts
import cleaner
from config import TEXTS_DIR, AUDIO_DIR, UPLOAD_DIR

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max upload

progress_queues: dict[str, queue.Queue] = {}


@app.route("/")
def index():
    articles = db.get_all_articles()
    voices = tts.get_available_voices()
    return render_template("index.html", articles=articles, voices=voices)


@app.route("/process/url", methods=["POST"])
def process_url():
    data = request.get_json()
    url = data.get("url", "").strip()
    voice = data.get("voice", "am_adam")

    if not url:
        return jsonify({"error": "URL is required"}), 400

    task_id = str(uuid.uuid4())[:8]
    progress_queues[task_id] = queue.Queue()

    def process_task():
        try:
            q = progress_queues[task_id]

            q.put({"status": "Extracting text...", "percent": 10})
            title, text = extractor.extract_from_url(url)

            file_id = str(uuid.uuid4())[:8]
            txt_filename = f"{file_id}.txt"
            txt_path = TEXTS_DIR / txt_filename
            extractor.save_text(text, str(txt_path))

            article_id = db.create_article(
                title=title, source_type="url", source_path=url, txt_path=txt_filename
            )

            if cleaner.is_ollama_running():
                q.put({"status": "Cleaning text...", "percent": 30})
                try:
                    cleaned = cleaner.cleanup_text_chunked(
                        text,
                        progress_callback=lambda c, t, s: q.put(
                            {
                                "status": f"Cleaning: {s}",
                                "percent": 30 + int((c / t) * 20),
                            }
                        ),
                    )
                    txt_path.write_text(cleaned, encoding="utf-8")
                    text = cleaned
                except Exception as e:
                    q.put({"status": f"Cleanup skipped: {str(e)[:50]}", "percent": 50})
            else:
                q.put(
                    {"status": "Skipping cleanup (Ollama not running)", "percent": 50}
                )

            q.put({"status": "Generating audio...", "percent": 55})
            mp3_filename = f"{file_id}.mp3"
            mp3_path = AUDIO_DIR / mp3_filename

            tts.generate_audio_chunked(
                text,
                str(mp3_path),
                voice=voice,
                progress_callback=lambda c, t, s: q.put(
                    {"status": f"Audio: {s}", "percent": 55 + int((c / t) * 40)}
                ),
            )

            db.update_article_mp3(article_id, mp3_filename)

            article = db.get_article(article_id)
            q.put({"done": True, "article": article})

        except Exception as e:
            progress_queues[task_id].put({"error": str(e)})

    thread = threading.Thread(target=process_task)
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/process/pdf", methods=["POST"])
def process_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    voice = request.form.get("voice", "am_adam")

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "File must be a PDF"}), 400

    filename = secure_filename(file.filename)
    file_id = str(uuid.uuid4())[:8]
    pdf_filename = f"{file_id}_{filename}"
    pdf_path = UPLOAD_DIR / pdf_filename
    file.save(str(pdf_path))

    task_id = str(uuid.uuid4())[:8]
    progress_queues[task_id] = queue.Queue()

    def process_task():
        try:
            q = progress_queues[task_id]

            q.put({"status": "Parsing PDF...", "percent": 5})
            title, text = extractor.extract_from_pdf(str(pdf_path))

            q.put({"status": "Saving text...", "percent": 20})
            txt_filename = f"{file_id}.txt"
            txt_path = TEXTS_DIR / txt_filename
            extractor.save_text(text, str(txt_path))

            article_id = db.create_article(
                title=title,
                source_type="pdf",
                source_path=pdf_filename,
                txt_path=txt_filename,
            )

            if cleaner.is_ollama_running():
                q.put({"status": "Cleaning text...", "percent": 30})
                try:
                    cleaned = cleaner.cleanup_text_chunked(
                        text,
                        progress_callback=lambda c, t, s: q.put(
                            {
                                "status": f"Cleaning: {s}",
                                "percent": 30 + int((c / t) * 20),
                            }
                        ),
                    )
                    txt_path.write_text(cleaned, encoding="utf-8")
                    text = cleaned
                except Exception as e:
                    q.put({"status": f"Cleanup skipped: {str(e)[:50]}", "percent": 50})
            else:
                q.put(
                    {"status": "Skipping cleanup (Ollama not running)", "percent": 50}
                )

            q.put({"status": "Generating audio...", "percent": 55})
            mp3_filename = f"{file_id}.mp3"
            mp3_path = AUDIO_DIR / mp3_filename

            tts.generate_audio_chunked(
                text,
                str(mp3_path),
                voice=voice,
                progress_callback=lambda c, t, s: q.put(
                    {"status": f"Audio: {s}", "percent": 55 + int((c / t) * 40)}
                ),
            )

            db.update_article_mp3(article_id, mp3_filename)

            article = db.get_article(article_id)
            q.put({"done": True, "article": article})

        except Exception as e:
            progress_queues[task_id].put({"error": str(e)})

    thread = threading.Thread(target=process_task)
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/process/progress/<task_id>")
def process_progress(task_id):
    def event_stream():
        if task_id not in progress_queues:
            yield f"data: {json.dumps({'error': 'Task not found'})}\n\n"
            return

        q = progress_queues[task_id]
        while True:
            try:
                data = q.get(timeout=120)
                yield f"data: {json.dumps(data)}\n\n"

                if data.get("done") or data.get("error"):
                    del progress_queues[task_id]
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'status': 'Processing...'})}\n\n"

    return Response(event_stream(), mimetype="text/event-stream")


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
        if article["txt_path"]:
            txt_path = TEXTS_DIR / article["txt_path"]
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
    """Generate a short voice preview."""
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
    app.run(debug=True, port=5001)
