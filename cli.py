import argparse
import sys
import time
from pathlib import Path

import cleaner
import extractor
import tts


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Convert PDF to audio")
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument(
        "-o", "--output", help="Output MP3 path (default: <pdf_name>.mp3)"
    )
    parser.add_argument(
        "-v", "--voice", default="af_heart", help="Voice to use (default: af_heart)"
    )
    parser.add_argument(
        "--speed", type=float, default=1.0, help="Speech speed (default: 1.0)"
    )
    parser.add_argument(
        "--no-cleanup", action="store_true", help="Skip LLM text cleanup"
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or pdf_path.with_suffix(".mp3")

    log(f"Processing: {pdf_path}")

    log("Extracting text from PDF...")
    title, text = extractor.extract_from_pdf(str(pdf_path))
    log(f"Extracted {len(text)} characters, title: {title}")

    if not args.no_cleanup and cleaner.is_ollama_running():
        log("Cleaning text with Ollama...")
        try:
            text = cleaner.cleanup_text_chunked(
                text,
                progress_callback=lambda c, t, s: log(f"  Cleaning [{c}/{t}]: {s}"),
            )
            log(f"Cleaned text: {len(text)} characters")
        except Exception as e:
            log(f"Cleanup failed, using raw text: {e}")
    elif not args.no_cleanup:
        log("Skipping cleanup (Ollama not running)")

    log(f"Generating audio with voice '{args.voice}'...")
    tts.generate_audio_chunked(
        text,
        str(output_path),
        voice=args.voice,
        speed=args.speed,
        progress_callback=lambda c, t, s: log(f"  [{c}/{t}] {s}"),
    )

    file_size = Path(output_path).stat().st_size
    log(f"Done! Output: {output_path} ({file_size:,} bytes)")


if __name__ == "__main__":
    main()
