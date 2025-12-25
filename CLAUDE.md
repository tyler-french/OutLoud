# OutLoud

Web-based text-to-speech that converts articles and PDFs to audio using Kokoro TTS.

## Run

```bash
bazel run //:app    # http://localhost:5001
```

## System Dependencies

**macOS:** `brew install ffmpeg libsndfile`
**Linux:** `apt install ffmpeg libsndfile1`

## Architecture

```
app.py        - Flask routes, SSE streaming
├── extractor.py  - URL/PDF text extraction
├── cleaner.py    - LLM text cleanup (Ollama)
├── tts.py        - Kokoro-ONNX audio generation
├── db.py         - SQLite operations
└── config.py     - Path configuration
```

## Data Storage

User data stored in `~/.outloud/`:
- `reader.db` - SQLite database
- `texts/` - Extracted text files
- `audio/` - Generated MP3 files
- `uploads/` - Uploaded PDFs

Override with `OUTLOUD_DATA_DIR` env var.

## Bazel Commands

```bash
bazel build //...              # Build all
bazel run //:app               # Run app
bazel run //:requirements.update  # Update lock file
```
