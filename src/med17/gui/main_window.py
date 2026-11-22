"""Janela principal (Fase 2): estrutura de abas e painel de logs.

As abas de operação ficam desabilitadas até as fases correspondentes serem
implementadas e validadas. Nenhuma operação com ECU existe nesta fase.
"""
from __future__ import annotations

import logging
import threading

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
from ..j2534.client import BridgeClient, BridgeError, bridge_command
from ..j2534.registry import discover_dlls, pe_bitness

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
    """Seleção de DLL J2534, configuração CAN e conexão via ponte (Fase 2).

    Nesta fase não se transmite nada à ECU: a conexão apenas abre o dispositivo,
    lê versões/tensão e permite escutar o barramento passivamente.
    """

    _fim = Signal(object, object)  # resultado, exceção (da thread de trabalho)

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.client: BridgeClient | None = None
        self._depois = None
        self._fim.connect(self._concluir)

        self.dlls = QComboBox()
        self.dlls.setMinimumWidth(380)
        self.dlls.currentIndexChanged.connect(self._dll_escolhida)
        detectar = QPushButton("Detectar interfaces")
        detectar.clicked.connect(self.detectar)
        self.dll = QLineEdit(cfg.j2534.dll_path)
        self.dll.setPlaceholderText("Caminho da DLL J2534 (ou escolha acima)")
        procurar = QPushButton("Procurar…")
        procurar.clicked.connect(self._procurar)
        linha = QHBoxLayout()
        linha.addWidget(self.dll)
        linha.addWidget(procurar)
        linha2 = QHBoxLayout()
        linha2.addWidget(self.dlls)
        linha2.addWidget(detectar)

        self.bitrate = QComboBox()
        for b in BITRATES_VALIDOS:
            self.bitrate.addItem(f"{b // 1000} kbit/s", b)
        self.bitrate.setCurrentIndex(self.bitrate.findData(cfg.can.bitrate))
        self.id29 = QCheckBox("Identificadores de 29 bits")
        self.id29.setChecked(cfg.can.id_29_bits)
        self.simulador = QCheckBox("Usar simulador J2534 (SIMULADO — sem hardware)")
        self.simulador.setChecked(cfg.j2534.simulador)
        self.nivel = QComboBox()
        self.nivel.addItems(NIVEIS_LOG)
        self.nivel.setCurrentText(cfg.log_level)

        form = QFormLayout()
        form.addRow("Interfaces:", linha2)
        form.addRow("DLL J2534:", linha)
        form.addRow("Bitrate CAN:", self.bitrate)
        form.addRow("", self.id29)
        form.addRow("", self.simulador)
        form.addRow("Nível de log:", self.nivel)
        grupo = QGroupBox("Configuração")
        grupo.setLayout(form)

        self.b_salvar = QPushButton("Salvar configuração")
        self.b_salvar.clicked.connect(self.salvar)
        self.b_conectar = QPushButton("Conectar")
        self.b_conectar.clicked.connect(self.conectar)
        self.b_escutar = QPushButton("Escutar CAN (2 s, passivo)")
        self.b_escutar.clicked.connect(self.escutar)
        self.b_desconectar = QPushButton("Desconectar")
        self.b_desconectar.clicked.connect(self.desconectar)
        botoes = QHBoxLayout()
        for b in (self.b_salvar, self.b_conectar, self.b_escutar, self.b_desconectar):
            botoes.addWidget(b)
        self.info = QLabel("Desconectado.")
        self.info.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.addWidget(grupo)
        lay.addLayout(botoes)
        lay.addWidget(self.info)
        lay.addStretch()
        self._estado(False)
        self.detectar()

    # -- estado / execução em segundo plano
    def _estado(self, conectado: bool, ocupado: bool = False) -> None:
        self.b_conectar.setEnabled(not conectado and not ocupado)
        self.b_escutar.setEnabled(conectado and not ocupado)
        self.b_desconectar.setEnabled(conectado and not ocupado)
        self._conectado = conectado

    def _executar(self, fn, depois) -> None:
        self._estado(self._conectado, ocupado=True)
        self._depois = depois

        def alvo():
            try:
                self._fim.emit(fn(), None)
            except Exception as exc:  # noqa: BLE001
                self._fim.emit(None, exc)

        threading.Thread(target=alvo, daemon=True).start()

    def _concluir(self, resultado, erro) -> None:
        depois, self._depois = self._depois, None
        if depois:
            depois(resultado, erro)

    # -- detecção
    def detectar(self) -> None:
        self.dlls.blockSignals(True)
        self.dlls.clear()
        self.dlls.addItem("(selecione)", None)
        for d in discover_dlls():
            rot = f"{d.name} — {d.bits or '?'} bits" + ("" if d.exists else " (arquivo ausente)")
            self.dlls.addItem(rot, d.path)
        self.dlls.blockSignals(False)
        log.info("%d interface(s) J2534 encontrada(s) no registro.", self.dlls.count() - 1)

    def _dll_escolhida(self) -> None:
        caminho = self.dlls.currentData()
        if caminho:
            self.dll.setText(caminho)

    def _procurar(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(self, "DLL J2534", "", "DLL (*.dll)")
        if caminho:
            self.dll.setText(caminho)

    def salvar(self) -> None:
        self.cfg.j2534.dll_path = self.dll.text().strip()
        self.cfg.j2534.simulador = self.simulador.isChecked()
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

    # -- conexão
    def conectar(self) -> None:
        self.salvar()
        simular = self.cfg.j2534.simulador
        dll = self.cfg.j2534.dll_path
        if not simular and not dll:
            QMessageBox.warning(self, "DLL", "Selecione a DLL J2534 ou ative o simulador.")
            return
        bits = pe_bitness(dll) if (dll and not simular) else None
        if not simular and bits is None:
            QMessageBox.warning(self, "DLL", "Arquivo não encontrado ou não é uma DLL válida.")
            return
        bitrate, ext = self.cfg.can.bitrate, self.cfg.can.id_29_bits
        log.info("Conectando%s (DLL de %s bits)...", " [SIMULADO]" if simular else "", bits or "-")

        def trabalho():
            client = BridgeClient(bridge_command(bits, simular), default_timeout=15)
            client.start()
            try:
                ver = client.call("open", dll_path=dll)  # abre o dispositivo e devolve versões
                try:
                    mv = client.call("vbatt")["mv"]
                except BridgeError as exc:
                    log.warning("Tensão não disponível: %s", exc)
                    mv = None
                client.call("connect_can", bitrate=bitrate, extended=ext)
                return client, ver, mv
            except Exception:
                client.stop()
                raise

        self._executar(trabalho, self._conectado_ok)

    def _conectado_ok(self, res, erro) -> None:
        if erro:
            log.error("Falha ao conectar: %s", erro)
            self.info.setText(f"Falha ao conectar: {erro}")
            self._estado(False)
            return
        self.client, ver, mv = res
        v = f"{mv / 1000:.1f} V" if mv else "indisponível"
        self.info.setText(f"Conectado. Firmware: {ver['firmware']} | DLL: {ver['dll']} | API: {ver['api']} | Tensão: {v}"
                          + ("  [SIMULADO]" if self.cfg.j2534.simulador else ""))
        log.info("Conectado: %s | tensão %s", ver, v)
        self._estado(True)

    def escutar(self) -> None:
        cli = self.client

        def trabalho():
            return cli.call("read", timeout=5, wait_ms=2000, max=64)["frames"]

        def fim(frames, erro):
            if erro:
                log.error("Falha ao escutar: %s", erro)
            else:
                log.info("Escuta: %d quadro(s) recebido(s).", len(frames))
                for f in frames[:20]:
                    log.info("  ID 0x%X  %s", f["id"], f["data"])
            self._estado(cli.running)

        self._executar(trabalho, fim)

    def desconectar(self) -> None:
        cli, self.client = self.client, None

        def trabalho():
            if cli:
                cli.stop()

        def fim(_r, erro):
            if erro:
                log.error("Erro ao desconectar: %s", erro)
            self.info.setText("Desconectado.")
            log.info("Desconectado.")
            self._estado(False)

        self._executar(trabalho, fim)

    def encerrar(self) -> None:
        if self.client:
            self.client.stop()
            self.client = None


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
        self.statusBar().showMessage("Desconectado — nenhuma operação com ECU disponível (Fase 2)")
        log.info("Interface iniciada (Fase 2).")

    def closeEvent(self, event) -> None:
        self.conexao.encerrar()
        self.logs.detach()
        super().closeEvent(event)
