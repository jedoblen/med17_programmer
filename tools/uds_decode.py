"""Decodifica, OFFLINE, uma sessão UDS a partir de um CSV de captura passiva.

1) Rode antes: python tools/can_capture.py --arquivo captura.csv   (para achar os IDs candidatos)
2) Depois:     python tools/uds_decode.py captura.csv --tx 0x7E0 --rx 0x7E8 [--saida sessao.txt]

Não transmite nada; não deriva algoritmo de Security Access.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from med17.can.capture import carregar_csv  # noqa: E402
from med17.can.decode_uds import decodificar_sessao, relatorio_sessao  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--tx", required=True, type=lambda x: int(x, 0), help="ID tester -> ECU")
    ap.add_argument("--rx", required=True, type=lambda x: int(x, 0), help="ID ECU -> tester")
    ap.add_argument("--saida")
    a = ap.parse_args()
    eventos = decodificar_sessao(carregar_csv(a.csv), a.tx, a.rx)
    texto = relatorio_sessao(eventos)
    print(texto)
    if a.saida:
        Path(a.saida).write_text(texto, encoding="utf-8")
        print(f"\nSalvo em {a.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
