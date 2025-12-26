import os
from pathlib import Path

USER_DATA_DIR = Path.home() / ".outloud"


def get_data_dir() -> Path:
    if env_dir := os.environ.get("OUTLOUD_DATA_DIR"):
        return Path(env_dir)
    return USER_DATA_DIR


DATA_DIR = get_data_dir()
DB_PATH = DATA_DIR / "reader.db"
TEXTS_DIR = DATA_DIR / "texts"
AUDIO_DIR = DATA_DIR / "audio"
UPLOAD_DIR = DATA_DIR / "uploads"

DATA_DIR.mkdir(parents=True, exist_ok=True)
TEXTS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
