"""SIMULAÇÃO: barramento virtual e ECU virtual (servidor ISO-TP/UDS).

Nada aqui reproduz uma ECU real. O seed/key é um esquema FICTÍCIO de teste (key = seed XOR 0xFF).
"""
from __future__ import annotations

import queue
import threading
import time

from ..can.frame import CanFrame
from ..isotp.isotp import IsoTpConfig, IsoTpError, IsoTpLink, IsoTpTimeout


class VirtualBus:
    """Ponta de um par de barramentos ligados entre si. `sent` registra o que foi enviado."""

    def __init__(self) -> None:
        self._q: queue.Queue[CanFrame] = queue.Queue()
        self.peer: VirtualBus | None = None
        self.sent: list[tuple[int, bytes]] = []

    @staticmethod
    def pair() -> tuple["VirtualBus", "VirtualBus"]:
        a, b = VirtualBus(), VirtualBus()
        a.peer, b.peer = b, a
        return a, b

    def send(self, can_id: int, data: bytes, extended: bool = False) -> None:
        self.sent.append((can_id, bytes(data)))
        self.peer._q.put(CanFrame(can_id, bytes(data), extended))

    def recv(self, timeout: float) -> CanFrame | None:
        try:
            return self._q.get(timeout=max(timeout, 0.0))
        except queue.Empty:
            return None


class VirtualEcu:
    def __init__(self, bus: VirtualBus, request_id: int, response_id: int, *, dids: dict[int, bytes] | None = None,
                 memory_size: int = 0x1000, config: IsoTpConfig | None = None) -> None:
        self.link = IsoTpLink(bus, tx_id=response_id, rx_id=request_id, config=config)
        self.dids = dict(dids or {})
        self.memory = bytearray(i % 251 for i in range(memory_size))
        self.session = 1
        self.unlocked = False
        self.tp_count = 0
        self.silent = False
        self.pending_for: dict[int, int] = {}  # sid -> nº de 0x78 antes da resposta
        self._seed = b"\x12\x34\x56\x78"
        self._dl_addr = self._dl_left = 0
        self._dl_seq = 1
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def start(self) -> None:
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def stop(self) -> None:
        self._stop.set()
        if self._t:
            self._t.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                req = self.link.recv(0.05)
            except (IsoTpTimeout, IsoTpError):
                continue
            for _ in range(self.pending_for.get(req[0], 0)):
                self.link.send(bytes([0x7F, req[0], 0x78]))
                time.sleep(0.05)
            resp = self.handle(req)
            if resp is not None and not self.silent:
                self.link.send(resp)

    @staticmethod
    def _nrc(sid: int, nrc: int) -> bytes:
        return bytes([0x7F, sid, nrc])

    def handle(self, req: bytes) -> bytes | None:
        sid = req[0]
        try:
            if sid == 0x10 and len(req) == 2:
                sub = req[1] & 0x7F
                if sub not in (1, 2, 3):
                    return self._nrc(sid, 0x12)
                self.session = sub
                return None if req[1] & 0x80 else bytes([0x50, sub, 0x00, 0x32, 0x01, 0xF4])
            if sid == 0x3E and len(req) == 2:
                self.tp_count += 1
                return None if req[1] & 0x80 else bytes([0x7E, req[1] & 0x7F])
            if sid == 0x22 and len(req) == 3:
                did = int.from_bytes(req[1:3], "big")
                return bytes([0x62]) + req[1:3] + self.dids[did] if did in self.dids else self._nrc(sid, 0x31)
            if sid == 0x23 and len(req) >= 4:
                al, sl = req[1] & 0xF, req[1] >> 4
                if len(req) != 2 + al + sl:
                    return self._nrc(sid, 0x13)
                addr = int.from_bytes(req[2:2 + al], "big")
                size = int.from_bytes(req[2 + al:], "big")
                if addr + size > len(self.memory) or size == 0:
                    return self._nrc(sid, 0x31)
                if size > 4094:
                    return self._nrc(sid, 0x14)
                return bytes([0x63]) + bytes(self.memory[addr:addr + size])
            if sid == 0x27 and len(req) >= 2:
                if req[1] % 2:
                    return bytes([0x67, req[1]]) + self._seed
                if req[2:] == bytes(b ^ 0xFF for b in self._seed):
                    self.unlocked = True
                    return bytes([0x67, req[1]])
                return self._nrc(sid, 0x35)
            if sid == 0x31 and len(req) >= 4:
                return bytes([0x71, req[1]]) + req[2:4] + b"\x00"
            if sid == 0x34 and len(req) >= 3:
                if not self.unlocked:
                    return self._nrc(sid, 0x33)
                al, sl = req[2] & 0xF, req[2] >> 4
                self._dl_addr = int.from_bytes(req[3:3 + al], "big")
                self._dl_left = int.from_bytes(req[3 + al:3 + al + sl], "big")
                self._dl_seq = 1
                return bytes([0x74, 0x20, 0x00, 0x80])
            if sid == 0x36 and len(req) >= 2:
                if req[1] != self._dl_seq:
                    return self._nrc(sid, 0x73)
                dados = req[2:]
                if len(dados) > self._dl_left:
                    return self._nrc(sid, 0x31)
                self.memory[self._dl_addr:self._dl_addr + len(dados)] = dados
                self._dl_addr += len(dados)
                self._dl_left -= len(dados)
                self._dl_seq = (self._dl_seq + 1) & 0xFF
                return bytes([0x76, req[1]])
            if sid == 0x37:
                return bytes([0x77])
        except (IndexError, ValueError):
            return self._nrc(sid, 0x13)
        return self._nrc(sid, 0x11)
