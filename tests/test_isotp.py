import threading

import pytest

from med17.can.frame import CanFrame
from med17.isotp.isotp import IsoTpConfig, IsoTpError, IsoTpLink, IsoTpTimeout, decode_stmin
from med17.simulator.virtual_ecu import VirtualBus

A_ID, B_ID = 0x100, 0x200  # IDs arbitrários de teste


def _links(cfg_a=None, cfg_b=None):
    a, b = VirtualBus.pair()
    return a, b, IsoTpLink(a, A_ID, B_ID, config=cfg_a), IsoTpLink(b, B_ID, A_ID, config=cfg_b)


def _enviar_em_thread(link, payload):
    erro = []

    def alvo():
        try:
            link.send(payload)
        except Exception as e:  # noqa: BLE001
            erro.append(e)

    t = threading.Thread(target=alvo)
    t.start()
    return t, erro


def test_single_frame():
    a, b, la, lb = _links()
    la.send(b"\x22\xf1\x90")
    assert lb.recv(1) == b"\x22\xf1\x90"


def test_single_frame_limite_7_bytes_e_8_vira_multiframe():
    a, b, la, lb = _links()
    la.send(bytes(range(7)))
    assert lb.recv(1) == bytes(range(7))
    t, erro = _enviar_em_thread(la, bytes(range(8)))
    assert lb.recv(2) == bytes(range(8))
    t.join()
    assert not erro


def _multi(n, cfg_b=None):
    a, b, la, lb = _links(cfg_b=cfg_b)
    dados = bytes(i % 256 for i in range(n))
    t, erro = _enviar_em_thread(la, dados)
    assert lb.recv(5) == dados
    t.join()
    assert not erro
    return a, b


def test_multiframe_100_e_4095_bytes():
    _multi(100)
    _multi(4095)


def test_block_size_gera_flow_control_intermediarios():
    a, b = _multi(100, cfg_b=IsoTpConfig(block_size=4))
    fcs = [d for _, d in b.sent if d[0] >> 4 == 3]
    assert len(fcs) == 4  # inicial + após blocos 1, 2 e 3


def test_stmin_do_receptor_e_respeitado():
    import time
    a, b, la, lb = _links(cfg_b=IsoTpConfig(stmin_ms=10))
    t, erro = _enviar_em_thread(la, bytes(40))  # 6 no FF + 5 CFs
    ini = time.monotonic()
    assert lb.recv(5) == bytes(40)
    t.join()
    assert time.monotonic() - ini >= 0.035 and not erro


def test_decode_stmin():
    assert decode_stmin(5) == 0.005 and abs(decode_stmin(0xF3) - 0.0003) < 1e-9
    assert decode_stmin(0xAA) == 0.127


def test_padding():
    a, b, la, lb = _links(cfg_a=IsoTpConfig(pad_byte=0xAA))
    la.send(b"\x3e\x00")
    f = b.recv(1)
    assert f.data == bytes([2, 0x3E, 0, 0xAA, 0xAA, 0xAA, 0xAA, 0xAA])


def test_timeout_sem_flow_control():
    a, b, la, lb = _links(cfg_a=IsoTpConfig(n_bs=0.2))
    with pytest.raises(IsoTpTimeout):
        la.send(bytes(20))


def test_overflow_do_receptor_aborta_envio():
    a, b, la, lb = _links()
    t, erro = _enviar_em_thread(la, bytes(20))
    assert b.recv(1) is not None  # First Frame
    b.send(B_ID, bytes([0x32, 0, 0]))  # FC overflow
    t.join()
    assert erro and isinstance(erro[0], IsoTpError)


def test_sequencia_errada_na_recepcao():
    a, b, la, lb = _links()
    a.send(A_ID, bytes([0x10, 20]) + bytes(6))
    a.send(A_ID, bytes([0x23]) + bytes(7))  # SN 3, esperado 1
    with pytest.raises(IsoTpError):
        lb.recv(1)


def test_ids_diferentes_sao_ignorados():
    a, b, la, lb = _links()
    a.send(0x555, b"\x01\x99")
    a.send(A_ID, b"\x01\x42")
    assert lb.recv(1) == b"\x42"


def test_recv_timeout():
    a, b, la, lb = _links()
    with pytest.raises(IsoTpTimeout):
        lb.recv(0.1)


def test_quadro_can_invalido():
    with pytest.raises(ValueError):
        CanFrame(0x800, b"")
    with pytest.raises(ValueError):
        CanFrame(0x1, bytes(9))
