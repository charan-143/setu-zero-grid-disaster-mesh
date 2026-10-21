"""
Store-Carry-Forward (SCF) Epidemic Mesh Router
Features:
- Bloom Filter packet deduplication to prevent broadcast storms.
- TTL (Hop Count) aging and battery-aware transmission intervals.
- Priority Queue based on Triage Severity (RED > YELLOW > GREEN > BLACK).
"""

import hashlib
import time
from typing import Dict, List, Optional, Set
import sys
import os

# Import core SOS packet
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.sos_packet import (
    unpack_sos_packet,
    calculate_crc16_ccitt,
    SEVERITY_RED,
    SEVERITY_YELLOW,
    SEVERITY_GREEN,
    SEVERITY_BLACK
)


class SimpleBloomFilter:
    """Lightweight 256-bit Bloom Filter with 3 hash functions for low memory mobile devices."""
    def __init__(self, size_bits: int = 512):
        self.size = size_bits
        self.bit_array = [0] * (size_bits // 8)

    def _hashes(self, item: bytes) -> List[int]:
        h1 = int(hashlib.md5(item).hexdigest(), 16)
        h2 = int(hashlib.sha1(item).hexdigest(), 16)
        return [
            h1 % self.size,
            h2 % self.size,
            (h1 ^ h2) % self.size
        ]

    def add(self, item: bytes):
        for idx in self._hashes(item):
            byte_idx = idx // 8
            bit_idx = idx % 8
            self.bit_array[byte_idx] |= (1 << bit_idx)

    def contains(self, item: bytes) -> bool:
        for idx in self._hashes(item):
            byte_idx = idx // 8
            bit_idx = idx % 8
            if not (self.bit_array[byte_idx] & (1 << bit_idx)):
                return False
        return True


class EpidemicMeshNode:
    """
    Store-Carry-Forward (SCF) node running on survivor devices or responder mules.
    """
    def __init__(self, node_id: str, is_gateway: bool = False, max_cache_size: int = 100):
        self.node_id = node_id
        self.is_gateway = is_gateway
        self.max_cache_size = max_cache_size
        self.packet_cache: Dict[str, bytes] = {}  # packet_id -> raw 120-byte packet
        self.metadata_cache: Dict[str, dict] = {} # packet_id -> unpacked dict
        self.bloom_filter = SimpleBloomFilter()
        self.forwarded_count = 0
        self.received_count = 0

    def _get_packet_key(self, packet: bytes) -> str:
        """Returns unique identifier for a packet (Device_Hash + Timestamp)."""
        dev_hash = packet[0:6].hex()
        ts = packet[6:10].hex()
        return f"{dev_hash}_{ts}"

    def receive_packet(self, raw_packet: bytes) -> bool:
        """
        Processes an incoming 120-byte packet.
        Returns True if accepted and cached; False if duplicate, corrupt, or expired.
        """
        if len(raw_packet) != 120:
            return False

        # 1. Check Bloom Filter
        packet_key = self._get_packet_key(raw_packet)
        key_bytes = packet_key.encode('utf-8')
        if self.bloom_filter.contains(key_bytes):
            return False  # Already seen, prevent storm

        # 2. Validate CRC
        try:
            unpacked = unpack_sos_packet(raw_packet)
        except Exception:
            return False  # Corrupt packet

        # 3. Check TTL (Hop count)
        hop_count = unpacked["hop_count"]
        if hop_count <= 0 and not self.is_gateway:
            return False  # Expired packet

        # 4. Accept into cache
        self.bloom_filter.add(key_bytes)
        self.packet_cache[packet_key] = raw_packet
        self.metadata_cache[packet_key] = unpacked
        self.received_count += 1

        # Enforce max cache size by dropping lowest priority/oldest packet
        if len(self.packet_cache) > self.max_cache_size:
            self._evict_lowest_priority()

        return True

    def _evict_lowest_priority(self):
        """Evicts lowest severity and oldest packet."""
        # Severity order: BLACK(3) is expectant, GREEN(0) is minor, YELLOW(1), RED(2) highest urgency
        # Sort key: severity priority (RED > YELLOW > GREEN > BLACK), then timestamp
        def priority_score(item):
            unpacked = item[1]
            sev_rank = {SEVERITY_RED: 4, SEVERITY_YELLOW: 3, SEVERITY_GREEN: 2, SEVERITY_BLACK: 1}
            return (sev_rank.get(unpacked["severity"], 0), unpacked["timestamp"])

        sorted_items = sorted(self.metadata_cache.items(), key=priority_score)
        if sorted_items:
            evict_key = sorted_items[0][0]
            del self.packet_cache[evict_key]
            del self.metadata_cache[evict_key]

    def get_packets_for_forwarding(self, max_packets: int = 10) -> List[bytes]:
        """
        Returns high-priority packets prepared for the next BLE / Wi-Fi exchange,
        decrementing hop count (TTL) in-flight.
        """
        # Sort by urgency
        def urgency_key(item):
            unpacked = item[1]
            # Prioritize RED > YELLOW > GREEN > BLACK, and then lowest battery of survivor
            sev_weight = {SEVERITY_RED: 1000, SEVERITY_YELLOW: 500, SEVERITY_GREEN: 100, SEVERITY_BLACK: 10}
            base = sev_weight.get(unpacked["severity"], 0)
            batt_urgency = (100 - unpacked["battery_pct"]) # Lower battery = higher urgency
            return -(base + batt_urgency)

        sorted_keys = sorted(self.metadata_cache.items(), key=urgency_key)
        outgoing_packets = []

        for key, unpacked in sorted_keys[:max_packets]:
            original_pkt = self.packet_cache[key]
            # Decrement hop count if > 0
            current_hop = unpacked["hop_count"]
            if current_hop > 1:
                # Modify byte 23 in payload (Mesh_Telemetry)
                # Byte 23: [4b Hop Count][4b Battery / 10]
                byte23 = original_pkt[23]
                batt_bits = byte23 & 0x0F
                new_hop = (current_hop - 1) & 0x0F
                new_byte23 = (new_hop << 4) | batt_bits
                
                # Rebuild payload and recalculate CRC
                payload_list = bytearray(original_pkt[:118])
                payload_list[23] = new_byte23
                new_crc = calculate_crc16_ccitt(bytes(payload_list))
                repacked = bytes(payload_list) + new_crc.to_bytes(2, 'big')
                outgoing_packets.append(repacked)
            else:
                outgoing_packets.append(original_pkt)
            
            self.forwarded_count += 1

        return outgoing_packets
