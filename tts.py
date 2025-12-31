import glob
import io
import os
import re
import tempfile
from pathlib import Path
from typing import Callable

for _pattern in [
    "/opt/homebrew/Cellar/espeak-ng/*/share/espeak-ng-data",
    "/usr/local/Cellar/espeak-ng/*/share/espeak-ng-data",
]:
    _matches = glob.glob(_pattern)
    if _matches and Path(_matches[0] + "/phontab").exists():
        os.environ["ESPEAK_DATA_PATH"] = _matches[0]
        break
else:
    for _path in [
        "/opt/homebrew/share/espeak-ng-data",
        "/usr/local/share/espeak-ng-data",
        "/usr/share/espeak-ng-data",
        "/usr/lib/x86_64-linux-gnu/espeak-ng-data",
    ]:
        if Path(_path + "/phontab").exists():
            os.environ["ESPEAK_DATA_PATH"] = _path
            break

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from kokoro_onnx import Kokoro  # noqa: E402
from pydub import AudioSegment  # noqa: E402

try:
    from python.runfiles import runfiles
except ImportError:
    runfiles = None

_BITRATE = "192k"


def _find_model_paths() -> tuple[Path, Path]:
    if runfiles:
        r = runfiles.Create()
        if r:
            model_path = r.Rlocation("+_repo_rules+kokoro_model/file/kokoro-v1.0.onnx")
            voices_path = r.Rlocation("+_repo_rules+kokoro_voices/file/voices-v1.0.bin")
            if model_path and voices_path:
                return Path(model_path), Path(voices_path)

    base_dir = Path(__file__).parent
    return base_dir / "kokoro-v1.0.onnx", base_dir / "voices-v1.0.bin"


MODEL_PATH, VOICES_PATH = _find_model_paths()
_kokoro = None


def get_kokoro() -> Kokoro:
    global _kokoro
    if _kokoro is None:
        _kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
    return _kokoro


def split_into_chunks(text: str, max_chars: int = 1000) -> list[str]:
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
                paragraphs = sentence.split("\n\n")
                for para in paragraphs:
                    if len(para) <= max_chars:
                        chunks.append(para.strip())
                    else:
                        for i in range(0, len(para), max_chars):
                            chunks.append(para[i : i + max_chars].strip())
                current_chunk = ""
            else:
                current_chunk = sentence + " "

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks if chunks else [text]


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
        samples, sample_rate = kokoro.create(chunk, voice=voice, speed=speed)
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
    voice_info = voices.get(voice, {"name": "this voice"})
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
