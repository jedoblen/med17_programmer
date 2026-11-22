import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from med17.core.config import AppConfig  # noqa: E402
from med17.gui.main_window import MainWindow  # noqa: E402


def test_janela_abre_e_abas_futuras_desabilitadas(monkeypatch, tmp_path):
    monkeypatch.setenv("MED17_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    w = MainWindow(AppConfig())
    assert w.tabs.isTabEnabled(0) and w.tabs.isTabEnabled(1)
    assert w.tabs.tabText(1) == "Identificação ECU"
    assert not any(w.tabs.isTabEnabled(i) for i in range(2, w.tabs.count()))
    assert not w.ident.botao.isEnabled()  # desconectado
    assert (tmp_path / "profiles" / "_modelo_med17.json").exists()
    w.close()
    app.processEvents()


def test_conectar_e_desconectar_no_simulador(monkeypatch, tmp_path):
    import time

    monkeypatch.setenv("MED17_HOME", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    cfg = AppConfig()
    cfg.j2534.simulador = True
    w = MainWindow(cfg)
    t = w.conexao
    t.conectar()
    fim = time.time() + 20
    while not t.b_desconectar.isEnabled() and time.time() < fim:
        app.processEvents()
        time.sleep(0.02)
    assert t.b_desconectar.isEnabled() and "SIMULADO" in t.info.text()
    t.desconectar()
    fim = time.time() + 10
    while t.b_desconectar.isEnabled() or not t.b_conectar.isEnabled():
        if time.time() > fim:
            break
        app.processEvents()
        time.sleep(0.02)
    assert t.b_conectar.isEnabled() and t.client is None
    w.close()
