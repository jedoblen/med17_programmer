"""Quadro CAN (clássico, até 8 bytes) independente de hardware."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CanFrame:
    can_id: int
    data: bytes
    extended: bool = False  # True = identificador de 29 bits
    is_tx_echo: bool = False
    timestamp: int = 0

    def __post_init__(self) -> None:
        limite = 0x1FFFFFFF if self.extended else 0x7FF
        if not 0 <= self.can_id <= limite:
            raise ValueError(f"ID CAN fora do intervalo: 0x{self.can_id:X}")
        if len(self.data) > 8:
            raise ValueError("quadro CAN clássico aceita no máximo 8 bytes")
