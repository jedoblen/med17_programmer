"""Carga, gravação e casamento de perfis (arquivos JSON em uma pasta)."""
from __future__ import annotations

import json
import logging
from fnmatch import fnmatchcase
from pathlib import Path

from .models import EcuProfile, ProfileError, modelo

log = logging.getLogger("med17.profiles")
NOME_MODELO = "_modelo_med17.json"  # arquivos iniciados por "_" não são carregados


class ProfileManager:
    def __init__(self, pasta: Path) -> None:
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.perfis: list[EcuProfile] = []
        self.erros: dict[str, str] = {}

    def garantir_modelo(self) -> Path:
        alvo = self.pasta / NOME_MODELO
        if not alvo.exists():
            self._gravar(alvo, modelo())
        return alvo

    def carregar(self) -> list[EcuProfile]:
        self.perfis, self.erros = [], {}
        for arq in sorted(self.pasta.glob("*.json")):
            if arq.name.startswith("_"):
                continue
            try:
                p = EcuProfile.from_dict(json.loads(arq.read_text(encoding="utf-8")))
            except (OSError, ValueError, ProfileError) as exc:
                self.erros[arq.name] = str(exc)
                log.error("Perfil %s ignorado: %s", arq.name, exc)
                continue
            if any(x.id == p.id for x in self.perfis):
                self.erros[arq.name] = f"id duplicado: {p.id}"
                log.error("Perfil %s ignorado: id duplicado %s", arq.name, p.id)
                continue
            self.perfis.append(p)
        log.info("%d perfil(is) carregado(s), %d com erro.", len(self.perfis), len(self.erros))
        return self.perfis

    def obter(self, pid: str) -> EcuProfile | None:
        return next((p for p in self.perfis if p.id == pid), None)

    def salvar(self, perfil: EcuProfile) -> Path:
        alvo = self.pasta / f"{perfil.id}.json"
        self._gravar(alvo, perfil)
        return alvo

    @staticmethod
    def _gravar(alvo: Path, perfil: EcuProfile) -> None:
        tmp = alvo.with_suffix(".tmp")
        tmp.write_text(json.dumps(perfil.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(alvo)

    def casar(self, ident) -> list[EcuProfile]:
        """Perfis cujas regras de identificação casam com a identificação lida.
        Todas as regras (DIDs) devem casar; dentro de um DID, basta um padrão. Sem regras = nunca casa."""
        achados = []
        for p in self.perfis:
            if not p.identificacao:
                continue
            ok = True
            for did, padroes in p.identificacao.items():
                txt = ident.texto(did)
                if txt is None or not any(fnmatchcase(txt.lower(), pad.lower()) for pad in padroes):
                    ok = False
                    break
            if ok:
                achados.append(p)
        return achados
