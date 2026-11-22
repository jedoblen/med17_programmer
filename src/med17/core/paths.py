"""Caminhos do aplicativo (pasta de dados do usuário no Windows)."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "MED17Programmer"


def app_data_dir() -> Path:
    """Pasta de dados: %APPDATA%\\MED17Programmer (ou ~/.med17programmer fora do Windows)."""
    override = os.environ.get("MED17_HOME")
    if override:
        base = Path(override)
    elif os.name == "nt" and os.environ.get("APPDATA"):
        base = Path(os.environ["APPDATA"]) / APP_NAME
    else:
        base = Path.home() / ".med17programmer"
    base.mkdir(parents=True, exist_ok=True)
    return base


def logs_dir() -> Path:
    p = app_data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def backups_dir() -> Path:
    p = app_data_dir() / "backups"
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_file() -> Path:
    return app_data_dir() / "config.json"
