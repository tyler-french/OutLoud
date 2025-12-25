# OutLoud

Web-based text-to-speech that converts articles and PDFs to audio using Kokoro TTS. Optionally cleans text with a local LLM before synthesis.

## Features

- **URL Import** - Paste any article URL to extract and convert to audio
- **PDF Import** - Upload PDFs with smart column/layout detection (via marker-pdf)
- **Text Cleanup** - Automatically clean text using local LLM (Ollama) if running
- **TTS Generation** - High-quality speech synthesis using Kokoro-ONNX
- **Multiple Voices** - 11 voices: American/British, Male/Female options
- **Library** - Track pending and completed readings

## Quick Start

```bash
# Install system dependencies
# macOS:
brew install ffmpeg libsndfile

# Linux:
sudo apt install ffmpeg libsndfile1

# Run the app
bazel run //:app
```

Open **http://localhost:5001** in your browser.

## Architecture

```
app.py          Flask routes, SSE streaming
├── extractor.py    URL/PDF text extraction
├── cleaner.py      LLM text cleanup (Ollama)
├── tts.py          Kokoro-ONNX audio generation
├── db.py           SQLite operations
└── config.py       Path configuration
```

## Components

### Text Extraction (`extractor.py`)

**URL Extraction:**
- Uses `trafilatura` for clean article text extraction
- Automatically extracts title and removes boilerplate

**PDF Extraction:**
- Uses `marker-pdf` for ML-powered PDF parsing
- Handles multi-column layouts and academic papers
- Cleans markdown output for TTS (removes images, code blocks, references)

### Text Cleanup (`cleaner.py`)

Optional cleanup using Ollama with `llama3.2:1b`. Runs automatically if Ollama is available.

**What it removes:**
- Reference markers `[1]`, `[2,3]`
- Author affiliations, emails, page numbers
- Acknowledgments and funding sections

**What it preserves:**
- Original author language and words
- Sentence structure (no paraphrasing)
- All substantive content

### TTS Generation (`tts.py`)

Uses Kokoro-ONNX for speech synthesis:

- **Model**: kokoro-v1.0.onnx (310MB)
- **Voices**: voices-v1.0.bin (27MB)
- **Sample Rate**: 24kHz
- **Output**: MP3 (192kbps)

Processes text in chunks with progress reporting.

### Database (`db.py`)

SQLite database stored at `~/.outloud/reader.db`:
- Article metadata (title, source URL/PDF path)
- File paths (txt, mp3)
- Status (pending → ready → completed)

## Data Storage

User data is stored in `~/.outloud/`:

```
~/.outloud/
├── reader.db     SQLite database
├── texts/        Extracted text files
├── audio/        Generated MP3 files
└── uploads/      Uploaded PDFs
```

Override location with `OUTLOUD_DATA_DIR` environment variable.

## Voices

| ID | Name | Accent | Gender |
|-----|------|--------|--------|
| am_adam | Adam | American | Male |
| am_michael | Michael | American | Male |
| af_heart | Heart | American | Female |
| af_bella | Bella | American | Female |
| af_nicole | Nicole | American | Female |
| af_sarah | Sarah | American | Female |
| af_sky | Sky | American | Female |
| bf_emma | Emma | British | Female |
| bf_isabella | Isabella | British | Female |
| bm_george | George | British | Male |
| bm_lewis | Lewis | British | Male |

## Bazel Commands

```bash
bazel build //...                 # Build all targets
bazel run //:app                  # Run the app
bazel run //:requirements.update  # Update requirements.lock
```

## Optional: Text Cleanup with Ollama

For automatic text cleanup before TTS:

```bash
# Install Ollama (https://ollama.ai)
# Pull the model
ollama pull llama3.2:1b

# Start Ollama (in a separate terminal)
ollama serve
```

The app will automatically use Ollama for text cleanup if it's running. If not, it skips cleanup and uses the raw extracted text.

## Usage

1. **Import** - Paste a URL and press Enter, or drag/drop a PDF
2. **Wait** - Progress shows extraction → cleanup → audio generation
3. **Listen** - Click Play on completed items
4. **Done** - Mark items as completed to filter them

## Development

### Project Structure

```
outloud/
├── app.py              # Flask application
├── db.py               # Database operations
├── extractor.py        # URL/PDF text extraction
├── tts.py              # Kokoro TTS wrapper
├── cleaner.py          # Ollama text cleanup
├── config.py           # Path configuration
├── templates/
│   └── index.html      # Web UI template
├── static/
│   ├── style.css       # Styling
│   └── app.js          # Frontend logic
├── BUILD.bazel         # Bazel build rules
├── MODULE.bazel        # Bazel module definition
├── requirements.txt    # Python dependencies
└── requirements.lock   # Locked dependencies
```

### Adding Dependencies

1. Add to `requirements.txt`
2. Run `bazel run //:requirements.update`
3. Add to `deps` in `BUILD.bazel`
