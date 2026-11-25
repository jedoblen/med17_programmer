"""Decodificação OFFLINE de UDS a partir de uma captura PASSIVA já gravada.

Remonta as mensagens ISO-TP completas (SF/FF/CF) por ID e decodifica os serviços
prioritários do projeto. Não envia nada, não deriva algoritmo de segurança: quando
houver Security Access, só informa que ocorreu e em qual serviço, sem analisar
semente/chave.
"""
from __future__ import annotations

from dataclasses import dataclass

from .capture import Registro

NOMES_SID = {
    0x10: "DiagnosticSessionControl", 0x22: "ReadDataByIdentifier", 0x23: "ReadMemoryByAddress",
    0x27: "SecurityAccess", 0x28: "CommunicationControl", 0x2E: "WriteDataByIdentifier",
    0x31: "RoutineControl", 0x34: "RequestDownload", 0x35: "RequestUpload",
    0x36: "TransferData", 0x37: "RequestTransferExit", 0x3E: "TesterPresent",
    0x19: "ReadDTCInformation", 0x14: "ClearDiagnosticInformation",
}


@dataclass
class Mensagem:
    t: float
    payload: bytes


def reassemble_isotp(frames: list[Registro]) -> list[Mensagem]:
    """`frames` deve conter só os quadros de UM ID, em ordem de tempo. Ignora
    quadros de Flow Control (tipo 3): eles pertencem ao fluxo, não ao payload."""
    out: list[Mensagem] = []
    i = 0
    while i < len(frames):
        f = frames[i]
        d = f.data
        tipo = (d[0] >> 4) if d else None
        if tipo == 0:  # Single Frame
            n = d[0] & 0xF
            if 1 <= n <= 7 and len(d) >= 1 + n:
                out.append(Mensagem(f.t, bytes(d[1:1 + n])))
            i += 1
        elif tipo == 1 and len(d) >= 8:  # First Frame
            total = ((d[0] & 0xF) << 8) | d[1]
            buf = bytearray(d[2:8])
            j, esperado, t_fim = i + 1, 1, f.t
            while len(buf) < total and j < len(frames):
                cf = frames[j]
                t2 = (cf.data[0] >> 4) if cf.data else None
                if t2 == 2 and (cf.data[0] & 0xF) == esperado:
                    buf += cf.data[1:1 + min(7, total - len(buf))]
                    esperado = (esperado + 1) & 0xF
                    t_fim = cf.t
                    j += 1
                elif t2 == 3:  # Flow Control: faz parte do fluxo, não do payload
                    j += 1
                else:
                    break  # quadro inesperado: aborta esta remontagem
            if len(buf) >= total:
                out.append(Mensagem(t_fim, bytes(buf[:total])))
                i = j
            else:
                i += 1  # remontagem incompleta: descarta e segue
        else:
            i += 1  # Flow Control isolado ou lixo: ignora
    return out


def _alfi(payload: bytes, pos: int):
    if pos >= len(payload):
        return None, None, pos
    b = payload[pos]
    size_len, addr_len = b >> 4, b & 0xF
    fim = pos + 1 + addr_len + size_len
    if addr_len == 0 or size_len == 0 or fim > len(payload):
        return None, None, pos
    addr = int.from_bytes(payload[pos + 1:pos + 1 + addr_len], "big")
    size = int.from_bytes(payload[pos + 1 + addr_len:fim], "big")
    return {"endereco": addr, "endereco_hex": f"0x{addr:X}", "tamanho": size,
            "endereco_len": addr_len, "tamanho_len": size_len}, fim, fim


def decodificar_mensagem(payload: bytes) -> dict:
    """Decodifica uma mensagem UDS já remontada. `papel` é preenchido por quem chama."""
    if not payload:
        return {"sid": None, "nome": "(vazio)"}
    sid = payload[0]
    if sid == 0x7F and len(payload) >= 3:
        return {"sid": payload[1], "nome": "RespostaNegativa", "nrc": payload[2]}
    base = sid - 0x40 if sid >= 0x40 else sid
    nome = NOMES_SID.get(base, f"0x{sid:02X}")
    resposta = sid >= 0x40
    info: dict = {"sid": base, "nome": nome, "resposta": resposta}
    try:
        if base == 0x10:
            info["subfuncao"] = payload[1] & 0x7F
        elif base == 0x3E:
            info["subfuncao"] = payload[1] & 0x7F
        elif base == 0x22:
            info["did"] = int.from_bytes(payload[1:3], "big") if not resposta or len(payload) >= 3 else None
            if resposta:
                info["dados_hex"] = payload[3:].hex()
        elif base == 0x23:
            if resposta:
                info["dados_hex"] = payload[1:].hex()
                info["bytes"] = len(payload) - 1
            else:
                campos, _, _ = _alfi(payload, 1)
                if campos:
                    info.update(campos)
        elif base == 0x27:
            info["nivel"] = payload[1] if len(payload) > 1 else None
            info["contem_seed_ou_key"] = len(payload) > 2
        elif base in (0x34, 0x35):
            if resposta:
                if len(payload) >= 2:
                    n = payload[1] >> 4
                    info["max_bloco"] = int.from_bytes(payload[2:2 + n], "big") if len(payload) >= 2 + n else None
            else:
                campos, pos, _ = _alfi(payload, 2)
                if campos:
                    info.update(campos)
                    info["formato_dados"] = payload[1]
        elif base == 0x36:
            info["contador_bloco"] = payload[1] if len(payload) > 1 else None
            info["bytes_dados"] = max(len(payload) - 2, 0)
        elif base == 0x31:
            info["subfuncao"] = payload[1] if len(payload) > 1 else None
            info["rotina_id"] = int.from_bytes(payload[2:4], "big") if len(payload) >= 4 else None
    except (IndexError, ValueError):
        info["aviso"] = "payload curto/ inesperado para este serviço"
    return info


def decodificar_sessao(regs: list[Registro], req_id: int, resp_id: int) -> list[dict]:
    """Decodifica a troca entre dois IDs específicos (vindos do relatório de pares).
    `req_id` = tester -> ECU, `resp_id` = ECU -> tester."""
    req = sorted((r for r in regs if r.can_id == req_id), key=lambda r: r.t)
    resp = sorted((r for r in regs if r.can_id == resp_id), key=lambda r: r.t)
    eventos = [("tester", m) for m in reassemble_isotp(req)] + [("ECU", m) for m in reassemble_isotp(resp)]
    eventos.sort(key=lambda x: x[1].t)
    out = []
    for papel, msg in eventos:
        info = decodificar_mensagem(msg.payload)
        info["t"] = msg.t
        info["papel"] = papel
        info["payload_hex"] = msg.payload.hex()
        out.append(info)
    return out


def relatorio_sessao(eventos: list[dict]) -> str:
    L = []
    for e in eventos:
        if e["nome"] == "RespostaNegativa":
            L.append(f"[{e['t']:7.3f}s] {e['papel']:6} NRC para 0x{e['sid']:02X}: 0x{e['nrc']:02X}")
            continue
        extra = ", ".join(f"{k}={v}" for k, v in e.items()
                          if k not in ("t", "papel", "nome", "sid", "resposta", "payload_hex"))
        L.append(f"[{e['t']:7.3f}s] {e['papel']:6} {e['nome']}" + (f"  ({extra})" if extra else ""))
        if e["nome"] == "SecurityAccess" and e.get("contem_seed_ou_key"):
            L.append("           (semente/chave presente — não decodificada; válida só para esta sessão)")
    return "\n".join(L) if L else "(nenhum evento decodificado)"
