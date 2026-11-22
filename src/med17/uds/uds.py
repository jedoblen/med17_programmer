"""Cliente UDS (ISO 14229-1) sobre ISO-TP.

Apenas transporte e codificação dos serviços: não contém algoritmos de seed-key,
endereços nem procedimentos de programação de nenhuma ECU. Nada presume que a
ECU suporte determinado serviço: NRCs viram exceções.
"""
from __future__ import annotations

import logging
import threading
import time

from ..isotp.isotp import IsoTpError, IsoTpLink, IsoTpTimeout

log = logging.getLogger("med17.uds")

NRC_NOMES = {
    0x10: "generalReject", 0x11: "serviceNotSupported", 0x12: "subFunctionNotSupported",
    0x13: "incorrectMessageLengthOrInvalidFormat", 0x14: "responseTooLong",
    0x21: "busyRepeatRequest", 0x22: "conditionsNotCorrect", 0x24: "requestSequenceError",
    0x25: "noResponseFromSubnetComponent", 0x26: "failurePreventsExecutionOfRequestedAction",
    0x31: "requestOutOfRange", 0x33: "securityAccessDenied", 0x35: "invalidKey",
    0x36: "exceededNumberOfAttempts", 0x37: "requiredTimeDelayNotExpired",
    0x70: "uploadDownloadNotAccepted", 0x71: "transferDataSuspended",
    0x72: "generalProgrammingFailure", 0x73: "wrongBlockSequenceCounter",
    0x78: "requestCorrectlyReceivedResponsePending", 0x7E: "subFunctionNotSupportedInActiveSession",
    0x7F: "serviceNotSupportedInActiveSession",
}


class UdsError(Exception):
    pass


class UdsTimeout(UdsError):
    pass


class UdsNegativeResponse(UdsError):
    def __init__(self, sid: int, nrc: int) -> None:
        self.sid, self.nrc = sid, nrc
        self.nome = NRC_NOMES.get(nrc, "desconhecido")
        super().__init__(f"serviço 0x{sid:02X}: resposta negativa 0x{nrc:02X} ({self.nome})")


def _int_bytes(valor: int, n: int) -> bytes:
    if n < 1 or valor < 0 or valor >= 1 << (8 * n):
        raise ValueError(f"valor 0x{valor:X} não cabe em {n} byte(s)")
    return valor.to_bytes(n, "big")


def _alfi(addr: int, size: int, addr_len: int, size_len: int) -> bytes:
    """addressAndLengthFormatIdentifier + endereço + tamanho (comprimentos explícitos)."""
    if not (1 <= addr_len <= 15 and 1 <= size_len <= 15):
        raise ValueError("comprimentos devem estar entre 1 e 15")
    return bytes([(size_len << 4) | addr_len]) + _int_bytes(addr, addr_len) + _int_bytes(size, size_len)


class UdsClient:
    def __init__(self, link: IsoTpLink, p2: float = 1.0, p2_star: float = 5.0, max_pending: int = 200) -> None:
        self.link, self.p2, self.p2_star, self.max_pending = link, p2, p2_star, max_pending
        self._lock = threading.Lock()

    # -- núcleo
    def request(self, payload: bytes) -> bytes:
        with self._lock:
            return self._request_locked(payload)

    def _request_locked(self, payload: bytes) -> bytes:
        sid = payload[0]
        log.debug("UDS >> %s", payload.hex())
        self.link.send(payload)
        timeout, pendentes = self.p2, 0
        while True:
            try:
                resp = self.link.recv(timeout)
            except IsoTpTimeout:
                raise UdsTimeout(f"sem resposta ao serviço 0x{sid:02X}") from None
            log.debug("UDS << %s", resp.hex())
            if resp[0] == 0x7F:
                if len(resp) < 3 or resp[1] != sid:
                    continue  # negativa de outro serviço: ignora
                if resp[2] == 0x78:
                    pendentes += 1
                    if pendentes > self.max_pending:
                        raise UdsTimeout("response pending em excesso")
                    timeout = self.p2_star
                    continue
                raise UdsNegativeResponse(sid, resp[2])
            if resp[0] == (sid + 0x40) & 0xFF:
                return resp
            raise UdsError(f"resposta inesperada: {resp.hex()}")

    # -- serviços prioritários
    def diagnostic_session_control(self, session: int) -> dict:
        r = self.request(bytes([0x10, session]))
        out = {"session": r[1] if len(r) > 1 else session}
        if len(r) >= 6:
            out["p2"] = int.from_bytes(r[2:4], "big") / 1000
            out["p2_star"] = int.from_bytes(r[4:6], "big") * 10 / 1000
            self.p2 = max(self.p2, out["p2"])
            self.p2_star = max(self.p2_star, out["p2_star"])
        return out

    def read_data_by_identifier(self, did: int) -> bytes:
        r = self.request(bytes([0x22]) + _int_bytes(did, 2))
        if r[1:3] != _int_bytes(did, 2):
            raise UdsError("DID da resposta difere do solicitado")
        return r[3:]

    def read_memory_by_address(self, addr: int, size: int, *, addr_len: int, size_len: int) -> bytes:
        return self.request(bytes([0x23]) + _alfi(addr, size, addr_len, size_len))[1:]

    def security_access_request_seed(self, level: int) -> bytes:
        if level % 2 == 0:
            raise ValueError("nível de requestSeed deve ser ímpar")
        return self.request(bytes([0x27, level]))[2:]

    def security_access_send_key(self, level: int, key: bytes) -> None:
        if level % 2 == 0:
            raise ValueError("informe o nível do requestSeed (ímpar); o sendKey usa nível+1")
        self.request(bytes([0x27, level + 1]) + key)

    def routine_control(self, subfunction: int, routine_id: int, data: bytes = b"") -> bytes:
        r = self.request(bytes([0x31, subfunction]) + _int_bytes(routine_id, 2) + data)
        return r[4:]

    def _transfer_request(self, sid: int, addr: int, size: int, addr_len: int, size_len: int,
                          data_format: int) -> int:
        r = self.request(bytes([sid, data_format]) + _alfi(addr, size, addr_len, size_len))
        n = (r[1] >> 4) if len(r) > 1 else 0
        if n == 0 or len(r) < 2 + n:
            raise UdsError("resposta sem maxNumberOfBlockLength")
        return int.from_bytes(r[2:2 + n], "big")

    def request_download(self, addr: int, size: int, *, addr_len: int, size_len: int, data_format: int = 0) -> int:
        """Devolve maxNumberOfBlockLength informado pela ECU."""
        return self._transfer_request(0x34, addr, size, addr_len, size_len, data_format)

    def request_upload(self, addr: int, size: int, *, addr_len: int, size_len: int, data_format: int = 0) -> int:
        return self._transfer_request(0x35, addr, size, addr_len, size_len, data_format)

    def transfer_data(self, sequence: int, data: bytes = b"") -> bytes:
        r = self.request(bytes([0x36, sequence & 0xFF]) + data)
        if len(r) < 2 or r[1] != sequence & 0xFF:
            raise UdsError("contador de bloco da resposta difere do enviado")
        return r[2:]

    def request_transfer_exit(self, data: bytes = b"") -> bytes:
        return self.request(bytes([0x37]) + data)[1:]

    def tester_present(self) -> None:
        self.request(bytes([0x3E, 0x00]))

    def tester_present_suppressed(self) -> bool:
        """Envia 3E 80 sem aguardar resposta. Não interfere em requisição em andamento (devolve False)."""
        if not self._lock.acquire(blocking=False):
            return False
        try:
            self.link.send(bytes([0x3E, 0x80]))
            return True
        except IsoTpError as exc:
            log.warning("Falha ao enviar Tester Present: %s", exc)
            return False
        finally:
            self._lock.release()


class TesterPresentKeeper:
    __test__ = False  # evita coleta indevida pelo pytest
    """Envia Tester Present periodicamente em segundo plano (sessão não-padrão ativa)."""

    def __init__(self, client: UdsClient, interval: float = 2.0) -> None:
        self.client, self.interval = client, interval
        self.enviados = 0
        self._stop = threading.Event()
        self._t: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            if self.client.tester_present_suppressed():
                self.enviados += 1

    def stop(self) -> None:
        self._stop.set()
        if self._t:
            self._t.join(timeout=self.interval + 1)
