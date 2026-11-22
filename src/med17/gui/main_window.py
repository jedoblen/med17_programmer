"""Janela principal (Fase 1): estrutura de abas e painel de logs.

As abas de operação ficam desabilitadas até as fases correspondentes serem
implementadas e validadas. Nenhuma operação com ECU existe nesta fase.
"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from .. import __version__
from ..core.config import BITRATES_VALIDOS, NIVEIS_LOG, AppConfig, save_config
from ..core.logging_setup import attach_callback

log = logging.getLogger("med17.gui")

_CORES = {
    logging.DEBUG: "#888888", logging.INFO: "#222222",
    logging.WARNING: "#b36b00", logging.ERROR: "#c0392b", logging.CRITICAL: "#c0392b",
}


class LogPanel(QPlainTextEdit):
    """Painel de logs; seguro para receber registros de qualquer thread."""

    _nova_linha = Signal(str, int)

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        self._nova_linha.connect(self._append)
        self._handler = attach_callback(lambda msg, lvl: self._nova_linha.emit(msg, lvl))

    def _append(self, msg: str, level: int) -> None:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(_CORES.get(level, "#222222")))
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        cur.insertText(msg + "\n", fmt)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def detach(self) -> None:
        logging.getLogger("med17").removeHandler(self._handler)


class ConexaoTab(QWidget):
    """Configuração de DLL J2534 e CAN. A conexão real chega na Fase 2."""

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.dll = QLineEdit(cfg.j2534.dll_path)
        self.dll.setPlaceholderText("Selecione a DLL J2534 do fabricante da interface")
        procurar = QPushButton("Procurar…")
        procurar.clicked.connect(self._procurar)
        linha = QHBoxLayout()
        linha.addWidget(self.dll)
        linha.addWidget(procurar)

        self.bitrate = QComboBox()
        for b in BITRATES_VALIDOS:
            self.bitrate.addItem(f"{b // 1000} kbit/s", b)
        self.bitrate.setCurrentIndex(self.bitrate.findData(cfg.can.bitrate))
        self.id29 = QCheckBox("Identificadores de 29 bits")
        self.id29.setChecked(cfg.can.id_29_bits)
        self.nivel = QComboBox()
        self.nivel.addItems(NIVEIS_LOG)
        self.nivel.setCurrentText(cfg.log_level)

        form = QFormLayout()
        form.addRow("DLL J2534:", linha)
        form.addRow("Bitrate CAN:", self.bitrate)
        form.addRow("", self.id29)
        form.addRow("Nível de log:", self.nivel)
        grupo = QGroupBox("Configuração")
        grupo.setLayout(form)

        salvar = QPushButton("Salvar configuração")
        salvar.clicked.connect(self.salvar)
        conectar = QPushButton("Conectar (disponível na Fase 2)")
        conectar.setEnabled(False)

        lay = QVBoxLayout(self)
        lay.addWidget(grupo)
        lay.addWidget(salvar)
        lay.addWidget(conectar)
        lay.addStretch()

    def _procurar(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(self, "DLL J2534", "", "DLL (*.dll)")
        if caminho:
            self.dll.setText(caminho)

    def salvar(self) -> None:
        self.cfg.j2534.dll_path = self.dll.text().strip()
        self.cfg.can.bitrate = int(self.bitrate.currentData())
        self.cfg.can.id_29_bits = self.id29.isChecked()
        self.cfg.log_level = self.nivel.currentText()
        try:
            destino = save_config(self.cfg)
        except (OSError, ValueError) as exc:
            log.error("Falha ao salvar configuração: %s", exc)
            QMessageBox.critical(self, "Erro", str(exc))
            return
        logging.getLogger("med17").setLevel(self.cfg.log_level)
        log.info("Configuração salva em %s", destino)


def _aba_futura(titulo: str, fase: int) -> QWidget:
    w = QWidget()
    lab = QLabel(f"{titulo}\n\nNão implementado. Previsto para a FASE {fase}.")
    lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay = QVBoxLayout(w)
    lay.addWidget(lab)
    return w


class MainWindow(QMainWindow):
    ABAS_FUTURAS = (
        ("Identificação ECU", 4), ("FLASH", 5), ("EEPROM", 5),
        ("Gravação", 6), ("DUMPs / Editor HEX", 7),
    )

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.setWindowTitle(f"Bosch MED17 Programmer {__version__}")
        self.resize(1000, 700)

        self.tabs = QTabWidget()
        self.conexao = ConexaoTab(cfg)
        self.tabs.addTab(self.conexao, "Conexão")
        for titulo, fase in self.ABAS_FUTURAS:
            i = self.tabs.addTab(_aba_futura(titulo, fase), titulo)
            self.tabs.setTabEnabled(i, False)

        self.logs = LogPanel()
        split = QSplitter(Qt.Orientation.Vertical)
        split.addWidget(self.tabs)
        split.addWidget(self.logs)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.setCentralWidget(split)
        self.statusBar().showMessage("Desconectado — nenhuma operação com ECU disponível (Fase 1)")
        log.info("Interface iniciada (Fase 1).")

    def closeEvent(self, event) -> None:
        self.logs.detach()
        super().closeEvent(event)
