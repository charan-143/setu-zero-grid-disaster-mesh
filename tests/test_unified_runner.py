"""
Automated Unit & Integration Tests for the Master Unified Orchestrator (main.py)
Tests that all 4 layers (A, B, C, D) initialize, execute, and communicate in a single combined runner.
"""

import unittest
import time
import urllib.request
import json
import socket
from main import SetuUnifiedSystem


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class TestUnifiedRunner(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dash_port = get_free_port()
        cls.captive_port = get_free_port()
        cls.system = SetuUnifiedSystem(
            dashboard_port=cls.dash_port,
            captive_port=cls.captive_port,
            dns_port=0,
            auto_open_browser=False
        )
        cls.system.start_servers()
        cls.system.run_survivor_simulations()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.system.shutdown()

    def test_01_dashboard_server_alive_and_serving(self):
        url = f"http://127.0.0.1:{self.dash_port}/api/v1/victims"
        req = urllib.request.urlopen(url, timeout=3)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode('utf-8'))
        self.assertIn("victims", data)
        self.assertGreater(data["total"], 0)

    def test_02_vitality_forecast_endpoint(self):
        url = f"http://127.0.0.1:{self.dash_port}/api/v1/vitality_forecast"
        req = urllib.request.urlopen(url, timeout=3)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode('utf-8'))
        self.assertIn("forecast", data)
        self.assertIn("summary", data)

    def test_03_captive_portal_probe_and_status(self):
        probe_url = f"http://127.0.0.1:{self.captive_port}/generate_204"
        req_probe = urllib.request.urlopen(probe_url, timeout=3)
        self.assertEqual(req_probe.status, 200)

        status_url = f"http://127.0.0.1:{self.captive_port}/api/v1/status"
        req_status = urllib.request.urlopen(status_url, timeout=3)
        self.assertEqual(req_status.status, 200)
        status_data = json.loads(req_status.read().decode('utf-8'))
        self.assertEqual(status_data["status"], "online")

    def test_04_all_layers_injected_records(self):
        records = self.system.gateway.db.get_all_records()
        channels = {r["source_channel"] for r in records}
        self.assertTrue(any("BLE" in c for c in channels), "Layer B BLE packets not found")
        self.assertTrue(any("SAR" in c for c in channels), "Layer A SAR-Tap packets not found")
        self.assertTrue(any("ACOUSTIC" in c for c in channels), "Layer C Acoustic 3D TDoA packets not found")


if __name__ == "__main__":
    unittest.main()
