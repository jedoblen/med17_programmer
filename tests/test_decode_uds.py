from med17.can.capture import Registro
from med17.can.decode_uds import decodificar_mensagem, decodificar_sessao, reassemble_isotp, relatorio_sessao

TX, RX = 0x7E0, 0x7E8


def R(t, cid, data):
    return Registro(t, int(t * 1e6), cid, False, bytes(data))


def test_reassemble_single_e_multiframe():
    sf = [R(0, TX, [2, 0x3E, 0])]
    assert reassemble_isotp(sf)[0].payload == b"\x3e\x00"
    total = 20
    payload = bytes(range(total))
    frames = [R(0, RX, [0x10 | (total >> 8), total & 0xFF] + list(payload[:6])),
             R(0.01, TX, [0x30, 0, 0]),  # FC do tester, deve ser ignorado na remontagem
             R(0.02, RX, [0x21] + list(payload[6:13])),
             R(0.03, RX, [0x22] + list(payload[13:20]))]
    msgs = reassemble_isotp(sorted(frames, key=lambda r: r.t))
    assert len(msgs) == 1 and msgs[0].payload == payload


def test_remontagem_incompleta_e_descartada():
    frames = [R(0, RX, [0x10, 15, 1, 2, 3, 4, 5, 6]),  # FF: total 15, 6 bytes aqui
             R(0.01, RX, [0x21, 7, 8, 9, 10, 11, 12, 13])]  # CF 1: +7 = 13; falta 1 CF p/ chegar a 15
    assert reassemble_isotp(frames) == []


def test_decodificar_read_memory_by_address_requisicao_e_resposta():
    req = decodificar_mensagem(bytes([0x23, 0x24, 0x00, 0x01, 0x00, 0x00, 0x02, 0x00]))
    assert req["nome"] == "ReadMemoryByAddress" and req["endereco_hex"] == "0x10000" and req["tamanho"] == 0x200
    resp = decodificar_mensagem(bytes([0x63]) + bytes(4))
    assert resp["resposta"] and resp["bytes"] == 4


def test_decodificar_request_download_e_transfer_data():
    req = decodificar_mensagem(bytes([0x34, 0x00, 0x24, 0x00, 0x02, 0x00, 0x00, 0x10, 0x00]))
    assert req["nome"] == "RequestDownload" and req["endereco_hex"] == "0x20000" and req["tamanho"] == 0x1000
    resp = decodificar_mensagem(bytes([0x74, 0x20, 0x01, 0x00]))
    assert resp["max_bloco"] == 0x100
    td = decodificar_mensagem(bytes([0x36, 0x01]) + bytes(50))
    assert td["contador_bloco"] == 1 and td["bytes_dados"] == 50


def test_resposta_negativa():
    assert decodificar_mensagem(bytes([0x7F, 0x27, 0x35])) == {"sid": 0x27, "nome": "RespostaNegativa", "nrc": 0x35}


def test_security_access_nao_decodifica_conteudo():
    info = decodificar_mensagem(bytes([0x67, 0x01, 0x12, 0x34, 0x56, 0x78]))
    assert info["nome"] == "SecurityAccess" and info["contem_seed_ou_key"] is True
    assert "semente" not in info and "chave" not in info and "0x12" not in str(info)


def test_sessao_completa_com_leitura_de_memoria():
    # alfi 0x12: size_len=1, addr_len=2 -> endereco 0x2100 (2 bytes), tamanho 10 (1 byte)
    regs = [
        R(0.00, TX, [2, 0x10, 1]), R(0.01, RX, [6, 0x50, 1, 0, 0x32, 1, 0xF4]),
        R(0.10, TX, [5, 0x23, 0x12, 0x21, 0x00, 0x0A]),
        R(0.11, RX, [0x10, 0x0B, 0x63, 0, 1, 2, 3, 4]),  # FF: total 11, carrega 0x63 + 5 bytes
        R(0.12, TX, [0x30, 0, 0]),  # Flow Control do tester: ignorado na remontagem
        R(0.13, RX, [0x21, 5, 6, 7, 8, 9]),  # CF: completa os 5 bytes finais (total 11)
    ]
    ev = decodificar_sessao(regs, TX, RX)
    nomes = [e["nome"] for e in ev]
    assert nomes == ["DiagnosticSessionControl", "DiagnosticSessionControl", "ReadMemoryByAddress", "ReadMemoryByAddress"]
    assert ev[2]["papel"] == "tester" and ev[2]["endereco_hex"] == "0x2100" and ev[2]["tamanho"] == 10
    assert ev[3]["papel"] == "ECU" and ev[3]["bytes"] == 10
    assert "ReadMemoryByAddress" in relatorio_sessao(ev)


def test_ids_trocados_nao_misturam_payloads():
    ev = decodificar_sessao([R(0, TX, [2, 0x3E, 0]), R(0.01, RX, [2, 0x7E, 0])], TX, RX)
    assert [e["papel"] for e in ev] == ["tester", "ECU"]


def test_decodificar_ecu_reset_e_communication_control():
    r = decodificar_mensagem(bytes([0x11, 0x01]))
    assert r["nome"] == "ECUReset" and r["tipo"] == "hardReset"
    cc = decodificar_mensagem(bytes([0x28, 0x03, 0x01]))
    assert cc["nome"] == "CommunicationControl" and cc["subfuncao"] == 3 and cc["tipo_comunicacao"] == 1
    resp = decodificar_mensagem(bytes([0x51, 0x01]))
    assert resp["nome"] == "ECUReset" and resp["resposta"] is True
