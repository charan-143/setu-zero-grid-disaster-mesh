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

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
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

        self.send_response(404)
        self.end_headers()


def start_server(port: int = 8080):
    server = HTTPServer(('0.0.0.0', port), TacticalDashboardHandler)
    print(f"[IncidentCommand] Tactical Situational Dashboard online at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    start_server()
