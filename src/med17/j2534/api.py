"""Wrapper ctypes da API J2534. Recebe a biblioteca já carregada (`lib`),
o que permite usar a DLL real (WinDLL) ou o simulador (FakeJ2534Lib)."""
from __future__ import annotations

import ctypes
import logging
from ctypes import byref, c_ulong, create_string_buffer
from dataclasses import dataclass

from . import constants as C

log = logging.getLogger("med17.j2534")


class J2534Error(Exception):
    def __init__(self, code: int, func: str, detail: str = "") -> None:
        self.code, self.func, self.detail = code, func, detail
        self.name = C.ERROR_NAMES.get(code, f"0x{code:X}")
        super().__init__(f"{func}: {self.name}" + (f" — {detail}" if detail else ""))


class PassThruMsg(ctypes.Structure):
    _fields_ = [
        ("ProtocolID", c_ulong), ("RxStatus", c_ulong), ("TxFlags", c_ulong),
        ("Timestamp", c_ulong), ("DataSize", c_ulong), ("ExtraDataIndex", c_ulong),
        ("Data", ctypes.c_ubyte * 4128),
    ]


@dataclass
class CanFrame:
    can_id: int
    data: bytes
    extended: bool = False
    rx_status: int = 0
    timestamp: int = 0

    @property
    def is_tx_echo(self) -> bool:
        return bool(self.rx_status & C.TX_MSG_TYPE)


def _fill(msg: PassThruMsg, protocol: int, flags: int, payload: bytes) -> None:
    msg.ProtocolID, msg.TxFlags, msg.DataSize = protocol, flags, len(payload)
    msg.RxStatus = msg.Timestamp = msg.ExtraDataIndex = 0
    for i, b in enumerate(payload):
        msg.Data[i] = b


def _id_bytes(can_id: int) -> bytes:
    return can_id.to_bytes(4, "big")


class J2534:
    def __init__(self, lib) -> None:
        self.lib = lib
        self.device_id: int | None = None
        self.channel_id: int | None = None
        self._flags = 0

    # -- utilidades
    def _last_error(self) -> str:
        try:
            buf = create_string_buffer(256)
            self.lib.PassThruGetLastError(buf)
            return buf.value.decode("ascii", "replace")
        except Exception:
            return ""

    def _check(self, rc: int, func: str) -> None:
        if rc != 0:
            raise J2534Error(rc, func, self._last_error())

    # -- dispositivo
    def open(self) -> None:
        dev = c_ulong()
        self._check(self.lib.PassThruOpen(None, byref(dev)), "PassThruOpen")
        self.device_id = dev.value
        log.info("Dispositivo J2534 aberto (id=%d)", self.device_id)

    def read_version(self) -> dict:
        fw, dll, api = (create_string_buffer(80) for _ in range(3))
        self._check(self.lib.PassThruReadVersion(self.device_id, fw, dll, api), "PassThruReadVersion")
        return {k: v.value.decode("ascii", "replace") for k, v in
                (("firmware", fw), ("dll", dll), ("api", api))}

    def read_vbatt_mv(self) -> int:
        mv = c_ulong()
        self._check(self.lib.PassThruIoctl(self.device_id, C.READ_VBATT, None, byref(mv)), "PassThruIoctl(READ_VBATT)")
        return mv.value

    def close(self) -> None:
        """Desconexão segura: nunca levanta exceção, tenta fechar tudo."""
        if self.channel_id is not None:
            try:
                self.disconnect()
            except Exception as exc:
                log.warning("Falha ao desconectar canal: %s", exc)
        if self.device_id is not None:
            try:
                self.lib.PassThruClose(self.device_id)
            except Exception as exc:
                log.warning("Falha ao fechar dispositivo: %s", exc)
            self.device_id = None

    # -- canal CAN
    def connect_can(self, bitrate: int, extended: bool = False) -> None:
        self._flags = C.CAN_29BIT_ID if extended else 0
        ch = c_ulong()
        self._check(self.lib.PassThruConnect(self.device_id, C.CAN, self._flags, bitrate, byref(ch)),
                    "PassThruConnect")
        self.channel_id = ch.value
        log.info("Canal CAN aberto (id=%d, %d bit/s, 29 bits=%s)", self.channel_id, bitrate, extended)

    def disconnect(self) -> None:
        ch, self.channel_id = self.channel_id, None
        if ch is not None:
            self._check(self.lib.PassThruDisconnect(ch), "PassThruDisconnect")

    def start_filter(self, filter_type: int, mask: int, pattern: int) -> int:
        """Filtro de passagem/bloqueio por ID (mask/pattern no formato de ID CAN)."""
        m, p = PassThruMsg(), PassThruMsg()
        _fill(m, C.CAN, self._flags, _id_bytes(mask))
        _fill(p, C.CAN, self._flags, _id_bytes(pattern))
        fid = c_ulong()
        self._check(self.lib.PassThruStartMsgFilter(self.channel_id, filter_type, byref(m), byref(p), None, byref(fid)),
                    "PassThruStartMsgFilter")
        return fid.value

    def pass_all(self) -> int:
        return self.start_filter(C.PASS_FILTER, 0, 0)

    def clear_filters(self) -> None:
        self._check(self.lib.PassThruIoctl(self.channel_id, C.CLEAR_MSG_FILTERS, None, None),
                    "PassThruIoctl(CLEAR_MSG_FILTERS)")

    def write(self, can_id: int, data: bytes, timeout_ms: int = 100) -> None:
        if len(data) > 8:
            raise ValueError("quadro CAN clássico aceita no máximo 8 bytes")
        msg = PassThruMsg()
        _fill(msg, C.CAN, self._flags, _id_bytes(can_id) + bytes(data))
        n = c_ulong(1)
        self._check(self.lib.PassThruWriteMsgs(self.channel_id, byref(msg), byref(n), timeout_ms), "PassThruWriteMsgs")
        if n.value != 1:
            raise J2534Error(C.ERR_TIMEOUT, "PassThruWriteMsgs", "quadro não aceito pelo buffer")

    def read(self, timeout_ms: int = 100, max_msgs: int = 16) -> list[CanFrame]:
        arr = (PassThruMsg * max_msgs)()
        n = c_ulong(max_msgs)
        rc = self.lib.PassThruReadMsgs(self.channel_id, arr, byref(n), timeout_ms)
        if rc not in (0, C.ERR_TIMEOUT, C.ERR_BUFFER_EMPTY):
            raise J2534Error(rc, "PassThruReadMsgs", self._last_error())
        frames = []
        for i in range(n.value):
            m = arr[i]
            if m.DataSize < 4:  # indicações sem dados (ex.: início de mensagem)
                continue
            raw = bytes(m.Data[: m.DataSize])
            frames.append(CanFrame(int.from_bytes(raw[:4], "big"), raw[4:],
                                   bool(m.RxStatus & C.CAN_29BIT_RX), m.RxStatus, m.Timestamp))
        return frames
