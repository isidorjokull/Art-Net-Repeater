"""Art-Net packet parsing and construction (ArtDmx only)."""
import struct

ARTNET_HEADER = b"Art-Net\x00"
ARTNET_PORT = 6454
OPCODE_DMX = 0x5000

# Sentinel written into the Physical byte of every packet we send.
# Real devices use 0–3; 0xFF marks our own loopback so we can drop it on receipt.
_SELF_PHYSICAL = 0xFF


def parse_artdmx(data: bytes) -> dict | None:
    """
    Parse a raw UDP payload into {universe, dmx} or None.
    Returns None for invalid packets and for packets we sent ourselves
    (identified by the Physical sentinel byte).
    """
    if len(data) < 18:
        return None
    if data[:8] != ARTNET_HEADER:
        return None
    opcode = struct.unpack_from("<H", data, 8)[0]
    if opcode != OPCODE_DMX:
        return None
    if data[13] == _SELF_PHYSICAL:   # our own loopback — drop it
        return None
    sub_uni = data[14]
    net = data[15]
    universe = (net << 8) | sub_uni
    length = struct.unpack_from(">H", data, 16)[0]
    if len(data) < 18 + length:
        return None
    dmx = data[18 : 18 + length]
    return {"universe": universe, "dmx": dmx}


def build_artdmx(universe: int, dmx: bytes) -> bytes:
    """Build a complete ArtDmx UDP payload stamped with the self-sent sentinel."""
    if len(dmx) % 2:
        dmx = dmx + b"\x00"
    sub_uni = universe & 0xFF
    net = (universe >> 8) & 0x7F
    pkt = ARTNET_HEADER
    pkt += struct.pack("<H", OPCODE_DMX)                 # OpCode, little-endian
    pkt += struct.pack(">H", 14)                         # ProtVer 14, big-endian
    pkt += bytes([0, _SELF_PHYSICAL, sub_uni, net])      # Sequence=0, Physical=sentinel, SubUni, Net
    pkt += struct.pack(">H", len(dmx))                   # Length, big-endian
    pkt += dmx
    return pkt
