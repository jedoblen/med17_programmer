"""Transporte ISO-TP (ISO 15765-2) sobre CAN clássico, endereçamento normal.

Os IDs de transmissão/recepção são sempre informados pelo chamador (vêm do perfil da ECU).
Limitações atuais: payload até 4095 bytes; sem endereçamento estendido/misto; STmin < 1 ms
depende da resolução do temporizador do Windows.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ..can.bus import CanBus

log = logging.getLogger("med17.isotp")

SF, FF, CF, FC = 0, 1, 2, 3
FS_CTS, FS_WAIT, FS_OVFLW = 0, 1, 2


class IsoTpError(Exception):
    pass


class IsoTpTimeout(IsoTpError):
    pass


@dataclass
class IsoTpConfig:
    block_size: int = 0          # BS que anunciamos ao receber (0 = sem novos FC)
    stmin_ms: int = 0            # STmin que anunciamos ao receber (0..127)
    pad_byte: int | None = None  # None = sem preenchimento (DLC variável)
    n_bs: float = 1.0            # espera pelo Flow Control (s)
    n_cr: float = 1.0            # espera pelo próximo Consecutive Frame (s)
    max_wait_frames: int = 10    # FC "WAIT" tolerados


def decode_stmin(b: int) -> float:
    """STmin em segundos (valores reservados = 127 ms, conforme a norma)."""
    if b <= 0x7F:
        return b / 1000
    if 0xF1 <= b <= 0xF9:
        return (b - 0xF0) * 0.0001
    return 0.127


class IsoTpLink:
    def __init__(self, bus: CanBus, tx_id: int, rx_id: int, *, extended: bool = False,
                 config: IsoTpConfig | None = None) -> None:
        self.bus, self.tx_id, self.rx_id, self.extended = bus, tx_id, rx_id, extended
        self.cfg = config or IsoTpConfig()
        if not 0 <= self.cfg.stmin_ms <= 0x7F:
            raise ValueError("stmin_ms deve estar entre 0 e 127")

    # -- quadros
    def _send_frame(self, data: bytes) -> None:
        if self.cfg.pad_byte is not None:
            data = data + bytes([self.cfg.pad_byte]) * (8 - len(data))
        self.bus.send(self.tx_id, data, self.extended)

    def _recv_frame(self, timeout: float) -> bytes | None:
        fim = time.monotonic() + timeout
        while True:
            f = self.bus.recv(max(fim - time.monotonic(), 0.0))
            if f is None:
                return None
            if f.can_id == self.rx_id and f.extended == self.extended and not f.is_tx_echo and f.data:
                return f.data
            if time.monotonic() >= fim:
                return None

    def _send_fc(self, status: int = FS_CTS) -> None:
        self._send_frame(bytes([0x30 | status, self.cfg.block_size, self.cfg.stmin_ms]))

    def _wait_fc(self) -> tuple[int, float]:
        waits = 0
        while True:
            fr = self._recv_frame(self.cfg.n_bs)
            if fr is None:
                raise IsoTpTimeout("N_Bs: Flow Control não recebido")
            if fr[0] >> 4 != FC:
                log.warning("Quadro inesperado aguardando FC: %s", fr.hex())
                continue
            fs = fr[0] & 0xF
            if fs == FS_CTS:
                if len(fr) < 3:
                    raise IsoTpError("Flow Control incompleto")
                return fr[1], decode_stmin(fr[2])
            if fs == FS_WAIT:
                waits += 1
                if waits > self.cfg.max_wait_frames:
                    raise IsoTpError("receptor pediu WAIT em excesso")
                continue
            if fs == FS_OVFLW:
                raise IsoTpError("receptor sinalizou overflow de buffer")
            raise IsoTpError(f"FlowStatus inválido: {fs}")

    # -- envio
    def send(self, payload: bytes) -> None:
        n = len(payload)
        if n == 0 or n > 4095:
            raise ValueError("payload ISO-TP deve ter de 1 a 4095 bytes")
        if n <= 7:
            self._send_frame(bytes([n]) + payload)
            return
        self._send_frame(bytes([0x10 | (n >> 8), n & 0xFF]) + payload[:6])
        sent, sn, in_block = 6, 1, 0
        bs, st = self._wait_fc()
        while sent < n:
            chunk = payload[sent:sent + 7]
            self._send_frame(bytes([0x20 | sn]) + chunk)
            sent += len(chunk)
            sn = (sn + 1) & 0xF
            in_block += 1
            if sent >= n:
                break
            if bs and in_block >= bs:
                bs, st = self._wait_fc()
                in_block = 0
            elif st:
                time.sleep(st)

    # -- recepção
    def recv(self, timeout: float = 1.0) -> bytes:
        while True:
            fr = self._recv_frame(timeout)
            if fr is None:
                raise IsoTpTimeout("nenhum quadro recebido")
            tipo = fr[0] >> 4
            if tipo == SF:
                ln = fr[0] & 0xF
                if ln == 0 or ln > 7 or len(fr) - 1 < ln:
                    raise IsoTpError(f"Single Frame inválido: {fr.hex()}")
                return bytes(fr[1:1 + ln])
            if tipo == FF:
                break
            log.debug("Ignorando quadro %s fora de contexto", fr.hex())
        total = ((fr[0] & 0xF) << 8) | fr[1]
        if total <= 7 or len(fr) < 8:
            raise IsoTpError(f"First Frame inválido: {fr.hex()}")
        buf = bytearray(fr[2:8])
        self._send_fc(FS_CTS)
        esperado, in_block = 1, 0
        while len(buf) < total:
            cf = self._recv_frame(self.cfg.n_cr)
            if cf is None:
                raise IsoTpTimeout("N_Cr: Consecutive Frame não recebido")
            if cf[0] >> 4 != CF:
                raise IsoTpError(f"esperava Consecutive Frame, recebeu {cf.hex()}")
            if cf[0] & 0xF != esperado:
                raise IsoTpError(f"sequência errada: esperado {esperado}, recebido {cf[0] & 0xF}")
            buf += cf[1:1 + min(7, total - len(buf))]
            esperado = (esperado + 1) & 0xF
            in_block += 1
            if len(buf) < total and self.cfg.block_size and in_block >= self.cfg.block_size:
                self._send_fc(FS_CTS)
                in_block = 0
        return bytes(buf)
