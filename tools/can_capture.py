"""Captura PASSIVA de tráfego CAN (não transmite nada) e análise de diagnóstico.

Captura:  python tools/can_capture.py --segundos 90 [--bitrate 500000] [--ext] [--saida captura.csv]
Analisar: python tools/can_capture.py --arquivo captura.csv

Atenção: a interface entra no barramento como um nó. Um bitrate errado gera quadros de erro e pode
atrapalhar a comunicação. Nunca capture durante gravação/programação de ECU.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from med17.can.bus import BridgeCanBus  # noqa: E402
from med17.can.capture import capturar, carregar_csv, relatorio, salvar_csv  # noqa: E402
from med17.core.config import load_config  # noqa: E402
from med17.j2534.client import BridgeClient, bridge_command  # noqa: E402
from med17.j2534.registry import pe_bitness  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segundos", type=float, default=60)
    ap.add_argument("--bitrate", type=int)
    ap.add_argument("--ext", action="store_true", help="IDs de 29 bits")
    ap.add_argument("--saida", default="captura.csv")
    ap.add_argument("--arquivo", help="apenas analisar um CSV existente")
    ap.add_argument("--sim-confirmacao", action="store_true", help="não pedir confirmação")
    a = ap.parse_args()

    if a.arquivo:
        print(relatorio(carregar_csv(a.arquivo)))
        return 0

    cfg = load_config()
    dll = cfg.j2534.dll_path
    bits = pe_bitness(dll) if dll else None
    if bits is None:
        print("Configure a DLL J2534 na aba Conexão do programa primeiro.")
        return 2
    bitrate = a.bitrate or cfg.can.bitrate
    print(f"Captura passiva por {a.segundos:.0f} s a {bitrate} bit/s ({'29' if a.ext else '11'} bits).")
    print("Confirme: bitrate correto, ECU alimentada, NENHUMA gravação em andamento.")
    if not a.sim_confirmacao and input("Continuar? [s/N] ").strip().lower() != "s":
        return 1
    client = BridgeClient(bridge_command(bits), default_timeout=15)
    client.start()
    try:
        client.call("open", dll_path=dll)
        client.call("connect_can", bitrate=bitrate, extended=a.ext)
        print("Capturando... faça agora as operações de diagnóstico no scanner (identificação, falhas, dados).")
        regs = capturar(BridgeCanBus(client, a.ext, batch=128), a.segundos)
    finally:
        client.stop()
    salvar_csv(regs, a.saida)
    print(f"\nSalvo em {a.saida}\n")
    print(relatorio(regs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
