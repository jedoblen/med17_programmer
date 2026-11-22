from med17.can.bus import BridgeCanBus
from med17.j2534.client import BridgeClient, bridge_command


def test_bus_sobre_ponte_simulada():
    c = BridgeClient(bridge_command(None, simulate=True), default_timeout=15)
    c.start()
    try:
        c.call("open", dll_path="")
        c.call("connect_can", bitrate=500000)
        bus = BridgeCanBus(c)
        assert bus.recv(0.05) is None
        bus.send(0x123, b"\x01\x02")  # o simulador devolve em loopback
        f = bus.recv(1)
        assert f.can_id == 0x123 and f.data == b"\x01\x02"
    finally:
        c.stop()
