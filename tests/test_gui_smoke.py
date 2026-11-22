import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from med17.core.config import AppConfig  # noqa: E402
from med17.gui.main_window import MainWindow  # noqa: E402


def test_janela_abre_e_abas_futuras_desabilitadas():
    app = QApplication.instance() or QApplication([])
    w = MainWindow(AppConfig())
    assert w.tabs.isTabEnabled(0)
    assert not any(w.tabs.isTabEnabled(i) for i in range(1, w.tabs.count()))
    w.close()
    app.processEvents()
