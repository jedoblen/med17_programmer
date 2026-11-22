"""Sistema de logs: arquivo rotativo + console + gancho para a interface."""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable

from .paths import logs_dir

FORMATO = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_ROOT = "med17"


class CallbackHandler(logging.Handler):
    """Entrega cada registro formatado a uma função (painel de logs da GUI)."""

    def __init__(self, callback: Callable[[str, int], None]) -> None:
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._callback(self.format(record), record.levelno)
        except Exception:  # nunca derrubar o app por causa de log
            self.handleError(record)


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> logging.Logger:
    """Configura o logger raiz do aplicativo. Idempotente."""
    logger = logging.getLogger(_ROOT)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    fmt = logging.Formatter(FORMATO)
    arquivo = RotatingFileHandler(
        (log_dir or logs_dir()) / "med17.log",
        maxBytes=2_000_000, backupCount=5, encoding="utf-8",
    )
    arquivo.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(arquivo)
    logger.addHandler(console)
    logger.propagate = False
    return logger


def attach_callback(callback: Callable[[str, int], None]) -> CallbackHandler:
    h = CallbackHandler(callback)
    h.setFormatter(logging.Formatter(FORMATO))
    logging.getLogger(_ROOT).addHandler(h)
    return h
