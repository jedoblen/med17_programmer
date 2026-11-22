import json

import pytest

from med17.ecu.identification import EcuIdentification
from med17.profiles.manager import NOME_MODELO, ProfileManager
from med17.profiles.models import EcuProfile, ProfileError, modelo


def _completo(**extra):
    """Perfil SIMULADO totalmente preenchido (IDs/valores de teste, sem relação com ECU real)."""
    d = {
        "id": "sim-teste", "nome": "Simulado", "simulado": True, "fonte_documentacao": "teste interno",
        "validado_leitura": True, "validado_escrita": True,
        "identificacao": {"0xF191": ["HW-*"], "0xF194": ["SW-1?"]},
        "protocolo": {"bitrate": 500000, "id_29_bits": False, "tx_id": "0x100", "rx_id": "0x200",
                      "isotp": {"pad_byte": "0x00"}},
        "estrategia_leitura": "teste", "estrategia_escrita": "teste",
        "memoria": [{"nome": "FLASH", "tipo": "flash", "inicio": "0x0", "tamanho": "0x1000",
                     "endereco_len": 4, "tamanho_len": 3}],
    }
    d.update(extra)
    return d


def _ident(**dids):
    i = EcuIdentification()
    for k, v in dids.items():
        i.valores[int(k, 16)] = v.encode()
    return i


def test_modelo_em_branco_bloqueia_tudo():
    p = modelo()
    for op in ("leitura", "escrita"):
        ok, pend = p.permite(op, hardware_real=True)
        assert not ok and any("documentação" in x for x in pend) and any("protocolo incompleto" in x for x in pend)


def test_roundtrip_dict():
    p = EcuProfile.from_dict(_completo())
    assert EcuProfile.from_dict(p.to_dict()).to_dict() == p.to_dict()
    assert p.protocolo.tx_id == 0x100 and p.identificacao[0xF191] == ["HW-*"]


def test_simulado_libera_so_sem_hardware_real():
    p = EcuProfile.from_dict(_completo())
    assert p.permite("escrita", hardware_real=False) == (True, [])
    ok, pend = p.permite("escrita", hardware_real=True)
    assert not ok and any("SIMULADO" in x for x in pend)


def test_escrita_exige_regras_de_identificacao_e_estrategia():
    p = EcuProfile.from_dict(_completo(identificacao={}, estrategia_escrita=""))
    assert p.permite("leitura", False)[0]
    ok, pend = p.permite("escrita", False)
    assert not ok and len(pend) == 2


@pytest.mark.parametrize("campo,valor", [
    ("id", "ID Inválido"), ("tipo_errado", 1), ("simulado", "sim"),
    ("memoria", [{"nome": "x", "tipo": "cartao", "inicio": "0x0"}]),
    ("protocolo", {"bitrate": 123}), ("protocolo", {"tx_id": "0x800", "id_29_bits": False}),
    ("protocolo", {"tx_tid": 1}), ("identificacao", {"xyz": ["a"]}),
])
def test_validacao_rejeita(campo, valor):
    with pytest.raises(ProfileError):
        EcuProfile.from_dict(_completo(**{campo: valor}))


def test_gerenciador_carrega_ignora_invalidos_e_modelo(tmp_path):
    m = ProfileManager(tmp_path)
    m.garantir_modelo()
    (tmp_path / "ok.json").write_text(json.dumps(_completo()), encoding="utf-8")
    (tmp_path / "quebrado.json").write_text("{x", encoding="utf-8")
    (tmp_path / "typo.json").write_text(json.dumps(_completo(id="outro", protocolo={"tx_tid": 1})), encoding="utf-8")
    perfis = m.carregar()
    assert [p.id for p in perfis] == ["sim-teste"] and set(m.erros) == {"quebrado.json", "typo.json"}
    assert (tmp_path / NOME_MODELO).exists()


def test_salvar_e_recarregar(tmp_path):
    m = ProfileManager(tmp_path)
    m.salvar(EcuProfile.from_dict(_completo()))
    assert ProfileManager(tmp_path).carregar()[0].protocolo.rx_id == 0x200


def test_casamento_de_perfil(tmp_path):
    m = ProfileManager(tmp_path)
    m.salvar(EcuProfile.from_dict(_completo()))
    m.salvar(EcuProfile.from_dict(_completo(id="sem-regras", identificacao={})))
    m.carregar()
    assert [p.id for p in m.casar(_ident(F191="hw-abc", F194="SW-12"))] == ["sim-teste"]  # sem diferenciar maiúsculas
    assert m.casar(_ident(F191="hw-abc", F194="SW-123")) == []  # '?' casa um caractere
    assert m.casar(_ident(F191="hw-abc")) == []  # DID exigido ausente
    assert m.casar(_ident()) == []
