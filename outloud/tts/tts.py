import ctypes
import glob
import io
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

MAGIC_DIVISOR = 80.0
SAMPLE_RATE = 24000


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
import onnxruntime as ort  # noqa: E402
import soundfile as sf  # noqa: E402
from kokoro_onnx import Kokoro  # noqa: E402
from misaki import en, espeak  # noqa: E402
from pydub import AudioSegment  # noqa: E402

_BITRATE = "192k"


def _get_vocab() -> dict[str, int]:
    _pad = "$"
    _punctuation = ';:,.!?¡¿—…"«»"" '
    _letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    _letters_ipa = "ɑɐɒæɓʙβɔɕçɗɖðʤəɘɚɛɜɝɞɟʄɡɠɢʛɦɧħɥʜɨɪʝɭɬɫɮʟɱɯɰŋɳɲɴøɵɸθœɶʘɹɺɾɻʀʁɽʂʃʈʧʉʊʋⱱʌɣɤʍχʎʏʑʐʒʔʡʕʢǀǁǂǃˈˌːˑʼʴʰʱʲʷˠˤ˞↓↑→↗↘'̩'ᵻ"
    symbols = [_pad] + list(_punctuation) + list(_letters) + list(_letters_ipa)
    return {symbols[i]: i for i in range(len(symbols))}


_VOCAB = _get_vocab()
_g2p = None


def _get_g2p():
    global _g2p
    if _g2p is None:
        fallback = espeak.EspeakFallback(british=False)
        _g2p = en.G2P(trf=False, british=False, fallback=fallback)
    return _g2p


def _tokenize_phonemes(phonemes: str) -> list[int]:
    return [i for i in map(_VOCAB.get, phonemes) if i is not None]


def _calculate_word_timestamps(
    tokens: list, pred_dur: np.ndarray, speed: float = 1.0
) -> list[dict]:
    if not tokens or len(pred_dur) < 3:
        return []

    timestamps = []
    left = right = 2 * max(0.0, float(pred_dur[0]) - 3.0)
    i = 1

    for token in tokens:
        if i >= len(pred_dur) - 1:
            break
        if not hasattr(token, "phonemes") or not token.phonemes:
            if hasattr(token, "whitespace") and token.whitespace:
                i += 1
                if i < len(pred_dur):
                    left = right + float(pred_dur[i])
                    right = left + float(pred_dur[i])
                    i += 1
            continue

        j = i + len(token.phonemes)
        if j >= len(pred_dur):
            break

        start_ts = left / MAGIC_DIVISOR / speed
        token_dur = float(pred_dur[i:j].sum())
        space_dur = (
            float(pred_dur[j])
            if (hasattr(token, "whitespace") and token.whitespace)
            else 0.0
        )
        left = right + (2 * token_dur) + space_dur
        end_ts = left / MAGIC_DIVISOR / speed
        right = left + space_dur
        i = j + (1 if (hasattr(token, "whitespace") and token.whitespace) else 0)

        word_text = token.text if hasattr(token, "text") else str(token)
        timestamps.append({"word": word_text, "start": start_ts, "end": end_ts})

    return timestamps


def _load_voice_data(voices_path: Path) -> dict[str, np.ndarray]:
    data = np.load(str(voices_path), allow_pickle=True)
    if isinstance(data, np.ndarray) and data.dtype == object:
        return data.item()
    return dict(data)


def _find_model_paths() -> tuple[Path, Path, Path | None]:
    timestamped_path = None
    if _runfiles:
        model_path = _runfiles.Rlocation("kokoro_model/file/kokoro-v1.0.onnx")
        voices_path = _runfiles.Rlocation("kokoro_voices/file/voices-v1.0.bin")
        ts_path = _runfiles.Rlocation(
            "kokoro_model_timestamped/file/kokoro-v1.0-timestamped.onnx"
        )
        if ts_path:
            timestamped_path = Path(ts_path)
        if model_path and voices_path:
            return Path(model_path), Path(voices_path), timestamped_path
    for base in [Path.cwd(), Path(__file__).parent, Path.home() / ".outloud"]:
        model = base / "kokoro-v1.0.onnx"
        voices = base / "voices-v1.0.bin"
        if model.exists() and voices.exists():
            ts = base / "kokoro-v1.0-timestamped.onnx"
            return model, voices, ts if ts.exists() else None
    raise RuntimeError(
        "Kokoro model files not found. Run with Bazel or place model files in working directory."
    )


MODEL_PATH, VOICES_PATH, TIMESTAMPED_MODEL_PATH = _find_model_paths()
_kokoro = None


def get_kokoro() -> Kokoro:
    global _kokoro
    if _kokoro is None:
        _kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
    return _kokoro


def split_into_chunks(text: str, max_chars: int = 250) -> list[str]:
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


_onnx_session_timestamped = None
_voice_data = None


def _get_onnx_session_timestamped():
    global _onnx_session_timestamped
    if _onnx_session_timestamped is None:
        if TIMESTAMPED_MODEL_PATH is None:
            raise RuntimeError("Timestamped model not available")
        _onnx_session_timestamped = ort.InferenceSession(
            str(TIMESTAMPED_MODEL_PATH), providers=["CPUExecutionProvider"]
        )
    return _onnx_session_timestamped


def _get_voice_data():
    global _voice_data
    if _voice_data is None:
        _voice_data = _load_voice_data(VOICES_PATH)
    return _voice_data


MAX_PHONEME_LENGTH = 500


def _get_durations_from_timestamped_model(
    chunk: str, voice: str, speed: float
) -> tuple[list, np.ndarray | None]:
    """Get duration predictions from timestamped model (for timestamp calculation only)."""
    g2p = _get_g2p()
    sess = _get_onnx_session_timestamped()
    voice_data = _get_voice_data()

    if voice not in voice_data:
        return [], None

    voice_styles = voice_data[voice]

    phonemes, tokens = g2p(chunk)
    input_ids = _tokenize_phonemes(phonemes)

    if not input_ids or len(input_ids) > MAX_PHONEME_LENGTH:
        return tokens, None

    input_ids_padded = np.array([[0] + input_ids + [0]], dtype=np.int64)
    style_idx = min(len(input_ids), len(voice_styles) - 1)
    style = voice_styles[style_idx].astype(np.float32)
    speed_arr = np.array([speed], dtype=np.float32)

    inputs = {
        "input_ids": input_ids_padded,
        "style": style,
        "speed": speed_arr,
    }

    outputs = sess.run(None, inputs)
    pred_dur = outputs[1].squeeze() if len(outputs) > 1 else None

    return tokens, pred_dur


def _generate_chunk_with_timestamps(
    chunk: str, voice: str, speed: float
) -> tuple[np.ndarray, list[dict]]:
    """Generate audio with kokoro-onnx (quality) and get timestamps from timestamped model."""
    kokoro = get_kokoro()
    audio, _ = _generate_chunk_audio(kokoro, chunk, voice, speed)

    if len(audio) == 0:
        return audio, []

    try:
        tokens, pred_dur = _get_durations_from_timestamped_model(chunk, voice, speed)
        if pred_dur is not None:
            raw_timestamps = _calculate_word_timestamps(tokens, pred_dur, speed)
            if raw_timestamps:
                predicted_duration = raw_timestamps[-1]["end"]
                actual_duration = len(audio) / SAMPLE_RATE
                if predicted_duration > 0:
                    scale = actual_duration / predicted_duration
                    for ts in raw_timestamps:
                        ts["start"] *= scale
                        ts["end"] *= scale
                    return audio, raw_timestamps
    except Exception:
        pass

    return audio, []


def _split_into_sentences(text: str) -> list[str]:
    abbreviations = r"(?<!\bMr)(?<!\bMrs)(?<!\bDr)(?<!\bMs)(?<!\bProf)(?<!\bSr)(?<!\bJr)(?<!\bvs)(?<!\betc)(?<!\be\.g)(?<!\bi\.e)(?<!\bNo)(?<!\bSt)"
    pattern = abbreviations + r'(?<=[.!?])\s+(?=[A-Z"\']|$)'
    sentences = [s.strip() for s in re.split(pattern, text) if s.strip()]
    return sentences


def _organize_timestamps_into_sentences(
    text: str, word_timestamps: list[dict]
) -> list[dict]:
    if not word_timestamps:
        return []

    sentences = _split_into_sentences(text)
    result = []
    word_idx = 0

    for sentence in sentences:
        sentence_lower = sentence.lower()
        sentence_data = {"text": sentence, "words": []}

        while word_idx < len(word_timestamps):
            word_data = word_timestamps[word_idx]
            word = word_data["word"]

            if word.lower() in sentence_lower or word in ".!?,;:":
                sentence_data["words"].append(word_data)
                word_idx += 1

                if word in ".!?" and word_idx < len(word_timestamps):
                    break
            else:
                break

        if sentence_data["words"]:
            result.append(sentence_data)

    return result


def generate_audio_with_timestamps(
    text: str,
    output_path: str,
    voice: str = "am_adam",
    speed: float = 1.0,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> tuple[str, list[dict]]:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    chunks = split_into_chunks(text)
    total_chunks = len(chunks)
    all_samples = []
    all_timestamps = []
    cumulative_time = 0.0

    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(
                i + 1, total_chunks, f"Processing chunk {i + 1}/{total_chunks}"
            )

        audio, chunk_timestamps = _generate_chunk_with_timestamps(chunk, voice, speed)

        if len(audio) == 0:
            continue

        for ts in chunk_timestamps:
            ts["start"] += cumulative_time
            ts["end"] += cumulative_time

        all_timestamps.extend(chunk_timestamps)
        all_samples.append(audio)
        cumulative_time += len(audio) / SAMPLE_RATE

    if not all_samples:
        raise ValueError("No audio generated")

    if progress_callback:
        progress_callback(total_chunks, total_chunks, "Combining audio...")

    combined = np.concatenate(all_samples)
    wav_path = output_path.with_suffix(".wav")
    sf.write(str(wav_path), combined, SAMPLE_RATE)

    if progress_callback:
        progress_callback(total_chunks, total_chunks, "Converting to MP3...")

    audio_segment = AudioSegment.from_wav(str(wav_path))
    audio_segment.export(str(output_path), format="mp3", bitrate=_BITRATE)
    wav_path.unlink()

    sentences = _organize_timestamps_into_sentences(text, all_timestamps)

    if progress_callback:
        progress_callback(total_chunks, total_chunks, "Complete!")

    return str(output_path), sentences
