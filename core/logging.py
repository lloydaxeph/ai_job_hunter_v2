from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console


class AppLogger:
    """Process-wide singleton for the stdlib logger and the Rich console.

    v1 re-instantiated a wrapper class at every call site (`Logger().instance`,
    `ConsoleManager().instance`), which re-ran `logging.basicConfig` repeatedly.
    Here the underlying logger/console are built once at import time.
    """

    _logger: logging.Logger | None = None
    _console: Console | None = None

    @classmethod
    def logger(cls) -> logging.Logger:
        if cls._logger is None:
            cls._logger = cls._build_logger()
        return cls._logger

    @classmethod
    def console(cls) -> Console:
        if cls._console is None:
            cls._console = Console()
        return cls._console

    @staticmethod
    def _build_logger() -> logging.Logger:
        log_dir = Path("Data")
        log_dir.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("job_hunter")
        logger.setLevel(logging.INFO)
        logger.propagate = False

        formatter = logging.Formatter(
            fmt='{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"logger": "%(name)s", "message": "%(message)s"}',
        )

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(stream_handler)

        file_handler = logging.FileHandler(log_dir / "job_hunter.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger
