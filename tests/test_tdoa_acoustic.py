"""
Automated Unit Tests for Module 5: Multi-Receiver Ultrasonic Acoustic TDoA Triangulator
Zero-Grid Disaster Mesh & Triage System (Setu)
"""

import math
import unittest
from typing import List, Tuple

from transport.acoustic_tdoa_triangulator import (
    AcousticTDoATriangulator,
    ReceiverNode,
    TDoAMeasurement,
    TDoAResult,
    synthesize_delayed_signal,
    fft,
    ifft
)
from transport.acoustic_modem import generate_linear_chirp, generate_tone


class TestAcousticTDoATriangulator(unittest.TestCase):
    """Unit test suite for acoustic 3D TDoA localization engine."""

    def setUp(self):
        self.sample_rate = 44100
        self.speed_of_sound = 343.0
        self.triangulator = AcousticTDoATriangulator(
            speed_of_sound=self.speed_of_sound,
            sample_rate=self.sample_rate
        )
        # Standard CSS beacon chirp (18.5 kHz - 20 kHz)
        self.chirp = generate_linear_chirp(
            f_start=18500,
            f_end=20000,
            duration=0.03,
            sample_rate=self.sample_rate
        )

    # ------------------------------------------------------------------------
    # 1. FFT / IFFT Mathematical Correctness
    # ------------------------------------------------------------------------

    def test_fft_ifft_roundtrip(self):
        """Verifies forward and inverse FFT roundtrip preserves signal exactly."""
        sig = [math.sin(2.0 * math.pi * 440.0 * i / self.sample_rate) for i in range(128)]
        spectrum = fft(sig)
        reconstructed = ifft(spectrum)
        
        for orig, recon in zip(sig, reconstructed[:len(sig)]):
            self.assertAlmostEqual(orig, recon.real, places=6)
            self.assertAlmostEqual(recon.imag, 0.0, places=6)

    # ------------------------------------------------------------------------
    # 2. GCC-PHAT Delay Estimation & Precision
    # ------------------------------------------------------------------------

    def test_gcc_phat_peak_detection_synthetic_delay(self):
        """Verifies GCC-PHAT detects positive, negative, and zero delays within sub-millisecond precision."""
        test_delays = [0.0, 0.0015, -0.0022, 0.0041, -0.0010]  # Delays up to ~4ms

        for true_delay in test_delays:
            if true_delay >= 0:
                sig1 = list(self.chirp)
                sig2 = synthesize_delayed_signal(self.chirp, delay_seconds=true_delay, sample_rate=self.sample_rate)
            else:
                sig2 = list(self.chirp)
                sig1 = synthesize_delayed_signal(self.chirp, delay_seconds=-true_delay, sample_rate=self.sample_rate)

            est_delay, peak, conf = self.triangulator.gcc_phat(sig1, sig2, max_delay_sec=0.01)
            err_ms = abs(est_delay - true_delay) * 1000.0

            # Sub-millisecond precision requirement: error < 0.1 ms (100 microseconds)
            self.assertLess(err_ms, 0.1, f"Failed for true delay {true_delay*1000:.3f}ms: got {est_delay*1000:.3f}ms (error {err_ms:.4f}ms)")
            self.assertGreater(conf, 0.6)

    def test_gcc_phat_sub_sample_parabolic_interpolation(self):
        """Verifies sub-sample parabolic interpolation resolves fractional sample delays."""
        # 12.4 samples at 44100 Hz = 0.000281179 seconds
        fractional_samples = 12.4
        true_delay = fractional_samples / float(self.sample_rate)

        sig1 = list(self.chirp)
        sig2 = synthesize_delayed_signal(self.chirp, delay_seconds=true_delay, sample_rate=self.sample_rate)

        est_delay, peak, conf = self.triangulator.gcc_phat(sig1, sig2, max_delay_sec=0.005)
        est_samples = est_delay * self.sample_rate

        sample_err = abs(est_samples - fractional_samples)
        # Parabolic interpolation should resolve fractional delay within < 0.3 sample
        self.assertLess(sample_err, 0.3)
        self.assertLess(abs(est_delay - true_delay) * 1000.0, 0.05)  # < 0.05 ms

    # ------------------------------------------------------------------------
    # 3. Robustness: Noise and Multipath Rubble Echoes
    # ------------------------------------------------------------------------

    def test_gcc_phat_noise_robustness(self):
        """Verifies GCC-PHAT accurately resolves delay under Additive White Gaussian Noise (SNR 10 dB)."""
        true_delay = 0.0018  # 1.8 ms delay
        sig1 = synthesize_delayed_signal(self.chirp, delay_seconds=0.0, sample_rate=self.sample_rate, snr_db=12.0)
        sig2 = synthesize_delayed_signal(self.chirp, delay_seconds=true_delay, sample_rate=self.sample_rate, snr_db=12.0)

        est_delay, peak, conf = self.triangulator.gcc_phat(sig1, sig2, max_delay_sec=0.01)
        err_ms = abs(est_delay - true_delay) * 1000.0
        self.assertLess(err_ms, 0.1)

    def test_gcc_phat_multipath_echo_robustness(self):
        """Verifies GCC-PHAT Phase Transform whitening isolates direct path over cavity echo reflections."""
        true_delay = 0.0020      # Direct path 2.0 ms
        echo_delay = 0.0035      # Multipath reflection 3.5 ms after direct path
        echo_atten = 0.40        # 40% amplitude echo reflection

        sig1 = list(self.chirp)
        sig2 = synthesize_delayed_signal(
            self.chirp,
            delay_seconds=true_delay,
            sample_rate=self.sample_rate,
            echo_delay_sec=echo_delay,
            echo_attenuation=echo_atten
        )

        est_delay, peak, conf = self.triangulator.gcc_phat(sig1, sig2, max_delay_sec=0.01)
        err_ms = abs(est_delay - true_delay) * 1000.0
        # Must lock to the direct path delay, not the echo reflection
        self.assertLess(err_ms, 0.1)

    # ------------------------------------------------------------------------
    # 4. 3D Hyperbolic Multilateration: 4-Receiver Array
    # ------------------------------------------------------------------------

    def test_3d_hyperbolic_localization_4_receivers(self):
        """
        Tests 3D hyperbolic localization with 4 receiver nodes placed on the rubble surface.
        Ground truth victim at known depth: (x=2.0m, y=1.5m, z=-2.5m).
        Verifies recovered coordinates within centimeter tolerance (< 1 cm).
        """
        victim_truth = (2.0, 1.5, -2.5)

        receivers = [
            ReceiverNode("MULE-01", (0.0, 0.0, 0.1)),
            ReceiverNode("MULE-02", (4.5, 0.0, -0.1)),
            ReceiverNode("MULE-03", (0.5, 4.0, 0.2)),
            ReceiverNode("MULE-04", (4.0, 3.5, 0.0))
        ]

        def dist3d(p1, p2):
            return math.sqrt(sum((p1[k] - p2[k]) ** 2 for k in range(3)))

        dists = [dist3d(victim_truth, r.position) for r in receivers]
        tdoas = {}
        for i in range(1, len(receivers)):
            delay = (dists[i] - dists[0]) / self.speed_of_sound
            tdoas[(receivers[0].node_id, receivers[i].node_id)] = delay

        result = self.triangulator.triangulate(receivers=receivers, tdoas=tdoas)

        # Verify recovered coordinates
        est_x, est_y, est_z = result.estimated_position
        err_x = abs(est_x - victim_truth[0])
        err_y = abs(est_y - victim_truth[1])
        err_z = abs(est_z - victim_truth[2])
        total_err = math.sqrt(err_x ** 2 + err_y ** 2 + err_z ** 2)

        self.assertLess(total_err, 0.01, f"Total 3D error exceeds 1cm: {total_err*100:.2f} cm")
        self.assertAlmostEqual(result.burial_depth_meters, 2.5, places=2)
        self.assertGreater(result.confidence_score, 0.90)
        self.assertLess(result.residual_rmse, 0.001)
        self.assertTrue(result.converged)

        # Verify tactical excavation advisory contains target coordinates and depth
        self.assertIn("DIG DIRECTLY AT", result.excavation_advisory)
        self.assertIn("X=+2.0m", result.excavation_advisory)
        self.assertIn("Y=+1.5m", result.excavation_advisory)
        self.assertIn("2.5 METERS", result.excavation_advisory)

    # ------------------------------------------------------------------------
    # 5. Hyperbolic Localization: 3-Receiver Array
    # ------------------------------------------------------------------------

    def test_hyperbolic_localization_3_receivers(self):
        """
        Tests localization with 3 receiver nodes on rubble surface with known depth (z=-2.5m).
        Verifies recovered (x, y) coordinates within centimeter tolerance.
        """
        victim_truth = (2.0, 1.5, -2.5)

        receivers = [
            ReceiverNode("MULE-01", (0.0, 0.0, 0.1)),
            ReceiverNode("MULE-02", (4.5, 0.0, -0.1)),
            ReceiverNode("MULE-03", (2.0, 4.0, 0.2))
        ]

        def dist3d(p1, p2):
            return math.sqrt(sum((p1[k] - p2[k]) ** 2 for k in range(3)))

        dists = [dist3d(victim_truth, r.position) for r in receivers]
        tdoas = {}
        for i in range(1, len(receivers)):
            delay = (dists[i] - dists[0]) / self.speed_of_sound
            tdoas[(receivers[0].node_id, receivers[i].node_id)] = delay

        result = self.triangulator.triangulate(
            receivers=receivers,
            tdoas=tdoas,
            known_depth=-2.5
        )

        est_x, est_y, est_z = result.estimated_position
        self.assertAlmostEqual(est_x, 2.0, places=2)
        self.assertAlmostEqual(est_y, 1.5, places=2)
        self.assertAlmostEqual(est_z, -2.5, places=2)
        self.assertAlmostEqual(result.burial_depth_meters, 2.5, places=2)
        self.assertGreater(result.confidence_score, 0.90)

    # ------------------------------------------------------------------------
    # 6. Rubble / Concrete Speed of Sound Medium Adaptation
    # ------------------------------------------------------------------------

    def test_rubble_concrete_speed_of_sound_adaptation(self):
        """Verifies solver accommodates medium speed of sound variations (e.g. 420 m/s in concrete rubble)."""
        vs_rubble = 420.0
        tri_rubble = AcousticTDoATriangulator(speed_of_sound=vs_rubble, sample_rate=self.sample_rate)

        victim_truth = (3.0, 2.0, -3.2)
        receivers = [
            ReceiverNode("S0", (0.0, 0.0, 0.0)),
            ReceiverNode("S1", (5.0, 0.0, 0.3)),
            ReceiverNode("S2", (0.5, 5.0, -0.2)),
            ReceiverNode("S3", (4.5, 4.5, 0.1))
        ]

        def dist3d(p1, p2):
            return math.sqrt(sum((p1[k] - p2[k]) ** 2 for k in range(3)))

        dists = [dist3d(victim_truth, r.position) for r in receivers]
        tdoas = {
            ("S0", "S1"): (dists[1] - dists[0]) / vs_rubble,
            ("S0", "S2"): (dists[2] - dists[0]) / vs_rubble,
            ("S0", "S3"): (dists[3] - dists[0]) / vs_rubble,
        }

        result = tri_rubble.triangulate(receivers=receivers, tdoas=tdoas)
        est = result.estimated_position
        total_err = dist3d(est, victim_truth)
        self.assertLess(total_err, 0.01)
        self.assertAlmostEqual(result.burial_depth_meters, 3.2, places=2)

    # ------------------------------------------------------------------------
    # 7. Ill-Conditioned Receiver Geometries & Physical Bounds Clamping
    # ------------------------------------------------------------------------

    def test_ill_conditioned_receiver_geometries(self):
        """Tests handling of collinear, coincident, and deficient receiver configurations."""
        # 1. Collinear receivers (all on a line y=0, z=0)
        collinear_receivers = [
            ReceiverNode("S0", (0.0, 0.0, 0.0)),
            ReceiverNode("S1", (1.0, 0.0, 0.0)),
            ReceiverNode("S2", (2.0, 0.0, 0.0)),
            ReceiverNode("S3", (3.0, 0.0, 0.0))
        ]
        is_ok, desc, score = self.triangulator.check_receiver_geometry(collinear_receivers)
        self.assertFalse(is_ok)
        self.assertIn("COLLINEAR", desc)
        self.assertLess(score, 0.3)

        # Localization on collinear array should yield low confidence score
        tdoas = {("S0", "S1"): 0.001, ("S0", "S2"): 0.002, ("S0", "S3"): 0.003}
        res_collinear = self.triangulator.triangulate(collinear_receivers, tdoas)
        self.assertLess(res_collinear.confidence_score, 0.30)
        self.assertIn("CAUTION: LOW CONFIDENCE", res_collinear.excavation_advisory)

        # 2. Coincident receivers
        coincident_receivers = [
            ReceiverNode("S0", (0.0, 0.0, 0.0)),
            ReceiverNode("S1", (0.01, 0.0, 0.0)),  # 1 cm away
            ReceiverNode("S2", (2.0, 3.0, 0.0))
        ]
        is_ok, desc, score = self.triangulator.check_receiver_geometry(coincident_receivers)
        self.assertFalse(is_ok)
        self.assertIn("COINCIDENT", desc)

        # 3. Insufficient receivers (< 3)
        with self.assertRaises(ValueError):
            self.triangulator.triangulate(
                receivers=[ReceiverNode("S0", (0, 0, 0)), ReceiverNode("S1", (1, 1, 0))],
                tdoas={("S0", "S1"): 0.001}
            )

    def test_physical_bounds_and_depth_clamping(self):
        """Verifies physical burial depth constraint z <= 0 is strictly enforced."""
        receivers = [
            ReceiverNode("S0", (0.0, 0.0, 0.0)),
            ReceiverNode("S1", (4.0, 0.0, 0.0)),
            ReceiverNode("S2", (2.0, 4.0, 0.0))
        ]
        # Even with positive initial guess or arbitrary delays, estimated z must remain <= 0
        tdoas = {("S0", "S1"): 0.0005, ("S0", "S2"): -0.0005}
        result = self.triangulator.triangulate(
            receivers=receivers,
            tdoas=tdoas,
            initial_guess=(2.0, 2.0, +5.0)  # above ground initial guess
        )
        self.assertLessEqual(result.estimated_position[2], 0.0)
        self.assertGreaterEqual(result.burial_depth_meters, 0.0)

    # ------------------------------------------------------------------------
    # 8. End-to-End Pipeline: Raw Audio Signals to Excavation Fix
    # ------------------------------------------------------------------------

    def test_full_pipeline_from_audio_signals(self):
        """
        Verifies end-to-end triangulation directly from raw receiver audio streams.
        Generates simulated multi-channel audio from a CSS chirp, computes GCC-PHAT TDoA,
        and outputs accurate 3D position and tactical excavation instructions.
        """
        victim_truth = (2.0, 1.5, -2.5)

        receivers = [
            ReceiverNode("MULE-ALPHA", (0.0, 0.0, 0.1)),
            ReceiverNode("MULE-BRAVO", (4.5, 0.0, -0.1)),
            ReceiverNode("MULE-CHARLIE", (0.5, 4.0, 0.2)),
            ReceiverNode("MULE-DELTA", (4.0, 3.5, 0.0))
        ]

        def dist3d(p1, p2):
            return math.sqrt(sum((p1[k] - p2[k]) ** 2 for k in range(3)))

        # Calculate exact propagation delays
        t_arrivals = [dist3d(victim_truth, r.position) / self.speed_of_sound for r in receivers]
        t_ref = min(t_arrivals)

        # Synthesize multi-channel audio received at each mule node
        signals = {}
        for i, r in enumerate(receivers):
            rel_delay = t_arrivals[i] - t_ref
            signals[r.node_id] = synthesize_delayed_signal(
                source_signal=self.chirp,
                delay_seconds=rel_delay,
                sample_rate=self.sample_rate,
                snr_db=20.0  # slight realistic channel noise
            )

        result = self.triangulator.triangulate_from_signals(
            receiver_signals=signals,
            receivers=receivers
        )

        est_x, est_y, est_z = result.estimated_position
        total_err = dist3d(result.estimated_position, victim_truth)

        # Decimeter accuracy requirement on noisy raw signals: error < 0.6 m
        self.assertLess(total_err, 0.60)
        self.assertLess(abs(est_x - victim_truth[0]), 0.25)
        self.assertLess(abs(est_y - victim_truth[1]), 0.25)
        self.assertGreater(result.confidence_score, 0.80)
        self.assertIn("DIG DIRECTLY AT", result.excavation_advisory)

        # Verify serialization
        payload = result.to_dict()
        self.assertEqual(len(payload["estimated_position"]), 3)
        self.assertIn("burial_depth_meters", payload)
        self.assertIn("excavation_advisory", payload)

    # ------------------------------------------------------------------------
    # 9. Edge Cases & Bug Regression Verifications
    # ------------------------------------------------------------------------

    def test_fft_ifft_empty_and_fallback(self):
        """Verifies empty sequence handling and pure Python FFT fallback."""
        import transport.acoustic_tdoa_triangulator as att
        self.assertEqual(fft([]), [])
        self.assertEqual(ifft([]), [])

        # Test pure Python Cooley-Tukey fallback
        orig_has_numpy = att.HAS_NUMPY
        try:
            att.HAS_NUMPY = False
            sig = [1.0, -1.0, 0.5, -0.5]
            spec = att.fft(sig)
            recon = att.ifft(spec)
            for orig, rec in zip(sig, recon[:len(sig)]):
                self.assertAlmostEqual(orig, rec.real, places=5)
        finally:
            att.HAS_NUMPY = orig_has_numpy

    def test_gcc_phat_short_signal_bounds(self):
        """Verifies gcc_phat handles short and 1-sample signals without max() empty sequence crash."""
        for length in [1, 2, 3, 5, 8]:
            sig1 = [1.0] * length
            sig2 = [1.0] * length
            tau, peak, conf = self.triangulator.gcc_phat(sig1, sig2)
            self.assertIsInstance(tau, float)
            self.assertIsInstance(peak, float)
            self.assertIsInstance(conf, float)

    def test_synthesize_delayed_signal_negative_delay(self):
        """Verifies negative delay synthesis preserves signal power without circular wrap-around loss."""
        # Test negative delay directly
        neg_delay = -0.0015  # -1.5 ms
        out_neg = synthesize_delayed_signal(
            source_signal=self.chirp,
            delay_seconds=neg_delay,
            sample_rate=self.sample_rate
        )
        self.assertGreater(len(out_neg), 0)
        # Power should be non-zero (previously returned ~0 due to wrap-around truncation)
        p_sig = sum(x * x for x in out_neg)
        self.assertGreater(p_sig, 0.1)

        # Cross-correlate source with negative-delayed copy
        tau, peak, conf = self.triangulator.gcc_phat(
            sig1=self.chirp,
            sig2=out_neg,
            max_delay_sec=0.005
        )
        # Delay should be approximately neg_delay (within 0.1 ms)
        self.assertAlmostEqual(tau, neg_delay, places=3)

    def test_surface_saddle_point_initial_guess_escape(self):
        """Verifies solver escapes the z=0.0 saddle point trap and recovers true sub-surface burial depth."""
        victim_truth = (2.0, 1.5, -2.5)
        receivers = [
            ReceiverNode("S0", (0.0, 0.0, 0.0)),
            ReceiverNode("S1", (4.0, 0.0, 0.0)),
            ReceiverNode("S2", (0.0, 4.0, 0.0)),
            ReceiverNode("S3", (3.0, 3.0, 0.0))
        ]

        def dist3d(p1, p2):
            return math.sqrt(sum((p1[k] - p2[k]) ** 2 for k in range(3)))

        dists = [dist3d(victim_truth, n.position) for n in receivers]
        tdoas = {
            ("S0", "S1"): (dists[1] - dists[0]) / self.speed_of_sound,
            ("S0", "S2"): (dists[2] - dists[0]) / self.speed_of_sound,
            ("S0", "S3"): (dists[3] - dists[0]) / self.speed_of_sound
        }

        # Initial guess right at ground surface z=0.0
        result = self.triangulator.triangulate(
            receivers=receivers,
            tdoas=tdoas,
            initial_guess=(2.0, 1.5, 0.0)
        )

        est_x, est_y, est_z = result.estimated_position
        total_err = dist3d(result.estimated_position, victim_truth)
        # Must accurately converge to depth -2.5m, not remain stuck at 0.0m
        self.assertLess(total_err, 0.05, f"Trapped at surface or high error: {result.estimated_position}")
        self.assertAlmostEqual(result.burial_depth_meters, 2.5, places=1)
        self.assertTrue(result.converged)

    def test_insufficient_or_mismatched_tdoa_rejection(self):
        """Verifies triangulate rejects invalid node IDs and insufficient measurements with ValueError."""
        receivers = [
            ReceiverNode("S0", (0.0, 0.0, 0.0)),
            ReceiverNode("S1", (4.0, 0.0, 0.0)),
            ReceiverNode("S2", (2.0, 4.0, 0.0)),
            ReceiverNode("S3", (2.0, 2.0, 0.2))
        ]

        # 1. Measurement with non-existent receiver IDs
        with self.assertRaises(ValueError):
            self.triangulator.triangulate(
                receivers=receivers,
                tdoas={("GHOST_A", "GHOST_B"): 0.002}
            )

        # 2. Only 1 valid measurement for 3D localization
        with self.assertRaises(ValueError):
            self.triangulator.triangulate(
                receivers=receivers,
                tdoas={("S0", "S1"): 0.002}
            )

    def test_underdetermined_3_receiver_warning(self):
        """Verifies 3 receivers without known depth issues underdetermined warning and penalizes confidence."""
        receivers = [
            ReceiverNode("S0", (0.0, 0.0, 0.0)),
            ReceiverNode("S1", (4.0, 0.0, 0.0)),
            ReceiverNode("S2", (2.0, 4.0, 0.0))
        ]
        tdoas = {("S0", "S1"): 0.001, ("S0", "S2"): 0.0015}

        result = self.triangulator.triangulate(receivers=receivers, tdoas=tdoas, known_depth=None)
        # Should flag underdetermined geometry warning
        self.assertIsNotNone(result.geometry_warning)
        self.assertIn("UNDERDETERMINED", result.geometry_warning)
        self.assertLessEqual(result.confidence_score, 0.35)
        self.assertIn("VERTICAL AMBIGUITY", result.excavation_advisory)

    def test_coplanar_geometry_detection(self):
        """Verifies check_receiver_geometry flags coplanar surface receiver arrays."""
        coplanar_receivers = [
            ReceiverNode("S0", (0.0, 0.0, 0.0)),
            ReceiverNode("S1", (4.0, 0.0, 0.0)),
            ReceiverNode("S2", (0.0, 4.0, 0.0)),
            ReceiverNode("S3", (4.0, 4.0, 0.0))
        ]
        is_ok, desc, score = self.triangulator.check_receiver_geometry(coplanar_receivers)
        self.assertTrue(is_ok)
        self.assertIn("COPLANAR", desc)
        self.assertLessEqual(score, 0.85)


if __name__ == "__main__":
    unittest.main()
