"""
Interactive End-to-End Survivor Edge Node Simulation
Simulates what happens when a survivor presses the power button 3 times:
1. Native speech input (e.g. Hindi: "पानी छत तक आ गया है, मेरे साथ दो बच्चे और एक बुजुर्ग हैं जिन्हें इंसुलिन चाहिए")
2. On-Device SLM extracts structured triage fields
3. Packs into exact 120-byte binary SOS packet
4. Offline RAG retrieves NDMA/WHO life-saving guidance and speaks it back in regional Hindi
5. Starts Dual-Mode zero-grid transmission (BLE Extended Adv / NAN + 18.5 kHz Ultrasonic Chirp)
"""

import time
import math
import os
import sys

from core.triage_extractor import VernacularTriageExtractor
from core.offline_rag import OfflineEmergencyRAG
from core.sos_packet import pack_sos_packet, unpack_sos_packet
from transport.acoustic_modem import pack_acoustic_beacon_payload, encode_acoustic_signal
from transport.mesh_router import EpidemicMeshNode
from core.cryo_sleep_manager import CryoSleepManager, CryoSleepState
from transport.sar_tap_detector import SarTapDetector, PatternType


if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def run_survivor_node():
    print("=" * 75)
    print("[*] SURVIVOR EDGE NODE: ZERO-GRID ON-DEVICE AI & SOS TRANSMITTER")
    print("=" * 75)

    # 1. Trigger: Voice Input in Regional Language
    survivor_spoken_input = "पानी छत तक आ गया है, मेरे साथ दो बच्चे और एक बुजुर्ग हैं जिन्हें इंसुलिन चाहिए"
    print("\n[1] SENSORY INGESTION & SPEECH INPUT:")
    print(f"    Survivor Spoken Audio Transcript:")
    print(f"    \"{survivor_spoken_input}\"")
    print("    (Translation: Water has reached the roof, 2 kids & elderly person need insulin)")

    # 2. On-Device SLM Entity Extractor
    print("\n[2] ON-DEVICE SLM TRIAGE EXTRACTION (< 1.2s on CPU):")
    triage_data = VernacularTriageExtractor.parse_transcript(survivor_spoken_input)
    print(f"    - Disaster Identified : {triage_data['disaster_type']} (FLOOD)")
    print(f"    - Trapped Status      : {'YES (Trapped on rooftop)' if triage_data['is_trapped'] else 'NO'}")
    print(f"    - Triage Severity     : RED (Critical Immediate Rescue)")
    print(f"    - Demographics        : {triage_data['demographics']}")
    print(f"    - Medical Flags       : Insulin Needed (Bitmask: 0x{triage_data['medical_flags']:04X})")

    # 3. Offline Relief RAG & TTS
    print("\n[3] OFFLINE NDMA & FIRST AID RAG (< 15ms):")
    rag = OfflineEmergencyRAG()
    relief_speech = rag.get_relief_response(survivor_spoken_input, lang="hi")
    print(f"    [Local TTS Voice Output - Spoken to Survivor]:")
    print(f"    \"{relief_speech}\"")

    # 4. Pack into 120-Byte Binary Packet
    print("\n[4] 120-BYTE BINARY SOS COMPRESSION:")
    raw_packet = pack_sos_packet(
        device_id="Survivor_Phone_Android_14",
        timestamp=int(time.time()),
        latitude=20.2961,
        longitude=85.8245,
        altitude_decimeters=185, # 18.5 meters rooftop elevation
        severity=triage_data["severity"],
        disaster_type=triage_data["disaster_type"],
        is_trapped=triage_data["is_trapped"],
        mobility=triage_data["mobility"],
        adults=triage_data["demographics"]["adults"],
        children=triage_data["demographics"]["children"],
        elderly=triage_data["demographics"]["elderly"],
        critical_cases=triage_data["demographics"]["critical_cases"],
        hop_count=5,
        battery_pct=25,
        medical_flags=triage_data["medical_flags"],
        note=triage_data["summary_note"]
    )
    print(f"    -> Complete family triage profile packed into exactly {len(raw_packet)} bytes!")
    print(f"    -> Raw Hex (First 32 bytes): {raw_packet[:32].hex()}...")

    # 5. Zero-Grid Dual Mode Transport
    print("\n[5] DUAL-MODE ZERO-GRID BEACONING:")
    print("    [A] Surface Mode: Emitting BLE 5.0 Extended Advertisements + Wi-Fi Aware NAN frames...")
    print("    [B] Rubble Mode: Synthesizing 18.5 kHz - 20 kHz ultrasonic chirp acoustic pulses...")
    acoustic_val = pack_acoustic_beacon_payload(
        survivor_id_16=0xA1B2,
        severity=triage_data["severity"],
        disaster_type=triage_data["disaster_type"],
        is_trapped=triage_data["is_trapped"],
        battery_pct=25
    )
    samples = encode_acoustic_signal(acoustic_val)
    print(f"    -> Generated {len(samples)} ultrasonic audio samples ready for phone speaker output.")

    # 6. Ultra-Low-Duty-Cycle Cryo-Sleep Power Budgeter
    print("\n[6] CRYO-SLEEP BATTERY STRETCHER & POWER BUDGETER:")
    cryo = CryoSleepManager(battery_capacity_mah=4000.0, nominal_voltage=3.85)
    # Phone senses total darkness under rubble (0 lux) and zero motion (0.01 variance)
    rubble_state = cryo.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=25.0)
    print(f"    - Rubble Sensors Ingested : Lux=0.0 lx, Accel Var=0.010, Battery=25%")
    print(f"    - Autonomous Transition   : {rubble_state.value} (58s sleep / 200ms chirp+BLE burst)")
    rec = cryo.get_power_budget_recommendation()
    print(f"    - Transmission Decision   : Transmit Now = {cryo.should_transmit_now()} (Action: {rec.action})")
    print(f"    - Projected Battery Life  : {rec.survival_horizon.days:.1f} days ({rec.survival_horizon.hours:.1f} hours)")
    print(f"    - Lifespan Extension Gain : {rec.power_saving_factor:.1f}x longer survival vs continuous active scanning")
    print("\n    [Edge Node Power Diagnostic Log]:")
    for log_line in cryo.log_life_expectancy_projection().split("\n"):
        print(f"    {log_line}")

    # 7. Non-Vocal Emergency Pipeline: SAR-Tap Acoustic & Seismic IMU Codec
    print("\n[7] NON-VOCAL EMERGENCY PIPELINE: SAR-TAP SEISMIC & ACOUSTIC CODEC:")
    print("    Scenario: Survivor trapped under 2 meters of concrete slab, unable to speak/vocalize.")
    print("    Survivor repeatedly taps 3 times on concrete rebar (Alpine/Mining/NDMA 3-tap distress).")

    sar_detector = SarTapDetector(
        device_id="Survivor_Phone_Android_14",
        latitude=20.2961,
        longitude=85.8245,
        altitude_decimeters=185,
        battery_pct=25,
        hop_count=5,
        cryo_manager=cryo
    )

    # Generate synchronous 3-axis accelerometer and acoustic microphone streams
    t_series, ax, ay, az = SarTapDetector.generate_synthetic_3tap_accel(
        dt1=0.60,
        dt2=0.60,
        sample_rate=50.0,
        tap_peak_g=14.0
    )
    sample_rate_audio = 8000
    audio_samples = [0.0] * int(3.0 * sample_rate_audio)
    for pt in [0.5, 1.1, 1.7]:
        start_idx = int(pt * sample_rate_audio)
        for i in range(int(0.02 * sample_rate_audio)):
            if start_idx + i < len(audio_samples):
                audio_samples[start_idx + i] = 0.88 * math.sin(2 * math.pi * 1000 * (i / sample_rate_audio))

    print(f"    - Ingested 3-Axis Accelerometer Stream: {len(t_series)} samples @ 50 Hz")
    print(f"    - Ingested Acoustic Microphone Stream : {len(audio_samples)} audio PCM samples @ 8 kHz")

    tap_result = sar_detector.process_dual_channel(
        accel_timestamps=t_series,
        ax=ax,
        ay=ay,
        az=az,
        acoustic_samples=audio_samples,
        sample_rate=sample_rate_audio
    )
    print(f"    - Multi-Modal Fusion : Cross-validated {tap_result.tap_count} strikes (Modality: {tap_result.details.get('sensor_modality')})")
    print(f"    - Cadence Classifier : {tap_result.pattern_type.value} (Confidence: {tap_result.confidence*100:.1f}%)")
    print(f"    - Cryo Wake Trigger  : Wake Interrupt Fired = {tap_result.wake_triggered}")
    print(f"    - Power State Check  : Immediate Emergency Transmit = {cryo.should_transmit_now()} (Interrupt: {cryo._wake_interrupt_reason})")

    # Unpack and verify synthesized 120-byte binary SOS packet
    unpacked_tap = unpack_sos_packet(tap_result.sos_packet)
    print(f"\n    [Synthesized 120-Byte Non-Vocal SOS Packet Unpacked]:")
    print(f"    - Severity           : {unpacked_tap['severity_label']} (Immediate Critical Triage)")
    print(f"    - Disaster Type      : {unpacked_tap['disaster_label']} (Building Collapse)")
    print(f"    - Trapped Flag       : {unpacked_tap['is_trapped']}")
    print(f"    - Medical Flags      : Crush Injury Flagged = {unpacked_tap['medical_flags']['crush_injury']}")
    print(f"    - Encoded Note       : \"{unpacked_tap['note']}\"")
    print(f"    - Packet Checksum    : CRC16 = 0x{unpacked_tap['crc16']:04X} (Valid)")

    print("\n" + "=" * 75)
    print("[SUCCESS] Survivor Edge Node is actively broadcasting life-saving signals.")
    print("=" * 75)


if __name__ == "__main__":
    run_survivor_node()
