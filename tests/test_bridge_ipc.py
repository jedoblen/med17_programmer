import pytest

from med17.j2534.client import BridgeClient, BridgeError, BridgeTimeout, bridge_command


def _cli():
    c = BridgeClient(bridge_command(None, simulate=True), default_timeout=15)
    c.start()
    return c


def test_fluxo_completo_simulado():
    c = _cli()
    try:
        assert c.call("ping")["simulate"] is True
        assert c.call("open", dll_path="")["api"] == "04.04"
        assert c.call("vbatt")["mv"] == 12600
        c.call("connect_can", bitrate=500000)
        c.call("write", id=0x7E0, data="021003")
        fr = c.call("read", wait_ms=50)["frames"]
        assert fr[0]["id"] == 0x7E0 and fr[0]["data"] == "021003"
        c.call("disconnect")
        c.call("close")
    finally:
        c.stop()
    assert not c.running


def test_erro_j2534_chega_com_codigo():
    c = _cli()
    try:
        c.call("open", dll_path="", fail={"PassThruConnect": 8})
        with pytest.raises(BridgeError) as e:
            c.call("connect_can", bitrate=500000)
        assert e.value.info["code"] == 8
        assert c.running  # erro de comando não derruba a ponte
    finally:
        c.stop()


def test_comando_sem_abrir_e_desconhecido():
    c = _cli()
    try:
        with pytest.raises(BridgeError):
            c.call("vbatt")
        with pytest.raises(BridgeError):
            c.call("xyz")
    finally:
        c.stop()


def test_chamada_apos_parada_falha():
    c = _cli()
    c.stop()
    with pytest.raises(BridgeError):
        c.call("ping")
