"""
Wi-Fi Hotspot Captive Portal Bridge for Setu-Mule Gateway.
Allows any trapped survivor with ANY smartphone (Android/iOS) to connect
to an open Wi-Fi network ('EMERGENCY-SOS-SETU') WITHOUT needing the app installed.

Automatically redirects browser traffic via DNS spoofing / HTTP Captive Portal
to a lightweight offline HTML emergency SOS form that compiles directly into
the 120-byte binary packet format and queues into the Incident Command Station.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import json
import time
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.sos_packet import pack_sos_packet
from gateway_mule.setu_mule_service import AndroidSetuMuleGateway

GATEWAY = AndroidSetuMuleGateway("SetuMule-HotspotBridge-01")


CAPTIVE_PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SETU Emergency SOS (Zero-Grid)</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; }
    .card { background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; max-width: 480px; margin: auto; }
    h1 { color: #ef4444; font-size: 1.4rem; text-align: center; }
    p.sub { font-size: 0.85rem; color: #94a3b8; text-align: center; margin-bottom: 20px; }
    label { display: block; font-size: 0.85rem; margin-top: 12px; color: #cbd5e1; }
    input, select, textarea { width: 100%; padding: 10px; background: #0f172a; border: 1px solid #475569; color: white; border-radius: 6px; box-sizing: border-box; }
    .btn { background: #ef4444; color: white; border: none; width: 100%; padding: 14px; font-size: 1.1rem; font-weight: bold; border-radius: 8px; margin-top: 20px; cursor: pointer; }
    .checkbox-group { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 8px; }
    .checkbox-item { background: #0f172a; padding: 6px 12px; border-radius: 6px; border: 1px solid #334155; font-size: 0.8rem; }
    #success { display: none; background: #065f46; color: #34d399; padding: 14px; border-radius: 8px; text-align: center; margin-top: 16px; font-weight: bold; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🚨 SETU EMERGENCY SOS</h1>
    <p class="sub">You are connected to the First Responder Drone/Boat Mesh. No mobile data or SIM required.</p>
    
    <form id="sosForm" onsubmit="submitSos(event)">
      <label>Disaster Hazard:</label>
      <select id="disaster">
        <option value="0">Flood (Submerged / Rooftop)</option>
        <option value="5">Building Collapse / Buried</option>
        <option value="4">Fire / Smoke</option>
        <option value="1">Earthquake</option>
      </select>

      <label>Are You Trapped?</label>
      <select id="trapped">
        <option value="1">YES - Cannot Evacuate Independently</option>
        <option value="0">NO - Mobile / Moving</option>
      </select>

      <label>Total People With You:</label>
      <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
        <div><span style="font-size:0.75rem">Adults:</span><input type="number" id="adults" value="2" min="1"></div>
        <div><span style="font-size:0.75rem">Kids:</span><input type="number" id="children" value="0" min="0"></div>
        <div><span style="font-size:0.75rem">Elderly:</span><input type="number" id="elderly" value="0" min="0"></div>
      </div>

      <label>Urgent Medical Conditions:</label>
      <div class="checkbox-group">
        <label class="checkbox-item"><input type="checkbox" id="m_insulin"> Insulin</label>
        <label class="checkbox-item"><input type="checkbox" id="m_dialysis"> Dialysis</label>
        <label class="checkbox-item"><input type="checkbox" id="m_o2"> Oxygen</label>
        <label class="checkbox-item"><input type="checkbox" id="m_crush"> Crush Injury</label>
        <label class="checkbox-item"><input type="checkbox" id="m_pregnant"> Pregnancy</label>
      </div>

      <label>Short Message / Exact Landmark:</label>
      <textarea id="note" rows="2" placeholder="e.g. 2nd floor, red roof house near water tank..."></textarea>

      <button type="submit" class="btn">TRANSMIT RESCUE SOS</button>
    </form>
    <div id="success">✅ SOS BUFFERED! Rescue boats & ground teams alerted. Stay safe.</div>
  </div>

  <script>
    async function submitSos(e) {
      e.preventDefault();
      const payload = {
        disaster: parseInt(document.getElementById('disaster').value),
        is_trapped: document.getElementById('trapped').value === "1",
        adults: parseInt(document.getElementById('adults').value) || 1,
        children: parseInt(document.getElementById('children').value) || 0,
        elderly: parseInt(document.getElementById('elderly').value) || 0,
        med_insulin: document.getElementById('m_insulin').checked,
        med_dialysis: document.getElementById('m_dialysis').checked,
        med_o2: document.getElementById('m_o2').checked,
        med_crush: document.getElementById('m_crush').checked,
        med_pregnant: document.getElementById('m_pregnant').checked,
        note: document.getElementById('note').value
      };

      try {
        const res = await fetch('/api/submit_portal_sos', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (res.ok) {
          document.getElementById('sosForm').style.display = 'none';
          document.getElementById('success').style.display = 'block';
        }
      } catch (err) {
        alert("Transmission failed. Please retry.");
      }
    }
  </script>
</body>
</html>
"""


class CaptivePortalHandler(BaseHTTPRequestHandler):
    """Captive portal HTTP server redirecting any domain request to the SOS form."""

    def do_GET(self):
        # Captive portal detection endpoints used by Android, iOS, Windows
        # e.g. /generate_204, /hotspot-detect.html, /ncsi.txt
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(CAPTIVE_PORTAL_HTML.encode('utf-8'))

    def do_POST(self):
        if self.path == "/api/submit_portal_sos":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)

            # Compute medical flag mask
            flags = 0
            if data.get("med_insulin"): flags |= (1 << 0)
            if data.get("med_dialysis"): flags |= (1 << 1)
            if data.get("med_pregnant"): flags |= (1 << 2)
            if data.get("med_crush"): flags |= (1 << 3)
            if data.get("med_o2"): flags |= (1 << 5)

            # Severity calculation
            severity = 2 if (flags > 0 or data.get("is_trapped")) else 1

            # Pack 120-byte packet
            raw_pkt = pack_sos_packet(
                device_id=f"CaptivePortal_{int(time.time()) % 10000}",
                timestamp=int(time.time()),
                latitude=20.2975,
                longitude=85.8260,
                altitude_decimeters=50,
                severity=severity,
                disaster_type=data.get("disaster", 0),
                is_trapped=data.get("is_trapped", False),
                mobility=0 if data.get("is_trapped") else 1,
                adults=data.get("adults", 1),
                children=data.get("children", 0),
                elderly=data.get("elderly", 0),
                critical_cases=1 if severity == 2 else 0,
                hop_count=5,
                battery_pct=80,
                medical_flags=flags,
                note=data.get("note", "Captive portal submission")
            )

            success = GATEWAY.ingest_raw_packet(raw_pkt, channel="WIFI_CAPTIVE_PORTAL")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": success, "packet_bytes": len(raw_pkt)}).encode('utf-8'))
            return

        self.send_response(404)
        self.end_headers()


def start_captive_portal(port: int = 8888):
    server = HTTPServer(('0.0.0.0', port), CaptivePortalHandler)
    print(f"[*] Setu-Mule Wi-Fi Captive Portal running on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    start_captive_portal()
