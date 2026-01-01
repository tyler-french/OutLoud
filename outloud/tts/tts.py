import glob
import io
import logging
import os
import platform
import re
import tempfile
from pathlib import Path
from typing import Callable

try:
    from python.runfiles import runfiles

    _runfiles = runfiles.Create()
except ImportError:
    _runfiles = None


def _configure_espeak():
    system = platform.system()
    if system == "Darwin":
        paths = [
            "/opt/homebrew/share/espeak-ng-data",
            "/usr/local/share/espeak-ng-data",
        ]
        paths.extend(glob.glob("/opt/homebrew/Cellar/espeak-ng/*/share/espeak-ng-data"))
        paths.extend(glob.glob("/usr/local/Cellar/espeak-ng/*/share/espeak-ng-data"))
        for path in paths:
            if Path(path).exists():
                os.environ["ESPEAK_DATA_PATH"] = path
                return
        raise RuntimeError("espeak-ng not found. Install with: brew install espeak-ng")
    elif system == "Linux":
        if _runfiles:
            lib = _runfiles.Rlocation(
                "bazel_linux_packages++apt+espeak_ng/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1"
            )
            data = _runfiles.Rlocation(
                "bazel_linux_packages++apt+espeak_ng/usr/lib/x86_64-linux-gnu/espeak-ng-data/phontab"
            )
            pcaudio = _runfiles.Rlocation(
                "bazel_linux_packages++apt+espeak_ng/usr/lib/x86_64-linux-gnu/libpcaudio.so.0"
            )
            sonic = _runfiles.Rlocation(
                "bazel_linux_packages++apt+espeak_ng/usr/lib/x86_64-linux-gnu/libsonic.so.0"
            )
            if lib and data:
                import ctypes

                if sonic:
                    ctypes.CDLL(str(Path(sonic).resolve()), mode=ctypes.RTLD_GLOBAL)
                if pcaudio:
                    ctypes.CDLL(str(Path(pcaudio).resolve()), mode=ctypes.RTLD_GLOBAL)
                os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = str(Path(lib).resolve())
                os.environ["ESPEAK_DATA_PATH"] = str(Path(data).resolve().parent)
                return
        if Path("/usr/lib/x86_64-linux-gnu/espeak-ng-data").exists():
            os.environ["ESPEAK_DATA_PATH"] = "/usr/lib/x86_64-linux-gnu/espeak-ng-data"
            return
        raise RuntimeError(
            "espeak-ng not found. Install with: apt install espeak-ng-data"
        )
    else:
        raise RuntimeError(f"Unsupported platform: {system}")


_configure_espeak()

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kokoro_onnx import Kokoro  # noqa: E402
from pydub import AudioSegment  # noqa: E402

logging.getLogger("phonemizer").setLevel(logging.ERROR)
logging.getLogger("kokoro_onnx").setLevel(logging.ERROR)

_BITRATE = "192k"


def _find_model_paths() -> tuple[Path, Path]:
    if _runfiles:
        model_path = _runfiles.Rlocation("kokoro_model/file/kokoro-v1.0.onnx")
        voices_path = _runfiles.Rlocation("kokoro_voices/file/voices-v1.0.bin")
        if model_path and voices_path:
            return Path(model_path), Path(voices_path)
    for base in [Path.cwd(), Path(__file__).parent, Path.home() / ".outloud"]:
        model = base / "kokoro-v1.0.onnx"
        voices = base / "voices-v1.0.bin"
        if model.exists() and voices.exists():
            return model, voices
    raise RuntimeError(
        "Kokoro model files not found. Run with Bazel or place model files in working directory."
    )


MODEL_PATH, VOICES_PATH = _find_model_paths()
_kokoro = None


def get_kokoro() -> Kokoro:
    global _kokoro
    if _kokoro is None:
        _kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
    return _kokoro


def split_into_chunks(text: str, max_chars: int = 350) -> list[str]:
    """Split text into chunks that are conservative for the TTS phoneme limit."""
    abbreviations = r"(?<!\bMr)(?<!\bMrs)(?<!\bDr)(?<!\bMs)(?<!\bProf)(?<!\bSr)(?<!\bJr)(?<!\bvs)(?<!\betc)(?<!\be\.g)(?<!\bi\.e)(?<!\bNo)(?<!\bSt)"
    pattern = abbreviations + r'(?<=[.!?])\s+(?=[A-Z"\']|$)'
    sentences = [s.strip() for s in re.split(pattern, text) if s.strip()]

    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) + 1 <= max_chars:
            current_chunk += sentence + " "
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            if len(sentence) > max_chars:
                parts = re.split(r"[,;:]\s+", sentence)
                for part in parts:
                    if len(part) <= max_chars:
                        chunks.append(part.strip())
                    else:
                        for i in range(0, len(part), max_chars):
                            chunks.append(part[i : i + max_chars].strip())
                current_chunk = ""
            else:
                current_chunk = sentence + " "

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return [c for c in chunks if c] if chunks else [text]


def _generate_chunk_audio(
    kokoro, chunk: str, voice: str, speed: float, max_retries: int = 3
):
    """Generate audio for a single chunk, retrying with smaller pieces if needed."""
    try:
        samples, sample_rate = kokoro.create(chunk, voice=voice, speed=speed)
        return samples, sample_rate
    except IndexError as e:
        if "510" in str(e) and max_retries > 0:
            mid = len(chunk) // 2
            space_pos = chunk.rfind(" ", 0, mid)
            if space_pos > 0:
                mid = space_pos

            part1 = chunk[:mid].strip()
            part2 = chunk[mid:].strip()

            samples1, sr = _generate_chunk_audio(
                kokoro, part1, voice, speed, max_retries - 1
            )
            samples2, sr = _generate_chunk_audio(
                kokoro, part2, voice, speed, max_retries - 1
            )

            return np.concatenate([samples1, samples2]), sr
        raise


def generate_audio_chunked(
    text: str,
    output_path: str,
    voice: str = "am_adam",
    speed: float = 1.0,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> str:
    kokoro = get_kokoro()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    chunks = split_into_chunks(text)
    total_chunks = len(chunks)
    all_samples = []
    sample_rate = 24000

    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(
                i + 1, total_chunks, f"Processing chunk {i + 1}/{total_chunks}"
            )
        samples, sample_rate = _generate_chunk_audio(kokoro, chunk, voice, speed)
        all_samples.append(samples)

    if progress_callback:
        progress_callback(total_chunks, total_chunks, "Combining audio...")

    combined = np.concatenate(all_samples)
    wav_path = output_path.with_suffix(".wav")
    sf.write(str(wav_path), combined, sample_rate)

    if progress_callback:
        progress_callback(total_chunks, total_chunks, "Converting to MP3...")

    audio = AudioSegment.from_wav(str(wav_path))
    audio.export(str(output_path), format="mp3", bitrate=_BITRATE)
    wav_path.unlink()

    if progress_callback:
        progress_callback(total_chunks, total_chunks, "Complete!")

    return str(output_path)


def generate_audio(
    text: str, output_path: str, voice: str = "am_adam", speed: float = 1.0
) -> str:
    return generate_audio_chunked(text, output_path, voice, speed)


def generate_preview(voice: str, speed: float = 1.0) -> bytes:
    """Generate a short voice preview and return MP3 bytes."""
    kokoro = get_kokoro()

    voices = {v["id"]: v for v in get_available_voices()}
    if voice not in voices:
        raise ValueError(f"Invalid voice ID: {voice}")
    voice_info = voices[voice]
    preview_text = f"Hi, I'm {voice_info['name']}. I'll be reading your articles."

    samples, sample_rate = kokoro.create(preview_text, voice=voice, speed=speed)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_file:
        wav_path = wav_file.name

    try:
        sf.write(wav_path, samples, sample_rate)
        audio = AudioSegment.from_wav(wav_path)
    finally:
        Path(wav_path).unlink(missing_ok=True)

    mp3_buffer = io.BytesIO()
    audio.export(mp3_buffer, format="mp3", bitrate=_BITRATE)
    mp3_buffer.seek(0)
    return mp3_buffer.read()


def get_available_voices() -> list[dict]:
    return [
        {"id": "am_adam", "name": "Adam", "lang": "American English", "gender": "Male"},
        {
            "id": "am_michael",
            "name": "Michael",
            "lang": "American English",
            "gender": "Male",
        },
        {
            "id": "af_heart",
            "name": "Heart",
            "lang": "American English",
            "gender": "Female",
        },
        {
            "id": "af_bella",
            "name": "Bella",
            "lang": "American English",
            "gender": "Female",
        },
        {
            "id": "af_nicole",
            "name": "Nicole",
            "lang": "American English",
            "gender": "Female",
        },
        {
            "id": "af_sarah",
            "name": "Sarah",
            "lang": "American English",
            "gender": "Female",
        },
        {"id": "af_sky", "name": "Sky", "lang": "American English", "gender": "Female"},
        {
            "id": "bf_emma",
            "name": "Emma",
            "lang": "British English",
            "gender": "Female",
        },
        {
            "id": "bf_isabella",
            "name": "Isabella",
            "lang": "British English",
            "gender": "Female",
        },
        {
            "id": "bm_george",
            "name": "George",
            "lang": "British English",
            "gender": "Male",
        },
        {
            "id": "bm_lewis",
            "name": "Lewis",
            "lang": "British English",
            "gender": "Male",
        },
    ]
