"""
Multi-Receiver Ultrasonic Acoustic TDoA - 3D Rubble Depth Triangulator
Zero-Grid Disaster Mesh & Triage System (Setu) - Module 5

State-of-the-art acoustic 3D sub-surface localization engine for trapped victims
under concrete rubble and collapsed structures where GPS, cellular, and RF fail.

Key Capabilities:
1. Signal Processing (GCC-PHAT):
   - Generalized Cross-Correlation with Phase Transform (GCC-PHAT).
   - Pure Python Cooley-Tukey Radix-2 FFT/IFFT with seamless NumPy hardware acceleration when available.
   - Normalizes cross-spectral density magnitude |X1(f) X2*(f)| to whiten spectrum and eliminate
     resonant acoustic cavity ringing and multipath rubble reflections.
   - Sub-sample parabolic interpolation of cross-correlation peak for microsecond / millimeter precision.
2. Rubble Medium Acoustic Propagation:
   - Configurable speed of sound v_s (default 343.0 m/s for air voids, adjustable 340 - 500 m/s
     for porous rubble and mixed fractured concrete).
3. 3D Hyperbolic Multilateration Solver:
   - Ingests 3 or 4+ surface receiver positions (e.g. Setu-Mule Android microphones or seismic nodes).
   - Formulates non-linear hyperbolic range difference equations: d_ij = v_s * Delta_tau_ij = ||P - S_i|| - ||P - S_j||.
   - Solves non-linear least squares using Levenberg-Marquardt with coarse-to-fine multi-start grid search.
   - Strictly enforces physical burial depth constraint: z <= 0 (sub-surface rubble depth).
   - Detects and handles ill-conditioned/collinear geometries safely with geometric dilution of precision (GDOP) checks.
4. Tactical Excavation Outputs:
   - 3D coordinates (x, y, z) in meters relative to reference node.
   - Burial depth in meters (|z| beneath surface).
   - Combined confidence score (0.0 to 1.0) derived from cross-correlation peak sharpness, residual RMSE, and array geometry.
   - Tactical excavation advisory for search-and-rescue teams (e.g. "DIG DIRECTLY AT X=+1.2m, Y=+2.4m, TARGET DEPTH: 2.8 METERS BENEATH SLAB").
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional, Union

try:
    import numpy as np  # type: ignore
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ============================================================================
# FFT & Signal Processing Mathematics
# ============================================================================

def _next_power_of_two(n: int) -> int:
    """Returns the smallest power of 2 greater than or equal to n."""
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def _fft_pure(x: List[complex], inverse: bool = False) -> List[complex]:
    """
    Cooley-Tukey Radix-2 Fast Fourier Transform in pure Python.
    Supports forward FFT and inverse IFFT. Requires len(x) to be a power of 2.
    """
    n = len(x)
    if n <= 1:
        return [complex(v) for v in x]

    # Bit-reversal permutation
    bits = n.bit_length() - 1
    a = [complex(0.0, 0.0)] * n
    for i in range(n):
        r = 0
        val = i
        for _ in range(bits):
            r = (r << 1) | (val & 1)
            val >>= 1
        a[r] = complex(x[i])

    # Iterative decimation-in-time
    sign = 1.0 if inverse else -1.0
    step = 2
    while step <= n:
        half = step // 2
        w_step = sign * 2.0 * math.pi / step
        twiddles = [
            complex(math.cos(w_step * k), math.sin(w_step * k))
            for k in range(half)
        ]
        for i in range(0, n, step):
            for k in range(half):
                u = a[i + k]
                v = a[i + k + half] * twiddles[k]
                a[i + k] = u + v
                a[i + k + half] = u - v
        step *= 2

    if inverse:
        scale = 1.0 / n
        a = [v * scale for v in a]
    return a


def fft(x: List[Union[float, complex]]) -> List[complex]:
    """Forward FFT of sequence x, padded to next power of 2."""
    if not x:
        return []
    n = len(x)
    n_pad = _next_power_of_two(n)
    if HAS_NUMPY:
        arr = np.array(x, dtype=complex)
        if n_pad > n:
            arr = np.pad(arr, (0, n_pad - n))
        return list(np.fft.fft(arr))
    
    padded = [complex(v) for v in x]
    if n_pad > n:
        padded.extend([complex(0.0, 0.0)] * (n_pad - n))
    return _fft_pure(padded, inverse=False)


def ifft(X: List[complex]) -> List[complex]:
    """Inverse FFT of complex spectrum X."""
    if not X:
        return []
    n = len(X)
    n_pad = _next_power_of_two(n)
    if HAS_NUMPY:
        arr = np.array(X, dtype=complex)
        if n_pad > n:
            arr = np.pad(arr, (0, n_pad - n))
        return list(np.fft.ifft(arr))
    
    padded = [complex(v) for v in X]
    if n_pad > n:
        padded.extend([complex(0.0, 0.0)] * (n_pad - n))
    return _fft_pure(padded, inverse=True)


# ============================================================================
# Dataclasses
# ============================================================================

@dataclass
class ReceiverNode:
    """Represents an acoustic receiver / mule phone positioned on the rubble surface."""
    node_id: str
    position: Tuple[float, float, float]  # (x, y, z) in meters
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if len(self.position) != 3:
            raise ValueError(f"Receiver position must be a 3D coordinate (x, y, z), got {self.position}")


@dataclass
class TDoAMeasurement:
    """Pairwise Time Difference of Arrival (TDoA) measurement between two receiver nodes."""
    receiver_a: str
    receiver_b: str
    delay_seconds: float              # tau_b - tau_a (>0 means signal reached B after A)
    range_difference_meters: float    # v_s * delay_seconds
    peak_correlation: float = 1.0     # Peak normalized correlation magnitude
    confidence: float = 1.0           # Peak-to-Sidelobe / SNR confidence (0.0 to 1.0)


@dataclass
class TDoAResult:
    """Outcome of 3D hyperbolic acoustic multilateration."""
    estimated_position: Tuple[float, float, float]  # (x, y, z) in meters relative to reference
    burial_depth_meters: float                      # Absolute depth beneath rubble surface (|z|)
    confidence_score: float                         # Overall confidence score [0.0, 1.0]
    residual_rmse: float                            # Multilateration residual root-mean-square error (m)
    excavation_advisory: str                        # Human-readable tactical search & rescue instruction
    converged: bool = True
    iterations: int = 0
    tdoa_measurements: List[TDoAMeasurement] = field(default_factory=list)
    geometry_warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "estimated_position": [round(c, 4) for c in self.estimated_position],
            "burial_depth_meters": round(self.burial_depth_meters, 4),
            "confidence_score": round(self.confidence_score, 4),
            "residual_rmse": round(self.residual_rmse, 4),
            "excavation_advisory": self.excavation_advisory,
            "converged": self.converged,
            "iterations": self.iterations,
            "geometry_warning": self.geometry_warning,
            "tdoa_count": len(self.tdoa_measurements)
        }


# ============================================================================
# Acoustic TDoA Triangulator Engine
# ============================================================================

class AcousticTDoATriangulator:
    """
    State-of-the-art 3D acoustic sub-surface localization engine.
    Uses GCC-PHAT signal processing and constrained hyperbolic multilateration.
    """

    def __init__(
        self,
        speed_of_sound: float = 343.0,
        sample_rate: int = 44100,
        regularization_phat: float = 0.05
    ):
        """
        Args:
            speed_of_sound: Acoustic propagation velocity in medium (m/s).
                            343.0 m/s for air voids; 340-500 m/s for fractured concrete rubble.
            sample_rate: Audio sampling frequency in Hz (default 44100).
            regularization_phat: Spectral whitening noise threshold to prevent division-by-zero
                                 and out-of-band noise blowup.
        """
        if speed_of_sound <= 0:
            raise ValueError(f"Speed of sound must be positive, got {speed_of_sound}")
        if sample_rate <= 0:
            raise ValueError(f"Sample rate must be positive, got {sample_rate}")

        self.speed_of_sound = float(speed_of_sound)
        self.sample_rate = int(sample_rate)
        self.regularization_phat = float(regularization_phat)

    # ------------------------------------------------------------------------
    # Signal Processing: GCC-PHAT
    # ------------------------------------------------------------------------

    def gcc_phat(
        self,
        sig1: List[float],
        sig2: List[float],
        sample_rate: Optional[int] = None,
        max_delay_sec: Optional[float] = None
    ) -> Tuple[float, float, float]:
        """
        Computes Generalized Cross-Correlation with Phase Transform (GCC-PHAT)
        between two discrete audio signals.

        Returns:
            (tau_delay_seconds, peak_magnitude, confidence)
            where tau_delay_seconds = tau_2 - tau_1.
            A positive value means signal 2 arrived later than signal 1.
        """
        fs = sample_rate if sample_rate is not None else self.sample_rate
        l1, l2 = len(sig1), len(sig2)
        if l1 == 0 or l2 == 0:
            return 0.0, 0.0, 0.0

        # Zero-pad to next power of 2 >= l1 + l2 - 1 for linear correlation (min 32 for stability)
        min_n = l1 + l2 - 1
        n_fft = max(32, _next_power_of_two(min_n))

        # Pad signals
        pad1 = list(sig1) + [0.0] * (n_fft - l1)
        pad2 = list(sig2) + [0.0] * (n_fft - l2)

        # FFT
        X1 = fft(pad1)
        X2 = fft(pad2)

        # Cross-spectral density: G12 = X2 * conj(X1)
        # (This convention maps positive lag m to signal 2 arriving later than signal 1)
        cross = [X2[k] * X1[k].conjugate() for k in range(n_fft)]
        mags = [abs(c) for c in cross]
        max_mag = max(mags) if mags else 0.0

        if max_mag < 1e-15:
            return 0.0, 0.0, 0.0

        # Phase Transform (PHAT) spectral whitening with regularization
        threshold = self.regularization_phat * max_mag
        R = []
        for k in range(n_fft):
            c = cross[k]
            m = mags[k]
            denom = m if m > threshold else threshold
            R.append(c / denom)

        # Transform to analytic signal in frequency domain for envelope detection:
        # Zero out negative frequencies and double positive frequencies
        # This completely resolves carrier phase cycle-ambiguity for bandlimited signals (e.g. 18.5 - 20 kHz chirps)
        R_analytic = (
            [R[0]]
            + [2.0 * R[k] for k in range(1, n_fft // 2)]
            + [R[n_fft // 2]]
            + [complex(0.0, 0.0)] * (n_fft // 2 - 1)
        )
        analytic_cc = ifft(R_analytic)
        envelope = [abs(v) for v in analytic_cc]

        # Maximum physical lag search window
        max_limit = max(1, n_fft // 2 - 2)
        if max_delay_sec is not None and max_delay_sec > 0:
            max_lag = max(1, min(int(math.ceil(max_delay_sec * fs)), max_limit))
        else:
            max_lag = max_limit

        # Map circular correlation buffer into [-max_lag, +max_lag]
        lags = list(range(-max_lag, max_lag + 1))
        cc_vals = [envelope[l % n_fft] for l in lags]
        if not cc_vals:
            return 0.0, 0.0, 0.0

        # Locate global integer peak
        best_local_idx = max(range(len(cc_vals)), key=lambda i: cc_vals[i])
        best_lag = lags[best_local_idx]
        peak_val = cc_vals[best_local_idx]

        # Sub-sample parabolic interpolation of correlation peak
        # y(x) = a x^2 + b x + c fitted through (-1, y_m1), (0, y_0), (1, y_p1)
        if 0 < best_local_idx < len(cc_vals) - 1:
            y_m1 = cc_vals[best_local_idx - 1]
            y_0 = cc_vals[best_local_idx]
            y_p1 = cc_vals[best_local_idx + 1]

            denom = y_m1 - 2.0 * y_0 + y_p1
            if abs(denom) > 1e-12 and denom < 0:  # concave down peak
                delta = (y_m1 - y_p1) / (2.0 * denom)
                delta = max(-0.5, min(0.5, delta))
            else:
                delta = 0.0
        else:
            delta = 0.0

        subsample_lag = best_lag + delta
        tau_delay_sec = subsample_lag / float(fs)

        # Calculate Peak-to-Sidelobe Ratio (PSR) for signal confidence
        # Exclude immediate neighborhood of peak (+/- 3 samples)
        sidelobes = [
            cc_vals[i]
            for i in range(len(cc_vals))
            if abs(i - best_local_idx) > 3
        ]
        if sidelobes:
            mean_side = sum(sidelobes) / len(sidelobes)
            var_side = sum((s - mean_side) ** 2 for s in sidelobes) / len(sidelobes)
            std_side = math.sqrt(max(1e-12, var_side))
            psr = (peak_val - mean_side) / std_side
            # Sigmoid normalization of PSR: 5.0 PSR ~ 0.85, 10.0+ PSR ~ 0.99
            confidence = 1.0 / (1.0 + math.exp(-0.5 * (psr - 4.0)))
            confidence = max(0.0, min(1.0, confidence))
        else:
            confidence = 0.5

        return tau_delay_sec, float(peak_val), float(confidence)

    # ------------------------------------------------------------------------
    # Geometry Analysis & Dilution of Precision
    # ------------------------------------------------------------------------

    def check_receiver_geometry(
        self,
        receivers: List[ReceiverNode]
    ) -> Tuple[bool, str, float]:
        """
        Validates receiver node geometric distribution.
        Checks for collinearity, coincident nodes, and coplanarity/degeneracy.

        Returns:
            (is_well_conditioned, issue_description, condition_score)
        """
        if len(receivers) < 3:
            return False, f"INSUFFICIENT RECEIVERS: Minimum 3 required, got {len(receivers)}", 0.0

        # Check for coincident nodes
        for i in range(len(receivers)):
            for j in range(i + 1, len(receivers)):
                p1 = receivers[i].position
                p2 = receivers[j].position
                dist = math.sqrt(sum((p1[k] - p2[k]) ** 2 for k in range(3)))
                if dist < 0.05:  # less than 5cm apart
                    return False, f"COINCIDENT RECEIVERS: Nodes {receivers[i].node_id} and {receivers[j].node_id} are too close ({dist:.3f}m)", 0.0

        # Collinearity check using cross-product of relative vectors
        p0 = receivers[0].position
        v1 = None
        for r in receivers[1:]:
            p = r.position
            dx, dy, dz = p[0] - p0[0], p[1] - p0[1], p[2] - p0[2]
            mag = math.sqrt(dx * dx + dy * dy + dz * dz)
            if mag > 0.05:
                v1 = (dx / mag, dy / mag, dz / mag)
                break

        if v1 is None:
            return False, "ALL RECEIVERS COINCIDENT", 0.0

        max_cross_norm = 0.0
        for r in receivers[2:]:
            p = r.position
            dx, dy, dz = p[0] - p0[0], p[1] - p0[1], p[2] - p0[2]
            mag = math.sqrt(dx * dx + dy * dy + dz * dz)
            if mag < 0.05:
                continue
            v = (dx / mag, dy / mag, dz / mag)
            cx = v1[1] * v[2] - v1[2] * v[1]
            cy = v1[2] * v[0] - v1[0] * v[2]
            cz = v1[0] * v[1] - v1[1] * v[0]
            cross_mag = math.sqrt(cx * cx + cy * cy + cz * cz)
            if cross_mag > max_cross_norm:
                max_cross_norm = cross_mag

        if max_cross_norm < 0.08:
            return False, "COLLINEAR RECEIVERS: Receivers form a linear array; 3D hyperbolic localization is ambiguous", 0.15

        # Check for coplanar array (all receivers on nearly same plane)
        zs = [r.position[2] for r in receivers]
        z_span = max(zs) - min(zs)
        condition_score = min(1.0, max_cross_norm * 1.2)
        if z_span < 0.05:
            return True, "COPLANAR RECEIVERS: All receivers lie on flat 2D surface; vertical depth resolution has elevated GDOP", min(0.85, condition_score)

        return True, "GEOMETRY OPTIMAL", float(condition_score)

    # ------------------------------------------------------------------------
    # 3D Hyperbolic Multilateration Solver
    # ------------------------------------------------------------------------

    def triangulate(
        self,
        receivers: List[ReceiverNode],
        tdoas: Union[Dict[Tuple[str, str], float], List[TDoAMeasurement]],
        known_depth: Optional[float] = None,
        initial_guess: Optional[Tuple[float, float, float]] = None,
        bounds: Optional[Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]] = None
    ) -> TDoAResult:
        """
        Solves 3D hyperbolic multilateration from receiver positions and TDoA delays.

        Args:
            receivers: List of ReceiverNodes with (x, y, z) coordinates.
            tdoas: Pairwise delays either as TDoAMeasurement list or dict {(id_a, id_b): tau_sec}.
            known_depth: Optional known/constrained depth z <= 0 (e.g. -2.5). If provided,
                         solver constrains z to this depth (enabling exact 2D fix with 3 nodes).
            initial_guess: Optional starting (x, y, z).
            bounds: Search volume bounds ((x_min, x_max), (y_min, y_max), (z_min, z_max)).
                    Defaults to [-30, 30]m surrounding receivers, with z <= 0.

        Returns:
            TDoAResult containing estimated 3D position, depth, confidence, and excavation advisory.
        """
        if len(receivers) < 3:
            raise ValueError(f"At least 3 receiver nodes required for TDoA triangulation, got {len(receivers)}")

        is_valid_geom, geom_desc, geom_score = self.check_receiver_geometry(receivers)

        # Normalize and filter TDoA measurements
        rec_map = {r.node_id: r for r in receivers}
        raw_measurements: List[TDoAMeasurement] = []
        if isinstance(tdoas, list):
            raw_measurements = tdoas
        elif isinstance(tdoas, dict):
            for (id_a, id_b), delay in tdoas.items():
                range_diff = delay * self.speed_of_sound
                raw_measurements.append(TDoAMeasurement(
                    receiver_a=id_a,
                    receiver_b=id_b,
                    delay_seconds=delay,
                    range_difference_meters=range_diff,
                    confidence=1.0
                ))

        measurements = [
            m for m in raw_measurements
            if m.receiver_a in rec_map and m.receiver_b in rec_map
        ]

        fix_z = known_depth is not None
        if len(measurements) < 2:
            raise ValueError(
                f"Insufficient valid TDoA measurements matching receiver nodes: expected at least 2, got {len(measurements)}"
            )

        underdetermined = False
        if not fix_z and (len(receivers) == 3 or len(measurements) < 3):
            underdetermined = True
            is_valid_geom = False
            geom_desc = (
                "UNDERDETERMINED ARRAY: 3 receivers provide only 2 independent TDoA constraints "
                "for 3 unknowns (x,y,z); vertical depth is ambiguous without a 4th receiver or known_depth."
            )
            geom_score = min(geom_score, 0.30)

        # Set default bounds around receiver nodes
        xs = [r.position[0] for r in receivers]
        ys = [r.position[1] for r in receivers]
        zs = [r.position[2] for r in receivers]

        margin = 15.0
        x_min, x_max = min(xs) - margin, max(xs) + margin
        y_min, y_max = min(ys) - margin, max(ys) + margin
        z_min, z_max = -30.0, 0.0  # Physical constraint: z <= 0 (sub-surface rubble)

        if bounds is not None:
            (bx0, bx1), (by0, by1), (bz0, bz1) = bounds
            x_min, x_max = bx0, bx1
            y_min, y_max = by0, by1
            z_min, z_max = bz0, min(0.0, bz1)

        def dist3d(p1, p2):
            return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2 + (p1[2] - p2[2]) ** 2)

        # Residual function: r_k(P) = (||P - S_b|| - ||P - S_a||) - d_meas
        def compute_residuals(P: Tuple[float, float, float]) -> List[float]:
            res = []
            for m in measurements:
                sa = rec_map[m.receiver_a].position
                sb = rec_map[m.receiver_b].position
                da = dist3d(P, sa)
                db = dist3d(P, sb)
                diff = (db - da) - m.range_difference_meters
                res.append(diff)
            return res

        def compute_cost(P: Tuple[float, float, float]) -> float:
            r = compute_residuals(P)
            return sum(e * e for e in r) if r else float('inf')

        # --------------------------------------------------------------------
        # Step 1: Multi-Start Coarse-to-Fine Grid Search for Global Attraction Basin
        # --------------------------------------------------------------------
        best_p: Tuple[float, float, float] = (
            sum(xs) / len(xs),
            sum(ys) / len(ys),
            -1.5 if not fix_z else -abs(known_depth)
        )
        min_cost = compute_cost(best_p)

        if initial_guess is not None:
            # If initial_guess is at surface (z >= -0.01), nudge slightly sub-surface (-0.1m)
            # to prevent vanishing vertical gradient at saddle point when surface nodes are coplanar
            init_z = initial_guess[2]
            if not fix_z and init_z >= -0.01:
                init_z = -0.1
            clamped_init = (
                max(x_min, min(x_max, initial_guess[0])),
                max(y_min, min(y_max, initial_guess[1])),
                -abs(known_depth) if fix_z else min(0.0, max(z_min, init_z))
            )
            c_init = compute_cost(clamped_init)
            if c_init < min_cost:
                min_cost = c_init
                best_p = clamped_init

        # Coarse grid search to escape local minima / bad initializations
        if min_cost > 1e-4:
            x_steps = [x_min + i * (x_max - x_min) / 8.0 for i in range(9)]
            y_steps = [y_min + i * (y_max - y_min) / 8.0 for i in range(9)]
            if fix_z:
                z_steps = [-abs(known_depth)]
            else:
                z_steps = [-0.1, -0.5, -1.2, -2.0, -3.0, -4.5, -6.5, -10.0]

            for gx in x_steps:
                for gy in y_steps:
                    for gz in z_steps:
                        c = compute_cost((gx, gy, gz))
                        if c < min_cost:
                            min_cost = c
                            best_p = (gx, gy, gz)

        # --------------------------------------------------------------------
        # Step 2: Damped Levenberg-Marquardt / Gauss-Newton Optimization
        # --------------------------------------------------------------------
        P = list(best_p)
        lam = 0.001
        iterations = 0
        max_iter = 80
        converged = False

        for it in range(max_iter):
            iterations += 1
            curr_pos = (P[0], P[1], P[2])
            r = compute_residuals(curr_pos)
            if not r:
                break

            cost_curr = sum(e * e for e in r)

            # Build Jacobian
            # J[k] = [d r_k / dx, d r_k / dy, d r_k / dz]
            J: List[List[float]] = []
            for m in measurements:
                sa = rec_map[m.receiver_a].position
                sb = rec_map[m.receiver_b].position
                da = max(1e-4, dist3d(curr_pos, sa))
                db = max(1e-4, dist3d(curr_pos, sb))

                jx = (curr_pos[0] - sb[0]) / db - (curr_pos[0] - sa[0]) / da
                jy = (curr_pos[1] - sb[1]) / db - (curr_pos[1] - sa[1]) / da

                if fix_z:
                    J.append([jx, jy])
                else:
                    dz_b = curr_pos[2] - sb[2]
                    dz_a = curr_pos[2] - sa[2]
                    # Numerical finite-difference fallback if vertical derivative vanishes at surface
                    if abs(dz_b) < 1e-4 and abs(dz_a) < 1e-4:
                        eps_z = -0.05
                        p_pert = (curr_pos[0], curr_pos[1], curr_pos[2] + eps_z)
                        da_p = dist3d(p_pert, sa)
                        db_p = dist3d(p_pert, sb)
                        jz = ((db_p - da_p) - (db - da)) / eps_z
                    else:
                        jz = dz_b / db - dz_a / da
                    J.append([jx, jy, jz])

            n_dim = 2 if fix_z else 3
            # JTJ: (n_dim x n_dim), JTr: (n_dim x 1)
            JTJ = [
                [sum(J[k][row] * J[k][col] for k in range(len(r))) for col in range(n_dim)]
                for row in range(n_dim)
            ]
            JTr = [
                sum(J[k][row] * r[k] for k in range(len(r)))
                for row in range(n_dim)
            ]

            # Damping: JTJ + lam * I
            for i in range(n_dim):
                JTJ[i][i] += lam

            # Solve (JTJ + lam I) * delta = -JTr
            delta = [0.0] * n_dim
            if n_dim == 2:
                det = JTJ[0][0] * JTJ[1][1] - JTJ[0][1] * JTJ[1][0]
                if abs(det) > 1e-14:
                    delta[0] = (-JTJ[1][1] * JTr[0] + JTJ[0][1] * JTr[1]) / det
                    delta[1] = (JTJ[1][0] * JTr[0] - JTJ[0][0] * JTr[1]) / det
                else:
                    delta = [-0.05 * g for g in JTr]
            else:
                det = (
                    JTJ[0][0] * (JTJ[1][1] * JTJ[2][2] - JTJ[1][2] * JTJ[2][1])
                    - JTJ[0][1] * (JTJ[1][0] * JTJ[2][2] - JTJ[1][2] * JTJ[2][0])
                    + JTJ[0][2] * (JTJ[1][0] * JTJ[2][1] - JTJ[1][1] * JTJ[2][0])
                )
                if abs(det) > 1e-14:
                    inv = [
                        [
                            (JTJ[1][1] * JTJ[2][2] - JTJ[1][2] * JTJ[2][1]) / det,
                            (JTJ[0][2] * JTJ[2][1] - JTJ[0][1] * JTJ[2][2]) / det,
                            (JTJ[0][1] * JTJ[1][2] - JTJ[0][2] * JTJ[1][1]) / det,
                        ],
                        [
                            (JTJ[1][2] * JTJ[2][0] - JTJ[1][0] * JTJ[2][2]) / det,
                            (JTJ[0][0] * JTJ[2][2] - JTJ[0][2] * JTJ[2][0]) / det,
                            (JTJ[0][2] * JTJ[1][0] - JTJ[0][0] * JTJ[1][2]) / det,
                        ],
                        [
                            (JTJ[1][0] * JTJ[2][1] - JTJ[1][1] * JTJ[2][0]) / det,
                            (JTJ[0][1] * JTJ[2][0] - JTJ[0][0] * JTJ[2][1]) / det,
                            (JTJ[0][0] * JTJ[1][1] - JTJ[0][1] * JTJ[1][0]) / det,
                        ],
                    ]
                    delta = [-sum(inv[row][col] * JTr[col] for col in range(3)) for row in range(3)]
                else:
                    delta = [-0.05 * g for g in JTr]

            # Candidate position with physical bounds and depth constraint (z <= 0)
            cand_x = max(x_min, min(x_max, P[0] + delta[0]))
            cand_y = max(y_min, min(y_max, P[1] + delta[1]))
            if fix_z:
                cand_z = -abs(known_depth)
            else:
                cand_z = max(z_min, min(0.0, P[2] + delta[2]))

            cost_new = compute_cost((cand_x, cand_y, cand_z))
            step_norm = math.sqrt(sum(d * d for d in delta))

            if cost_new < cost_curr:
                P = [cand_x, cand_y, cand_z]
                lam = max(1e-7, lam * 0.5)
                if step_norm < 1e-4 or cost_new < 1e-8:
                    converged = True
                    break
            else:
                lam = min(1e6, lam * 2.5)
                if lam >= 1e5:
                    converged = (cost_curr < 0.05)
                    break

        # Calculate residual RMSE
        final_residuals = compute_residuals((P[0], P[1], P[2]))
        if final_residuals:
            rmse = math.sqrt(sum(e * e for e in final_residuals) / len(final_residuals))
        else:
            rmse = 0.0

        est_pos = (float(P[0]), float(P[1]), float(P[2]))
        burial_depth = abs(float(P[2]))

        # Calculate confidence score
        # 1. Fit quality from residual RMSE
        q_fit = math.exp(-rmse / 0.35)
        # 2. Geometry score
        q_geom = geom_score if is_valid_geom else 0.15
        # 3. Measurement correlation confidence
        avg_meas_conf = (
            sum(m.confidence for m in measurements) / len(measurements)
            if measurements else 0.5
        )

        overall_conf = max(0.0, min(1.0, q_fit * q_geom * avg_meas_conf))
        if not converged:
            overall_conf *= 0.5
        if underdetermined:
            overall_conf = min(overall_conf, 0.30)
        elif not is_valid_geom:
            overall_conf = min(overall_conf, 0.25)

        # Generate Tactical Excavation Advisory
        advisory = self.generate_excavation_advisory(
            position=est_pos,
            confidence=overall_conf,
            residual_rmse=rmse,
            is_valid_geometry=is_valid_geom and not underdetermined,
            num_receivers=len(receivers),
            known_depth_used=fix_z,
            is_underdetermined=underdetermined
        )

        return TDoAResult(
            estimated_position=est_pos,
            burial_depth_meters=burial_depth,
            confidence_score=overall_conf,
            residual_rmse=rmse,
            excavation_advisory=advisory,
            converged=converged,
            iterations=iterations,
            tdoa_measurements=measurements,
            geometry_warning=None if (is_valid_geom and not underdetermined) else geom_desc
        )

    # ------------------------------------------------------------------------
    # End-to-End Pipeline: Triangulation directly from Raw Audio Signals
    # ------------------------------------------------------------------------

    def triangulate_from_signals(
        self,
        receiver_signals: Dict[str, List[float]],
        receivers: List[ReceiverNode],
        known_depth: Optional[float] = None
    ) -> TDoAResult:
        """
        Processes multi-channel raw audio from receiver nodes using GCC-PHAT,
        extracts TDoA delays, and performs 3D hyperbolic triangulation.
        """
        if len(receivers) < 3:
            raise ValueError(f"Need at least 3 receivers, got {len(receivers)}")

        # Pairwise GCC-PHAT relative to reference node (first receiver)
        ref_node = receivers[0]
        if ref_node.node_id not in receiver_signals:
            raise ValueError(f"Reference receiver {ref_node.node_id} has no audio signal")

        ref_sig = receiver_signals[ref_node.node_id]
        tdoas: List[TDoAMeasurement] = []

        # Cross-correlate reference node with every other node
        for r in receivers[1:]:
            if r.node_id not in receiver_signals:
                continue
            sig_i = receiver_signals[r.node_id]
            # Max plausible physical delay across bounding box
            dist_max = math.sqrt(
                sum((ref_node.position[k] - r.position[k]) ** 2 for k in range(3))
            ) + 20.0
            max_delay = dist_max / self.speed_of_sound

            delay_sec, peak_mag, conf = self.gcc_phat(
                sig1=ref_sig,
                sig2=sig_i,
                max_delay_sec=max_delay
            )

            range_diff = delay_sec * self.speed_of_sound
            tdoas.append(TDoAMeasurement(
                receiver_a=ref_node.node_id,
                receiver_b=r.node_id,
                delay_seconds=delay_sec,
                range_difference_meters=range_diff,
                peak_correlation=peak_mag,
                confidence=conf
            ))

        return self.triangulate(
            receivers=receivers,
            tdoas=tdoas,
            known_depth=known_depth
        )

    # ------------------------------------------------------------------------
    # Advisory Generator
    # ------------------------------------------------------------------------

    def generate_excavation_advisory(
        self,
        position: Tuple[float, float, float],
        confidence: float,
        residual_rmse: float,
        is_valid_geometry: bool = True,
        num_receivers: int = 4,
        known_depth_used: bool = False,
        is_underdetermined: bool = False
    ) -> str:
        """Generates standard tactical excavation advisories for search and rescue units."""
        x, y, z = position
        depth = abs(z)

        if is_underdetermined:
            return (
                f"CAUTION: 3-RECEIVER VERTICAL AMBIGUITY (Score: {confidence:.2f}). "
                f"ESTIMATED X={x:+.1f}m, Y={y:+.1f}m. DEPLOY 4TH RECEIVER OR SPECIFY DEPTH BEFORE CORE DRILLING."
            )

        if not is_valid_geometry:
            return (
                f"CAUTION: LOW CONFIDENCE (Score: {confidence:.2f}). "
                f"ILL-CONDITIONED SENSOR GEOMETRY - REPOSITION RECEIVER NODES FOR TRIANGULATION BEFORE HEAVY EXCAVATION."
            )

        if confidence < 0.35:
            return (
                f"UNCERTAIN LOCALIZATION (Conf: {confidence:.2f}, RMSE: {residual_rmse:.2f}m). "
                f"POSSIBLE VOID CAVITY MULTIPATH. DIG CAREFULLY AT X={x:+.1f}m, Y={y:+.1f}m, ESTIMATED DEPTH: {depth:.1f} METERS."
            )

        # High / moderate confidence tactical advisory
        instruction = f"DIG DIRECTLY AT X={x:+.1f}m, Y={y:+.1f}m, TARGET DEPTH: {depth:.1f} METERS BENEATH SLAB"
        if known_depth_used:
            instruction += f" [CONSTRAINED DEPTH: {depth:.1f}m]"
        elif num_receivers == 3:
            instruction += " [3-NODE ESTIMATE: DEPLOY 4TH RECEIVER FOR SUB-DECIMETER VERTICAL LOCK]"

        return instruction


# ============================================================================
# Synthetic Signal Helper for Testing & Multi-Receiver Simulation
# ============================================================================

def synthesize_delayed_signal(
    source_signal: List[float],
    delay_seconds: float,
    sample_rate: int = 44100,
    snr_db: Optional[float] = None,
    echo_delay_sec: Optional[float] = None,
    echo_attenuation: float = 0.35
) -> List[float]:
    """
    Creates a time-delayed, optionally noisy, multipath-echoed copy of a source signal.
    Uses continuous frequency-domain phase shifting with leading and trailing zero-padding
    to completely prevent circular wrap-around artifacts for both positive and negative delays.
    """
    if not source_signal:
        return []

    shift_samples = delay_seconds * sample_rate
    n_src = len(source_signal)

    # Lead and trailing padding to prevent circular wrap-around for +/- shifts
    lead = int(math.ceil(abs(shift_samples))) + 200
    echo_samples = int(math.ceil((echo_delay_sec if echo_delay_sec else 0.0) * sample_rate))
    n_total = n_src + int(math.ceil(abs(shift_samples))) + echo_samples + 200
    n_fft = max(64, _next_power_of_two(lead + n_total))

    pad = [0.0] * lead + list(source_signal) + [0.0] * (n_fft - lead - n_src)
    X = fft(pad)

    # Apply exact phase shift in frequency domain: e^{-j 2 pi k shift / N}
    X_out = []
    for k in range(n_fft):
        freq_k = k if k <= n_fft // 2 else k - n_fft
        angle = -2.0 * math.pi * freq_k * shift_samples / float(n_fft)
        shift = complex(math.cos(angle), math.sin(angle))

        # Add multipath cavity echo if requested
        if echo_delay_sec is not None and echo_delay_sec > 0:
            total_echo_samples = shift_samples + echo_delay_sec * sample_rate
            angle_echo = -2.0 * math.pi * freq_k * total_echo_samples / float(n_fft)
            shift_echo = complex(math.cos(angle_echo), math.sin(angle_echo))
            val = X[k] * shift + echo_attenuation * (X[k] * shift_echo)
        else:
            val = X[k] * shift
        X_out.append(val)

    out_complex = ifft(X_out)
    out = [v.real for v in out_complex[lead : lead + n_total]]

    # Additive White Gaussian Noise (AWGN)
    if snr_db is not None:
        p_sig = sum(x * x for x in out) / max(1, len(out))
        if p_sig > 1e-12:
            snr_linear = 10.0 ** (snr_db / 10.0)
            p_noise = p_sig / snr_linear
            std_noise = math.sqrt(p_noise)
            for i in range(len(out)):
                out[i] += random.gauss(0.0, std_noise)

    return out
