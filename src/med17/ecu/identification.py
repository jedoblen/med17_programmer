"""Identificação de ECU via UDS 0x22 (DIDs de identificação da ISO 14229-1, Anexo C).

Nem toda ECU suporta esses DIDs; a ausência é registrada, não tratada como falha.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ..uds.uds import UdsClient, UdsError, UdsNegativeResponse, UdsTimeout

log = logging.getLogger("med17.ecu")

DIDS_PADRAO = {
    0xF187: "Nº de peça (fabricante do veículo)",
    0xF188: "Nº de software da ECU (fabricante do veículo)",
    0xF189: "Versão de software da ECU (fabricante do veículo)",
    0xF18A: "Identificação do fornecedor do sistema",
    0xF18C: "Nº de série da ECU",
    0xF190: "VIN",
    0xF191: "Nº de hardware da ECU (fabricante do veículo)",
    0xF192: "Nº de hardware (fornecedor)",
    0xF193: "Versão de hardware (fornecedor)",
    0xF194: "Nº de software (fornecedor)",
    0xF195: "Versão de software (fornecedor)",
}


class IdentificationError(Exception):
    pass


def decodificar(b: bytes) -> str:
    limpo = b.rstrip(b"\x00\xff ")
    if limpo and all(0x20 <= x <= 0x7E for x in limpo):
        return limpo.decode("ascii")
    return "0x" + b.hex().upper()


@dataclass
class EcuIdentification:
    valores: dict[int, bytes] = field(default_factory=dict)
    nao_suportados: dict[int, int] = field(default_factory=dict)  # DID -> NRC
    sem_resposta: list[int] = field(default_factory=list)

    def texto(self, did: int) -> str | None:
        v = self.valores.get(did)
        return None if v is None else decodificar(v)


def identify(uds: UdsClient, dids: list[int] | None = None, session: int | None = None,
             max_timeouts_seguidos: int = 3) -> EcuIdentification:
    """Lê os DIDs informados. Aborta se a ECU não responder a vários DIDs seguidos."""
    if session is not None:
        uds.diagnostic_session_control(session)
    ident = EcuIdentification()
    seguidos = 0
    for did in (dids if dids is not None else sorted(DIDS_PADRAO)):
        try:
            ident.valores[did] = uds.read_data_by_identifier(did)
            seguidos = 0
        except UdsNegativeResponse as exc:
            ident.nao_suportados[did] = exc.nrc
            seguidos = 0
        except UdsTimeout:
            ident.sem_resposta.append(did)
            seguidos += 1
            if seguidos >= max_timeouts_seguidos:
                raise IdentificationError("ECU não respondeu: confira alimentação, ligações, IDs e bitrate") from None
        except UdsError as exc:
            log.warning("DID 0x%04X: %s", did, exc)
            ident.sem_resposta.append(did)
    if not ident.valores and not ident.nao_suportados:
        raise IdentificationError("nenhuma resposta da ECU aos DIDs solicitados")
    return ident
