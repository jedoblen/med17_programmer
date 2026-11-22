import threading
import time

from med17.can.capture import (Registro, capturar, carregar_csv, detectar_pares_uds, indicios_tp20,
                               relatorio, resumo_por_id, salvar_csv)
from med17.simulator.virtual_ecu import VirtualBus


def R(t, cid, data, ext=False):
    return Registro(t, int(t * 1e6), cid, ext, bytes(data))


def _trafego_uds():
    regs = []
    for i in range(4):  # 4 trocas: 10 01 -> 50 01 ; 22 F1 90 -> 7F 22 31
        t = i * 0.5
        regs += [R(t, 0x100, [2, 0x10, 1]), R(t + .01, 0x200, [6, 0x50, 1, 0, 0x32, 1, 0xF4]),
                 R(t + .1, 0x100, [3, 0x22, 0xF1, 0x90]), R(t + .11, 0x200, [3, 0x7F, 0x22, 0x31])]
    for i in range(30):  # ruído periódico
        regs.append(R(i * 0.1, 0x3C0, [1, 2, 3, 4, 5, 6, 7, 8]))
    return regs


def test_detecta_par_uds():
    pares = detectar_pares_uds(_trafego_uds())
    assert pares[0]["req_id"] == 0x100 and pares[0]["resp_id"] == 0x200
    assert pares[0]["n"] == 8 and pares[0]["servicos"] == [0x10, 0x22]
    assert all(p["req_id"] != 0x3C0 for p in pares)


def test_sem_pares_com_apenas_ruido():
    regs = [R(i * 0.1, 0x3C0, [1, 2, 3, 4, 5, 6, 7, 8]) for i in range(30)]
    assert detectar_pares_uds(regs) == []
    assert "Nenhum diagnóstico CAN identificado" in relatorio(regs)


def test_kwp_e_marcado_no_relatorio():
    regs = []
    for i in range(3):
        regs += [R(i, 0x100, [2, 0x1A, 0x9B]), R(i + .01, 0x200, [4, 0x5A, 0x9B, 1, 2])]
    assert "KWP2000" in relatorio(regs)


def test_indicio_tp20():
    regs = [R(0, 0x200, [1, 0xC0, 0, 0x10, 0, 3, 1]), R(0.01, 0x201, [0, 0xD0, 0, 0x03, 0x8, 0x40, 0x07])]
    assert len(indicios_tp20(regs)) == 2


def test_resumo_periodo():
    d = resumo_por_id([R(i * 0.1, 0x3C0, [0] * 8) for i in range(11)])[0]
    assert d["n"] == 11 and abs(d["periodo_ms"] - 100) < 1 and d["dlc"] == [8]


def test_csv_roundtrip(tmp_path):
    regs = _trafego_uds()
    salvar_csv(regs, tmp_path / "c.csv")
    volta = carregar_csv(tmp_path / "c.csv")
    assert [(r.can_id, r.data) for r in volta] == [(r.can_id, r.data) for r in regs]


def test_capturar_de_barramento_virtual():
    a, b = VirtualBus.pair()

    def emissor():
        for i in range(5):
            time.sleep(0.02)
            b.send(0x123, bytes([i]))

    threading.Thread(target=emissor).start()
    regs = capturar(a, 0.4)
    assert [r.data[0] for r in regs] == [0, 1, 2, 3, 4]
    assert not b.sent == [] and a.sent == []  # captura não transmite nada


def test_relatorio_vazio():
    assert "Nenhum quadro" in relatorio([])
