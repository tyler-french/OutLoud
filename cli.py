import argparse
import sys
import time
from pathlib import Path

from outloud import cleaner, extractor, tts


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Convert PDF or text to audio",
        epilog="Examples:\n"
        "  %(prog)s document.pdf\n"
        "  %(prog)s article.txt\n"
        "  %(prog)s -o output.mp3 document.pdf\n"
        "  echo 'Hello world' | %(prog)s -o hello.mp3\n"
        "  cat article.txt | %(prog)s -o article.mp3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input", nargs="?", help="Path to PDF or TXT file (omit to read from stdin)"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output MP3 path (required for stdin, default: <input>.mp3)",
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
    parser.add_argument(
        "--list-voices", action="store_true", help="List available voices and exit"
    )
    args = parser.parse_args()

    if args.list_voices:
        voices = tts.get_available_voices()
        print("Available voices:")
        for v in voices:
            print(f"  {v['id']:15} {v['name']:10} ({v['gender']}, {v['lang']})")
        sys.exit(0)

    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: File not found: {input_path}", file=sys.stderr)
            sys.exit(1)

        output_path = args.output or input_path.with_suffix(".mp3")
        suffix = input_path.suffix.lower()

        log(f"Processing: {input_path}")

        if suffix == ".pdf":
            log("Extracting text from PDF...")
            title, text = extractor.extract_from_pdf(str(input_path))
            log(f"Extracted {len(text)} characters, title: {title}")
        elif suffix == ".txt":
            log("Reading text file...")
            text = input_path.read_text(encoding="utf-8")
            log(f"Read {len(text)} characters")
        else:
            print(
                f"Error: Unsupported file type '{suffix}'. Use .pdf or .txt",
                file=sys.stderr,
            )
            sys.exit(1)

    elif not sys.stdin.isatty():
        if not args.output:
            print(
                "Error: -o/--output is required when reading from stdin",
                file=sys.stderr,
            )
            sys.exit(1)

        output_path = args.output
        log("Reading text from stdin...")
        text = sys.stdin.read().strip()

        if not text:
            print("Error: No text provided", file=sys.stderr)
            sys.exit(1)

        log(f"Read {len(text)} characters from stdin")

    else:
        parser.print_help()
        sys.exit(1)

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
