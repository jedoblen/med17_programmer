"""Captura PASSIVA de tráfego CAN e análise para descobrir IDs/protocolo de diagnóstico.

Nada é transmitido ao barramento. Os resultados são indícios heurísticos, a confirmar.
"""
from __future__ import annotations

import csv
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SIDS_UDS = {0x10, 0x11, 0x14, 0x19, 0x22, 0x23, 0x27, 0x28, 0x2E, 0x31, 0x34, 0x35, 0x36, 0x37, 0x3E, 0x85}
SIDS_KWP = {0x1A, 0x21, 0x81, 0x82, 0x83}  # típicos de KWP2000, ausentes no conjunto UDS acima


@dataclass
class Registro:
    t: float          # segundos desde o início da captura (relógio do PC)
    ts_dev: int       # timestamp da interface (µs, 32 bits)
    can_id: int
    extended: bool
    data: bytes


def capturar(bus, segundos: float, parar: Callable[[], bool] | None = None) -> list[Registro]:
    ini = time.monotonic()
    regs: list[Registro] = []
    while time.monotonic() - ini < segundos and not (parar and parar()):
        f = bus.recv(0.2)
        if f is not None:
            regs.append(Registro(time.monotonic() - ini, f.timestamp, f.can_id, f.extended, f.data))
    return regs


def salvar_csv(regs: list[Registro], caminho: str | Path) -> None:
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "ts_dev_us", "id_hex", "ext", "dados_hex"])
        for r in regs:
            w.writerow([f"{r.t:.6f}", r.ts_dev, f"{r.can_id:X}", int(r.extended), r.data.hex()])


def carregar_csv(caminho: str | Path) -> list[Registro]:
    with open(caminho, newline="", encoding="utf-8") as f:
        return [Registro(float(l["t_s"]), int(l["ts_dev_us"]), int(l["id_hex"], 16), bool(int(l["ext"])),
                         bytes.fromhex(l["dados_hex"])) for l in csv.DictReader(f)]


def resumo_por_id(regs: list[Registro]) -> list[dict]:
    por: dict[tuple[int, bool], list[Registro]] = defaultdict(list)
    for r in regs:
        por[(r.can_id, r.extended)].append(r)
    out = []
    for (cid, ext), lst in por.items():
        ts = [x.t for x in lst]
        periodo = (ts[-1] - ts[0]) / (len(ts) - 1) * 1000 if len(ts) > 2 else None
        out.append({"id": cid, "ext": ext, "n": len(lst), "dlc": sorted({len(x.data) for x in lst}),
                    "periodo_ms": periodo})
    return sorted(out, key=lambda d: d["id"])


def _payload_isotp(data: bytes) -> bytes | None:
    """Início do payload ISO-TP de Single/First Frame (None se não for SF/FF plausível)."""
    if not data:
        return None
    tipo = data[0] >> 4
    if tipo == 0:
        n = data[0] & 0xF
        return data[1:1 + n] if 1 <= n <= 7 and len(data) >= 1 + n else None
    if tipo == 1 and len(data) >= 3:
        return data[2:]
    return None


def detectar_pares_uds(regs: list[Registro], janela: float = 1.0, minimo: int = 2) -> list[dict]:
    """Pares (ID de requisição, ID de resposta) cujos payloads ISO-TP lembram serviços UDS/KWP."""
    pend: dict[tuple[int, int], list[tuple[float, int]]] = {}  # (id,sid) -> requisições recentes
    contagem: Counter = Counter()
    servicos: dict[tuple[int, int], set[int]] = defaultdict(set)
    for r in sorted(regs, key=lambda x: x.t):
        p = _payload_isotp(r.data)
        if not p:
            continue
        sid = p[0]
        alvo = None
        if sid == 0x7F and len(p) >= 3:
            alvo = p[1]
        elif (sid - 0x40) in SIDS_UDS | SIDS_KWP:
            alvo = sid - 0x40
        if alvo is not None:
            for (rid, s), lst in pend.items():
                if s == alvo and rid != r.can_id and lst and r.t - lst[-1][0] <= janela:
                    contagem[(rid, r.can_id)] += 1
                    servicos[(rid, r.can_id)].add(alvo)
        if sid in SIDS_UDS | SIDS_KWP:
            pend.setdefault((r.can_id, sid), []).append((r.t, sid))
    return [{"req_id": a, "resp_id": b, "n": n, "servicos": sorted(servicos[(a, b)])}
            for (a, b), n in contagem.most_common() if n >= minimo]


def indicios_tp20(regs: list[Registro]) -> list[str]:
    """Indício de VW TP 2.0: configuração de canal no ID 0x200 (opcode 0xC0 / resposta 0xD0)."""
    pedidos = [r for r in regs if r.can_id == 0x200 and len(r.data) == 7 and r.data[1] == 0xC0]
    resp = [r for r in regs if 0x200 < r.can_id <= 0x2FF and len(r.data) == 7 and r.data[1] == 0xD0]
    out = []
    if pedidos:
        out.append(f"{len(pedidos)} pedido(s) de abertura de canal no ID 0x200 (padrão do VW TP 2.0)")
    if resp:
        out.append(f"{len(resp)} resposta(s) de canal em IDs 0x2xx (padrão do VW TP 2.0)")
    return out


def relatorio(regs: list[Registro]) -> str:
    if not regs:
        return "Nenhum quadro capturado (confira conexão CAN, bitrate e se há tráfego)."
    dur = regs[-1].t - regs[0].t if len(regs) > 1 else 0.0
    L = [f"{len(regs)} quadros em {dur:.1f} s, {len({(r.can_id, r.extended) for r in regs})} IDs distintos.", "",
         "IDs observados:"]
    for d in resumo_por_id(regs):
        per = "" if d["periodo_ms"] is None else f", período ~{d['periodo_ms']:.0f} ms"
        L.append(f"  0x{d['id']:X}{' (29b)' if d['ext'] else ''}: {d['n']} quadros, DLC {d['dlc']}{per}")
    pares = detectar_pares_uds(regs)
    L += ["", "Candidatos a diagnóstico (ISO-TP + serviços UDS/KWP) — indício, confirmar:"]
    if pares:
        for p in pares:
            sv = ", ".join(f"0x{s:02X}" for s in p["servicos"])
            kwp = " [serviços típicos de KWP2000]" if set(p["servicos"]) & SIDS_KWP else ""
            L.append(f"  tester 0x{p['req_id']:X} -> ECU 0x{p['resp_id']:X}: {p['n']} trocas, serviços {sv}{kwp}")
    else:
        L.append("  nenhum par encontrado")
    tp = indicios_tp20(regs)
    if tp:
        L += ["", "Indícios de VW TP 2.0:"] + [f"  {x}" for x in tp]
    if not pares and not tp:
        L += ["", "Nenhum diagnóstico CAN identificado: o scanner pode usar a linha K, outro bitrate ou outro",
              "formato de endereçamento. Capture novamente durante uma operação do scanner."]
    return "\n".join(L)
