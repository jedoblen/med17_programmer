"""Sonda UDS somente-leitura (sessão padrão + Tester Present) com hardware J2534.

Uso (na pasta do projeto, com o venv ativo):
    python tools/uds_probe.py --tx 0x... --rx 0x... [--ext] [--bitrate 500000] [--pad 0x00]
    python tools/uds_probe.py --virtual          # demonstração com ECU virtual (SIMULADA)

Os IDs vêm da documentação da sua ECU; este script não os adivinha.
Envia apenas 0x10 0x01 e 0x3E 0x00. Não lê nem grava memórias.
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from med17.can.bus import BridgeCanBus  # noqa: E402
from med17.core.config import load_config  # noqa: E402
from med17.isotp.isotp import IsoTpConfig, IsoTpLink  # noqa: E402
from med17.j2534.client import BridgeClient, bridge_command  # noqa: E402
from med17.j2534.registry import pe_bitness  # noqa: E402
from med17.uds.uds import UdsClient, UdsError  # noqa: E402


def sondar(uds: UdsClient) -> None:
    print("Sessão padrão:", uds.diagnostic_session_control(0x01))
    uds.tester_present()
    print("Tester Present: OK")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tx", type=lambda x: int(x, 0))
    ap.add_argument("--rx", type=lambda x: int(x, 0))
    ap.add_argument("--ext", action="store_true")
    ap.add_argument("--bitrate", type=int)
    ap.add_argument("--pad", type=lambda x: int(x, 0), default=None)
    ap.add_argument("--virtual", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

    if a.virtual:
        from med17.simulator.virtual_ecu import VirtualBus, VirtualEcu
        x, y = VirtualBus.pair()
        ecu = VirtualEcu(y, 0x100, 0x200)
        ecu.start()
        try:
            print("[SIMULADO] ECU virtual, IDs de teste 0x100/0x200")
            sondar(UdsClient(IsoTpLink(x, 0x100, 0x200), p2=0.5))
        finally:
            ecu.stop()
        return 0

    if a.tx is None or a.rx is None:
        ap.error("informe --tx e --rx (IDs da documentação da ECU)")
    cfg = load_config()
    dll = cfg.j2534.dll_path
    bits = pe_bitness(dll)
    if not dll or bits is None:
        print("Configure a DLL J2534 na aba Conexão do programa primeiro.")
        return 2
    client = BridgeClient(bridge_command(bits), default_timeout=15)
    client.start()
    try:
        print("Interface:", client.call("open", dll_path=dll))
        print("Tensão (mV):", client.call("vbatt")["mv"])
        client.call("connect_can", bitrate=a.bitrate or cfg.can.bitrate, extended=a.ext)
        link = IsoTpLink(BridgeCanBus(client, a.ext), a.tx, a.rx, extended=a.ext,
                         config=IsoTpConfig(pad_byte=a.pad))
        sondar(UdsClient(link, p2=1.0))
    except UdsError as exc:
        print("UDS:", exc)
        return 1
    finally:
        client.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
