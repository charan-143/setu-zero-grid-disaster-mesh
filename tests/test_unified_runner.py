"""
Automated Unit & Integration Tests for the Single Unified Orchestrator (main.py)
Verifies that all 4 layers execute together, both on a single unified port (8080) and in 100% serverless mode.
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
        cls.port = get_free_port()
        cls.system = SetuUnifiedSystem(
            port=cls.port,
            enable_server=True,
            auto_open_browser=False
        )
        cls.system.start_servers()
        cls.system.run_survivor_simulations()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.system.shutdown()

    def test_01_dashboard_server_alive_and_serving(self):
        url = f"http://127.0.0.1:{self.port}/api/v1/victims"
        req = urllib.request.urlopen(url, timeout=3)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode('utf-8'))
        self.assertIn("victims", data)
        self.assertGreater(data["total"], 0)

    def test_02_vitality_forecast_endpoint(self):
        url = f"http://127.0.0.1:{self.port}/api/v1/vitality_forecast"
        req = urllib.request.urlopen(url, timeout=3)
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode('utf-8'))
        self.assertIn("forecast", data)
        self.assertIn("summary", data)

    def test_03_pwa_and_captive_routes_on_same_port(self):
        # Micro-PWA route on SAME port
        pwa_url = f"http://127.0.0.1:{self.port}/pwa"
        req_pwa = urllib.request.urlopen(pwa_url, timeout=3)
        self.assertEqual(req_pwa.status, 200)
        pwa_html = req_pwa.read().decode('utf-8')
        self.assertIn("Setu", pwa_html)

        # Captive probe route on SAME port
        probe_url = f"http://127.0.0.1:{self.port}/generate_204"
        req_probe = urllib.request.urlopen(probe_url, timeout=3)
        self.assertEqual(req_probe.status, 200)

        # Status route on SAME port
        status_url = f"http://127.0.0.1:{self.port}/api/v1/status"
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

    def test_05_serverless_mode_runs_without_sockets(self):
        # Verifies 100% serverless peer-to-peer operation
        serverless = SetuUnifiedSystem(enable_server=False, auto_open_browser=False)
        serverless.start_servers()
        self.assertIsNone(serverless.server)
        serverless.run_survivor_simulations()
        serverless.shutdown()


if __name__ == "__main__":
    unittest.main()
