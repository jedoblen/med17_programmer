"""Interface de barramento CAN e implementação sobre a ponte J2534."""
from __future__ import annotations

import time
from collections import deque
from typing import Protocol

from .frame import CanFrame


class CanBus(Protocol):
    def send(self, can_id: int, data: bytes, extended: bool = False) -> None: ...

    def recv(self, timeout: float) -> CanFrame | None:
        """Próximo quadro recebido (sem ecos de transmissão) ou None no timeout."""
        ...


class BridgeCanBus:
    """CanBus usando um BridgeClient já conectado (canal CAN aberto, filtro configurado)."""

    def __init__(self, client, extended: bool = False, poll_ms: int = 50) -> None:
        self.client, self.extended, self.poll_ms = client, extended, poll_ms
        self._buf: deque[CanFrame] = deque()

    def send(self, can_id: int, data: bytes, extended: bool = False) -> None:
        if extended != self.extended:
            raise ValueError("formato de ID difere do configurado na conexão")
        CanFrame(can_id, bytes(data), extended)  # valida
        self.client.call("write", id=can_id, data=bytes(data).hex(), wait_ms=100)

    def recv(self, timeout: float) -> CanFrame | None:
        fim = time.monotonic() + max(timeout, 0.0)
        while True:
            if self._buf:
                return self._buf.popleft()
            restante = fim - time.monotonic()
            espera = int(min(max(restante, 0.0) * 1000, self.poll_ms))
            r = self.client.call("read", timeout=espera / 1000 + 3, wait_ms=espera, max=16)
            for f in r["frames"]:
                if not f["tx_echo"]:
                    self._buf.append(CanFrame(f["id"], bytes.fromhex(f["data"]), f["ext"], False, f["ts"]))
            if self._buf:
                continue
            if time.monotonic() >= fim:
                return None
