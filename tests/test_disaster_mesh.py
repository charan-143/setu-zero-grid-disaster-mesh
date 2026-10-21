import unittest
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sos_packet import (
    pack_sos_packet,
    unpack_sos_packet,
    calculate_crc16_ccitt,
    SEVERITY_RED,
    SEVERITY_YELLOW,
    DISASTER_FLOOD,
    MED_FLAG_INSULIN,
    MED_FLAG_O2_NEEDED
)
from transport.acoustic_modem import (
    pack_acoustic_beacon_payload,
    unpack_acoustic_beacon_payload,
    generate_tone,
    generate_linear_chirp,
    encode_acoustic_signal,
    decode_fsk_spectrum_slice
)
from transport.mesh_router import EpidemicMeshNode, SimpleBloomFilter
from gateway_mule.setu_mule_service import AndroidSetuMuleGateway


class TestDisasterMeshSystem(unittest.TestCase):

    def test_01_binary_packet_codec_exact_120_bytes(self):
        """Verifies 120-byte exact packet packing, unpacking, bitfields and CRC validation."""
        device_id = "device_survivor_99"
        ts = int(time.time())
        lat = 20.296058
        lon = 85.824539
        alt_dm = 145 # 14.5 meters
        note = "Water level rising fast, 2 children need insulin"

        pkt = pack_sos_packet(
            device_id=device_id,
            timestamp=ts,
            latitude=lat,
            longitude=lon,
            altitude_decimeters=alt_dm,
            severity=SEVERITY_RED,
            disaster_type=DISASTER_FLOOD,
            is_trapped=True,
            mobility=1,
            adults=2,
            children=2,
            elderly=1,
            critical_cases=1,
            hop_count=5,
            battery_pct=42,
            medical_flags=MED_FLAG_INSULIN | MED_FLAG_O2_NEEDED,
            note=note
        )

        self.assertEqual(len(pkt), 120, "Packet must be exactly 120 bytes")

        # Unpack and verify
        unpacked = unpack_sos_packet(pkt)
        self.assertEqual(unpacked["severity"], SEVERITY_RED)
        self.assertEqual(unpacked["severity_label"], "RED")
        self.assertEqual(unpacked["disaster_label"], "FLOOD")
        self.assertTrue(unpacked["is_trapped"])
        self.assertEqual(unpacked["demographics"]["adults"], 2)
        self.assertEqual(unpacked["demographics"]["children"], 2)
        self.assertEqual(unpacked["demographics"]["elderly"], 1)
        self.assertEqual(unpacked["battery_pct"], 40) # 10% steps
        self.assertTrue(unpacked["medical_flags"]["insulin"])
        self.assertTrue(unpacked["medical_flags"]["oxygen_needed"])
        self.assertFalse(unpacked["medical_flags"]["dialysis"])
        self.assertAlmostEqual(unpacked["latitude"], lat, places=5)
        self.assertAlmostEqual(unpacked["longitude"], lon, places=5)
        self.assertIn("insulin", unpacked["note"])

    def test_02_packet_tamper_detection_crc16(self):
        """Verifies that tampering with even 1 bit in 120 bytes causes CRC failure."""
        pkt = pack_sos_packet(
            device_id="dev1",
            timestamp=1700000000,
            latitude=19.0,
            longitude=72.0,
            altitude_decimeters=50,
            severity=SEVERITY_YELLOW,
            disaster_type=DISASTER_FLOOD,
            is_trapped=False,
            mobility=2,
            adults=1,
            children=0,
            elderly=0,
            critical_cases=0,
            hop_count=3,
            battery_pct=80,
            medical_flags=0,
            note="Test note"
        )

        # Corrupt 1 byte in the payload
        corrupted = bytearray(pkt)
        corrupted[15] ^= 0x01

        with self.assertRaises(ValueError):
            unpack_sos_packet(bytes(corrupted))

    def test_03_acoustic_modem_synthesis(self):
        """Verifies ultrasonic chirp and 32-bit FSK payload synthesis."""
        payload_32 = pack_acoustic_beacon_payload(
            survivor_id_16=0xA1B2,
            severity=2,
            disaster_type=1,
            is_trapped=True,
            battery_pct=65
        )
        unpacked_beacon = unpack_acoustic_beacon_payload(payload_32)
        self.assertEqual(unpacked_beacon["survivor_id_hex"], "0xA1B2")
        self.assertEqual(unpacked_beacon["severity"], 2)
        self.assertTrue(unpacked_beacon["is_trapped"])
        self.assertEqual(unpacked_beacon["battery_pct"], 65)

        # Generate audio signal
        audio_samples = encode_acoustic_signal(payload_32)
        self.assertGreater(len(audio_samples), 1000)

    def test_04_mesh_router_bloom_filter_and_scf(self):
        """Verifies Store-Carry-Forward, Bloom filter deduplication and TTL decrements."""
        node = EpidemicMeshNode("node_test_1")
        pkt = pack_sos_packet(
            device_id="dev_mesh_test",
            timestamp=int(time.time()),
            latitude=12.9716,
            longitude=77.5946,
            altitude_decimeters=9200,
            severity=SEVERITY_RED,
            disaster_type=DISASTER_FLOOD,
            is_trapped=True,
            mobility=0,
            adults=3,
            children=1,
            elderly=0,
            critical_cases=1,
            hop_count=4,
            battery_pct=30,
            medical_flags=MED_FLAG_INSULIN,
            note="Urgent medical assistance"
        )

        # First receive should succeed
        accepted_first = node.receive_packet(pkt)
        self.assertTrue(accepted_first)

        # Immediate duplicate should be rejected by Bloom Filter
        accepted_dup = node.receive_packet(pkt)
        self.assertFalse(accepted_dup)

        # Forwarding should decrement hop count
        forward_pkts = node.get_packets_for_forwarding(max_packets=5)
        self.assertEqual(len(forward_pkts), 1)
        unpacked_fwd = unpack_sos_packet(forward_pkts[0])
        self.assertEqual(unpacked_fwd["hop_count"], 3) # 4 - 1 = 3

    def test_05_android_setu_mule_gateway_integration(self):
        """Verifies the zero-cost Android Setu-Mule gateway caching and acoustic bridging."""
        test_db_path = "test_mule_gateway.db"
        if os.path.exists(test_db_path):
            os.remove(test_db_path)

        gateway = AndroidSetuMuleGateway(mule_device_name="Test-Mule-Phone", db_path=test_db_path)

        # 1. Ingest BLE SOS packet
        pkt_ble = pack_sos_packet(
            device_id="survivor_phone_1",
            timestamp=int(time.time()),
            latitude=20.30,
            longitude=85.83,
            altitude_decimeters=10,
            severity=SEVERITY_RED,
            disaster_type=DISASTER_FLOOD,
            is_trapped=False,
            mobility=1,
            adults=2,
            children=1,
            elderly=0,
            critical_cases=1,
            hop_count=3,
            battery_pct=15,
            medical_flags=MED_FLAG_INSULIN,
            note="Roof submerged, insulin needed"
        )
        self.assertTrue(gateway.ingest_raw_packet(pkt_ble, channel="BLE"))

        # 2. Ingest Ultrasonic Chirp (Survivor buried under concrete rubble)
        payload_32 = pack_acoustic_beacon_payload(
            survivor_id_16=0xBEEF,
            severity=2,
            disaster_type=5, # COLLAPSE
            is_trapped=True,
            battery_pct=25
        )
        self.assertTrue(gateway.ingest_acoustic_beacon(payload_32, approx_lat=20.301, approx_lon=85.832))

        # Check export payload for Incident Command Dashboard
        dashboard_data = gateway.export_dashboard_payload()
        self.assertEqual(dashboard_data["cached_packets_total"], 2)
        self.assertEqual(dashboard_data["gateway_device"], "Test-Mule-Phone")

        # Cleanup test DB safely on Windows
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except PermissionError:
            pass


if __name__ == "__main__":
    unittest.main()
