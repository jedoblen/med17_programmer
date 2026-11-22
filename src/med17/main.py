"""Ponto de entrada: python -m med17"""
from __future__ import annotations

import sys

from .core.config import load_config
from .core.logging_setup import setup_logging


def main() -> int:
    cfg = load_config()
    setup_logging(cfg.log_level)

    from PySide6.QtWidgets import QApplication  # import tardio: facilita testes sem GUI
    from .gui.main_window import MainWindow

    app = QApplication(sys.argv)
    janela = MainWindow(cfg)
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
