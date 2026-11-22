"""Detecção das interfaces J2534 instaladas (registro do Windows) e bitness das DLLs."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

CHAVE = r"SOFTWARE\PassThruSupport.04.04"


@dataclass
class DllInfo:
    name: str
    path: str
    bits: int | None  # 32, 64 ou None (arquivo ausente/ilegível)

    @property
    def exists(self) -> bool:
        return self.bits is not None


def pe_bitness(path: str | Path) -> int | None:
    """Lê o cabeçalho PE e devolve 32 ou 64; None se não for um PE válido."""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
            if head[:2] != b"MZ":
                return None
            f.seek(int.from_bytes(head[0x3C:0x40], "little"))
            pe = f.read(6)
        if pe[:4] != b"PE\0\0":
            return None
        return {0x14C: 32, 0x8664: 64}.get(int.from_bytes(pe[4:6], "little"))
    except OSError:
        return None


def discover_dlls() -> list[DllInfo]:
    """Lista DLLs J2534 registradas (visões de 64 e 32 bits). Vazio fora do Windows."""
    if os.name != "nt":
        return []
    import winreg

    achados: dict[str, DllInfo] = {}
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        try:
            raiz = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CHAVE, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with raiz:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(raiz, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(raiz, sub) as k:
                        nome = winreg.QueryValueEx(k, "Name")[0]
                        dll = winreg.QueryValueEx(k, "FunctionLibrary")[0]
                except OSError:
                    continue
                chave = os.path.normcase(dll)
                if chave not in achados:
                    achados[chave] = DllInfo(str(nome), str(dll), pe_bitness(dll))
    return sorted(achados.values(), key=lambda d: d.name.lower())
