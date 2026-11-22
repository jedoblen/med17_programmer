"""Cliente da ponte J2534 (roda no processo da interface)."""
from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger("med17.j2534.client")
_SRC = Path(__file__).resolve().parents[2]  # pasta que contém o pacote med17


class BridgeError(Exception):
    def __init__(self, msg: str, info: dict | None = None) -> None:
        super().__init__(msg)
        self.info = info or {}


class BridgeTimeout(BridgeError):
    pass


def bridge_command(bits: int | None, simulate: bool = False) -> list[str]:
    """Escolhe o Python da ponte conforme o bitness da DLL."""
    base = ["-m", "med17.j2534.bridge"] + (["--simulate"] if simulate else [])
    host_bits = 64 if sys.maxsize > 2**32 else 32
    if simulate or bits is None or bits == host_bits:
        return [sys.executable, *base]
    if os.name != "nt" or shutil.which("py") is None:
        raise BridgeError("Launcher 'py' não encontrado; instale o Python de %d bits." % bits)
    return ["py", f"-3-{bits}", *base]


class BridgeClient:
    def __init__(self, cmd: list[str], default_timeout: float = 10.0) -> None:
        self.cmd, self.default_timeout = cmd, default_timeout
        self._proc: subprocess.Popen | None = None
        self._q: queue.Queue = queue.Queue()
        self._next = 0
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        env = dict(os.environ, PYTHONPATH=str(_SRC), PYTHONIOENCODING="utf-8")
        self._proc = subprocess.Popen(self.cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, env=env)
        threading.Thread(target=self._pump_out, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()
        log.info("Ponte iniciada: %s", " ".join(self.cmd))

    def _pump_out(self) -> None:
        for raw in self._proc.stdout:
            try:
                self._q.put(json.loads(raw.decode("utf-8")))
            except ValueError:
                log.warning("Linha inválida da ponte: %r", raw[:200])
        self._q.put(None)  # fim do processo

    def _pump_err(self) -> None:
        for raw in self._proc.stderr:
            log.debug("[ponte] %s", raw.decode("utf-8", "replace").rstrip())

    def call(self, cmd: str, timeout: float | None = None, **args):
        with self._lock:
            if not self.running:
                raise BridgeError("ponte não está em execução")
            self._next += 1
            rid = self._next
            self._proc.stdin.write((json.dumps({"id": rid, "cmd": cmd, "args": args}) + "\n").encode("utf-8"))
            self._proc.stdin.flush()
            limite = timeout if timeout is not None else self.default_timeout
            while True:
                try:
                    resp = self._q.get(timeout=limite)
                except queue.Empty:
                    self.kill()
                    raise BridgeTimeout(f"timeout ({limite:.0f}s) aguardando '{cmd}'; ponte encerrada") from None
                if resp is None:
                    raise BridgeError("ponte encerrou inesperadamente")
                if resp.get("id") == rid:
                    break
            if not resp["ok"]:
                raise BridgeError(resp["error"].get("msg", "erro"), resp["error"])
            return resp["result"]

    def kill(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def stop(self) -> None:
        """Encerramento educado (a ponte fecha canal e dispositivo); mata se travar."""
        if self.running:
            try:
                self.call("shutdown", timeout=3)
            except BridgeError:
                pass
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.kill()
        log.info("Ponte encerrada.")
