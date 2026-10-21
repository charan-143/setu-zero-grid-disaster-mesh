"""
Zero-Grid Disaster Mesh - 120-Byte Binary Packet Specification

Byte Offset | Field Name       | Size     | Encoding / Purpose
0-5         | Device_Hash      | 6 Bytes  | Truncated SHA-256 of MAC/UUID for packet deduplication
6-9         | Timestamp_Delta  | 4 Bytes  | Uint32 UNIX epoch seconds
10-17       | Lat_Lon_Fixed    | 8 Bytes  | Int32 Latitude + Int32 Longitude (1e7 fixed point, 1.1cm precision)
18-19       | Altitude_Baro    | 2 Bytes  | Int16 relative elevation in decimeters (-3276.8m to +3276.7m)
20          | Triage_Bitmask   | 1 Byte   | [2b: Severity (0-3)][3b: Disaster Type][1b: Trapped][2b: Mobility]
21-22       | Demographics     | 2 Bytes  | [4b: Adults][4b: Children][4b: Elderly][4b: Critical Medical Flags]
23          | Mesh_Telemetry   | 1 Byte   | [4b: Hop Count (TTL)][4b: Phone Battery % in 10% steps]
24-25       | Medical_Codes    | 2 Bytes  | Bitflags for Dialysis, Insulin, Pregnancy, Crush, Snakebite, O2
26-117      | Compressed_Note  | 92 Bytes | Smaz/Huffman-compressed UTF-8 or ASCII summary
118-119     | CRC16_Checksum   | 2 Bytes  | CRC-16-CCITT error detection
Total = 120 Bytes
"""

import struct
import hashlib
import time
from typing import Dict, Any, Tuple

PACKET_SIZE = 120
COMPRESSED_NOTE_SIZE = 92

# Triage Severities
SEVERITY_GREEN = 0     # Minor
SEVERITY_YELLOW = 1    # Delayed
SEVERITY_RED = 2       # Immediate / Critical
SEVERITY_BLACK = 3     # Expectant / Deceased

# Disaster Types
DISASTER_FLOOD = 0
DISASTER_EARTHQUAKE = 1
DISASTER_CYCLONE = 2
DISASTER_LANDSLIDE = 3
DISASTER_FIRE = 4
DISASTER_BUILDING_COLLAPSE = 5
DISASTER_OTHER = 6

# Medical Code Bitflags (16-bit)
MED_FLAG_INSULIN    = 1 << 0
MED_FLAG_DIALYSIS   = 1 << 1
MED_FLAG_PREGNANCY  = 1 << 2
MED_FLAG_CRUSH      = 1 << 3
MED_FLAG_SNAKEBITE  = 1 << 4
MED_FLAG_O2_NEEDED  = 1 << 5
MED_FLAG_BLEEDING   = 1 << 6
MED_FLAG_FRACTURE   = 1 << 7


def calculate_crc16_ccitt(data: bytes) -> int:
    """Calculates CRC-16-CCITT (poly 0x1021, init 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def compress_note(note: str) -> bytes:
    """
    Compresses text note into 92 bytes max.
    Pads with null bytes if shorter; truncates if longer.
    """
    encoded = note.encode('utf-8')
    if len(encoded) > COMPRESSED_NOTE_SIZE:
        encoded = encoded[:COMPRESSED_NOTE_SIZE]
    return encoded.ljust(COMPRESSED_NOTE_SIZE, b'\x00')


def decompress_note(raw: bytes) -> str:
    """Extracts note string from 92-byte block, stripping padding."""
    return raw.split(b'\x00')[0].decode('utf-8', errors='replace')


def generate_device_hash(device_id: str) -> bytes:
    """Generates 6-byte truncated SHA-256 hash from device UUID/MAC."""
    return hashlib.sha256(device_id.encode('utf-8')).digest()[:6]


def pack_sos_packet(
    device_id: str,
    timestamp: int,
    latitude: float,
    longitude: float,
    altitude_decimeters: int,
    severity: int,
    disaster_type: int,
    is_trapped: bool,
    mobility: int,
    adults: int,
    children: int,
    elderly: int,
    critical_cases: int,
    hop_count: int,
    battery_pct: int,
    medical_flags: int,
    note: str
) -> bytes:
    """
    Packs triage telemetry into a strict 120-byte binary payload.
    """
    # 1. Device Hash (6B)
    dev_hash = generate_device_hash(device_id)

    # 2. Timestamp (4B, uint32)
    ts = int(timestamp) & 0xFFFFFFFF

    # 3. Lat / Lon fixed point (8B, int32 each, scaled by 1e7)
    lat_fixed = int(round(latitude * 1e7))
    lon_fixed = int(round(longitude * 1e7))

    # 4. Altitude Baro in decimeters (2B, int16)
    alt_clamped = max(-32768, min(32767, int(altitude_decimeters)))

    # 5. Triage Bitmask (1B): [2b: Severity][3b: Disaster Type][1b: Trapped][2b: Mobility]
    severity_bits = (severity & 0x03) << 6
    disaster_bits = (disaster_type & 0x07) << 3
    trapped_bits = (1 if is_trapped else 0) << 2
    mobility_bits = (mobility & 0x03)
    triage_bitmask = severity_bits | disaster_bits | trapped_bits | mobility_bits

    # 6. Demographics (2B): [4b Adults][4b Children][4b Elderly][4b Critical]
    demo_b1 = ((min(15, adults) & 0x0F) << 4) | (min(15, children) & 0x0F)
    demo_b2 = ((min(15, elderly) & 0x0F) << 4) | (min(15, critical_cases) & 0x0F)

    # 7. Mesh Telemetry (1B): [4b Hop Count][4b Battery / 10]
    batt_step = max(0, min(10, battery_pct // 10))
    mesh_telemetry = ((min(15, hop_count) & 0x0F) << 4) | (batt_step & 0x0F)

    # 8. Medical Codes (2B, uint16)
    med_codes = medical_flags & 0xFFFF

    # 9. Compressed Note (92B)
    comp_note = compress_note(note)

    # Assemble 118 bytes for CRC calculation
    header = dev_hash + struct.pack(
        ">IIiihBBBH",
        ts,
        lat_fixed & 0xFFFFFFFF,
        lon_fixed,
        alt_clamped,
        triage_bitmask,
        demo_b1,
        demo_b2,
        mesh_telemetry,
        med_codes
    )
    # Correct header packing:
    # ts: uint32 (4)
    # lat_fixed: int32 (4)
    # lon_fixed: int32 (4)
    # alt_clamped: int16 (2)
    # triage_bitmask: uint8 (1)
    # demo_b1: uint8 (1)
    # demo_b2: uint8 (1)
    # mesh_telemetry: uint8 (1)
    # med_codes: uint16 (2)
    # Total header = 6 (dev_hash) + 4 + 4 + 4 + 2 + 1 + 1 + 1 + 1 + 2 = 26 bytes.
    # Correct struct format:
    body_fields = struct.pack(
        ">Iii h B B B B H",
        ts,
        lat_fixed,
        lon_fixed,
        alt_clamped,
        triage_bitmask,
        demo_b1,
        demo_b2,
        mesh_telemetry,
        med_codes
    )
    assert len(dev_hash) + len(body_fields) == 26, f"Expected 26B header, got {len(dev_hash) + len(body_fields)}"

    raw_payload_118 = dev_hash + body_fields + comp_note
    assert len(raw_payload_118) == 118, f"Expected 118B before CRC, got {len(raw_payload_118)}"

    # 10. CRC16 Checksum (2B)
    crc = calculate_crc16_ccitt(raw_payload_118)
    crc_bytes = struct.pack(">H", crc)

    packet = raw_payload_118 + crc_bytes
    assert len(packet) == PACKET_SIZE, f"Packet must be exactly {PACKET_SIZE} bytes"
    return packet


def unpack_sos_packet(packet: bytes) -> Dict[str, Any]:
    """
    Unpacks and validates a 120-byte binary SOS packet.
    Raises ValueError if CRC fails or size is incorrect.
    """
    if len(packet) != PACKET_SIZE:
        raise ValueError(f"Invalid packet size: expected {PACKET_SIZE}, got {len(packet)}")

    payload_118 = packet[:118]
    expected_crc = struct.unpack(">H", packet[118:120])[0]
    actual_crc = calculate_crc16_ccitt(payload_118)

    if expected_crc != actual_crc:
        raise ValueError(f"CRC16 mismatch! Expected 0x{expected_crc:04X}, calculated 0x{actual_crc:04X}")

    dev_hash = payload_118[0:6].hex()
    ts, lat_fixed, lon_fixed, alt_decimeters, triage_b, demo_b1, demo_b2, mesh_tel, med_codes = struct.unpack(
        ">Iii h B B B B H",
        payload_118[6:26]
    )

    # Decode bitfields
    severity = (triage_b >> 6) & 0x03
    disaster_type = (triage_b >> 3) & 0x07
    is_trapped = bool((triage_b >> 2) & 0x01)
    mobility = triage_b & 0x03

    adults = (demo_b1 >> 4) & 0x0F
    children = demo_b1 & 0x0F
    elderly = (demo_b2 >> 4) & 0x0F
    critical_cases = demo_b2 & 0x0F

    hop_count = (mesh_tel >> 4) & 0x0F
    battery_pct = (mesh_tel & 0x0F) * 10

    note = decompress_note(payload_118[26:118])

    return {
        "device_hash": dev_hash,
        "timestamp": ts,
        "latitude": lat_fixed / 1e7,
        "longitude": lon_fixed / 1e7,
        "altitude_meters": alt_decimeters / 10.0,
        "altitude_decimeters": alt_decimeters,
        "severity": severity,
        "severity_label": ["GREEN", "YELLOW", "RED", "BLACK"][severity],
        "disaster_type": disaster_type,
        "disaster_label": ["FLOOD", "EARTHQUAKE", "CYCLONE", "LANDSLIDE", "FIRE", "COLLAPSE", "OTHER"][disaster_type],
        "is_trapped": is_trapped,
        "mobility": mobility,
        "demographics": {
            "adults": adults,
            "children": children,
            "elderly": elderly,
            "critical_cases": critical_cases,
            "total_headcount": adults + children + elderly
        },
        "hop_count": hop_count,
        "battery_pct": battery_pct,
        "medical_flags": {
            "insulin": bool(med_codes & MED_FLAG_INSULIN),
            "dialysis": bool(med_codes & MED_FLAG_DIALYSIS),
            "pregnancy": bool(med_codes & MED_FLAG_PREGNANCY),
            "crush_injury": bool(med_codes & MED_FLAG_CRUSH),
            "snakebite": bool(med_codes & MED_FLAG_SNAKEBITE),
            "oxygen_needed": bool(med_codes & MED_FLAG_O2_NEEDED),
            "bleeding": bool(med_codes & MED_FLAG_BLEEDING),
            "fracture": bool(med_codes & MED_FLAG_FRACTURE),
            "raw_flags": med_codes
        },
        "note": note,
        "crc16": expected_crc
    }
