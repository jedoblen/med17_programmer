"""Configuração persistente em JSON, com validação e valores padrão."""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .paths import config_file

log = logging.getLogger(__name__)

BITRATES_VALIDOS = (125000, 250000, 500000, 1000000)
NIVEIS_LOG = ("DEBUG", "INFO", "WARNING", "ERROR")


@dataclass
class CanConfig:
    bitrate: int = 500000
    id_29_bits: bool = False


@dataclass
class J2534Config:
    dll_path: str = ""  # selecionada pelo usuário; nunca presumida


@dataclass
class AppConfig:
    log_level: str = "INFO"
    can: CanConfig = field(default_factory=CanConfig)
    j2534: J2534Config = field(default_factory=J2534Config)
    pasta_backups: str = ""  # vazio = pasta padrão do aplicativo

    def validate(self) -> None:
        if self.log_level not in NIVEIS_LOG:
            raise ValueError(f"log_level inválido: {self.log_level!r}")
        if self.can.bitrate not in BITRATES_VALIDOS:
            raise ValueError(f"bitrate CAN inválido: {self.can.bitrate!r}")


def _merge(dc, data: dict):
    """Aplica `data` sobre o dataclass `dc`, ignorando chaves desconhecidas."""
    for f in fields(dc):
        if f.name not in data:
            continue
        atual = getattr(dc, f.name)
        if hasattr(atual, "__dataclass_fields__") and isinstance(data[f.name], dict):
            _merge(atual, data[f.name])
        else:
            setattr(dc, f.name, data[f.name])
    return dc


def load_config(path: Path | None = None) -> AppConfig:
    """Carrega a configuração; se ausente ou inválida, devolve o padrão."""
    path = path or config_file()
    if not path.exists():
        return AppConfig()
    try:
        cfg = _merge(AppConfig(), json.loads(path.read_text(encoding="utf-8")))
        cfg.validate()
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        log.warning("Configuração inválida em %s (%s); usando padrão.", path, exc)
        return AppConfig()
    return cfg


def save_config(cfg: AppConfig, path: Path | None = None) -> Path:
    cfg.validate()
    path = path or config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path
