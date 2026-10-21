"""
Tactical Incident Command Web Server & Safe-Path Routing Engine
Hosts the Incident Command Dashboard, ingest packets from Mule devices,
and computes flood-safe evacuation/rescue paths prioritizing high-risk clusters.
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import urllib.parse
import os
import sys
import time
import math

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.sos_packet import unpack_sos_packet
from core.vitality_decay_engine import VitalityDecayEngine, MultiTeamDispatchOptimizer
from gateway_mule.setu_mule_service import AndroidSetuMuleGateway

GATEWAY = AndroidSetuMuleGateway("SetuMule-Alpha-HQ")


class TacticalDashboardHandler(SimpleHTTPRequestHandler):
    """Handles static web requests and REST API endpoints for the dashboard."""

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/generate_204", "/hotspot-detect.html", "/ncsi.txt", "/connecttest.txt", "/pwa", "/sos"):
            from gateway_mule.captive_portal_server import CAPTIVE_PORTAL_HTML
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(CAPTIVE_PORTAL_HTML.encode('utf-8'))))
            self.end_headers()
            return
        super().do_HEAD()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        # Unified Zero-Install Micro-PWA and Captive Portal routes
        if parsed.path in ("/pwa", "/sos", "/captive", "/generate_204", "/hotspot-detect.html", "/ncsi.txt", "/connecttest.txt"):
            from gateway_mule.captive_portal_server import CAPTIVE_PORTAL_HTML
            body_bytes = CAPTIVE_PORTAL_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)
            return

        if parsed.path == "/api/v1/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            records = GATEWAY.db.get_all_records()
            status_payload = {
                "status": "online",
                "gateway_device": GATEWAY.device_name,
                "connected_victims_count": len(records),
                "spooled_packets_count": len(records),
                "gateway_telemetry": {
                    "device_name": GATEWAY.device_name,
                    "mode": "UNIFIED_ZERO_GRID",
                    "battery_pct": 95,
                    "is_gateway": True
                }
            }
            self.wfile.write(json.dumps(status_payload).encode('utf-8'))
            return

        if parsed.path == "/api/v1/vitality_forecast":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            records = GATEWAY.db.get_all_records()
            assessed = VitalityDecayEngine.rank_victims(records)
            dispatch_rec = MultiTeamDispatchOptimizer.optimize_dispatch(records)
            forecast_summary = {
                "critical_window": sum(1 for v in assessed if v["survival_state"] == "CRITICAL_WINDOW"),
                "extreme_imminent_collapse": sum(1 for v in assessed if v["survival_state"] == "EXTREME_IMMINENT_COLLAPSE"),
                "degrading": sum(1 for v in assessed if v["survival_state"] == "DEGRADING"),
                "stable": sum(1 for v in assessed if v["survival_state"] == "STABLE"),
                "expectant": sum(1 for v in assessed if v["survival_state"] == "EXPECTANT"),
            }
            payload = {
                "timestamp": int(time.time()),
                "total_victims": len(assessed),
                "forecast": assessed,
                "summary": forecast_summary,
                "dispatch_recommendation": dispatch_rec
            }
            self.wfile.write(json.dumps(payload).encode('utf-8'))
            return
        elif parsed.path == "/api/v1/victims":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            records = GATEWAY.db.get_all_records()
            assessed = VitalityDecayEngine.rank_victims(records)
            self.wfile.write(json.dumps({"total": len(assessed), "victims": assessed}).encode('utf-8'))
            return
        elif parsed.path == "/api/triage/packets":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            data = GATEWAY.export_dashboard_payload()
            # Enrich cached packets with real-time vitality assessment
            if "packets" in data and data["packets"]:
                data["packets"] = VitalityDecayEngine.rank_victims(data["packets"])
            self.wfile.write(json.dumps(data).encode('utf-8'))
            return
        elif parsed.path == "/api/triage/summary":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            records = GATEWAY.db.get_all_records()
            assessed = VitalityDecayEngine.rank_victims(records)
            summary = {
                "total_alerts": len(records),
                "red_critical": sum(1 for r in records if r["severity"] == 2),
                "yellow_delayed": sum(1 for r in records if r["severity"] == 1),
                "green_minor": sum(1 for r in records if r["severity"] == 0),
                "black_expectant": sum(1 for r in records if r["severity"] == 3),
                "total_headcount": sum(r["total_headcount"] for r in records),
                "trapped_count": sum(1 for r in records if r["is_trapped"] == 1),
                "extreme_collapse_count": sum(1 for r in assessed if r["survival_state"] == "EXTREME_IMMINENT_COLLAPSE"),
                "critical_window_count": sum(1 for r in assessed if r["survival_state"] == "CRITICAL_WINDOW")
            }
            self.wfile.write(json.dumps(summary).encode('utf-8'))
            return
        elif parsed.path == "/api/triage/mission_plan":
            from dashboard.safe_path_router import SafePathRouter
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            records = GATEWAY.db.get_all_records()
            # Reference base camp at (20.2900, 85.8200)
            plan = SafePathRouter.generate_rescue_mission_plan(20.2900, 85.8200, records)
            self.wfile.write(json.dumps({"mission_plan": plan}).encode('utf-8'))
            return
        elif parsed.path == "/api/dem/flood_contours":
            from dashboard.dem_raster_engine import OfflineDemRaster
            query_params = urllib.parse.parse_qs(parsed.query)
            water_level = float(query_params.get("water_level", [24.0])[0])
            dem = OfflineDemRaster()
            contours = dem.compute_flood_inundation_contours(water_level_m=water_level)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "water_level_m": water_level,
                "inundation_cells": len(contours),
                "contours": contours,
                "metadata": dem.export_dem_metadata()
            }).encode('utf-8'))
            return
        elif parsed.path.startswith("/api/mbtiles/"):
            from dashboard.mbtiles_server import LocalMbTilesServer
            # Format: /api/mbtiles/{z}/{x}/{y}.png
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 4:
                try:
                    z = int(parts[2])
                    x = int(parts[3])
                    y = int(parts[4].split(".")[0])
                    mbtiles = LocalMbTilesServer()
                    tile_bytes = mbtiles.get_tile(z, x, y)
                    if tile_bytes:
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.end_headers()
                        self.wfile.write(tile_bytes)
                        return
                except Exception:
                    pass
            self.send_response(204) # No tile, fallback to Leaflet fallback
            self.end_headers()
            return
        
        # Serve dashboard frontend files
        dashboard_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
        if parsed.path == "/" or parsed.path == "/index.html":
            file_to_serve = os.path.join(dashboard_dir, "index.html")
        else:
            file_to_serve = os.path.join(dashboard_dir, parsed.path.lstrip("/"))

        if os.path.exists(file_to_serve) and os.path.isfile(file_to_serve):
            self.send_response(200)
            if file_to_serve.endswith(".html"):
                self.send_header("Content-Type", "text/html")
            elif file_to_serve.endswith(".js"):
                self.send_header("Content-Type", "application/javascript")
            elif file_to_serve.endswith(".css"):
                self.send_header("Content-Type", "text/css")
            self.end_headers()
            with open(file_to_serve, "rb") as f:
                self.wfile.write(f.read())
            return

        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/v1/dispatch_optimize":
            content_length = int(self.headers.get('Content-Length', 0))
            body_data = {}
            if content_length > 0:
                try:
                    raw_body = self.rfile.read(content_length).decode('utf-8')
                    body_data = json.loads(raw_body) if raw_body.strip() else {}
                except Exception as e:
                    print(f"[DashboardServer] JSON decode error in dispatch_optimize: {e}")

            rescue_teams = body_data.get("rescue_teams")
            victims = body_data.get("victims")
            if victims is None:
                victims = GATEWAY.db.get_all_records()

            result = MultiTeamDispatchOptimizer.optimize_dispatch(
                victims=victims,
                rescue_teams=rescue_teams
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode('utf-8'))
            return
        elif parsed.path == "/api/triage/ingest_binary":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_data = self.rfile.read(content_length)

            if len(raw_data) == 120:
                success = GATEWAY.ingest_raw_packet(raw_data, channel="REST_INGEST")
                vitality_assessment = None
                if success:
                    try:
                        unpacked = unpack_sos_packet(raw_data)
                        vitality_assessment = VitalityDecayEngine.assess_victim(unpacked)
                    except Exception as err:
                        print(f"[DashboardServer] Error computing vitality assessment for packet: {err}")
                self.send_response(200 if success else 400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                resp = {"success": success}
                if vitality_assessment:
                    resp["vitality_assessment"] = vitality_assessment
                self.wfile.write(json.dumps(resp).encode('utf-8'))
            else:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Invalid packet size {len(raw_data)}, expected 120"}).encode('utf-8'))
            return
        elif parsed.path == "/api/v1/captive_sos":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_data = self.rfile.read(content_length).decode('utf-8')
            try:
                from gateway_mule.captive_portal_server import (
                    _safe_int, _safe_float, _safe_bool,
                    MED_FLAG_INSULIN, MED_FLAG_DIALYSIS, MED_FLAG_PREGNANCY,
                    MED_FLAG_CRUSH, MED_FLAG_SNAKEBITE, MED_FLAG_O2_NEEDED,
                    MED_FLAG_BLEEDING, MED_FLAG_FRACTURE,
                    SEVERITY_RED, SEVERITY_YELLOW, SEVERITY_GREEN,
                    DISASTER_FLOOD, OfflineEmergencyRAG, pack_sos_packet, unpack_sos_packet
                )
                data = json.loads(raw_data) if raw_data.strip() else {}
                flags = 0
                if _safe_bool(data.get("insulin")) or _safe_bool(data.get("med_insulin")): flags |= MED_FLAG_INSULIN
                if _safe_bool(data.get("dialysis")) or _safe_bool(data.get("med_dialysis")): flags |= MED_FLAG_DIALYSIS
                if _safe_bool(data.get("bleeding")) or _safe_bool(data.get("med_bleeding")): flags |= MED_FLAG_BLEEDING
                if _safe_bool(data.get("crush")) or _safe_bool(data.get("med_crush")): flags |= MED_FLAG_CRUSH
                if _safe_bool(data.get("fracture")) or _safe_bool(data.get("med_fracture")): flags |= MED_FLAG_FRACTURE
                if _safe_bool(data.get("pregnancy")) or _safe_bool(data.get("med_pregnant")): flags |= MED_FLAG_PREGNANCY
                if _safe_bool(data.get("o2")) or _safe_bool(data.get("med_o2")): flags |= MED_FLAG_O2_NEEDED
                if _safe_bool(data.get("snakebite")) or _safe_bool(data.get("med_snakebite")): flags |= MED_FLAG_SNAKEBITE

                adults = _safe_int(data.get("adults"), default=1, min_val=0, max_val=15)
                children = _safe_int(data.get("children"), default=0, min_val=0, max_val=15)
                elderly = _safe_int(data.get("elderly"), default=0, min_val=0, max_val=15)
                critical_cases = _safe_int(data.get("critical_cases"), default=0, min_val=0, max_val=15)
                is_trapped = _safe_bool(data.get("is_trapped"), default=False)

                if "severity" in data:
                    severity = _safe_int(data["severity"], default=SEVERITY_YELLOW, min_val=0, max_val=3)
                else:
                    urgent_flags = MED_FLAG_BLEEDING | MED_FLAG_CRUSH | MED_FLAG_DIALYSIS | MED_FLAG_INSULIN
                    if is_trapped or (flags & urgent_flags) != 0 or critical_cases > 0:
                        severity = SEVERITY_RED
                    elif (flags & (MED_FLAG_FRACTURE | MED_FLAG_PREGNANCY | MED_FLAG_O2_NEEDED)) != 0 or elderly > 0:
                        severity = SEVERITY_YELLOW
                    else:
                        severity = SEVERITY_GREEN

                note = str(data.get("note") or data.get("location_notes") or "Captive portal SOS")
                disaster_type = _safe_int(data.get("disaster_type", DISASTER_FLOOD), default=DISASTER_FLOOD, min_val=0, max_val=6)
                lat = _safe_float(data.get("latitude"), default=20.2975, min_val=-90.0, max_val=90.0)
                lon = _safe_float(data.get("longitude"), default=85.8260, min_val=-180.0, max_val=180.0)
                alt_dm = _safe_int(data.get("altitude_decimeters"), default=0, min_val=-32768, max_val=32767)
                batt_pct = _safe_int(data.get("battery_pct"), default=85, min_val=0, max_val=100)
                device_id = str(data.get("device_id") or f"CP_{int(time.time()*1000)%1000000:06d}")

                raw_pkt = pack_sos_packet(
                    device_id=device_id, timestamp=int(time.time()),
                    latitude=lat, longitude=lon, altitude_decimeters=alt_dm,
                    severity=severity, disaster_type=disaster_type, is_trapped=is_trapped,
                    mobility=0 if is_trapped else 1, adults=adults, children=children,
                    elderly=elderly, critical_cases=critical_cases, hop_count=5,
                    battery_pct=batt_pct, medical_flags=flags, note=note
                )
                GATEWAY.ingest_raw_packet(raw_pkt, channel="HOTSPOT_CAPTIVE_PORTAL")

                unpacked = unpack_sos_packet(raw_pkt)
                rag = OfflineEmergencyRAG()
                guidance_text = rag.get_relief_response(note or unpacked["disaster_label"], lang="en")

                resp_payload = {
                    "success": True,
                    "packet_hash": f"{unpacked['device_hash']}_{unpacked['timestamp']}",
                    "severity": unpacked["severity_label"],
                    "first_aid_guidance": guidance_text,
                    "triage_summary": f"Triage Priority: {unpacked['severity_label']} | Headcount: {adults+children+elderly}"
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(resp_payload).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            return

        self.send_response(404)
        self.end_headers()


def start_server(port: int = 8080):
    server = HTTPServer(('0.0.0.0', port), TacticalDashboardHandler)
    print(f"[IncidentCommand] Tactical Situational Dashboard online at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    start_server()
