from __future__ import annotations

import logging

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level_name: str) -> None:
    normalized = level_name.strip().upper()
    level = getattr(logging, normalized, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format=_LOG_FORMAT)
        return
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
