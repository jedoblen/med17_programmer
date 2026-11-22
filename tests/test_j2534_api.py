import pytest

from med17.j2534 import constants as C
from med17.j2534.api import J2534, J2534Error
from med17.simulator.fake_j2534 import FakeJ2534Lib


def _conectado(**kw):
    lib = FakeJ2534Lib(**kw)
    api = J2534(lib)
    api.open()
    return lib, api


def test_open_versao_e_bateria():
    lib, api = _conectado()
    assert api.read_version()["api"] == "04.04"
    assert api.read_vbatt_mv() == 12600


def test_loopback_can_11_bits():
    lib, api = _conectado()
    api.connect_can(500000)
    api.pass_all()
    api.write(0x7E0, bytes([2, 0x10, 3]))
    fr = api.read(50)
    assert len(fr) == 1 and fr[0].can_id == 0x7E0 and fr[0].data == bytes([2, 0x10, 3])


def test_recepcao_injetada_e_vazia():
    lib, api = _conectado()
    api.connect_can(500000)
    assert api.read(10) == []
    lib.inject(0x7E8, b"\x03\x7f\x10\x11")
    assert api.read(10)[0].can_id == 0x7E8


def test_erro_mapeado_com_nome():
    lib, api = _conectado(fail={"PassThruConnect": 0x08})
    with pytest.raises(J2534Error) as e:
        api.connect_can(500000)
    assert e.value.code == 8 and e.value.name == "ERR_DEVICE_NOT_CONNECTED"


def test_open_falha_propaga():
    api = J2534(FakeJ2534Lib(fail={"PassThruOpen": 0x08}))
    with pytest.raises(J2534Error):
        api.open()
    assert api.device_id is None


def test_close_seguro_desconecta_e_fecha():
    lib, api = _conectado()
    api.connect_can(500000)
    api.close()
    assert lib.disconnected and lib.closed and api.device_id is None and api.channel_id is None


def test_quadro_maior_que_8_bytes_rejeitado():
    lib, api = _conectado()
    api.connect_can(500000)
    with pytest.raises(ValueError):
        api.write(0x7E0, bytes(9))
