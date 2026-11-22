"""SIMULADOR de biblioteca J2534 (não é hardware). Usado em testes e no modo simulado.

Quadros enviados com PassThruWriteMsgs voltam na fila de recepção (loopback).
`fail` permite injetar códigos de erro: {"PassThruConnect": 8}.
"""
from __future__ import annotations

from ..j2534 import constants as C


def _o(p):
    return getattr(p, "_obj", p)


class FakeJ2534Lib:
    def __init__(self, fail: dict | None = None, vbatt_mv: int = 12600) -> None:
        self.fail = dict(fail or {})
        self.vbatt_mv = vbatt_mv
        self.rx: list[bytes] = []
        self.tx: list[bytes] = []
        self.filters = 0
        self.closed = False
        self.disconnected = False
        self._last = ""

    def _err(self, name: str) -> int:
        rc = self.fail.get(name, 0)
        if rc:
            self._last = f"{name} falhou (simulado)"
        return rc

    def inject(self, can_id: int, data: bytes) -> None:
        self.rx.append(can_id.to_bytes(4, "big") + data)

    def PassThruOpen(self, name, pdev):
        if rc := self._err("PassThruOpen"):
            return rc
        _o(pdev).value = 1
        return 0

    def PassThruClose(self, dev):
        self.closed = True
        return 0

    def PassThruConnect(self, dev, proto, flags, baud, pch):
        if rc := self._err("PassThruConnect"):
            return rc
        _o(pch).value = 7
        return 0

    def PassThruDisconnect(self, ch):
        self.disconnected = True
        return 0

    def PassThruReadVersion(self, dev, fw, dll, api):
        fw.value, dll.value, api.value = b"SIM-FW 0.1", b"SIM-DLL 0.1", b"04.04"
        return 0

    def PassThruGetLastError(self, buf):
        buf.value = self._last.encode("ascii", "replace")
        return 0

    def PassThruStartMsgFilter(self, ch, ftype, pmask, ppat, pflow, pfid):
        if rc := self._err("PassThruStartMsgFilter"):
            return rc
        self.filters += 1
        _o(pfid).value = self.filters
        return 0

    def PassThruWriteMsgs(self, ch, pmsg, pn, timeout):
        if rc := self._err("PassThruWriteMsgs"):
            return rc
        m = _o(pmsg)
        raw = bytes(m.Data[: m.DataSize])
        self.tx.append(raw)
        self.rx.append(raw)  # loopback
        return 0

    def PassThruReadMsgs(self, ch, arr, pn, timeout):
        n = _o(pn)
        k = min(len(self.rx), n.value)
        for i in range(k):
            raw = self.rx.pop(0)
            arr[i].DataSize = len(raw)
            arr[i].RxStatus = 0
            for j, b in enumerate(raw):
                arr[i].Data[j] = b
        n.value = k
        return 0 if k else C.ERR_BUFFER_EMPTY

    def PassThruIoctl(self, dev, ioctl, pin, pout):
        if ioctl == C.READ_VBATT:
            _o(pout).value = self.vbatt_mv
        return 0
