import json

import pytest

from med17.core.config import AppConfig, load_config, save_config


def test_padrao_quando_arquivo_ausente(tmp_path):
    cfg = load_config(tmp_path / "x.json")
    assert cfg.can.bitrate == 500000 and cfg.j2534.dll_path == ""


def test_salvar_e_carregar(tmp_path):
    p = tmp_path / "c.json"
    cfg = AppConfig()
    cfg.can.bitrate = 250000
    cfg.j2534.dll_path = r"C:\x\iface.dll"
    save_config(cfg, p)
    out = load_config(p)
    assert out.can.bitrate == 250000 and out.j2534.dll_path == r"C:\x\iface.dll"


def test_json_corrompido_volta_ao_padrao(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{nao e json", encoding="utf-8")
    assert load_config(p).can.bitrate == 500000


def test_bitrate_invalido_e_rejeitado(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"can": {"bitrate": 123}}), encoding="utf-8")
    assert load_config(p).can.bitrate == 500000
    cfg = AppConfig()
    cfg.can.bitrate = 123
    with pytest.raises(ValueError):
        save_config(cfg, p)


def test_chaves_desconhecidas_sao_ignoradas(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"futuro": 1, "log_level": "DEBUG"}), encoding="utf-8")
    assert load_config(p).log_level == "DEBUG"
