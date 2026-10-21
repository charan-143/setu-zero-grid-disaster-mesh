"""
Android "Setu-Mule" Gateway Node Architecture & Service Implementation
Replaces physical ₹1,500 ESP32-S3 + LoRa transceiver with a spare/old Android smartphone.

Responsibilities:
1. Continuous Background BLE 5.0 Scanner & Wi-Fi Aware NAN Sweeper.
2. Acoustic Microphone Listener for 18.5 - 20 kHz ultrasonic beacon chirps.
3. Offline Persistent SQLite Packet Buffer.
4. Long-Range Wi-Fi Direct / Local Hotspot AP Bridge to Incident Command Station.
5. REST / WebSocket bridge to feed Tactical Situational Dashboard.
"""

import sqlite3
import json
import time
import os
import sys
from typing import List, Dict, Any, Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.sos_packet import unpack_sos_packet, calculate_crc16_ccitt
from transport.mesh_router import EpidemicMeshNode


class SetuMuleDatabase:
    """Persistent local database running on the Android Mule device."""
    def __init__(self, db_path: str = "setu_mule_storage.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sos_packets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    packet_hash TEXT UNIQUE,
                    device_hash TEXT,
                    timestamp INTEGER,
                    latitude REAL,
                    longitude REAL,
                    altitude_m REAL,
                    severity INTEGER,
                    severity_label TEXT,
                    disaster_label TEXT,
                    is_trapped INTEGER,
                    total_headcount INTEGER,
                    battery_pct INTEGER,
                    medical_flags_json TEXT,
                    note TEXT,
                    raw_binary_hex TEXT,
                    source_channel TEXT, -- 'BLE', 'WIFI_AWARE', 'ACOUSTIC', 'HOTSPOT'
                    synced_to_command INTEGER DEFAULT 0,
                    received_at INTEGER
                )
            """)
            conn.commit()

    def insert_packet(self, raw_bytes: bytes, source_channel: str = "BLE") -> bool:
        try:
            unpacked = unpack_sos_packet(raw_bytes)
            packet_hash = f"{unpacked['device_hash']}_{unpacked['timestamp']}"
            now = int(time.time())

            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO sos_packets (
                        packet_hash, device_hash, timestamp, latitude, longitude,
                        altitude_m, severity, severity_label, disaster_label,
                        is_trapped, total_headcount, battery_pct, medical_flags_json,
                        note, raw_binary_hex, source_channel, synced_to_command, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """, (
                    packet_hash,
                    unpacked['device_hash'],
                    unpacked['timestamp'],
                    unpacked['latitude'],
                    unpacked['longitude'],
                    unpacked['altitude_meters'],
                    unpacked['severity'],
                    unpacked['severity_label'],
                    unpacked['disaster_label'],
                    1 if unpacked['is_trapped'] else 0,
                    unpacked['demographics']['total_headcount'],
                    unpacked['battery_pct'],
                    json.dumps(unpacked['medical_flags']),
                    unpacked['note'],
                    raw_bytes.hex(),
                    source_channel,
                    now
                ))
                conn.commit()
            return True
        except Exception as e:
            print(f"[SetuMuleDB] Error saving packet: {e}")
            return False

    def get_all_records(self, unsynced_only: bool = False) -> List[Dict[str, Any]]:
        query = "SELECT * FROM sos_packets"
        if unsynced_only:
            query += " WHERE synced_to_command = 0"
        query += " ORDER BY severity DESC, battery_pct ASC"

        results = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            for row in cursor.execute(query):
                item = dict(row)
                item['medical_flags'] = json.loads(item['medical_flags_json'])
                results.append(item)
        return results

    def get_packet_count(self, unsynced_only: bool = False) -> int:
        """Returns total count of stored SOS packets efficiently via SQL COUNT."""
        query = "SELECT COUNT(*) FROM sos_packets"
        if unsynced_only:
            query += " WHERE synced_to_command = 0"
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            return row[0] if row else 0

    def mark_synced(self, packet_hashes: List[str]):
        with sqlite3.connect(self.db_path) as conn:
            for ph in packet_hashes:
                conn.execute("UPDATE sos_packets SET synced_to_command = 1 WHERE packet_hash = ?", (ph,))
            conn.commit()


class AndroidSetuMuleGateway:
    """
    Simulated Android Setu-Mule Gateway service.
    Orchestrates BLE scanning, acoustic capture, local cache, and bridge sync.
    """
    def __init__(self, mule_device_name: str = "SetuMule-Android-01", db_path: str = "setu_mule_storage.db"):
        if mule_device_name.endswith(".db"):
            db_path = mule_device_name
            mule_device_name = "SetuMule-Android-01"
        self.device_name = mule_device_name
        self.db = SetuMuleDatabase(db_path)
        self.mesh_node = EpidemicMeshNode(node_id=mule_device_name, is_gateway=True)
        self.captive_portal_server = None
        self.dns_hijacker = None

    def ingest_raw_packet(self, raw_bytes: bytes, channel: str = "BLE") -> bool:
        """Called when BLE, Wi-Fi Aware or Acoustic modem receives a packet."""
        accepted = self.mesh_node.receive_packet(raw_bytes)
        if accepted:
            self.db.insert_packet(raw_bytes, source_channel=channel)
            return True
        return False

    def ingest_acoustic_beacon(
        self,
        payload_32bit: int,
        approx_lat: float,
        approx_lon: float,
        tdoa_result: Optional[Any] = None
    ) -> bool:
        """
        Synthesizes an SOS packet when an acoustic chirp is detected from rubble,
        geotagging with the Mule's current GPS position and optional 3D TDoA depth fix.
        """
        from transport.acoustic_modem import unpack_acoustic_beacon_payload
        from core.sos_packet import pack_sos_packet

        beacon = unpack_acoustic_beacon_payload(payload_32bit)
        survivor_id = f"AcousticSurvivor_{beacon['survivor_id_hex']}"

        # If 3D TDoA triangulation was computed, record burial depth in altitude (negative decimeters)
        if tdoa_result is not None:
            depth_m = getattr(tdoa_result, "burial_depth_meters", 0.0)
            alt_dm = -int(round(depth_m * 10.0))
            advisory = getattr(tdoa_result, "excavation_advisory", "")
            note = f"3D TDoA Fix: {advisory}"
        else:
            alt_dm = 0
            note = f"Acoustic beacon detected through rubble. ID: {beacon['survivor_id_hex']}"

        # Build 120-byte packet from acoustic detection
        raw_pkt = pack_sos_packet(
            device_id=survivor_id,
            timestamp=int(time.time()),
            latitude=approx_lat,
            longitude=approx_lon,
            altitude_decimeters=alt_dm,
            severity=beacon['severity'],
            disaster_type=beacon['disaster_type'],
            is_trapped=beacon['is_trapped'],
            mobility=0, # immobile under rubble
            adults=1,
            children=0,
            elderly=0,
            critical_cases=1 if beacon['severity'] >= 2 else 0,
            hop_count=1,
            battery_pct=beacon['battery_pct'],
            medical_flags=0,
            note=note
        )

        return self.ingest_raw_packet(raw_pkt, channel="ACOUSTIC_CHIRP")

    def export_dashboard_payload(self) -> Dict[str, Any]:
        """Provides full situational data for the Incident Command Station."""
        records = self.db.get_all_records()
        return {
            "gateway_device": self.device_name,
            "cached_packets_total": len(records),
            "packets": records
        }

    def start_captive_portal(
        self,
        http_port: int = 8080,
        dns_port: Optional[int] = 5353,
        gateway_ip: str = "192.168.4.1",
        bind_host: str = "0.0.0.0"
    ):
        """Spins up the zero-install captive portal and DNS hijacker alongside mesh node."""
        from gateway_mule.captive_portal_server import CaptivePortalServer, DNSHijacker

        # Stop existing instance if already running
        self.stop_captive_portal()

        self.captive_portal_server = CaptivePortalServer(
            host=bind_host,
            port=http_port,
            mule_service=self,
            gateway_ip=gateway_ip
        )
        self.captive_portal_server.start()

        if dns_port is not None and dns_port >= 0:
            try:
                self.dns_hijacker = DNSHijacker(host=bind_host, port=dns_port, gateway_ip=gateway_ip)
                self.dns_hijacker.start()
            except Exception as e:
                print(f"[SetuMuleService] Warning: Could not start DNS hijacker on port {dns_port}: {e}")

        return self.captive_portal_server

    def stop_captive_portal(self):
        """Gracefully terminates captive portal HTTP server and DNS hijacker."""
        if self.captive_portal_server:
            self.captive_portal_server.stop()
            self.captive_portal_server = None
        if self.dns_hijacker:
            self.dns_hijacker.stop()
            self.dns_hijacker = None


# Canonical alias as required by Module 3 specifications
SetuMuleService = AndroidSetuMuleGateway

