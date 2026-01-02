import logging
import os
import sys


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        reset = self.RESET if color else ""

        timestamp = self.formatTime(record, "%H:%M:%S")
        level = f"{color}{record.levelname:8}{reset}"
        name = f"{self.DIM}{record.name:20}{self.RESET}"
        message = record.getMessage()

        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return f"{self.DIM}{timestamp}{self.RESET} {level} {name} {message}"


class NoisyLibraryFilter(logging.Filter):
    NOISE_PATTERNS = [
        "words count mismatch",
        "phonemizer",
    ]

    def filter(self, record):
        msg = record.getMessage()
        if record.name == "werkzeug" and "/articles/status" in msg:
            return False
        for pattern in self.NOISE_PATTERNS:
            if pattern in msg.lower():
                return False
        return True


def setup_logging():
    level_name = os.environ.get("OUTLOUD_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(ColorFormatter())
    handler.addFilter(NoisyLibraryFilter())
    root.addHandler(handler)

    return logging.getLogger("outloud")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"outloud.{name}")
