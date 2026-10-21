"""
Live Demonstration Script for the Zero-Cost Zero-Grid Disaster Mesh
Simulates:
1. Two survivor smartphones generating 120-byte binary SOS packets over BLE.
2. One survivor trapped under deep concrete rubble emitting an 18.5 - 20 kHz ultrasonic chirp.
3. An old/spare Android phone acting as the Setu-Mule Gateway sweeping BLE packets and detecting the acoustic chirp.
4. Mule Gateway delivering all verified data to the Incident Command Tactical Dashboard.
"""

import time
import os
import sys

from core.sos_packet import (
    pack_sos_packet,
    unpack_sos_packet,
    SEVERITY_RED,
    SEVERITY_YELLOW,
    DISASTER_FLOOD,
    DISASTER_BUILDING_COLLAPSE,
    MED_FLAG_INSULIN,
    MED_FLAG_CRUSH,
    MED_FLAG_O2_NEEDED
)
from transport.acoustic_modem import pack_acoustic_beacon_payload
from transport.acoustic_tdoa_triangulator import AcousticTDoATriangulator, ReceiverNode
from gateway_mule.setu_mule_service import AndroidSetuMuleGateway


def run_demo():
    print("=" * 70)
    print("[*] ZERO-COST ZERO-GRID DISASTER TRIAGE MESH DEMONSTRATION")
    print("=" * 70)

    # 1. Initialize Setu-Mule Android Gateway (Zero Hardware Cost)
    if os.path.exists("live_demo_mule.db"):
        try:
            os.remove("live_demo_mule.db")
        except Exception:
            pass

    mule = AndroidSetuMuleGateway(mule_device_name="Mule-Android-Relay-01", db_path="live_demo_mule.db")
    print(f"\n[+] Gateway Online: '{mule.device_name}' (Zero-Cost Android Gateway)")
    print("    [BLE 5.0 Scanner: ACTIVE | Acoustic Rubble Listener: 18.5-20 kHz ACTIVE]")

    # 2. Survivor 1: Flood - Family on rooftop with insulin requirement
    print("\n[+] Survivor 1 (Flood Zone - Rooftop):")
    survivor_1_pkt = pack_sos_packet(
        device_id="Survivor_Kedar_01",
        timestamp=int(time.time()),
        latitude=20.2961,
        longitude=85.8245,
        altitude_decimeters=180, # 18m rooftop
        severity=SEVERITY_RED,
        disaster_type=DISASTER_FLOOD,
        is_trapped=True,
        mobility=0,
        adults=2,
        children=2,
        elderly=1,
        critical_cases=1,
        hop_count=5,
        battery_pct=18, # 18% remaining battery!
        medical_flags=MED_FLAG_INSULIN,
        note="Water at roof level. Elderly grandfather needs insulin urgently."
    )
    print(f"    -> Emitted 120-byte binary SOS packet via BLE Extended Adv (Size: {len(survivor_1_pkt)}B)")
    mule.ingest_raw_packet(survivor_1_pkt, channel="BLE_5.0_EXT")

    # 3. Survivor 2: Flood - Submerged ground floor
    print("\n[+] Survivor 2 (Flood Zone - Ground Floor):")
    survivor_2_pkt = pack_sos_packet(
        device_id="Survivor_Kedar_02",
        timestamp=int(time.time()) - 120,
        latitude=20.2980,
        longitude=85.8270,
        altitude_decimeters=20, # 2m ground level
        severity=SEVERITY_YELLOW,
        disaster_type=DISASTER_FLOOD,
        is_trapped=False,
        mobility=1,
        adults=3,
        children=1,
        elderly=0,
        critical_cases=0,
        hop_count=4,
        battery_pct=55,
        medical_flags=0,
        note="Water 3 feet deep. Safe for now on tables, need boat evacuation."
    )
    print(f"    -> Emitted 120-byte binary SOS packet via Wi-Fi Aware NAN (Size: {len(survivor_2_pkt)}B)")
    mule.ingest_raw_packet(survivor_2_pkt, channel="WIFI_AWARE_NAN")

    # 4. Survivor 3: Buried under collapsed concrete structure (RF blocked, Ultrasonic Chirp used)
    print("\n[+] Survivor 3 (Deep Rubble - Concrete Slab):")
    print("    [!] RF (BLE/Wi-Fi) attenuated by 45 dB through reinforced concrete.")
    print("    -> Emitting 18.5 kHz - 20 kHz Chirp Spread Spectrum (CSS) acoustic beacon...")
    acoustic_payload = pack_acoustic_beacon_payload(
        survivor_id_16=0xC0DE,
        severity=SEVERITY_RED,
        disaster_type=DISASTER_BUILDING_COLLAPSE,
        is_trapped=True,
        battery_pct=12
    )

    # 5. Multi-Receiver Ultrasonic Acoustic TDoA - 3D Rubble Depth Triangulation (Module 5)
    print("\n[+] Module 5: Multi-Receiver Ultrasonic Acoustic TDoA - 3D Rubble Depth Triangulation:")
    print("    [!] Deploying 4 Ground Mule Phones across rubble surface for 3D sub-surface localization:")
    receivers = [
        ReceiverNode("Mule-01-North", (0.0, 0.0, 0.1)),
        ReceiverNode("Mule-02-East",  (4.5, 0.0, -0.1)),
        ReceiverNode("Mule-03-West",  (0.5, 4.0, 0.2)),
        ReceiverNode("Mule-04-South", (4.0, 3.5, 0.0))
    ]
    for r in receivers:
        print(f"        * {r.node_id:<14}: Surface Pos (X={r.position[0]:.1f}m, Y={r.position[1]:.1f}m, Z={r.position[2]:+.1f}m)")

    # Buried survivor ground truth: (x=2.0m, y=1.5m, z=-2.5m)
    survivor_true = (2.0, 1.5, -2.5)
    speed_of_sound = 343.0
    import math
    dists = [math.sqrt(sum((survivor_true[k] - r.position[k])**2 for k in range(3))) for r in receivers]
    tdoas = {}
    for i in range(1, len(receivers)):
        delay = (dists[i] - dists[0]) / speed_of_sound
        tdoas[(receivers[0].node_id, receivers[i].node_id)] = delay

    print("    -> Ingesting multi-channel ultrasonic chirps via GCC-PHAT cross-correlation...")
    triangulator = AcousticTDoATriangulator(speed_of_sound=speed_of_sound, sample_rate=44100)
    tdoa_result = triangulator.triangulate(receivers=receivers, tdoas=tdoas)

    print(f"    [+] 3D Sub-Surface Fix ACQUIRED:")
    print(f"        * Localized Relative Position : X={tdoa_result.estimated_position[0]:+.2f}m, Y={tdoa_result.estimated_position[1]:+.2f}m, Z={tdoa_result.estimated_position[2]:+.2f}m")
    print(f"        * Absolute Burial Depth       : {tdoa_result.burial_depth_meters:.2f} METERS BENEATH SLAB")
    print(f"        * TDoA Multilateration Conf   : {tdoa_result.confidence_score*100:.1f}% (Residual RMSE: {tdoa_result.residual_rmse*100:.2f} cm)")
    print(f"        * TACTICAL RESCUE ADVISORY    : \"{tdoa_result.excavation_advisory}\"")

    mule.ingest_acoustic_beacon(
        acoustic_payload,
        approx_lat=20.2940,
        approx_lon=85.8210,
        tdoa_result=tdoa_result
    )
    print("    -> Mule Gateway synthesized 120-byte SOS alert tagged with 3D burial depth & excavation advisory.")

    # 6. Incident Command Sync
    print("\n" + "=" * 70)
    print("[*] INCIDENT COMMAND DISPATCH QUEUE (Exported from Mule)")
    print("=" * 70)
    dashboard_payload = mule.export_dashboard_payload()
    for idx, alert in enumerate(dashboard_payload["packets"], 1):
        sev_color = "[RED-CRITICAL]" if alert["severity"] == 2 else ("[YELLOW-DELAYED]" if alert["severity"] == 1 else "[GREEN-MINOR]")
        print(f"\n{idx}. {sev_color} - {alert['disaster_label']}")
        print(f"   Coordinates: ({alert['latitude']:.4f}, {alert['longitude']:.4f}) | Altitude: {alert['altitude_m']}m")
        print(f"   Headcount: {alert['total_headcount']} | Battery: {alert['battery_pct']}% | Channel: {alert['source_channel']}")
        meds = [k.upper() for k, v in alert["medical_flags"].items() if v and k != "raw_flags"]
        if meds:
            print(f"   Medical Flags: {', '.join(meds)}")
        print(f"   Tactical Note: \"{alert['note']}\"")

    print("\n" + "=" * 70)
    print("[+] System Ready! Tactical Dashboard can be opened at http://localhost:8080")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()

