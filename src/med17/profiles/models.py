"""Modelo de perfil de ECU. Dados vêm SEMPRE da documentação do usuário; nada é presumido.

`None` significa "desconhecido". Operações ficam bloqueadas enquanto houver pendências.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.config import BITRATES_VALIDOS

TIPOS_MEMORIA = ("flash", "eeprom_fisica", "nvm_emulada_em_flash")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_\-]*$")


class ProfileError(ValueError):
    pass


def _int(v, campo: str, erros: list[str], maximo: int | None = None):
    if v is None:
        return None
    try:
        n = int(v, 0) if isinstance(v, str) else int(v)
        if isinstance(v, bool) or n < 0 or (maximo is not None and n > maximo):
            raise ValueError
        return n
    except (ValueError, TypeError):
        erros.append(f"{campo}: valor inválido {v!r}")
        return None


def _hex(n):
    return None if n is None else f"0x{n:X}"


def _so_chaves(d: dict, permitidas: set, nome: str, erros: list[str]) -> None:
    for k in d:
        if k not in permitidas:
            erros.append(f"{nome}: chave desconhecida {k!r}")


@dataclass
class Regiao:
    nome: str
    tipo: str
    inicio: int | None = None
    tamanho: int | None = None
    endereco_len: int | None = None
    tamanho_len: int | None = None
    observacao: str = ""

    def definida(self) -> bool:
        return None not in (self.inicio, self.tamanho, self.endereco_len, self.tamanho_len)


@dataclass
class IsotpPerfil:
    pad_byte: int | None = None
    stmin_ms: int = 0
    block_size: int = 0


@dataclass
class Protocolo:
    tipo: str = "CAN-UDS"
    bitrate: int | None = None
    id_29_bits: bool | None = None
    tx_id: int | None = None
    rx_id: int | None = None
    isotp: IsotpPerfil = field(default_factory=IsotpPerfil)
    p2: float | None = None
    p2_star: float | None = None


@dataclass
class EcuProfile:
    id: str
    nome: str
    descricao: str = ""
    simulado: bool = False
    fonte_documentacao: str = ""
    validado_leitura: bool = False
    validado_escrita: bool = False
    hardware: str = ""
    numero_peca: str = ""
    software: str = ""
    identificacao: dict[int, list[str]] = field(default_factory=dict)  # DID -> padrões (* e ?)
    protocolo: Protocolo = field(default_factory=Protocolo)
    servicos: list[int] = field(default_factory=list)  # declarados pela documentação
    estrategia_leitura: str = ""
    estrategia_escrita: str = ""
    memoria: list[Regiao] = field(default_factory=list)
    limitacoes: list[str] = field(default_factory=list)

    # ---- permissões
    def pendencias(self, operacao: str, hardware_real: bool) -> list[str]:
        if operacao not in ("leitura", "escrita"):
            raise ValueError(operacao)
        p: list[str] = []
        if self.simulado and hardware_real:
            p.append("perfil SIMULADO não pode ser usado com hardware real")
        if not self.fonte_documentacao.strip():
            p.append("fonte da documentação não informada")
        faltando = [n for n in ("bitrate", "id_29_bits", "tx_id", "rx_id") if getattr(self.protocolo, n) is None]
        if faltando:
            p.append("protocolo incompleto: " + ", ".join(faltando))
        if not any(r.definida() for r in self.memoria):
            p.append("nenhuma região de memória totalmente definida")
        if not self.validado_leitura:
            p.append("leitura não marcada como validada")
        if not self.estrategia_leitura.strip():
            p.append("estratégia de leitura não descrita")
        if operacao == "escrita":
            if not self.validado_escrita:
                p.append("gravação não marcada como validada")
            if not self.estrategia_escrita.strip():
                p.append("estratégia de gravação não descrita")
            if not self.identificacao:
                p.append("sem regras de identificação: não dá para conferir a ECU antes de gravar")
        return p

    def permite(self, operacao: str, hardware_real: bool) -> tuple[bool, list[str]]:
        pend = self.pendencias(operacao, hardware_real)
        return (not pend, pend)

    # ---- (de)serialização
    def to_dict(self) -> dict:
        pr = self.protocolo
        return {
            "id": self.id, "nome": self.nome, "descricao": self.descricao, "simulado": self.simulado,
            "fonte_documentacao": self.fonte_documentacao,
            "validado_leitura": self.validado_leitura, "validado_escrita": self.validado_escrita,
            "hardware": self.hardware, "numero_peca": self.numero_peca, "software": self.software,
            "identificacao": {f"0x{d:04X}": list(v) for d, v in self.identificacao.items()},
            "protocolo": {
                "tipo": pr.tipo, "bitrate": pr.bitrate, "id_29_bits": pr.id_29_bits,
                "tx_id": _hex(pr.tx_id), "rx_id": _hex(pr.rx_id),
                "isotp": {"pad_byte": _hex(pr.isotp.pad_byte), "stmin_ms": pr.isotp.stmin_ms,
                          "block_size": pr.isotp.block_size},
                "p2": pr.p2, "p2_star": pr.p2_star,
            },
            "servicos": list(self.servicos),
            "estrategia_leitura": self.estrategia_leitura, "estrategia_escrita": self.estrategia_escrita,
            "memoria": [{"nome": r.nome, "tipo": r.tipo, "inicio": _hex(r.inicio), "tamanho": _hex(r.tamanho),
                         "endereco_len": r.endereco_len, "tamanho_len": r.tamanho_len,
                         "observacao": r.observacao} for r in self.memoria],
            "limitacoes": list(self.limitacoes),
        }

    @staticmethod
    def from_dict(d: dict) -> "EcuProfile":
        e: list[str] = []
        if not isinstance(d, dict):
            raise ProfileError("o perfil deve ser um objeto JSON")
        _so_chaves(d, {"id", "nome", "descricao", "simulado", "fonte_documentacao", "validado_leitura",
                       "validado_escrita", "hardware", "numero_peca", "software", "identificacao", "protocolo",
                       "servicos", "estrategia_leitura", "estrategia_escrita", "memoria", "limitacoes"}, "perfil", e)
        pid = d.get("id", "")
        if not isinstance(pid, str) or not _SLUG.match(pid):
            e.append("id: use letras minúsculas, números, '_' ou '-'")
        for k in ("simulado", "validado_leitura", "validado_escrita"):
            if not isinstance(d.get(k, False), bool):
                e.append(f"{k}: deve ser true/false")
        for k in ("nome", "descricao", "fonte_documentacao", "hardware", "numero_peca", "software",
                  "estrategia_leitura", "estrategia_escrita"):
            if not isinstance(d.get(k, ""), str):
                e.append(f"{k}: deve ser texto")

        ident: dict[int, list[str]] = {}
        for k, v in (d.get("identificacao") or {}).items():
            did = _int(k, f"identificacao[{k}]", e, 0xFFFF)
            if did is None:
                continue
            if not isinstance(v, list) or not all(isinstance(x, str) and x for x in v):
                e.append(f"identificacao[{k}]: lista de padrões de texto")
                continue
            ident[did] = v

        pd = d.get("protocolo") or {}
        _so_chaves(pd, {"tipo", "bitrate", "id_29_bits", "tx_id", "rx_id", "isotp", "p2", "p2_star"}, "protocolo", e)
        ext = pd.get("id_29_bits")
        if ext is not None and not isinstance(ext, bool):
            e.append("protocolo.id_29_bits: deve ser true/false/null")
        maxid = 0x1FFFFFFF if ext else 0x7FF
        br = _int(pd.get("bitrate"), "protocolo.bitrate", e)
        if br is not None and br not in BITRATES_VALIDOS:
            e.append(f"protocolo.bitrate: use um de {BITRATES_VALIDOS}")
        idict = pd.get("isotp") or {}
        _so_chaves(idict, {"pad_byte", "stmin_ms", "block_size"}, "protocolo.isotp", e)
        stmin = _int(idict.get("stmin_ms", 0), "isotp.stmin_ms", e, 127) or 0
        bs = _int(idict.get("block_size", 0), "isotp.block_size", e, 255) or 0
        proto = Protocolo(
            tipo=str(pd.get("tipo", "CAN-UDS")), bitrate=br, id_29_bits=ext,
            tx_id=_int(pd.get("tx_id"), "protocolo.tx_id", e, maxid),
            rx_id=_int(pd.get("rx_id"), "protocolo.rx_id", e, maxid),
            isotp=IsotpPerfil(_int(idict.get("pad_byte"), "isotp.pad_byte", e, 255), stmin, bs),
            p2=pd.get("p2"), p2_star=pd.get("p2_star"),
        )

        servicos = [_int(s, "servicos", e, 255) for s in (d.get("servicos") or [])]
        regs: list[Regiao] = []
        for i, r in enumerate(d.get("memoria") or []):
            _so_chaves(r, {"nome", "tipo", "inicio", "tamanho", "endereco_len", "tamanho_len", "observacao"},
                       f"memoria[{i}]", e)
            if r.get("tipo") not in TIPOS_MEMORIA:
                e.append(f"memoria[{i}].tipo: use um de {TIPOS_MEMORIA}")
            regs.append(Regiao(
                str(r.get("nome", "")), str(r.get("tipo", "")),
                _int(r.get("inicio"), f"memoria[{i}].inicio", e), _int(r.get("tamanho"), f"memoria[{i}].tamanho", e),
                _int(r.get("endereco_len"), f"memoria[{i}].endereco_len", e, 15),
                _int(r.get("tamanho_len"), f"memoria[{i}].tamanho_len", e, 15), str(r.get("observacao", ""))))
        if e:
            raise ProfileError("; ".join(e))
        return EcuProfile(
            id=pid, nome=d.get("nome", ""), descricao=d.get("descricao", ""), simulado=d.get("simulado", False),
            fonte_documentacao=d.get("fonte_documentacao", ""), validado_leitura=d.get("validado_leitura", False),
            validado_escrita=d.get("validado_escrita", False), hardware=d.get("hardware", ""),
            numero_peca=d.get("numero_peca", ""), software=d.get("software", ""), identificacao=ident,
            protocolo=proto, servicos=servicos, estrategia_leitura=d.get("estrategia_leitura", ""),
            estrategia_escrita=d.get("estrategia_escrita", ""), memoria=regs,
            limitacoes=list(d.get("limitacoes") or []))


def modelo() -> EcuProfile:
    """Perfil em branco: tudo desconhecido e nada validado."""
    return EcuProfile(
        id="med17-modelo", nome="MED17 — preencher a partir da documentação da ECU",
        memoria=[Regiao("FLASH", "flash"), Regiao("EEPROM", "eeprom_fisica")],
        limitacoes=["Preencha apenas com dados da documentação autorizada da sua ECU."])
