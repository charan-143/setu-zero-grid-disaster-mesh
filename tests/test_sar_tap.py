"""
Unit Tests for SAR-Tap Acoustic & Seismic IMU Codec
Zero-Grid Disaster Mesh & Triage System (Setu)
"""

import math
import struct
import unittest

from transport.sar_tap_detector import (
    SarTapDetector,
    PatternType,
    TapEvent,
    DetectionResult
)
from core.sos_packet import (
    unpack_sos_packet,
    SEVERITY_RED,
    DISASTER_BUILDING_COLLAPSE,
    MED_FLAG_CRUSH,
    PACKET_SIZE
)
from core.cryo_sleep_manager import CryoSleepManager, CryoSleepState


class TestSarTapDetector(unittest.TestCase):
    """Test suite for SAR-Tap seismic and acoustic transient detector."""

    def setUp(self):
        self.detector = SarTapDetector(
            device_id="TEST_PHONE_NODE_01",
            latitude=20.2961,
            longitude=85.8245,
            altitude_decimeters=150,
            battery_pct=45,
            hop_count=3
        )

    # -------------------------------------------------------------------------
    # 1. Three-Tap Distress Pattern Tests
    # -------------------------------------------------------------------------

    def test_canonical_three_tap_detection(self):
        """Tests standard 3-tap distress pattern (0.6s intervals)."""
        taps = [1.0, 1.6, 2.2]
        res = self.detector.classify_cadence(taps)
        self.assertEqual(res.pattern_type, PatternType.THREE_TAP_DISTRESS)
        self.assertTrue(res.is_emergency)
        self.assertGreater(res.confidence, 0.90)
        self.assertEqual(res.tap_count, 3)
        self.assertIsNotNone(res.sos_packet)

    def test_three_tap_with_human_jitter(self):
        """Tests 3-tap distress with natural human timing variance (within 50% tolerance)."""
        # Intervals: 0.65s and 0.50s (difference ratio: 0.15 / 0.65 = 23%)
        taps = [2.0, 2.65, 3.15]
        res = self.detector.classify_cadence(taps)
        self.assertEqual(res.pattern_type, PatternType.THREE_TAP_DISTRESS)
        self.assertTrue(res.is_emergency)
        self.assertGreater(res.confidence, 0.80)

    def test_three_tap_in_continuous_stream_with_silence(self):
        """Tests detecting 3-tap pattern embedded in a stream followed by silence."""
        # 3 taps isolated by >= 1.6s silence
        taps = [0.5, 2.5, 3.1, 3.7, 6.0]
        res = self.detector.classify_cadence(taps)
        self.assertEqual(res.pattern_type, PatternType.THREE_TAP_DISTRESS)
        self.assertEqual(len(res.tap_timestamps), 3)

    def test_synthetic_accelerometer_three_tap_pipeline(self):
        """Tests full end-to-end pipeline from 3-axis accelerometer data to cadence detection."""
        t, ax, ay, az = SarTapDetector.generate_synthetic_3tap_accel(
            dt1=0.6,
            dt2=0.6,
            sample_rate=50.0,
            tap_peak_g=15.0
        )
        res = self.detector.process_accelerometer_series(t, ax, ay, az)
        self.assertEqual(res.pattern_type, PatternType.THREE_TAP_DISTRESS)
        self.assertTrue(res.is_emergency)
        self.assertEqual(res.tap_count, 3)
        self.assertIsNotNone(res.sos_packet)

    def test_acoustic_audio_three_tap_pipeline(self):
        """Tests acoustic audio ingestion with 3 distinct transient audio pulses."""
        sample_rate = 8000
        total_duration = 3.0
        num_samples = int(total_duration * sample_rate)
        audio = [0.0] * num_samples

        # Insert 3 sharp transient sound bursts at t = 0.5s, 1.1s, 1.7s (dt = 0.6s)
        pulse_times = [0.5, 1.1, 1.7]
        for pt in pulse_times:
            start_idx = int(pt * sample_rate)
            pulse_len = int(0.02 * sample_rate)  # 20ms burst
            for i in range(pulse_len):
                if start_idx + i < num_samples:
                    audio[start_idx + i] = 0.85 * math.sin(2 * math.pi * 1000 * (i / sample_rate))

        res = self.detector.process_acoustic_series(audio, sample_rate=sample_rate)
        self.assertEqual(res.pattern_type, PatternType.THREE_TAP_DISTRESS)
        self.assertTrue(res.is_emergency)
        self.assertEqual(res.tap_count, 3)

    # -------------------------------------------------------------------------
    # 2. Morse SOS Pattern Tests
    # -------------------------------------------------------------------------

    def test_morse_sos_duration_based(self):
        """Tests standard Morse SOS (... --- ...) with 3 short, 3 long, 3 short pulses."""
        ts, durations = SarTapDetector.generate_synthetic_morse_sos_taps(
            unit_dot_s=0.20
        )
        res = self.detector.classify_cadence(ts, durations=durations)
        self.assertEqual(res.pattern_type, PatternType.MORSE_SOS)
        self.assertTrue(res.is_emergency)
        self.assertGreaterEqual(res.confidence, 0.90)
        self.assertEqual(res.details.get("mode"), "pulse_durations")
        self.assertIsNotNone(res.sos_packet)

    def test_morse_sos_with_human_duration_jitter(self):
        """Tests Morse SOS with human tempo variation in dot and dash lengths."""
        # Standard: dot ~ 0.2s, dash ~ 0.6s
        # With human jitter:
        durations = [
            0.18, 0.22, 0.19,  # S (...)
            0.58, 0.65, 0.62,  # O (---)
            0.21, 0.19, 0.20   # S (...)
        ]
        # Timestamps with appropriate spacing
        ts = [0.0]
        for d in durations[:-1]:
            ts.append(ts[-1] + d + 0.25)

        res = self.detector.classify_cadence(ts, durations=durations)
        self.assertEqual(res.pattern_type, PatternType.MORSE_SOS)
        self.assertTrue(res.is_emergency)

    def test_morse_sos_knock_intervals(self):
        """Tests knock-interval Morse SOS where impacts have 0 duration but timing intervals convey SOS."""
        # 9 taps: S (short intervals), O (longer intervals), S (short intervals)
        # S: 2 intervals of 0.25s
        # Gap S->O: 0.75s
        # O: 2 intervals of 0.75s
        # Gap O->S: 0.75s
        # S: 2 intervals of 0.25s
        intervals = [0.25, 0.25, 0.75, 0.75, 0.75, 0.75, 0.25, 0.25]
        ts = [1.0]
        for dt in intervals:
            ts.append(ts[-1] + dt)

        res = self.detector.classify_cadence(ts)
        self.assertEqual(res.pattern_type, PatternType.MORSE_SOS)
        self.assertTrue(res.is_emergency)
        self.assertEqual(res.details.get("mode"), "knock_intervals")

    # -------------------------------------------------------------------------
    # 3. Continuous Rhythmic Knocking Tests
    # -------------------------------------------------------------------------

    def test_continuous_rhythmic_knocking(self):
        """Tests periodic human knocking (6 taps at 0.5s intervals, 2 Hz)."""
        ts = SarTapDetector.generate_synthetic_rhythmic_taps(count=6, interval_s=0.50)
        res = self.detector.classify_cadence(ts)
        self.assertEqual(res.pattern_type, PatternType.CONTINUOUS_RHYTHMIC)
        self.assertTrue(res.is_emergency)
        self.assertEqual(res.tap_count, 6)
        self.assertEqual(res.details.get("tempo_bpm"), 120.0)

    def test_rhythmic_knocking_with_slight_tempo_variation(self):
        """Tests rhythmic knocking with slight natural human variation (CV <= 0.25)."""
        # Spacings: [0.60, 0.63, 0.58, 0.61, 0.59]
        ts = [0.0, 0.60, 1.23, 1.81, 2.42, 3.01]
        res = self.detector.classify_cadence(ts)
        self.assertEqual(res.pattern_type, PatternType.CONTINUOUS_RHYTHMIC)
        self.assertTrue(res.is_emergency)
        self.assertLessEqual(res.details.get("coefficient_of_variation"), 0.25)

    # -------------------------------------------------------------------------
    # 4. False Positive Immunity & Noise Floor Rejection
    # -------------------------------------------------------------------------

    def test_reject_single_accidental_tap(self):
        """Tests rejection of accidental single drop / impact."""
        taps = [1.5]
        res = self.detector.classify_cadence(taps)
        self.assertEqual(res.pattern_type, PatternType.NONE)
        self.assertFalse(res.is_emergency)
        self.assertIsNone(res.sos_packet)

    def test_reject_double_tap(self):
        """Tests rejection of 2 taps (insufficient for rescue confirmation)."""
        taps = [1.5, 2.1]
        res = self.detector.classify_cadence(taps)
        self.assertEqual(res.pattern_type, PatternType.NONE)
        self.assertFalse(res.is_emergency)

    def test_reject_random_debris_noise(self):
        """Tests rejection of sporadic non-periodic impacts (e.g. falling gravel / shifting rubble)."""
        # Highly irregular intervals: 0.15s, 1.80s, 0.40s, 2.90s
        taps = [0.10, 0.25, 2.05, 2.45, 5.35]
        res = self.detector.classify_cadence(taps)
        self.assertEqual(res.pattern_type, PatternType.NONE)
        self.assertFalse(res.is_emergency)

    def test_reject_continuous_earthquake_rumble(self):
        """Tests rejection of continuous aftershock ground oscillation (CFAR noise floor rejection)."""
        t, ax, ay, az = SarTapDetector.generate_synthetic_rumble_accel(
            duration_s=3.0,
            sample_rate=50.0,
            freq_hz=10.0,
            amp_g=3.0
        )
        res = self.detector.process_accelerometer_series(t, ax, ay, az)
        self.assertEqual(res.pattern_type, PatternType.NONE)
        self.assertFalse(res.is_emergency)
        self.assertIsNone(res.sos_packet)

    def test_reject_three_taps_outside_timing_limits(self):
        """Tests rejection of 3 taps that are too fast (< 0.3s) or too slow (> 1.5s)."""
        # Too fast (e.g. 0.1s mechanical chatter)
        fast_taps = [1.0, 1.1, 1.2]
        res_fast = self.detector.classify_cadence(fast_taps)
        self.assertEqual(res_fast.pattern_type, PatternType.NONE)

        # Too slow (e.g. 2.5s between taps)
        slow_taps = [1.0, 3.5, 6.0]
        res_slow = self.detector.classify_cadence(slow_taps)
        self.assertEqual(res_slow.pattern_type, PatternType.NONE)

    def test_reject_three_taps_with_erratic_intervals(self):
        """Tests rejection of 3 taps where intervals differ wildly (violating 50% tempo consistency)."""
        # dt1 = 0.35s, dt2 = 1.40s (diff ratio: 1.05 / 1.40 = 75% > 50%)
        erratic_taps = [1.0, 1.35, 2.75]
        res = self.detector.classify_cadence(erratic_taps)
        self.assertEqual(res.pattern_type, PatternType.NONE)

    def test_refractory_period_suppresses_bounce(self):
        """Tests that two spikes within refractory period (< 150ms) are de-duplicated into 1 tap."""
        timestamps = [0.0, 0.05, 0.60, 0.65, 1.20, 1.25]
        # High jerk spikes
        signal = [25.0, 22.0, 30.0, 28.0, 35.0, 31.0]
        taps = self.detector._cfar_peak_detector(
            timestamps=timestamps,
            signal=signal,
            min_threshold=5.0,
            channel="SEISMIC"
        )
        # 6 spikes should be filtered down to 3 taps
        self.assertEqual(len(taps), 3)

    # -------------------------------------------------------------------------
    # 5. SOS Packet Synthesis & Validation
    # -------------------------------------------------------------------------

    def test_sos_packet_binary_structure_and_unpack(self):
        """Verifies that generated 120-byte packet is compliant and unpackable."""
        taps = [1.0, 1.6, 2.2]
        res = self.detector.classify_cadence(taps, current_time=1700000000.0)
        packet = res.sos_packet

        self.assertIsNotNone(packet)
        self.assertEqual(len(packet), PACKET_SIZE)

        # Unpack using core.sos_packet
        unpacked = unpack_sos_packet(packet)
        self.assertEqual(unpacked["severity"], SEVERITY_RED)
        self.assertEqual(unpacked["severity_label"], "RED")
        self.assertTrue(unpacked["is_trapped"])
        self.assertEqual(unpacked["disaster_type"], DISASTER_BUILDING_COLLAPSE)
        self.assertEqual(unpacked["disaster_label"], "COLLAPSE")
        self.assertEqual(unpacked["medical_flags"]["raw_flags"], MED_FLAG_CRUSH)
        self.assertTrue(unpacked["medical_flags"]["crush_injury"])
        self.assertIn("SEISMIC/TAP DISTRESS", unpacked["note"])
        self.assertAlmostEqual(unpacked["latitude"], 20.2961, places=4)
        self.assertAlmostEqual(unpacked["longitude"], 85.8245, places=4)
        self.assertEqual(unpacked["battery_pct"], 40)  # Rounded to step in packet
        self.assertEqual(unpacked["hop_count"], 3)

    def test_sos_packet_crc16_integrity(self):
        """Tests that packet CRC16 is valid and any single-byte corruption fails unpack."""
        packet = self.detector.synthesize_sos_packet(
            pattern_type=PatternType.THREE_TAP_DISTRESS,
            timestamp=1700000000
        )
        # Valid packet unpacks
        unpacked = unpack_sos_packet(packet)
        self.assertIsNotNone(unpacked)

        # Corrupt one byte in payload
        corrupted = bytearray(packet)
        corrupted[15] ^= 0xFF
        with self.assertRaises(ValueError) as ctx:
            unpack_sos_packet(bytes(corrupted))
        self.assertIn("CRC16 mismatch", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 6. Integration with CryoSleepManager
    # -------------------------------------------------------------------------

    def test_cryo_sleep_wake_interrupt_triggered(self):
        """Verifies that CryoSleepManager immediately wakes from CRYO_DEEP_SLEEP on 3-tap distress."""
        now = 1000.0
        # 1. Initialize CryoSleepManager in deep sleep (buried in rubble) with synchronized clock
        cryo = CryoSleepManager(battery_capacity_mah=4000.0, clock_source=lambda: now)
        state = cryo.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=50.0, current_time=now)
        self.assertEqual(state, CryoSleepState.CRYO_DEEP_SLEEP)

        # 10s into deep sleep, phone should NOT transmit normally
        self.assertFalse(cryo.should_transmit_now(current_time=now + 10.0))

        # 2. Attach CryoSleepManager to detector
        self.detector.register_cryo_manager(cryo)

        # 3. Ingest 3-tap distress
        taps = [1.0, 1.6, 2.2]
        res = self.detector.classify_cadence(taps, current_time=now + 10.0)
        self.assertTrue(res.is_emergency)
        self.assertTrue(res.wake_triggered)

        # 4. Verify CryoSleepManager wake interrupt is active and transmission is immediately forced
        self.assertTrue(cryo._wake_interrupt_flag)
        self.assertEqual(cryo._wake_interrupt_reason, "SAR_TAP_THREE_TAP_DISTRESS")
        self.assertTrue(cryo.should_transmit_now(current_time=now + 10.0))

    def test_cryo_sleep_wake_interrupt_auto_expires(self):
        """Verifies that wake burst auto-expires after wake window so node resumes sleep."""
        now = 2000.0
        cryo = CryoSleepManager(clock_source=lambda: now)
        cryo.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=50.0, current_time=now)
        self.detector.register_cryo_manager(cryo)

        now = 2000.0
        taps = [1.0, 1.6, 2.2]
        self.detector.classify_cadence(taps, current_time=now)

        # Immediate wake burst is active (< 200ms)
        self.assertTrue(cryo.should_transmit_now(current_time=now + 0.05))

        # After wake burst duration (e.g. 500ms > 200ms burst), interrupt expires and phone sleeps
        self.assertFalse(cryo.should_transmit_now(current_time=now + 0.50))
        self.assertFalse(cryo._wake_interrupt_flag)

    # -------------------------------------------------------------------------
    # 7. Real-Time Streaming Ingestion Tests
    # -------------------------------------------------------------------------

    def test_streaming_accel_sample_pipeline(self):
        """Tests feeding individual samples one by one via add_accel_sample."""
        self.detector.reset_buffers()
        # Feed baseline silence
        for i in range(20):
            res = self.detector.add_accel_sample(t=i * 0.02, ax=0.0, ay=0.0, az=9.81)
            self.assertIsNone(res)

        # Strike 1 at t = 0.50s
        self.detector.add_accel_sample(t=0.50, ax=20.0, ay=15.0, az=12.0)
        self.detector.add_accel_sample(t=0.52, ax=0.0, ay=0.0, az=9.81)

        # Strike 2 at t = 1.10s (dt = 0.60s)
        self.detector.add_accel_sample(t=1.10, ax=22.0, ay=14.0, az=11.0)
        self.detector.add_accel_sample(t=1.12, ax=0.0, ay=0.0, az=9.81)

        # Strike 3 at t = 1.70s (dt = 0.60s)
        res3 = self.detector.add_accel_sample(t=1.70, ax=25.0, ay=16.0, az=13.0)

        self.assertIsNotNone(res3)
        self.assertEqual(res3.pattern_type, PatternType.THREE_TAP_DISTRESS)
        self.assertTrue(res3.is_emergency)

    # -------------------------------------------------------------------------
    # 8. Dual-Channel Fusion & Edge Case Immunity Tests
    # -------------------------------------------------------------------------

    def test_dual_channel_coincidence_fusion(self):
        """Verifies that simultaneous acoustic and seismic impacts are fused into confirmed dual-channel taps."""
        merged_taps = [
            TapEvent(timestamp=0.60, amplitude=15.0, channel="SEISMIC"),
            TapEvent(timestamp=0.61, amplitude=0.8, channel="ACOUSTIC"),
            TapEvent(timestamp=1.20, amplitude=14.0, channel="SEISMIC"),
            TapEvent(timestamp=1.21, amplitude=0.9, channel="ACOUSTIC"),
            TapEvent(timestamp=1.80, amplitude=16.0, channel="SEISMIC"),
            TapEvent(timestamp=1.82, amplitude=0.85, channel="ACOUSTIC"),
        ]
        res = self.detector.classify_cadence(merged_taps)
        self.assertEqual(res.pattern_type, PatternType.THREE_TAP_DISTRESS)
        self.assertTrue(res.is_emergency)
        self.assertEqual(res.tap_count, 3)
        self.assertTrue(res.details.get("dual_channel_confirmed"))
        self.assertEqual(res.details.get("sensor_modality"), "DUAL_SEISMIC_ACOUSTIC")
        self.assertGreaterEqual(res.confidence, 0.95)

    def test_process_dual_channel_end_to_end(self):
        """Tests process_dual_channel fusing synthetic accelerometer and audio streams."""
        t_accel, ax, ay, az = SarTapDetector.generate_synthetic_3tap_accel(dt1=0.6, dt2=0.6, sample_rate=50.0)
        # Generate matching audio
        sample_rate = 8000
        num_samples = int(3.0 * sample_rate)
        audio = [0.0] * num_samples
        for pt in [0.5, 1.1, 1.7]:
            idx = int(pt * sample_rate)
            for k in range(int(0.02 * sample_rate)):
                if idx + k < num_samples:
                    audio[idx + k] = 0.90 * math.sin(2 * math.pi * 1000 * (k / sample_rate))

        res = self.detector.process_dual_channel(
            accel_timestamps=t_accel,
            ax=ax,
            ay=ay,
            az=az,
            acoustic_samples=audio,
            sample_rate=sample_rate
        )
        self.assertEqual(res.pattern_type, PatternType.THREE_TAP_DISTRESS)
        self.assertTrue(res.is_emergency)
        self.assertIsNotNone(res.sos_packet)
        self.assertTrue(res.details.get("dual_channel_confirmed"))

    def test_continuous_rhythmic_subsequence_in_dirty_buffer(self):
        """Tests that 6 rhythmic knocks are detected even when preceded by debris noise."""
        dirty_taps = [0.1, 0.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5]
        res = self.detector.classify_cadence(dirty_taps)
        self.assertEqual(res.pattern_type, PatternType.CONTINUOUS_RHYTHMIC)
        self.assertTrue(res.is_emergency)
        self.assertEqual(res.tap_count, 6)
        self.assertEqual(res.intervals, [0.5, 0.5, 0.5, 0.5, 0.5])

    def test_streaming_accel_pruning_and_multi_day_stability(self):
        """Tests that stale taps (> 15s) are pruned so buffer does not accumulate or corrupt future bursts."""
        self.detector.reset_buffers()
        # Old tap from t = 0
        self.detector._streaming_taps.append(TapEvent(timestamp=0.0, amplitude=15.0, channel="SEISMIC"))
        self.detector._streaming_taps.append(TapEvent(timestamp=0.5, amplitude=12.0, channel="SEISMIC"))

        # Fast forward time to t = 100.0s and feed 3-tap distress
        self.detector._last_tap_time = -100.0
        self.detector._last_accel_sample = (99.98, 0.0, 0.0, 9.81)

        # Strike 1 at 100.0s
        self.detector.add_accel_sample(t=100.0, ax=20.0, ay=15.0, az=12.0)
        self.detector.add_accel_sample(t=100.02, ax=0.0, ay=0.0, az=9.81)

        # Strike 2 at 100.6s
        self.detector.add_accel_sample(t=100.6, ax=22.0, ay=14.0, az=11.0)
        self.detector.add_accel_sample(t=100.62, ax=0.0, ay=0.0, az=9.81)

        # Strike 3 at 101.2s
        res = self.detector.add_accel_sample(t=101.2, ax=25.0, ay=16.0, az=13.0)

        self.assertIsNotNone(res)
        self.assertEqual(res.pattern_type, PatternType.THREE_TAP_DISTRESS)
        # Verify stale taps from t=0.0 and 0.5 were pruned
        for tap in self.detector._streaming_taps:
            self.assertGreaterEqual(tap.timestamp, 100.0 - 15.0)

    def test_streaming_accel_dynamic_threshold_rumble_rejection(self):
        """Tests that streaming CFAR dynamically elevates threshold during continuous rumble."""
        self.detector.reset_buffers()
        t, ax, ay, az = SarTapDetector.generate_synthetic_rumble_accel(
            duration_s=4.0,
            sample_rate=50.0,
            freq_hz=1.5,
            amp_g=3.0
        )
        results = []
        for i in range(len(t)):
            r = self.detector.add_accel_sample(t[i], ax[i], ay[i], az[i])
            if r and r.is_emergency:
                results.append(r)

        self.assertEqual(len(results), 0, f"Spurious emergency triggers during rumble: {results}")

    def test_acoustic_streaming_ingestion(self):
        """Tests streaming acoustic ingestion via add_acoustic_sample."""
        self.detector.reset_buffers()
        # Feed silence
        for i in range(20):
            res = self.detector.add_acoustic_sample(t=i * 0.01, amplitude=0.01)
            self.assertIsNone(res)

        # Pulse 1 at t = 0.50s
        self.detector.add_acoustic_sample(t=0.50, amplitude=0.85)
        self.detector.add_acoustic_sample(t=0.52, amplitude=0.02)

        # Pulse 2 at t = 1.10s (dt = 0.60s)
        self.detector.add_acoustic_sample(t=1.10, amplitude=0.90)
        self.detector.add_acoustic_sample(t=1.12, amplitude=0.02)

        # Pulse 3 at t = 1.70s (dt = 0.60s)
        res = self.detector.add_acoustic_sample(t=1.70, amplitude=0.95)

        self.assertIsNotNone(res)
        self.assertEqual(res.pattern_type, PatternType.THREE_TAP_DISTRESS)
        self.assertTrue(res.is_emergency)

    def test_large_timeseries_cfar_performance(self):
        """Verifies that bisect-bounded CFAR peak detection runs in linear time (< 0.25s for 6000 samples)."""
        import time
        sample_count = 6000
        timestamps = [i * 0.005 for i in range(sample_count)]
        signal = [0.05 * math.sin(i * 0.1) for i in range(sample_count)]
        # Insert 3 sharp spikes
        signal[1000] = 25.0
        signal[2200] = 28.0
        signal[3400] = 30.0

        t0 = time.time()
        taps = self.detector._cfar_peak_detector(timestamps, signal, min_threshold=4.0, channel="SEISMIC")
        elapsed = time.time() - t0

        self.assertEqual(len(taps), 3)
        self.assertLess(elapsed, 0.25, f"CFAR execution took too long ({elapsed:.3f}s)")

    def test_morse_sos_with_tempo_jitter_generator(self):
        """Tests Morse SOS generation and classification with 15% tempo jitter."""
        ts, durations = SarTapDetector.generate_synthetic_morse_sos_taps(
            unit_dot_s=0.25,
            tempo_jitter_pct=0.15
        )
        res = self.detector.classify_cadence(ts, durations=durations)
        self.assertEqual(res.pattern_type, PatternType.MORSE_SOS)
        self.assertTrue(res.is_emergency)
        self.assertIsNotNone(res.sos_packet)


if __name__ == "__main__":
    unittest.main()
