import time

import pytest

from med17.isotp.isotp import IsoTpLink
from med17.simulator.virtual_ecu import VirtualBus, VirtualEcu
from med17.uds.uds import TesterPresentKeeper, UdsClient, UdsNegativeResponse, UdsTimeout

REQ, RESP = 0x100, 0x200  # IDs arbitrários de teste


class _Cenario:
    def __init__(self, p2=0.5, **kw):
        a, b = VirtualBus.pair()
        self.ecu = VirtualEcu(b, REQ, RESP, dids={0xF190: b"TESTE123"}, **kw)
        self.ecu.start()
        self.uds = UdsClient(IsoTpLink(a, REQ, RESP), p2=p2, p2_star=1.0)

    def fim(self):
        self.ecu.stop()


def test_sessao_atualiza_temporizacao():
    c = _Cenario()
    try:
        r = c.uds.diagnostic_session_control(0x03)
        assert r["session"] == 3 and r["p2"] == 0.05 and r["p2_star"] == 5.0
        assert c.ecu.session == 3
    finally:
        c.fim()


def test_leitura_por_did_e_endereco():
    c = _Cenario()
    try:
        assert c.uds.read_data_by_identifier(0xF190) == b"TESTE123"
        d = c.uds.read_memory_by_address(0x10, 300, addr_len=2, size_len=2)  # multiframe
        assert d == bytes(c.ecu.memory[0x10:0x10 + 300])
    finally:
        c.fim()


def test_resposta_negativa_tem_nome():
    c = _Cenario()
    try:
        with pytest.raises(UdsNegativeResponse) as e:
            c.uds.read_data_by_identifier(0x0001)
        assert e.value.nrc == 0x31 and e.value.nome == "requestOutOfRange"
        with pytest.raises(UdsNegativeResponse) as e:
            c.uds.request(bytes([0x85, 0x01]))
        assert e.value.nrc == 0x11
    finally:
        c.fim()


def test_response_pending_e_tratado():
    c = _Cenario(p2=0.2)
    c.ecu.pending_for[0x22] = 3  # 3 x 0x78 (150 ms) > p2: só funciona se estender para p2*
    try:
        assert c.uds.read_data_by_identifier(0xF190) == b"TESTE123"
    finally:
        c.fim()


def test_timeout_sem_resposta():
    c = _Cenario(p2=0.2)
    c.ecu.silent = True
    try:
        with pytest.raises(UdsTimeout):
            c.uds.tester_present()
    finally:
        c.fim()


def test_seguranca_e_download_simulados():
    c = _Cenario()
    try:
        with pytest.raises(UdsNegativeResponse):
            c.uds.request_download(0x100, 4, addr_len=2, size_len=1)  # bloqueado: sem unlock
        seed = c.uds.security_access_request_seed(1)
        with pytest.raises(UdsNegativeResponse) as e:
            c.uds.security_access_send_key(1, b"\x00\x00\x00\x00")
        assert e.value.nrc == 0x35
        c.uds.security_access_send_key(1, bytes(b ^ 0xFF for b in seed))
        maxlen = c.uds.request_download(0x100, 4, addr_len=2, size_len=1)
        assert maxlen == 0x80
        c.uds.transfer_data(1, b"\xde\xad\xbe\xef")
        c.uds.request_transfer_exit()
        assert bytes(c.ecu.memory[0x100:0x104]) == b"\xde\xad\xbe\xef"
        with pytest.raises(UdsNegativeResponse) as e:
            c.uds.request_download(0x100, 4, addr_len=2, size_len=1)
            c.uds.transfer_data(2, b"\x00")  # sequência errada (esperado 1)
        assert e.value.nrc == 0x73
    finally:
        c.fim()


def test_rotina_e_nivel_seguranca_invalido():
    c = _Cenario()
    try:
        assert c.uds.routine_control(1, 0xFF00) == b"\x00"
        with pytest.raises(ValueError):
            c.uds.security_access_request_seed(2)
        with pytest.raises(ValueError):
            c.uds.read_memory_by_address(0x100000, 1, addr_len=2, size_len=1)
    finally:
        c.fim()


def test_tester_present_periodico_nao_colide_com_requisicoes():
    c = _Cenario()
    k = TesterPresentKeeper(c.uds, interval=0.05)
    try:
        k.start()
        fim = time.monotonic() + 0.5
        while time.monotonic() < fim:
            assert c.uds.read_data_by_identifier(0xF190) == b"TESTE123"
            time.sleep(0.02)  # intervalos ociosos: o keeper só envia quando não há requisição em curso
        k.stop()
        assert k.enviados >= 3 and c.ecu.tp_count >= 3
    finally:
        k.stop()
        c.fim()
