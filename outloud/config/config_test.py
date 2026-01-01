import os
import tempfile
from pathlib import Path


def test_get_data_dir_default():
    from outloud.config import USER_DATA_DIR, get_data_dir

    orig = os.environ.pop("OUTLOUD_DATA_DIR", None)
    try:
        assert get_data_dir() == USER_DATA_DIR
    finally:
        if orig:
            os.environ["OUTLOUD_DATA_DIR"] = orig


def test_get_data_dir_from_env():
    from outloud.config import get_data_dir

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["OUTLOUD_DATA_DIR"] = tmpdir
        try:
            assert get_data_dir() == Path(tmpdir)
        finally:
            del os.environ["OUTLOUD_DATA_DIR"]
