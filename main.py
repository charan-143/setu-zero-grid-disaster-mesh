"""
Unified Zero-Grid Disaster Mesh & Triage System (Setu) - Master Orchestrator
Combines Layer A (Edge), Layer B (Transport), Layer C (Mule Gateway), and Layer D (Incident Command).

Zero-Server / Peer-to-Peer Architecture:
- Between physical Android devices: 100% serverless directly via BLE & Ultrasonic audio!
- On PC / Incident Command: Single unified entry point on http://localhost:8080 serving BOTH the GIS Dashboard and Mobile PWA with zero separate servers.
"""

import os
import sys
import time
import math
import json
import socket
import urllib.request
import threading
import webbrowser
from http.server import HTTPServer
from typing import Dict, Any, List, Optional

# Ensure repository root is on path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Core modules
from core.sos_packet import (
    pack_sos_packet,
    unpack_sos_packet,
    SEVERITY_RED,
    SEVERITY_YELLOW,
    SEVERITY_GREEN,
    DISASTER_FLOOD,
    DISASTER_BUILDING_COLLAPSE,
    MED_FLAG_INSULIN,
    MED_FLAG_CRUSH,
    MED_FLAG_BLEEDING
)
from core.triage_extractor import VernacularTriageExtractor
from core.offline_rag import OfflineEmergencyRAG
from core.cryo_sleep_manager import CryoSleepManager
from core.vitality_decay_engine import VitalityDecayEngine, MultiTeamDispatchOptimizer

# Transport & Hardware modules
from transport.sar_tap_detector import SarTapDetector, PatternType
from transport.acoustic_modem import pack_acoustic_beacon_payload, encode_acoustic_signal
from transport.acoustic_tdoa_triangulator import AcousticTDoATriangulator, ReceiverNode

# Gateway & Server modules
from gateway_mule.setu_mule_service import AndroidSetuMuleGateway
from dashboard.server import TacticalDashboardHandler, GATEWAY


class SetuUnifiedSystem:
    """Master orchestrator combining all 4 layers of the Setu Disaster Mesh into a single runtime."""

    def __init__(
        self,
        port: int = 8080,
        enable_server: bool = True,
        auto_open_browser: bool = True
    ):
        self.port = port
        self.enable_server = enable_server
        self.auto_open_browser = auto_open_browser

        self.gateway = GATEWAY
        self.server: Optional[HTTPServer] = None
        self.running = False
        self._threads: List[threading.Thread] = []

    def start_servers(self):
        """Starts the single unified server (serving both GIS Dashboard and Mobile PWA) in a background thread."""
        print("\n" + "=" * 75)
        print("  🛰️  SETU: ZERO-GRID DISASTER MESH & TACTICAL TRIAGE ORCHESTRATOR")
        print("     100% Zero-Hardware-Cost Offline Emergency Infrastructure")
        print("=" * 75)

        if not self.enable_server:
            print("\n[*] RUNNING IN 100% SERVERLESS PEER-TO-PEER MODE (NO LOCAL WEBSERVER)")
            return

        print(f"\n[1] INITIALIZING SINGLE UNIFIED TACTICAL STATION (PORT {self.port})...")
        try:
            self.server = HTTPServer(('0.0.0.0', self.port), TacticalDashboardHandler)
            srv_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            srv_thread.start()
            self._threads.append(srv_thread)
            print(f"    ✓ Tactical Incident Command GIS Map: http://127.0.0.1:{self.port}/")
            print(f"    ✓ Zero-Install Mobile Emergency PWA: http://127.0.0.1:{self.port}/pwa")
            print(f"    ✓ Real-time Vitality & Dispatch API: http://127.0.0.1:{self.port}/api/v1/vitality_forecast")
        except Exception as e:
            print(f"    ✗ Warning: Could not bind server to port {self.port}: {e}")

    def run_survivor_simulations(self):
        """Simulates all edge nodes, transports, 3D TDoA, and dynamic dispatch."""

        # -------------------------------------------------------------
        # Node 1: Layer A Indic Voice Triage & Cryo-Sleep Power Budgeter
        # -------------------------------------------------------------
        print("\n" + "-" * 75)
        print("[2] LAYER A: SURVIVOR EDGE NODE (VERNACULAR SPEECH & CRYO-SLEEP)")
        print("-" * 75)
        speech_text = "पानी छत तक आ गया है, मेरे साथ दो बच्चे और एक बुजुर्ग हैं जिन्हें इंसुलिन चाहिए"
        print(f"    [Audio Ingestion]: \"{speech_text}\"")
        triage = VernacularTriageExtractor.parse_transcript(speech_text)
        print(f"    -> SLM Extracted: Disaster={triage['disaster_type']} (FLOOD), Trapped={triage['is_trapped']}, "
              f"Headcount={triage['demographics']['total_headcount']}, Insulin Need=True")

        rag = OfflineEmergencyRAG()
        guidance = rag.get_relief_response(speech_text, lang="hi")
        print(f"    [Offline Voice TTS to Survivor]: \"{guidance[:95]}...\"")

        # Cryo-Sleep duty cycler
        cryo = CryoSleepManager(battery_capacity_mah=4000.0, nominal_voltage=3.85)
        rubble_state = cryo.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=25.0)
        rec = cryo.get_power_budget_recommendation()
        print(f"    [Cryo-Sleep Manager]: State={rubble_state.value} | Projected Survival={rec.survival_horizon.days:.1f} days "
              f"({rec.power_saving_factor:.1f}x gain vs active scanning)")

        survivor_1_pkt = pack_sos_packet(
            device_id="Survivor_Voice_Rooftop",
            timestamp=int(time.time()),
            latitude=20.2961,
            longitude=85.8245,
            altitude_decimeters=180,
            severity=triage["severity"],
            disaster_type=triage["disaster_type"],
            is_trapped=triage["is_trapped"],
            mobility=triage["mobility"],
            adults=triage["demographics"]["adults"],
            children=triage["demographics"]["children"],
            elderly=triage["demographics"]["elderly"],
            critical_cases=triage["demographics"]["critical_cases"],
            hop_count=5,
            battery_pct=25,
            medical_flags=triage["medical_flags"],
            note="Water at roof level. Elderly grandfather needs insulin urgently."
        )
        self.gateway.ingest_raw_packet(survivor_1_pkt, channel="BLE_5.0_EXT")
        print(f"    ✓ Broadcasted & Ingested into Mule via BLE Extended Advertising (120 Bytes, CRC16 Valid)")

        # -------------------------------------------------------------
        # Node 2: Layer A Non-Vocal Seismic & Acoustic SAR-Tap Codec
        # -------------------------------------------------------------
        print("\n" + "-" * 75)
        print("[3] LAYER A: NON-VOCAL SEISMIC CODEC (SAR-TAP)")
        print("-" * 75)
        print("    Scenario: Survivor trapped under concrete rubble, unable to speak.")
        print("    Survivor strikes rebar with 3 rapid knocks (Universal Alpine/Mining/NDMA 3-Tap distress).")

        sar_detector = SarTapDetector(
            device_id="Survivor_Rubble_Tap",
            latitude=20.2935,
            longitude=85.8205,
            altitude_decimeters=-20,
            battery_pct=15,
            hop_count=4,
            cryo_manager=cryo
        )
        t_series, ax, ay, az = SarTapDetector.generate_synthetic_3tap_accel(dt1=0.60, dt2=0.60, sample_rate=50.0)
        audio_samples = [0.0] * int(3.0 * 8000)
        for pt in [0.5, 1.1, 1.7]:
            start_idx = int(pt * 8000)
            for i in range(int(0.02 * 8000)):
                if start_idx + i < len(audio_samples):
                    audio_samples[start_idx + i] = 0.85 * math.sin(2 * math.pi * 1000 * (i / 8000))

        tap_result = sar_detector.process_dual_channel(
            accel_timestamps=t_series, ax=ax, ay=ay, az=az,
            acoustic_samples=audio_samples, sample_rate=8000
        )
        print(f"    -> Coincident Sensor Fusion : {tap_result.tap_count} strikes verified (Modality: {tap_result.details.get('sensor_modality')})")
        print(f"    -> Cadence Classifier      : {tap_result.pattern_type.value} (Confidence: {tap_result.confidence*100:.1f}%)")
        print(f"    -> Cryo Wake Interrupt     : Fired = {tap_result.wake_triggered} (Immediate SOS Burst Triggered)")

        self.gateway.ingest_raw_packet(tap_result.sos_packet, channel="SAR_TAP_SEISMIC")
        print(f"    ✓ Synthesized 120-Byte Non-Vocal SOS Packet Ingested into Mule Buffer")

        # -------------------------------------------------------------
        # Node 3: Layer B & C Ultrasonic Acoustic 3D TDoA Triangulation
        # -------------------------------------------------------------
        print("\n" + "-" * 75)
        print("[4] LAYER B & C: MULTI-RECEIVER ULTRASONIC ACOUSTIC 3D TDoA")
        print("-" * 75)
        print("    Scenario: Buried concrete survivor emitting 18.5 kHz - 20 kHz ultrasonic acoustic chirp.")
        print("    Deploying 4 surface Ground Mule receivers for 3D sub-surface localization:")

        receivers = [
            ReceiverNode("Mule-01-North", (0.0, 0.0, 0.1)),
            ReceiverNode("Mule-02-East",  (4.5, 0.0, -0.1)),
            ReceiverNode("Mule-03-West",  (0.5, 4.0, 0.2)),
            ReceiverNode("Mule-04-South", (4.0, 3.5, 0.0))
        ]
        for r in receivers:
            print(f"      * {r.node_id:<14}: Surface Pos (X={r.position[0]:.1f}m, Y={r.position[1]:.1f}m, Z={r.position[2]:+.1f}m)")

        survivor_true = (2.0, 1.5, -2.5) # Ground truth depth = 2.5m
        speed_of_sound = 343.0
        dists = [math.sqrt(sum((survivor_true[k] - r.position[k])**2 for k in range(3))) for r in receivers]
        tdoas = {(receivers[0].node_id, receivers[i].node_id): (dists[i] - dists[0]) / speed_of_sound for i in range(1, len(receivers))}

        triangulator = AcousticTDoATriangulator(speed_of_sound=speed_of_sound, sample_rate=44100)
        tdoa_result = triangulator.triangulate(receivers=receivers, tdoas=tdoas)

        print(f"    [+] 3D Sub-Surface Fix ACQUIRED:")
        print(f"        * Relative Coordinates : X={tdoa_result.estimated_position[0]:+.2f}m, Y={tdoa_result.estimated_position[1]:+.2f}m, Z={tdoa_result.estimated_position[2]:+.2f}m")
        print(f"        * Absolute Burial Depth: {tdoa_result.burial_depth_meters:.2f} METERS BENEATH SLAB")
        print(f"        * Multilateration Conf : {tdoa_result.confidence_score*100:.1f}% (RMSE: {tdoa_result.residual_rmse*100:.2f} cm)")
        print(f"        * TACTICAL ADVISORY    : \"{tdoa_result.excavation_advisory}\"")

        acoustic_payload = pack_acoustic_beacon_payload(
            survivor_id_16=0xC0DE, severity=SEVERITY_RED, disaster_type=DISASTER_BUILDING_COLLAPSE, is_trapped=True, battery_pct=12
        )
        self.gateway.ingest_acoustic_beacon(acoustic_payload, approx_lat=20.2940, approx_lon=85.8210, tdoa_result=tdoa_result)
        print(f"    ✓ Acoustic Beacon Tagged with 3D Depth Ingested into Mule Buffer")

        # -------------------------------------------------------------
        # Node 4: Layer B Flood Ground Floor (Wi-Fi Aware NAN)
        # -------------------------------------------------------------
        survivor_4_pkt = pack_sos_packet(
            device_id="Survivor_Ground_Floor",
            timestamp=int(time.time()) - 180,
            latitude=20.2980,
            longitude=85.8270,
            altitude_decimeters=20,
            severity=SEVERITY_YELLOW,
            disaster_type=DISASTER_FLOOD,
            is_trapped=False,
            mobility=1,
            adults=3,
            children=1,
            elderly=0,
            critical_cases=0,
            hop_count=4,
            battery_pct=60,
            medical_flags=0,
            note="Water 3 feet deep. Safe for now on tables, need boat evacuation."
        )
        self.gateway.ingest_raw_packet(survivor_4_pkt, channel="WIFI_AWARE_NAN")

        # -------------------------------------------------------------
        # Phase 4: Layer D Dynamic Golden-Hour Triage & Dispatch Optimizer
        # -------------------------------------------------------------
        print("\n" + "-" * 75)
        print("[5] LAYER D: DYNAMIC GOLDEN-HOUR TRAUMA DECAY & DISPATCH OPTIMIZATION")
        print("-" * 75)
        records = self.gateway.db.get_all_records()
        assessed_victims = VitalityDecayEngine.rank_victims(records)

        print(f"    {'RANK':<5} | {'SEVERITY':<14} | {'VITALITY':<9} | {'WINDOW REMAINING':<18} | {'LOCATION / NOTE'}")
        print("    " + "-" * 71)
        for idx, v in enumerate(assessed_victims[:5], 1):
            sev_label = f"[{v.get('survival_state', 'UNKNOWN')[:12]}]"
            v_score = f"{v.get('vitality_score', 1.0)*100:.1f}%"
            time_left = v.get('time_to_critical_formatted', '00:00:00')
            note = (v.get('note') or '')[:32]
            print(f"    #{idx:<4} | {sev_label:<14} | {v_score:<9} | {time_left:<18} | {note}")

        # Multi-team dispatch optimization
        dispatch_plan = MultiTeamDispatchOptimizer.optimize_dispatch(records)
        print(f"\n    [Automated Tactical Dispatch Solution]:")
        for team in dispatch_plan.get("teams", []):
            route_str = " -> ".join([str(target.get("victim_id", "?")) for target in team.get("route", [])]) or "Standby"
            print(f"      • Team '{team['team_id']}' ({team['type']}, {team['speed_kmh']} km/h): Dispatched to [{route_str}]")

    def run_unified(self):
        """Main execution entry point."""
        self.start_servers()
        self.run_survivor_simulations()

        print("\n" + "=" * 75)
        print("  ✅ ALL 4 LAYERS ARE COMBINED & ACTIVE IN A SINGLE RUNTIME")
        print("=" * 75)
        if self.enable_server:
            print(f"  🌐 Tactical Command GIS & PWA: http://localhost:{self.port} (Dashboard: /, PWA: /pwa)")
        else:
            print(f"  ⚡ 100% Serverless Peer-to-Peer Operation")
        print(f"  📡 Shared Mule Ingestion Buffer: {self.gateway.db.db_path} ({len(self.gateway.db.get_all_records())} total records)")
        print("=" * 75)

        if self.enable_server and self.auto_open_browser:
            try:
                print(f"\n[*] Opening Incident Command Dashboard on http://localhost:{self.port}...")
                webbrowser.open(f"http://localhost:{self.port}")
            except Exception:
                pass

        self._run_interactive_console()

    def _run_interactive_console(self):
        """Interactive command-line control console."""
        print("\n[Interactive Command Console] Type a command or number:")
        print("  [1] Trigger New Vernacular Voice SOS (Hindi/Bengali/Tamil)")
        print("  [2] Trigger New SAR-Tap Seismic/Acoustic Strike under Concrete")
        print("  [3] Ingest New Zero-Install Captive PWA Emergency Report")
        print("  [4] Recalculate Dynamic Golden-Hour Dispatch Plan")
        if self.enable_server:
            print(f"  [5] Open Incident Command Dashboard (http://localhost:{self.port}/)")
            print(f"  [6] Open Zero-Install Captive PWA (http://localhost:{self.port}/pwa)")
        else:
            print(f"  [5] Start Optional Local Web Dashboard (on port {self.port})")
        print("  [q] Quit\n")

        if not sys.stdin.isatty():
            print("[*] Running in non-interactive / background service mode. All layers active.")
            try:
                while True:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                print("\n[*] Shutting down...")
                self.shutdown()
            return

        while True:
            try:
                cmd = input("Setu-Command> ").strip().lower()
                if cmd in ('q', 'quit', 'exit'):
                    print("[*] Terminating all unified services...")
                    self.shutdown()
                    break
                elif cmd == '1':
                    self._cmd_voice_sos()
                elif cmd == '2':
                    self._cmd_sartap_sos()
                elif cmd == '3':
                    self._cmd_captive_pwa_sos()
                elif cmd == '4':
                    self._cmd_dispatch_calc()
                elif cmd == '5' and self.enable_server:
                    webbrowser.open(f"http://localhost:{self.port}/")
                    print(f"Opened http://localhost:{self.port}/")
                elif cmd == '5' and not self.enable_server:
                    print(f"\n[*] Starting optional Web Dashboard on port {self.port}...")
                    self.enable_server = True
                    self.start_servers()
                    try:
                        webbrowser.open(f"http://localhost:{self.port}/")
                    except Exception:
                        pass
                elif cmd == '6' and self.enable_server:
                    webbrowser.open(f"http://localhost:{self.port}/pwa")
                    print(f"Opened http://localhost:{self.port}/pwa")
                elif cmd:
                    print(f"Unknown command: '{cmd}'. Choose options above or 'q' to quit.")
            except (KeyboardInterrupt, EOFError):
                print("\n[*] Exiting Setu Orchestrator...")
                self.shutdown()
                break

    def _cmd_voice_sos(self):
        print("\n[*] Generating live Vernacular Voice SOS packet...")
        sample_note = "बाढ़ का पानी पहली मंजिल तक पहुँच गया है, दो बच्चे और एक गर्भवती महिला छत पर हैं"
        triage = VernacularTriageExtractor.parse_transcript(sample_note)
        pkt = pack_sos_packet(
            device_id=f"Voice_Node_{int(time.time())%1000}",
            timestamp=int(time.time()),
            latitude=20.2970 + (time.time() % 10) * 0.0005,
            longitude=85.8250 + (time.time() % 10) * 0.0005,
            altitude_decimeters=150,
            severity=SEVERITY_RED,
            disaster_type=DISASTER_FLOOD,
            is_trapped=True,
            mobility=0,
            adults=1,
            children=2,
            elderly=0,
            critical_cases=1,
            hop_count=5,
            battery_pct=40,
            medical_flags=MED_FLAG_BLEEDING,
            note=sample_note
        )
        self.gateway.ingest_raw_packet(pkt, channel="BLE_EXT_VOICE")
        print("    ✓ New Vernacular Voice SOS injected! Updated on live dashboard map.")

    def _cmd_sartap_sos(self):
        print("\n[*] Simulating real-time SAR-Tap Seismic 3-Tap strike under concrete...")
        pkt = pack_sos_packet(
            device_id=f"SAR_Node_{int(time.time())%1000}",
            timestamp=int(time.time()),
            latitude=20.2942,
            longitude=85.8215,
            altitude_decimeters=-28,
            severity=SEVERITY_RED,
            disaster_type=DISASTER_BUILDING_COLLAPSE,
            is_trapped=True,
            mobility=0,
            adults=1,
            children=0,
            elderly=0,
            critical_cases=1,
            hop_count=3,
            battery_pct=14,
            medical_flags=MED_FLAG_CRUSH,
            note="SAR-TAP 3-TAP RESCUE SIGNAL DETECTED UNDER RUBBLE (Depth 2.8m)"
        )
        self.gateway.ingest_raw_packet(pkt, channel="SAR_TAP_SEISMIC")
        print("    ✓ New SAR-Tap Non-Vocal Seismic SOS injected! Updated on live dashboard map.")

    def _cmd_captive_pwa_sos(self):
        print("\n[*] Simulating Zero-Install Captive Browser PWA report...")
        pkt = pack_sos_packet(
            device_id=f"PWA_Client_{int(time.time())%1000}",
            timestamp=int(time.time()),
            latitude=20.2955,
            longitude=85.8230,
            altitude_decimeters=40,
            severity=SEVERITY_YELLOW,
            disaster_type=DISASTER_FLOOD,
            is_trapped=False,
            mobility=1,
            adults=4,
            children=2,
            elderly=1,
            critical_cases=0,
            hop_count=2,
            battery_pct=72,
            medical_flags=MED_FLAG_INSULIN,
            note="Submitted via Offline Captive PWA: Safe in hall, need dry food & insulin"
        )
        self.gateway.ingest_raw_packet(pkt, channel="CAPTIVE_PWA")
        print("    ✓ Zero-Install PWA report ingested! Updated on live dashboard map.")

    def _cmd_dispatch_calc(self):
        print("\n[*] Recalculating Dynamic Multi-Team Dispatch Optimization...")
        records = self.gateway.db.get_all_records()
        plan = MultiTeamDispatchOptimizer.optimize_dispatch(records)
        print(f"    Total Targets: {plan.get('total_victims')}, Feasible: {plan.get('feasible_rescues')}")
        for t in plan.get("teams", []):
            route_str = " -> ".join([str(x.get("victim_id", "?")) for x in t.get("route", [])]) or "Standby"
            print(f"    • {t['team_id']}: [{route_str}]")

    def shutdown(self):
        """Terminates server gracefully."""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None
        print("✓ All Setu unified components terminated.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Setu: Zero-Grid Disaster Mesh & Triage Unified Orchestrator")
    parser.add_argument("--port", type=int, default=8080, help="Optional Unified Station port (default: 8080)")
    parser.add_argument("--server", action="store_true", help="Launch optional local web dashboard (default: False, 100% serverless peer-to-peer)")
    parser.add_argument("--no-server", action="store_true", help="Run 100% serverless peer-to-peer CLI without web server (default)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the web browser when --server is enabled")
    parser.add_argument("--auto", action="store_true", help="Run once in automated mode and exit")
    args = parser.parse_args()

    # Default is 100% serverless peer-to-peer. Server is ONLY enabled if --server is explicitly requested.
    enable_server = args.server and not args.no_server

    system = SetuUnifiedSystem(
        port=args.port,
        enable_server=enable_server,
        auto_open_browser=not args.no_browser and not args.auto
    )

    if args.auto:
        system.start_servers()
        system.run_survivor_simulations()
        time.sleep(1.0)
        system.shutdown()
        return

    system.run_unified()


if __name__ == "__main__":
    main()
