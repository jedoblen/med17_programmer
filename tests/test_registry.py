import struct

from med17.j2534.registry import pe_bitness


def _pe(machine: int) -> bytes:
    dos = bytearray(64)
    dos[:2] = b"MZ"
    dos[0x3C:0x40] = struct.pack("<I", 64)
    return bytes(dos) + b"PE\0\0" + struct.pack("<H", machine)


def test_pe_32_e_64(tmp_path):
    a, b = tmp_path / "a.dll", tmp_path / "b.dll"
    a.write_bytes(_pe(0x14C))
    b.write_bytes(_pe(0x8664))
    assert pe_bitness(a) == 32 and pe_bitness(b) == 64


def test_pe_invalido_ou_ausente(tmp_path):
    x = tmp_path / "x.dll"
    x.write_bytes(b"naoepe")
    assert pe_bitness(x) is None and pe_bitness(tmp_path / "nao.dll") is None
