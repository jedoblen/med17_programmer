"""Ponte J2534: processo separado (Python da MESMA arquitetura da DLL) que fala JSON por linha.

Executar:  py -3-32 -m med17.j2534.bridge        (DLL de 32 bits)
           python -m med17.j2534.bridge --simulate  (sem hardware: SIMULADO)

Somente biblioteca padrão. stdout é reservado ao protocolo; logs vão para stderr.
Requisição: {"id": 1, "cmd": "open", "args": {...}}
Resposta:   {"id": 1, "ok": true, "result": ...} | {"id": 1, "ok": false, "error": {...}}
"""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import sys

from . import constants as C
from .api import J2534, J2534Error

log = logging.getLogger("med17.bridge")


def _frame_dict(f) -> dict:
    return {"id": f.can_id, "data": f.data.hex(), "ext": f.extended, "tx_echo": f.is_tx_echo, "ts": f.timestamp}


class Session:
    def __init__(self, simulate: bool = False) -> None:
        self.simulate = simulate
        self.api: J2534 | None = None
        self.lib = None

    def _need(self) -> J2534:
        if self.api is None:
            raise RuntimeError("dispositivo não aberto")
        return self.api

    def handle(self, cmd: str, a: dict):
        if cmd == "ping":
            return {"bits": 8 * ctypes.sizeof(ctypes.c_void_p), "simulate": self.simulate}
        if cmd == "open":
            self.shutdown()
            if self.simulate:
                from ..simulator.fake_j2534 import FakeJ2534Lib
                self.lib = FakeJ2534Lib(fail=a.get("fail"))
            else:
                if os.name != "nt":
                    raise RuntimeError("DLLs J2534 só carregam no Windows")
                self.lib = ctypes.WinDLL(a["dll_path"])
            self.api = J2534(self.lib)
            self.api.open()
            return self.api.read_version()
        if cmd == "vbatt":
            return {"mv": self._need().read_vbatt_mv()}
        if cmd == "connect_can":
            api = self._need()
            api.connect_can(int(a["bitrate"]), bool(a.get("extended", False)))
            if a.get("pass_all", True):
                api.pass_all()
            return {}
        if cmd == "write":
            self._need().write(int(a["id"]), bytes.fromhex(a["data"]), int(a.get("wait_ms", 100)))
            return {}
        if cmd == "read":
            fr = self._need().read(int(a.get("wait_ms", 100)), int(a.get("max", 16)))
            return {"frames": [_frame_dict(f) for f in fr]}
        if cmd == "disconnect":
            self._need().disconnect()
            return {}
        if cmd == "close":
            self.shutdown()
            return {}
        raise ValueError(f"comando desconhecido: {cmd}")

    def shutdown(self) -> None:
        if self.api is not None:
            self.api.close()
        self.api = self.lib = None


def serve(stdin, stdout, simulate: bool = False) -> None:
    sess = Session(simulate)
    try:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            req_id = None
            try:
                req = json.loads(line)
                req_id = req.get("id")
                if req["cmd"] == "shutdown":
                    resp = {"id": req_id, "ok": True, "result": {}}
                    stdout.write(json.dumps(resp) + "\n")
                    stdout.flush()
                    break
                resp = {"id": req_id, "ok": True, "result": sess.handle(req["cmd"], req.get("args") or {})}
            except J2534Error as exc:
                resp = {"id": req_id, "ok": False,
                        "error": {"kind": "j2534", "code": exc.code, "name": exc.name, "msg": str(exc)}}
            except Exception as exc:  # erro do comando não derruba a ponte
                log.exception("erro no comando")
                resp = {"id": req_id, "ok": False, "error": {"kind": "bridge", "msg": f"{type(exc).__name__}: {exc}"}}
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
    finally:
        sess.shutdown()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulate", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    out = sys.stdout
    sys.stdout = sys.stderr  # protege o protocolo contra prints acidentais
    serve(sys.stdin, out, args.simulate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
