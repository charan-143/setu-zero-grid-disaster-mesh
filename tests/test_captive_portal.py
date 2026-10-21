"""
Comprehensive automated tests for Module 3:
Zero-Install Captive Portal & Offline Micro-PWA Gateway Server.

Tests:
1. DNS hijacker resolution: queries for google.com, apple.com, connectivitycheck.gstatic.com
   resolve authoritatively to the target gateway IP.
2. Captive probe detection:
   - Android (/generate_204, /gen_204) -> 302 Redirect to /
   - Apple iOS/macOS (/hotspot-detect.html) -> 200 with Captive Portal HTML
   - Windows (/ncsi.txt, /connecttest.txt) -> 200 with Captive Portal HTML
   - Catch-all redirect for arbitrary URLs -> 302 Redirect to /
3. Embedded offline Micro-PWA:
   - Standalone offline readiness: ZERO external dependencies (<script src="http...">, CDNs)
   - Multilingual UI support (English, Hindi, Bengali, Tamil, Telugu, Marathi)
   - Triage selectors, Demographics, Location/Notes, Broadcast button, Offline First-Aid Advice
4. REST Ingestion API (POST /api/v1/captive_sos):
   - JSON parsing and triage mapping
   - 120-byte binary packet generation and strict CRC16-CCITT validation
   - Persistent SQLite storage in Setu Mule buffer
   - Immediate NDMA offline first-aid guidance from OfflineEmergencyRAG
5. Malformed/invalid payload handling and boundary edge cases (clamping, truncation, empty payload).
6. Gateway Status API (GET /api/v1/status).
7. Integration with SetuMuleService (spins up and tears down captive portal & DNS hijacker).
"""

import http.client
import json
import os
import re
import socket
import struct
import sys
import tempfile
import time
import unittest
import urllib.parse
import urllib.request

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sos_packet import (
    unpack_sos_packet,
    calculate_crc16_ccitt,
    SEVERITY_RED,
    SEVERITY_YELLOW,
    SEVERITY_GREEN,
    DISASTER_FLOOD,
    MED_FLAG_BLEEDING,
    MED_FLAG_INSULIN,
    MED_FLAG_CRUSH,
    MED_FLAG_DIALYSIS,
)
from gateway_mule.captive_portal_server import (
    DNSHijacker,
    CaptivePortalServer,
    CAPTIVE_PORTAL_HTML,
    ZeroInstallCaptiveGateway
)
from gateway_mule.setu_mule_service import SetuMuleService, AndroidSetuMuleGateway


def build_raw_dns_query(domain: str, tx_id: bytes = b"\x12\x34") -> bytes:
    """Builds a standard DNS A-record query packet over UDP."""
    flags = b"\x01\x00"  # Standard query, RD=1
    qdcount = b"\x00\x01"
    ancount = b"\x00\x00"
    nscount = b"\x00\x00"
    arcount = b"\x00\x00"

    # Encode domain into DNS wire labels
    labels = b""
    for part in domain.split("."):
        encoded = part.encode("ascii")
        labels += bytes([len(encoded)]) + encoded
    labels += b"\x00"

    qtype = b"\x00\x01"   # Type A
    qclass = b"\x00\x01"  # Class IN (Internet)

    return tx_id + flags + qdcount + ancount + nscount + arcount + labels + qtype + qclass


def parse_dns_response_ip(response: bytes) -> str:
    """Extracts IPv4 address from the first answer of a DNS response."""
    assert len(response) >= 12, "DNS response too short"
    # Skip header (12 bytes)
    offset = 12
    # Skip question QNAME
    while offset < len(response) and response[offset] != 0:
        offset += 1 + response[offset]
    offset += 1  # null byte
    offset += 4  # skip QTYPE and QCLASS

    # Parse Answer: Name(2B ptr), Type(2B), Class(2B), TTL(4B), RDLENGTH(2B), RDATA(4B)
    assert offset + 12 <= len(response), "Answer section truncated"
    ptr, atype, aclass, ttl, rdlen = struct.unpack(">HHHIH", response[offset : offset + 12])
    assert atype == 1, f"Expected A record (1), got {atype}"
    assert rdlen == 4, f"Expected 4 bytes for IPv4, got {rdlen}"
    ip_raw = response[offset + 12 : offset + 12 + rdlen]
    return socket.inet_ntoa(ip_raw)


class TestCaptivePortalServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(cls.temp_db_fd)
        cls.mule_service = SetuMuleService("TestMule-01", db_path=cls.temp_db_path)

        # Spin up HTTP Captive Portal on an ephemeral OS-assigned port
        cls.target_gateway_ip = "192.168.4.1"
        cls.http_server = CaptivePortalServer(
            host="127.0.0.1",
            port=0,
            mule_service=cls.mule_service,
            gateway_ip=cls.target_gateway_ip
        )
        cls.http_server.start()
        cls.http_port = cls.http_server.server_port

        # Spin up DNS Hijacker on an ephemeral OS-assigned port
        cls.dns_hijacker = DNSHijacker(
            host="127.0.0.1",
            port=0,
            gateway_ip=cls.target_gateway_ip
        )
        cls.dns_hijacker.start()
        cls.dns_port = cls.dns_hijacker.port

    @classmethod
    def tearDownClass(cls):
        cls.http_server.stop()
        cls.dns_hijacker.stop()
        if os.path.exists(cls.temp_db_path):
            try:
                os.remove(cls.temp_db_path)
            except Exception:
                pass

    def test_01_dns_hijacker_resolution_various_domains(self):
        """Verifies DNS queries for any domain resolve to the target gateway IP."""
        test_domains = [
            "google.com",
            "apple.com",
            "connectivitycheck.gstatic.com",
            "www.msftconnecttest.com",
            "captive.apple.com"
        ]

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_sock.settimeout(2.0)

        try:
            for domain in test_domains:
                query = build_raw_dns_query(domain)
                client_sock.sendto(query, ("127.0.0.1", self.dns_port))
                response, _ = client_sock.recvfrom(512)

                # Verify response transaction ID matches query
                self.assertEqual(response[:2], query[:2])
                # Verify resolved IP matches gateway target IP
                resolved_ip = parse_dns_response_ip(response)
                self.assertEqual(resolved_ip, self.target_gateway_ip)

            self.assertGreaterEqual(self.dns_hijacker.query_count, len(test_domains))
        finally:
            client_sock.close()

    def test_02_android_captive_probe_detection(self):
        """Verifies Android captive portal probes (/generate_204 and /gen_204) redirect to /."""
        for path in ["/generate_204", "/gen_204"]:
            conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
            conn.request("GET", path)
            resp = conn.getresponse()
            self.assertEqual(resp.status, 302, f"Failed for {path}")
            self.assertEqual(resp.getheader("Location"), "/")
            conn.close()

    def test_03_apple_captive_probe_detection(self):
        """Verifies Apple iOS/macOS CNA probe (/hotspot-detect.html) returns 200 with captive portal HTML."""
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("GET", "/hotspot-detect.html")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertIn("text/html", resp.getheader("Content-Type"))
        body = resp.read().decode("utf-8")
        self.assertIn("SETU EMERGENCY SOS", body)
        conn.close()

    def test_04_windows_captive_probe_detection(self):
        """Verifies Windows probes (/ncsi.txt and /connecttest.txt) serve the captive portal."""
        for path in ["/ncsi.txt", "/connecttest.txt"]:
            conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
            conn.request("GET", path)
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200, f"Failed for {path}")
            body = resp.read().decode("utf-8")
            self.assertIn("SETU EMERGENCY SOS", body)
            conn.close()

    def test_05_generic_catchall_redirects_to_root(self):
        """Verifies arbitrary GET paths redirect to / with 302."""
        for path in ["/search?q=test", "/weather/today", "/random_page.html"]:
            conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
            conn.request("GET", path)
            resp = conn.getresponse()
            self.assertEqual(resp.status, 302, f"Failed for {path}")
            self.assertEqual(resp.getheader("Location"), "/")
            conn.close()

    def test_06_embedded_micro_pwa_offline_readiness_and_zero_cdn_dependencies(self):
        """
        Verifies that root '/' serves the embedded offline Micro-PWA,
        with strictly zero external script or stylesheet CDN dependencies.
        """
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("GET", "/")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        body = resp.read().decode("utf-8")
        conn.close()

        # Offline Readiness: No external CDN or internet dependencies
        external_scripts = re.findall(r'<script[^>]+src=["\']https?://[^"\']+["\']', body, re.IGNORECASE)
        external_links = re.findall(r'<link[^>]+href=["\']https?://[^"\']+["\']', body, re.IGNORECASE)
        self.assertEqual(len(external_scripts), 0, f"Found external scripts: {external_scripts}")
        self.assertEqual(len(external_links), 0, f"Found external stylesheets: {external_links}")

        # Core PWA UI components
        self.assertIn("SETU EMERGENCY SOS", body)
        # Multilingual presence
        self.assertIn("हिन्दी", body)
        self.assertIn("বাংলা", body)
        self.assertIn("தமிழ்", body)
        # Triage and Medical flags
        self.assertIn("m_bleed", body)
        self.assertIn("m_crush", body)
        self.assertIn("m_insulin", body)
        self.assertIn("m_dialysis", body)
        self.assertIn("m_fracture", body)
        self.assertIn("m_pregnant", body)
        # Demographics
        self.assertIn("val_adults", body)
        self.assertIn("val_children", body)
        self.assertIn("val_elderly", body)
        self.assertIn("val_critical", body)
        # Action button and Advice section
        self.assertIn("BROADCAST SOS NOW", body)
        self.assertIn("NDMA Offline First-Aid Advice", body)

    def test_07_post_captive_sos_ingestion_and_sqlite_storage(self):
        """
        Verifies POST /api/v1/captive_sos ingests JSON, packs authentic 120B packet,
        validates CRC16, persists to SQLite, and returns immediate NDMA first-aid advice.
        """
        payload = {
            "disaster_type": DISASTER_FLOOD,
            "is_trapped": True,
            "adults": 2,
            "children": 1,
            "elderly": 1,
            "critical_cases": 1,
            "arterial_bleed": True,
            "insulin": True,
            "latitude": 20.2961,
            "longitude": 85.8245,
            "altitude_decimeters": 120,
            "battery_pct": 80,
            "location_notes": "2nd floor terrace, rising water level",
            "language": "en"
        }

        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        headers = {"Content-Type": "application/json"}
        conn.request("POST", "/api/v1/captive_sos", body=json.dumps(payload), headers=headers)
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)

        data = json.loads(resp.read().decode("utf-8"))
        conn.close()

        # Check response schema
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["severity"], SEVERITY_RED)
        self.assertEqual(data["severity_label"], "RED")
        self.assertEqual(data["packet_size"], 120)
        self.assertTrue(data["saved_to_mule"])
        self.assertTrue(len(data["packet_hash"]) > 0)
        self.assertIn("Immediate instructions", data["first_aid_guidance"])

        # Check SQLite persistence
        records = self.mule_service.db.get_all_records()
        self.assertGreaterEqual(len(records), 1)

        latest_record = records[0]  # Sorted by severity DESC
        self.assertEqual(latest_record["source_channel"], "HOTSPOT_CAPTIVE_PORTAL")
        self.assertEqual(latest_record["severity"], SEVERITY_RED)
        self.assertEqual(latest_record["is_trapped"], 1)
        self.assertEqual(latest_record["total_headcount"], 4)
        self.assertIn("terrace", latest_record["note"])

        # Verify raw binary bytes stored in SQLite unpack cleanly and validate CRC16
        raw_binary = bytes.fromhex(latest_record["raw_binary_hex"])
        self.assertEqual(len(raw_binary), 120)
        unpacked = unpack_sos_packet(raw_binary)
        self.assertEqual(unpacked["severity"], SEVERITY_RED)
        self.assertTrue(unpacked["medical_flags"]["bleeding"])
        self.assertTrue(unpacked["medical_flags"]["insulin"])

    def test_08_post_captive_sos_vernacular_hindi_response(self):
        """Verifies NDMA first aid response in Hindi when requested."""
        payload = {
            "disaster_type": 5, # Collapse
            "is_trapped": True,
            "crush": True,
            "location_notes": "कंक्रीट के मलबे के नीचे फंसे हैं",
            "language": "hi"
        }

        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("POST", "/api/v1/captive_sos", body=json.dumps(payload), headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)

        data = json.loads(resp.read().decode("utf-8"))
        conn.close()

        self.assertEqual(data["status"], "success")
        self.assertIn("तुरंत यह करें", data["first_aid_guidance"])

    def test_09_post_captive_sos_malformed_and_edge_cases(self):
        """Verifies robust error handling for malformed JSON, empty payload, and boundary clamping."""
        # Case A: Empty payload -> 400
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("POST", "/api/v1/captive_sos", body="", headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 400)
        conn.close()

        # Case B: Malformed JSON syntax -> 400
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("POST", "/api/v1/captive_sos", body="{'unquoted': broken", headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 400)
        conn.close()

        # Case C: Boundary clamping: demographics > 15 clamped to 15, note > 92 bytes truncated
        super_long_note = "A" * 200
        edge_payload = {
            "adults": 99,       # Clamped to 15
            "children": 50,     # Clamped to 15
            "elderly": -5,      # Clamped to 0
            "note": super_long_note
        }
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("POST", "/api/v1/captive_sos", body=json.dumps(edge_payload), headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read().decode("utf-8"))
        conn.close()

        self.assertEqual(data["packet_size"], 120)

    def test_10_status_endpoint_telemetry(self):
        """Verifies GET /api/v1/status provides gateway telemetry and buffer metrics."""
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("GET", "/api/v1/status")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)

        data = json.loads(resp.read().decode("utf-8"))
        conn.close()

        self.assertEqual(data["status"], "online")
        self.assertEqual(data["gateway_device"], "TestMule-01")
        self.assertIn("connected_victims_count", data)
        self.assertIn("spooled_packets_count", data)
        self.assertGreaterEqual(data["spooled_packets_count"], 1)
        self.assertTrue(data["gateway_telemetry"]["is_gateway"])

    def test_11_setu_mule_service_portal_lifecycle_integration(self):
        """Verifies SetuMuleService can spin up and stop captive portal and DNS hijacker."""
        temp_fd, temp_db = tempfile.mkstemp(suffix=".db")
        os.close(temp_fd)

        try:
            mule = SetuMuleService("LifecycleMule", db_path=temp_db)
            portal = mule.start_captive_portal(http_port=0, dns_port=0, gateway_ip="192.168.4.1", bind_host="127.0.0.1")
            self.assertIsNotNone(portal)
            self.assertIsNotNone(mule.captive_portal_server)
            self.assertTrue(mule.captive_portal_server.is_running)
            self.assertIsNotNone(mule.dns_hijacker)
            self.assertTrue(mule.dns_hijacker.running)
            self.assertGreater(mule.dns_hijacker.port, 0)

            http_port = mule.captive_portal_server.server_port
            dns_port = mule.dns_hijacker.port

            # Test query against lifecycle instance
            conn = http.client.HTTPConnection("127.0.0.1", http_port, timeout=2.0)
            conn.request("GET", "/hotspot-detect.html")
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            conn.close()

            # Test DNS resolution on lifecycle instance (unconditionally verified)
            client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_sock.settimeout(2.0)
            q = build_raw_dns_query("apple.com")
            client_sock.sendto(q, ("127.0.0.1", dns_port))
            ans, _ = client_sock.recvfrom(512)
            resolved = parse_dns_response_ip(ans)
            self.assertEqual(resolved, "192.168.4.1")
            client_sock.close()

            mule.stop_captive_portal()
            self.assertIsNone(mule.captive_portal_server)
            self.assertIsNone(mule.dns_hijacker)
        finally:
            if os.path.exists(temp_db):
                try:
                    os.remove(temp_db)
                except Exception:
                    pass

    def test_12_dns_hijacker_malformed_and_truncated_queries(self):
        """Verifies DNS hijacker handles truncated or empty query bytes without crashing."""
        truncated_query = b"\x12\x34\x01\x00"  # only 4 bytes, invalid header
        response = self.dns_hijacker.craft_response(truncated_query)
        self.assertEqual(response, b"")

        # Unterminated QNAME label extending past end of packet
        malformed_query = b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x05abc"
        response2 = self.dns_hijacker.craft_response(malformed_query)
        self.assertEqual(response2, b"")

    def test_13_post_captive_sos_unicode_notes_and_all_medical_flags(self):
        """Verifies ingestion of Unicode multilingual text and combined medical flags."""
        payload = {
            "disaster_type": 1, # Earthquake
            "is_trapped": "1", # string integer representation
            "arterial_bleed": True,
            "crush": True,
            "insulin": True,
            "dialysis": True,
            "fracture": True,
            "pregnancy": True,
            "o2": True,
            "snakebite": True,
            "location_notes": "দ্বিতীয় তলা, সিঁড়ির নিচে জল বাড়ছে",
            "language": "bn"
        }

        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("POST", "/api/v1/captive_sos", body=json.dumps(payload), headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)

        data = json.loads(resp.read().decode("utf-8"))
        conn.close()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["severity"], SEVERITY_RED)
        self.assertEqual(data["packet_size"], 120)

    def test_14_post_to_unsupported_endpoint(self):
        """Verifies POST requests to unrecognized endpoints return 404."""
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("POST", "/api/v1/unknown_action", body="{}", headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 404)
        conn.close()

    def test_15_query_params_on_probes(self):
        """Verifies URL query parameters on probes do not prevent detection."""
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("GET", "/generate_204?android_version=14&ts=123456")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 302)
        self.assertEqual(resp.getheader("Location"), "/")
        conn.close()

        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("GET", "/hotspot-detect.html?client=apple_cna")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        body = resp.read().decode("utf-8")
        self.assertIn("SETU EMERGENCY SOS", body)
        conn.close()

    def test_16_head_requests_on_probes_and_root(self):
        """Verifies HEAD requests on probes and root return correct status and headers without body."""
        # HEAD on Android probe
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("HEAD", "/generate_204")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 302)
        self.assertEqual(resp.getheader("Location"), "/")
        self.assertEqual(len(resp.read()), 0)
        conn.close()

        # HEAD on Apple CNA probe
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("HEAD", "/hotspot-detect.html")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertIn("text/html", resp.getheader("Content-Type"))
        self.assertEqual(len(resp.read()), 0)
        conn.close()

        # HEAD on root
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("HEAD", "/")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertEqual(len(resp.read()), 0)
        conn.close()

    def test_17_options_cors_preflight(self):
        """Verifies OPTIONS preflight returns 200 with CORS headers for mobile WebView compatibility."""
        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("OPTIONS", "/api/v1/captive_sos")
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), "*")
        self.assertIn("POST", resp.getheader("Access-Control-Allow-Methods"))
        conn.close()

    def test_18_post_captive_sos_robustness_against_nulls_and_overflows(self):
        """Verifies server does not crash when payload contains null values, out-of-range coords, or invalid strings."""
        dirty_payload = {
            "adults": None,             # Should safely default to 1
            "children": "not_a_number", # Should safely default to 0
            "elderly": None,            # Should safely default to 0
            "critical_cases": -10,      # Should clamp to 0
            "latitude": 999.0,          # Out of range, should clamp to 90.0 without struct.error
            "longitude": -500.0,        # Out of range, should clamp to -180.0
            "altitude_decimeters": 999999, # Out of int16 range, should clamp safely
            "battery_pct": None,        # Should default to 85
            "disaster_type": 99,        # Out of 3-bit range, should clamp to 7
            "is_trapped": "YES",        # Truthy string
            "arterial_bleed": "false",  # Falsy string
            "crush": True
        }

        conn = http.client.HTTPConnection("127.0.0.1", self.http_port, timeout=2.0)
        conn.request("POST", "/api/v1/captive_sos", body=json.dumps(dirty_payload), headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)

        data = json.loads(resp.read().decode("utf-8"))
        conn.close()

        self.assertEqual(data["status"], "success")
        self.assertEqual(data["packet_size"], 120)
        self.assertTrue(data["saved_to_mule"])

    def test_19_zero_install_gateway_supervisor(self):
        """Verifies ZeroInstallCaptiveGateway orchestrates both HTTP and DNS services with port properties."""
        gw = ZeroInstallCaptiveGateway(host="127.0.0.1", http_port=0, dns_port=0, gateway_ip="192.168.4.1")
        gw.start()
        try:
            self.assertGreater(gw.http_port, 0)
            self.assertIsNotNone(gw.dns_port)
            self.assertGreater(gw.dns_port, 0)

            # Test HTTP via supervisor port
            conn = http.client.HTTPConnection("127.0.0.1", gw.http_port, timeout=2.0)
            conn.request("GET", "/hotspot-detect.html")
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            conn.close()

            # Test DNS via supervisor port
            client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_sock.settimeout(2.0)
            q = build_raw_dns_query("connectivitycheck.gstatic.com")
            client_sock.sendto(q, ("127.0.0.1", gw.dns_port))
            ans, _ = client_sock.recvfrom(512)
            self.assertEqual(parse_dns_response_ip(ans), "192.168.4.1")
            client_sock.close()
        finally:
            gw.stop()

    def test_20_setu_mule_database_packet_count_efficiency(self):
        """Verifies SetuMuleDatabase.get_packet_count returns accurate count via SQL COUNT."""
        temp_fd, temp_db = tempfile.mkstemp(suffix=".db")
        os.close(temp_fd)
        try:
            from gateway_mule.setu_mule_service import SetuMuleDatabase
            from core.sos_packet import pack_sos_packet
            db = SetuMuleDatabase(temp_db)
            self.assertEqual(db.get_packet_count(), 0)

            pkt = pack_sos_packet("Node1", int(time.time()), 20.0, 85.0, 0, 1, 0, False, 1, 1, 0, 0, 0, 1, 90, 0, "Test")
            db.insert_packet(pkt, "HOTSPOT")
            self.assertEqual(db.get_packet_count(), 1)
            self.assertEqual(db.get_packet_count(unsynced_only=True), 1)
        finally:
            if os.path.exists(temp_db):
                try:
                    os.remove(temp_db)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()

