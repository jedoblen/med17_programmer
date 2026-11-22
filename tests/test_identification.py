import pytest

from med17.ecu.identification import IdentificationError, decodificar, identify
from med17.isotp.isotp import IsoTpLink
from med17.simulator.virtual_ecu import VirtualBus, VirtualEcu
from med17.uds.uds import UdsClient

REQ, RESP = 0x100, 0x200


def _cenario(dids, p2=0.2):
    a, b = VirtualBus.pair()
    ecu = VirtualEcu(b, REQ, RESP, dids=dids)
    ecu.start()
    return ecu, UdsClient(IsoTpLink(a, REQ, RESP), p2=p2)


def test_decodificar():
    assert decodificar(b"ABC123\x00\x00") == "ABC123"
    assert decodificar(b"\x01\x02\xff") == "0x0102FF"
    assert decodificar(b"\xff\xff") == "0xFFFF"


def test_identifica_e_registra_nao_suportados():
    ecu, uds = _cenario({0xF191: b"HW-ABC", 0xF194: b"\x01\x02\x03", 0xF190: b"A" * 17})
    try:
        i = identify(uds)
        assert i.texto(0xF191) == "HW-ABC" and i.texto(0xF194) == "0x010203" and len(i.texto(0xF190)) == 17
        assert i.nao_suportados[0xF187] == 0x31 and not i.sem_resposta
        assert i.texto(0xF187) is None
    finally:
        ecu.stop()


def test_ecu_muda_nao_trava_e_levanta_erro():
    ecu, uds = _cenario({0xF191: b"X"}, p2=0.05)
    ecu.silent = True
    try:
        with pytest.raises(IdentificationError):
            identify(uds)
    finally:
        ecu.stop()


def test_dids_customizados_e_sessao():
    ecu, uds = _cenario({0x1234: b"custom"})
    try:
        i = identify(uds, [0x1234], session=3)
        assert i.texto(0x1234) == "custom" and ecu.session == 3
    finally:
        ecu.stop()
