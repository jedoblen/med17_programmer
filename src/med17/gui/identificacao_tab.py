"""Aba de identificação da ECU e verificação de perfis (Fase 4). Somente leitura de DIDs (UDS 0x22)."""
from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..can.bus import BridgeCanBus
from ..ecu.identification import DIDS_PADRAO, identify
from ..isotp.isotp import IsoTpConfig, IsoTpLink
from ..profiles.manager import ProfileManager
from ..uds.uds import NRC_NOMES, UdsClient

log = logging.getLogger("med17.gui.ident")


def _hex_ou_none(txt: str):
    txt = txt.strip()
    return int(txt, 0) if txt else None


class IdentificacaoTab(QWidget):
    _fim = Signal(object, object)

    def __init__(self, conexao, gerenciador: ProfileManager) -> None:
        super().__init__()
        self.conexao, self.gerenciador = conexao, gerenciador
        self._conectado = False
        self._ocupado = False
        self._fim.connect(self._concluir)

        self.perfil = QComboBox()
        self.perfil.currentIndexChanged.connect(self._perfil_escolhido)
        atualizar = QPushButton("Recarregar perfis")
        atualizar.clicked.connect(self.recarregar)
        pasta = QPushButton("Abrir pasta de perfis")
        pasta.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.gerenciador.pasta))))
        linha = QHBoxLayout()
        for w in (self.perfil, atualizar, pasta):
            linha.addWidget(w)

        self.tx = QLineEdit()
        self.tx.setPlaceholderText("ex.: 0x… (da documentação da ECU)")
        self.rx = QLineEdit()
        self.rx.setPlaceholderText("ex.: 0x… (da documentação da ECU)")
        self.pad = QLineEdit()
        self.pad.setPlaceholderText("opcional, ex.: 0x00")
        form = QFormLayout()
        form.addRow("Perfil:", linha)
        form.addRow("ID de envio (tester → ECU):", self.tx)
        form.addRow("ID de resposta (ECU → tester):", self.rx)
        form.addRow("Byte de preenchimento ISO-TP:", self.pad)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.botao = QPushButton("Identificar ECU")
        self.botao.clicked.connect(self.identificar)
        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(["DID", "Descrição", "Valor", "Estado"])
        self.tabela.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.resultado = QLabel()
        self.resultado.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.status)
        lay.addWidget(self.botao)
        lay.addWidget(self.tabela)
        lay.addWidget(self.resultado)

        conexao.conexao_alterada.connect(self._conexao_mudou)
        self.recarregar()
        self._atualizar_botao()

    # -- perfis
    def recarregar(self) -> None:
        self.gerenciador.garantir_modelo()
        self.gerenciador.carregar()
        self.perfil.blockSignals(True)
        self.perfil.clear()
        self.perfil.addItem("(nenhum — informar IDs manualmente)", None)
        for p in self.gerenciador.perfis:
            self.perfil.addItem(f"{p.nome}" + (" [SIMULADO]" if p.simulado else ""), p.id)
        self.perfil.blockSignals(False)
        self._perfil_escolhido()
        for arq, erro in self.gerenciador.erros.items():
            log.error("Perfil inválido %s: %s", arq, erro)

    def _perfil_atual(self):
        pid = self.perfil.currentData()
        return self.gerenciador.obter(pid) if pid else None

    def _perfil_escolhido(self) -> None:
        p = self._perfil_atual()
        if p is None:
            self.status.setText("Sem perfil: apenas identificação por DIDs padrão com IDs informados manualmente. "
                                "Operações de leitura/gravação de memória exigem um perfil validado.")
            return
        pr = p.protocolo
        self.tx.setText("" if pr.tx_id is None else f"0x{pr.tx_id:X}")
        self.rx.setText("" if pr.rx_id is None else f"0x{pr.rx_id:X}")
        self.pad.setText("" if pr.isotp.pad_byte is None else f"0x{pr.isotp.pad_byte:02X}")
        real = not self.conexao.cfg.j2534.simulador
        linhas = []
        for op in ("leitura", "escrita"):
            ok, pend = p.permite(op, real)
            linhas.append(f"{op.capitalize()}: " + ("liberada" if ok else "BLOQUEADA — " + "; ".join(pend)))
        self.status.setText("\n".join(linhas))

    # -- estado
    def _conexao_mudou(self, pronto: bool) -> None:
        self._conectado = pronto
        self._atualizar_botao()

    def _atualizar_botao(self) -> None:
        self.botao.setEnabled(self._conectado and not self._ocupado)

    # -- identificação
    def identificar(self) -> None:
        cli = self.conexao.client
        try:
            tx, rx, pad = _hex_ou_none(self.tx.text()), _hex_ou_none(self.rx.text()), _hex_ou_none(self.pad.text())
        except ValueError:
            QMessageBox.warning(self, "IDs", "Valores inválidos. Use decimal ou hexadecimal (0x…).")
            return
        if cli is None or tx is None or rx is None:
            QMessageBox.warning(self, "IDs", "Conecte a interface e informe os IDs de envio e resposta.")
            return
        p = self._perfil_atual()
        ext = self.conexao.cfg.can.id_29_bits
        cfg = IsoTpConfig(pad_byte=pad)
        p2, p2s = 1.0, 5.0
        dids = set(DIDS_PADRAO)
        if p:
            cfg.stmin_ms, cfg.block_size = p.protocolo.isotp.stmin_ms, p.protocolo.isotp.block_size
            p2, p2s = p.protocolo.p2 or p2, p.protocolo.p2_star or p2s
            dids |= set(p.identificacao)
        lista = sorted(dids)
        log.info("Identificando ECU (tx=0x%X, rx=0x%X)...", tx, rx)

        def trabalho():
            uds = UdsClient(IsoTpLink(BridgeCanBus(cli, ext), tx, rx, extended=ext, config=cfg), p2=p2, p2_star=p2s)
            return identify(uds, lista)

        self._ocupado = True
        self._atualizar_botao()

        def alvo():
            try:
                self._fim.emit(trabalho(), None)
            except Exception as exc:  # noqa: BLE001
                self._fim.emit(None, exc)

        threading.Thread(target=alvo, daemon=True).start()

    def _concluir(self, ident, erro) -> None:
        self._ocupado = False
        self._atualizar_botao()
        if erro:
            log.error("Identificação falhou: %s", erro)
            self.resultado.setText(f"Falha: {erro}")
            return
        self.tabela.setRowCount(0)
        for did in sorted(set(ident.valores) | set(ident.nao_suportados) | set(ident.sem_resposta)):
            if did in ident.valores:
                valor, estado = ident.texto(did), "ok"
            elif did in ident.nao_suportados:
                nrc = ident.nao_suportados[did]
                valor, estado = "", f"NRC 0x{nrc:02X} ({NRC_NOMES.get(nrc, '?')})"
            else:
                valor, estado = "", "sem resposta"
            r = self.tabela.rowCount()
            self.tabela.insertRow(r)
            for c, t in enumerate((f"0x{did:04X}", DIDS_PADRAO.get(did, "(do perfil)"), valor, estado)):
                self.tabela.setItem(r, c, QTableWidgetItem(t))
            log.info("DID 0x%04X: %s %s", did, valor, estado if estado != "ok" else "")
        achados = self.gerenciador.casar(ident)
        if len(achados) == 1:
            txt = f"Perfil correspondente: {achados[0].nome}"
        elif achados:
            txt = "Mais de um perfil corresponde (ambíguo; nenhum será usado automaticamente): " + \
                  ", ".join(p.nome for p in achados)
        else:
            txt = "Nenhum perfil corresponde a esta ECU. Operações de memória permanecem bloqueadas."
        self.resultado.setText(txt)
        log.info(txt)
