"""
SAR-Tap: Acoustic & Seismic IMU Impact Codec for Trapped Survivors
Zero-Grid Disaster Mesh & Triage System (Setu)

Dual-channel impact and transient vibration analyzer for survivors trapped
under concrete, rubble, or collapsed structures who cannot vocalize or speak.

Capabilities:
1. Dual-Channel Transient Ingestion:
   - Seismic / Accelerometer 3-axis time-series (ax, ay, az) and jerk magnitude (d|a|/dt).
   - Acoustic microphone audio samples (PCM envelope / transient power).
2. Noise Floor Rejection & Signal Conditioning:
   - High-pass / differentiator filter isolating sharp structural impact spikes (<50ms).
   - Cell-Averaging Constant False Alarm Rate (CA-CFAR) dynamic thresholding with
     guard cells and training cells.
   - Rejects continuous vibration, heavy aftershock rumble, ambient footsteps, and DC bias.
   - Refractory period suppression to prevent reverberation / multi-peak strike ringing.
3. Cadence & Pattern Classification:
   - PatternType.THREE_TAP_DISTRESS: Universal alpine/mining/NDMA rescue pattern
     (3 sharp impacts spaced 0.3s to 1.5s apart, followed by silence).
   - PatternType.MORSE_SOS: Standard Morse code (... --- ...) with dot/dash ratio modeling
     and human tempo jitter tolerance (supports duration-based and knock-interval Morse).
   - PatternType.CONTINUOUS_RHYTHMIC: Rhythmic repeated knocking (5+ periodic taps with CV <= 0.25).
4. Autonomous 120-Byte SOS Packet Synthesis:
   - Generates binary SOS packet with SEVERITY_RED, DISASTER_BUILDING_COLLAPSE,
     is_trapped=True, MED_FLAG_CRUSH.
5. Cryo-Sleep Power Wake Hook:
   - Triggers CryoSleepManager.trigger_wake_interrupt() to immediately awaken node from
     CRYO_DEEP_SLEEP and initiate priority zero-grid acoustic and RF transmission.
"""

import bisect
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import math
import time
from typing import List, Tuple, Dict, Any, Optional, Union

from core.sos_packet import (
    pack_sos_packet,
    unpack_sos_packet,
    SEVERITY_RED,
    DISASTER_BUILDING_COLLAPSE,
    MED_FLAG_CRUSH,
    PACKET_SIZE
)
from core.cryo_sleep_manager import CryoSleepManager


class PatternType(str, Enum):
    """Recognized non-vocal distress tap cadence patterns."""
    NONE = "NONE"
    THREE_TAP_DISTRESS = "THREE_TAP_DISTRESS"
    MORSE_SOS = "MORSE_SOS"
    CONTINUOUS_RHYTHMIC = "CONTINUOUS_RHYTHMIC"


@dataclass
class TapEvent:
    """Represents a discrete structural impact detected on seismic or acoustic channel."""
    timestamp: float
    amplitude: float = 1.0
    duration: float = 0.0
    channel: str = "SEISMIC"  # "SEISMIC" or "ACOUSTIC"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": round(self.timestamp, 4),
            "amplitude": round(self.amplitude, 4),
            "duration": round(self.duration, 4),
            "channel": self.channel
        }


@dataclass
class DetectionResult:
    """Outcome of cadence analysis across tap events."""
    pattern_type: PatternType
    confidence: float
    tap_count: int
    tap_timestamps: List[float] = field(default_factory=list)
    intervals: List[float] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    sos_packet: Optional[bytes] = None
    wake_triggered: bool = False

    @property
    def is_emergency(self) -> bool:
        return self.pattern_type != PatternType.NONE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type.value,
            "is_emergency": self.is_emergency,
            "confidence": round(self.confidence, 4),
            "tap_count": self.tap_count,
            "tap_timestamps": [round(t, 4) for t in self.tap_timestamps],
            "intervals": [round(dt, 4) for dt in self.intervals],
            "details": self.details,
            "has_sos_packet": self.sos_packet is not None,
            "wake_triggered": self.wake_triggered
        }


class SarTapDetector:
    """
    Dual-channel seismic & acoustic impact analyzer for trapped survivors.
    """

    # Default timing and cadence parameters
    MIN_TAP_INTERVAL: float = 0.20        # Minimum physical gap between human impacts (200ms)
    MAX_TAP_INTERVAL: float = 1.80        # Maximum gap between impacts within a single burst (1.8s)
    DISTRESS_MIN_INTERVAL: float = 0.30   # Minimum interval for 3-tap rescue pattern (300ms)
    DISTRESS_MAX_INTERVAL: float = 1.50   # Maximum interval for 3-tap rescue pattern (1500ms)
    TEMPO_JITTER_TOLERANCE: float = 0.50  # Max allowable delta between consecutive intervals (50%)
    RHYTHMIC_MAX_CV: float = 0.25         # Max coefficient of variation for periodic knocking
    REFRACTORY_PERIOD: float = 0.15       # 150ms lockout window to suppress mechanical bounce/ringing

    # CFAR Dynamic Thresholding defaults
    CFAR_WINDOW_SIZE: int = 30            # Number of training samples in sliding window
    CFAR_GUARD_CELLS: int = 2             # Guard cells on each side of test cell
    CFAR_K_SIGMA: float = 3.5             # Multiplier above background noise std dev
    MIN_JERK_THRESHOLD: float = 4.0       # Minimum absolute jerk spike in m/s^3 to avoid sensor noise
    MIN_ACOUSTIC_THRESHOLD: float = 0.12  # Minimum normalized audio amplitude envelope

    def __init__(
        self,
        device_id: str = "SAR_TAP_DEVICE_01",
        latitude: float = 0.0,
        longitude: float = 0.0,
        altitude_decimeters: int = 0,
        battery_pct: int = 100,
        hop_count: int = 5,
        cryo_manager: Optional[CryoSleepManager] = None,
        min_tap_interval: float = DISTRESS_MIN_INTERVAL,
        max_tap_interval: float = DISTRESS_MAX_INTERVAL,
        tempo_jitter_tolerance: float = TEMPO_JITTER_TOLERANCE,
        refractory_period: float = REFRACTORY_PERIOD,
        cfar_window_size: int = CFAR_WINDOW_SIZE,
        cfar_guard_cells: int = CFAR_GUARD_CELLS,
        cfar_k_sigma: float = CFAR_K_SIGMA,
        min_jerk_threshold: float = MIN_JERK_THRESHOLD,
        min_acoustic_threshold: float = MIN_ACOUSTIC_THRESHOLD,
        clock_source=None
    ):
        self.device_id = str(device_id)
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        self.altitude_decimeters = int(altitude_decimeters)
        self.battery_pct = max(0, min(100, int(battery_pct)))
        self.hop_count = max(0, min(15, int(hop_count)))
        self.cryo_manager: Optional[CryoSleepManager] = cryo_manager

        self.min_tap_interval = float(min_tap_interval)
        self.max_tap_interval = float(max_tap_interval)
        self.tempo_jitter_tolerance = float(tempo_jitter_tolerance)
        self.refractory_period = float(refractory_period)

        self.cfar_window_size = int(cfar_window_size)
        self.cfar_guard_cells = int(cfar_guard_cells)
        self.cfar_k_sigma = float(cfar_k_sigma)
        self.min_jerk_threshold = float(min_jerk_threshold)
        self.min_acoustic_threshold = float(min_acoustic_threshold)

        self._clock = clock_source or time.time

        # Streaming buffer state
        self._streaming_taps: List[TapEvent] = []
        self._last_accel_sample: Optional[Tuple[float, float, float, float]] = None
        self._last_tap_time: float = -100.0
        self._recent_jerks: deque = deque(maxlen=self.cfar_window_size)
        self._recent_acoustic: deque = deque(maxlen=self.cfar_window_size)
        self._max_tap_history_s: float = 15.0

    def register_cryo_manager(self, manager: CryoSleepManager) -> None:
        """Hooks a CryoSleepManager instance to be awakened upon confirmed distress cadence."""
        self.cryo_manager = manager

    def reset_buffers(self) -> None:
        """Clears accumulated streaming taps and state."""
        self._streaming_taps.clear()
        self._last_accel_sample = None
        self._last_tap_time = -100.0
        self._recent_jerks.clear()
        self._recent_acoustic.clear()

    def fuse_tap_events(
        self,
        taps: List[TapEvent],
        coincidence_window: Optional[float] = None
    ) -> List[TapEvent]:
        """
        Fuses multi-channel or simultaneous seismic and acoustic tap detections.
        If an acoustic spike and seismic spike occur within the coincidence window
        (< 150ms), they represent the same physical strike and are fused into a
        single dual-channel confirmed event with boosted amplitude and confidence.
        If two spikes on the same channel occur within refractory window, suppresses
        echo/reverberation keeping the higher amplitude strike.
        """
        if not taps:
            return []

        sorted_taps = sorted(taps, key=lambda x: x.timestamp)
        window = self.refractory_period if coincidence_window is None else float(coincidence_window)

        fused: List[TapEvent] = []
        for tap in sorted_taps:
            if not fused:
                fused.append(tap)
                continue

            last = fused[-1]
            dt = tap.timestamp - last.timestamp
            if dt < window:
                # Same physical strike observed across channels or mechanical bounce
                channels = set()
                for ch in last.channel.replace("DUAL (SEISMIC+ACOUSTIC)", "SEISMIC+ACOUSTIC").split("+"):
                    channels.add(ch.strip())
                for ch in tap.channel.replace("DUAL (SEISMIC+ACOUSTIC)", "SEISMIC+ACOUSTIC").split("+"):
                    channels.add(ch.strip())

                is_dual = len(channels) > 1 or ("SEISMIC" in channels and "ACOUSTIC" in channels)
                merged_channel = "DUAL (SEISMIC+ACOUSTIC)" if is_dual else last.channel
                merged_amp = max(last.amplitude, tap.amplitude)
                merged_dur = max(last.duration, tap.duration)
                merged_ts = (last.timestamp + tap.timestamp) / 2.0 if is_dual else (
                    last.timestamp if last.amplitude >= tap.amplitude else tap.timestamp
                )

                fused[-1] = TapEvent(
                    timestamp=merged_ts,
                    amplitude=merged_amp,
                    duration=merged_dur,
                    channel=merged_channel
                )
            else:
                fused.append(tap)

        return fused

    # -------------------------------------------------------------------------
    # Signal Processing: Seismic Accelerometer & Jerk Ingestion
    # -------------------------------------------------------------------------

    def extract_taps_from_accel(
        self,
        timestamps: List[float],
        ax: List[float],
        ay: List[float],
        az: List[float]
    ) -> List[TapEvent]:
        """
        Extracts discrete structural tap timestamps from 3-axis accelerometer data.
        Calculates jerk magnitude d|a|/dt to filter out 1g gravity DC offset and
        low-frequency continuous ground motion, followed by CFAR transient detection.
        """
        n = min(len(timestamps), len(ax), len(ay), len(az))
        if n < 4:
            return []

        # 1. Compute total acceleration magnitude: |a| = sqrt(ax^2 + ay^2 + az^2)
        mags = [math.sqrt(ax[i] ** 2 + ay[i] ** 2 + az[i] ** 2) for i in range(n)]

        # 2. Compute jerk magnitude: d|a|/dt
        jerks = [0.0] * n
        for i in range(1, n):
            dt = timestamps[i] - timestamps[i - 1]
            if dt <= 0.0:
                dt = 0.01  # Fallback to prevent divide-by-zero
            jerks[i] = abs(mags[i] - mags[i - 1]) / dt

        # 3. Apply CA-CFAR transient peak detector on jerk series
        return self._cfar_peak_detector(
            timestamps=timestamps,
            signal=jerks,
            min_threshold=self.min_jerk_threshold,
            channel="SEISMIC"
        )

    # -------------------------------------------------------------------------
    # Signal Processing: Acoustic Audio Ingestion
    # -------------------------------------------------------------------------

    def extract_taps_from_acoustic(
        self,
        samples: List[float],
        sample_rate: int = 8000,
        start_time: float = 0.0
    ) -> List[TapEvent]:
        """
        Extracts discrete impact transients from raw microphone audio samples.
        Computes short-term energy envelope in 5ms frames followed by CFAR.
        """
        if not samples or sample_rate <= 0:
            return []

        # Frame into 5ms blocks
        frame_len = max(1, int(0.005 * sample_rate))
        num_frames = len(samples) // frame_len
        if num_frames < 4:
            return []

        frame_timestamps = []
        frame_energies = []

        for f in range(num_frames):
            idx_start = f * frame_len
            idx_end = idx_start + frame_len
            frame_sub = samples[idx_start:idx_end]
            # Peak absolute amplitude in frame
            max_amp = max(abs(s) for s in frame_sub)
            t_center = start_time + (idx_start + frame_len / 2.0) / sample_rate
            frame_timestamps.append(t_center)
            frame_energies.append(max_amp)

        return self._cfar_peak_detector(
            timestamps=frame_timestamps,
            signal=frame_energies,
            min_threshold=self.min_acoustic_threshold,
            channel="ACOUSTIC"
        )

    # -------------------------------------------------------------------------
    # Core CA-CFAR (Cell-Averaging Constant False Alarm Rate) Detector
    # -------------------------------------------------------------------------

    def _cfar_peak_detector(
        self,
        timestamps: List[float],
        signal: List[float],
        min_threshold: float,
        channel: str
    ) -> List[TapEvent]:
        """
        Time-Averaging Censored Constant False Alarm Rate (CS-CFAR) peak detector.
        Uses physical time intervals with bisect-bounded search windows, making it
        linear in time complexity and invariant to varying sampling rates.
        Rejects continuous vibration and slow rumble while isolating transient impacts.
        """
        n = len(signal)
        if n < 4:
            return []

        # Physical time windows (seconds)
        guard_time = 0.08    # 80ms guard window around impact transient
        window_time = 0.60   # 600ms reference background noise window

        detected_taps: List[TapEvent] = []
        last_tap_t = -100.0

        for i in range(n):
            val = signal[i]
            t = timestamps[i]

            # Must exceed absolute minimum sensitivity
            if val < min_threshold:
                continue

            # Bounded window search using bisect on sorted timestamps
            left_idx = bisect.bisect_left(timestamps, t - window_time)
            right_idx = bisect.bisect_right(timestamps, t + window_time)

            # Local maximum test within guard region (|t_j - t_i| <= guard_time)
            is_local_max = True
            train_cells: List[float] = []

            for j in range(left_idx, right_idx):
                dt = abs(timestamps[j] - t)
                if dt <= guard_time:
                    if signal[j] > val:
                        is_local_max = False
                        break
                elif dt <= window_time:
                    train_cells.append(signal[j])

            if not is_local_max:
                continue

            # Calculate adaptive threshold using Censored-CFAR (trim top 25% outlier targets)
            if len(train_cells) >= 4:
                sorted_cells = sorted(train_cells)
                trim_count = max(2, int(len(sorted_cells) * 0.75))
                eff_cells = sorted_cells[:trim_count]

                mean_noise = sum(eff_cells) / len(eff_cells)
                variance = sum((x - mean_noise) ** 2 for x in eff_cells) / len(eff_cells)
                std_noise = math.sqrt(variance)
                dynamic_thresh = max(min_threshold, mean_noise + self.cfar_k_sigma * std_noise)
            else:
                dynamic_thresh = min_threshold

            # Threshold check & refractory debounce
            if val >= dynamic_thresh:
                if (t - last_tap_t) >= self.refractory_period:
                    detected_taps.append(TapEvent(
                        timestamp=t,
                        amplitude=val,
                        channel=channel
                    ))
                    last_tap_t = t

        return detected_taps

    # -------------------------------------------------------------------------
    # Cadence & Pattern Classification Engine
    # -------------------------------------------------------------------------

    def classify_cadence(
        self,
        taps: Union[List[TapEvent], List[float]],
        durations: Optional[List[float]] = None,
        current_time: Optional[float] = None
    ) -> DetectionResult:
        """
        Classifies sequence of tap timestamps and optional pulse durations into
        rescue distress patterns:
        - PatternType.THREE_TAP_DISTRESS: 3 sharp impacts spaced 0.3s to 1.5s apart.
        - PatternType.MORSE_SOS: ... --- ... standard dot/dash Morse SOS.
        - PatternType.CONTINUOUS_RHYTHMIC: 5+ periodic repeated knocks (CV <= 0.25).
        - PatternType.NONE: Random noise, single tap, or continuous rumble.

        If an emergency pattern is verified:
        - Automatically packs a 120-byte binary SOS packet.
        - Triggers CryoSleepManager wake interrupt if registered.
        """
        now = self._clock() if current_time is None else current_time

        # Check if input contains TapEvents for multi-channel coincidence fusion
        is_tap_event_list = any(isinstance(x, TapEvent) for x in taps)
        dual_channel_confirmed = False

        if is_tap_event_list:
            event_list: List[TapEvent] = []
            for item in taps:
                if isinstance(item, TapEvent):
                    event_list.append(item)
                else:
                    event_list.append(TapEvent(timestamp=float(item)))
            fused_events = self.fuse_tap_events(event_list)
            dual_channel_confirmed = any("DUAL" in e.channel for e in fused_events)
            ts_list = [e.timestamp for e in fused_events]
            dur_list = [e.duration for e in fused_events]
        else:
            raw_ts = [float(x) for x in taps]
            raw_dur = [float(durations[i]) if (durations and i < len(durations)) else 0.0 for i in range(len(raw_ts))]
            if len(raw_ts) > 1:
                paired = sorted(zip(raw_ts, raw_dur), key=lambda p: p[0])
                raw_ts = [p[0] for p in paired]
                raw_dur = [p[1] for p in paired]
            # Debounce raw timestamps within refractory period to prevent ringing/bounce corruption
            ts_list = []
            dur_list = []
            for t_val, d_val in zip(raw_ts, raw_dur):
                if not ts_list or (t_val - ts_list[-1]) >= self.refractory_period:
                    ts_list.append(t_val)
                    dur_list.append(d_val)
                else:
                    dur_list[-1] = max(dur_list[-1], d_val)

        n = len(ts_list)
        if n < 3:
            # Single tap or double tap is insufficient for distress confirmation
            return DetectionResult(
                pattern_type=PatternType.NONE,
                confidence=0.0,
                tap_count=n,
                tap_timestamps=ts_list,
                intervals=[],
                details={"reason": f"Insufficient tap count ({n} < 3)"}
            )

        # Compute inter-tap intervals: dt_i = ts_{i+1} - ts_i
        intervals = [ts_list[i + 1] - ts_list[i] for i in range(n - 1)]

        # ---------------------------------------------------------------------
        # 1. Check for PatternType.MORSE_SOS (... --- ...)
        # ---------------------------------------------------------------------
        morse_res = self._check_morse_sos(ts_list, dur_list, intervals)
        if morse_res is not None:
            return self._finalize_emergency_result(morse_res, now, dual_channel_confirmed=dual_channel_confirmed)

        # ---------------------------------------------------------------------
        # 2. Check for PatternType.THREE_TAP_DISTRESS
        # ---------------------------------------------------------------------
        three_tap_res = self._check_three_tap_distress(ts_list, intervals)
        if three_tap_res is not None:
            return self._finalize_emergency_result(three_tap_res, now, dual_channel_confirmed=dual_channel_confirmed)

        # ---------------------------------------------------------------------
        # 3. Check for PatternType.CONTINUOUS_RHYTHMIC (5+ periodic knocks)
        # ---------------------------------------------------------------------
        rhythmic_res = self._check_continuous_rhythmic(ts_list, intervals)
        if rhythmic_res is not None:
            return self._finalize_emergency_result(rhythmic_res, now, dual_channel_confirmed=dual_channel_confirmed)

        # None of the recognized distress cadences matched (random noise or irregular taps)
        return DetectionResult(
            pattern_type=PatternType.NONE,
            confidence=0.0,
            tap_count=n,
            tap_timestamps=ts_list,
            intervals=intervals,
            details={"reason": "Irregular cadence / noise rejection"}
        )

    # -------------------------------------------------------------------------
    # Cadence Checkers
    # -------------------------------------------------------------------------

    def _check_three_tap_distress(
        self,
        timestamps: List[float],
        intervals: List[float]
    ) -> Optional[DetectionResult]:
        """
        Evaluates sequence for universal 3-tap distress pattern.
        Criteria:
        - 3 sharp impacts spaced between DISTRESS_MIN_INTERVAL (0.3s) and DISTRESS_MAX_INTERVAL (1.5s).
        - Spacing between taps 1-2 and 2-3 is tempo-consistent (jitter <= 50%).
        - Followed by silence (isolated triplet).
        """
        n = len(timestamps)
        quiet_gap = max(1.2, self.max_tap_interval * 1.05)

        # Case A: Exactly 3 taps
        if n == 3:
            dt1, dt2 = intervals[0], intervals[1]
            if (self.min_tap_interval <= dt1 <= self.max_tap_interval and
                self.min_tap_interval <= dt2 <= self.max_tap_interval):
                max_dt = max(dt1, dt2)
                diff_ratio = abs(dt1 - dt2) / max_dt if max_dt > 0 else 0.0
                if diff_ratio <= self.tempo_jitter_tolerance:
                    confidence = 1.0 - (diff_ratio * 0.5)
                    return DetectionResult(
                        pattern_type=PatternType.THREE_TAP_DISTRESS,
                        confidence=confidence,
                        tap_count=3,
                        tap_timestamps=timestamps,
                        intervals=intervals,
                        details={
                            "dt1": round(dt1, 3),
                            "dt2": round(dt2, 3),
                            "tempo_jitter": round(diff_ratio, 3),
                            "pattern_name": "NDMA / Alpine 3-Tap Distress"
                        }
                    )

        # Case B: Stream of taps containing an isolated triplet separated by silence (gap >= quiet_gap)
        if n > 3:
            for i in range(n - 2):
                dt1 = timestamps[i + 1] - timestamps[i]
                dt2 = timestamps[i + 2] - timestamps[i + 1]
                if (self.min_tap_interval <= dt1 <= self.max_tap_interval and
                    self.min_tap_interval <= dt2 <= self.max_tap_interval):
                    max_dt = max(dt1, dt2)
                    diff_ratio = abs(dt1 - dt2) / max_dt if max_dt > 0 else 0.0
                    if diff_ratio <= self.tempo_jitter_tolerance:
                        # Check silence before
                        quiet_before = (i == 0) or ((timestamps[i] - timestamps[i - 1]) >= quiet_gap)
                        # Check silence after
                        quiet_after = (i + 2 == n - 1) or ((timestamps[i + 3] - timestamps[i + 2]) >= quiet_gap)
                        if quiet_before and quiet_after:
                            confidence = 1.0 - (diff_ratio * 0.5)
                            return DetectionResult(
                                pattern_type=PatternType.THREE_TAP_DISTRESS,
                                confidence=confidence,
                                tap_count=3,
                                tap_timestamps=timestamps[i:i + 3],
                                intervals=[dt1, dt2],
                                details={
                                    "dt1": round(dt1, 3),
                                    "dt2": round(dt2, 3),
                                    "tempo_jitter": round(diff_ratio, 3),
                                    "pattern_name": "NDMA / Alpine 3-Tap Distress (in stream)"
                                }
                            )

        return None

    def _check_morse_sos(
        self,
        timestamps: List[float],
        durations: List[float],
        intervals: List[float]
    ) -> Optional[DetectionResult]:
        """
        Evaluates 9-element sequence for Morse code SOS (... --- ...).
        Supports:
        1. Pulse duration Morse: 3 short pulses, 3 long pulses, 3 short pulses.
        2. Knock interval Morse: 9 impacts where S-intervals are short and O-intervals / letter gaps are long.
        """
        n = len(timestamps)
        if n < 9:
            return None

        # Check in sliding windows of 9 elements
        for start_idx in range(n - 8):
            window_ts = timestamps[start_idx:start_idx + 9]
            window_dur = durations[start_idx:start_idx + 9]
            window_intervals = [window_ts[i + 1] - window_ts[i] for i in range(8)]

            # Check Model 1: Duration-based (... --- ...)
            has_valid_durations = any(d > 0.05 for d in window_dur)
            if has_valid_durations:
                dots = [window_dur[0], window_dur[1], window_dur[2], window_dur[6], window_dur[7], window_dur[8]]
                dashes = [window_dur[3], window_dur[4], window_dur[5]]

                mean_dot = sum(dots) / len(dots)
                mean_dash = sum(dashes) / len(dashes)

                if mean_dot > 0.02:
                    ratio = mean_dash / mean_dot
                    # Standard Morse ratio is 3:1. Allow human tempo variation (1.8 to 5.0)
                    if 1.8 <= ratio <= 5.0:
                        min_dash = min(dashes)
                        max_dot = max(dots)
                        if min_dash > (max_dot * 1.15):
                            return DetectionResult(
                                pattern_type=PatternType.MORSE_SOS,
                                confidence=0.96,
                                tap_count=9,
                                tap_timestamps=window_ts,
                                intervals=window_intervals,
                                details={
                                    "mode": "pulse_durations",
                                    "mean_dot": round(mean_dot, 3),
                                    "mean_dash": round(mean_dash, 3),
                                    "dash_dot_ratio": round(ratio, 2)
                                }
                            )

            # Check Model 2: Knock Interval-based SOS
            # 8 intervals:
            # dt0, dt1: intra-S intervals (dots)
            # dt2: gap between S and O
            # dt3, dt4: intra-O intervals (dashes)
            # dt5: gap between O and S
            # dt6, dt7: intra-S intervals (dots)
            dot_intervals = [window_intervals[0], window_intervals[1], window_intervals[6], window_intervals[7]]
            dash_or_gap_intervals = [window_intervals[2], window_intervals[3], window_intervals[4], window_intervals[5]]

            mean_dot_int = sum(dot_intervals) / len(dot_intervals)
            mean_dash_int = sum(dash_or_gap_intervals) / len(dash_or_gap_intervals)

            if 0.15 <= mean_dot_int <= 1.0:
                int_ratio = mean_dash_int / mean_dot_int
                if 1.6 <= int_ratio <= 5.0:
                    min_dash_int = min(dash_or_gap_intervals)
                    max_dot_int = max(dot_intervals)
                    if min_dash_int >= (max_dot_int * 1.05):
                        return DetectionResult(
                            pattern_type=PatternType.MORSE_SOS,
                            confidence=0.94,
                            tap_count=9,
                            tap_timestamps=window_ts,
                            intervals=window_intervals,
                            details={
                                "mode": "knock_intervals",
                                "mean_dot_interval": round(mean_dot_int, 3),
                                "mean_dash_interval": round(mean_dash_int, 3),
                                "interval_ratio": round(int_ratio, 2)
                            }
                        )

        return None

    def _check_continuous_rhythmic(
        self,
        timestamps: List[float],
        intervals: List[float]
    ) -> Optional[DetectionResult]:
        """
        Evaluates for rhythmic repeated knocking (5+ periodic taps).
        Finds the longest or most recent contiguous sub-sequence of taps where
        all intervals are between 0.20s and 2.20s and coefficient of variation CV <= 0.25.
        """
        n = len(timestamps)
        if n < 5 or not intervals:
            return None

        # Search for valid rhythmic sub-sequences from longest window down to 4 intervals (5 taps)
        max_w = min(len(intervals), 16)
        for w in range(max_w, 3, -1):
            # Scan from newest (suffix) to oldest so latest cadence is prioritized in streaming
            for j in range(len(intervals) - w, -1, -1):
                sub_int = intervals[j : j + w]
                if all(0.20 <= dt <= 2.20 for dt in sub_int):
                    mean_dt = sum(sub_int) / len(sub_int)
                    if mean_dt <= 0.0:
                        continue
                    variance = sum((dt - mean_dt) ** 2 for dt in sub_int) / len(sub_int)
                    std_dt = math.sqrt(variance)
                    cv = std_dt / mean_dt

                    if cv <= self.RHYTHMIC_MAX_CV:
                        matched_ts = timestamps[j : j + w + 1]
                        confidence = max(0.50, min(1.0, 1.0 - (cv * 2.0)))
                        return DetectionResult(
                            pattern_type=PatternType.CONTINUOUS_RHYTHMIC,
                            confidence=confidence,
                            tap_count=len(matched_ts),
                            tap_timestamps=matched_ts,
                            intervals=sub_int,
                            details={
                                "mean_interval_s": round(mean_dt, 3),
                                "tempo_bpm": round(60.0 / mean_dt, 1),
                                "coefficient_of_variation": round(cv, 4),
                                "subsequence_offset": j
                            }
                        )

        return None

    # -------------------------------------------------------------------------
    # SOS Packet Synthesis & Wake Hook
    # -------------------------------------------------------------------------

    def synthesize_sos_packet(
        self,
        pattern_type: PatternType,
        note: Optional[str] = None,
        timestamp: Optional[int] = None
    ) -> bytes:
        """
        Synthesizes a 120-byte binary SOS packet compliant with core.sos_packet.
        Flags node as trapped under rubble with crush medical condition.
        """
        ts = int(self._clock()) if timestamp is None else int(timestamp)

        if note is None:
            if pattern_type == PatternType.THREE_TAP_DISTRESS:
                note_str = "SEISMIC/TAP DISTRESS: 3-TAP RESCUE SIGNAL DETECTED UNDER RUBBLE"
            elif pattern_type == PatternType.MORSE_SOS:
                note_str = "SEISMIC/TAP DISTRESS: MORSE SOS DETECTED UNDER RUBBLE"
            elif pattern_type == PatternType.CONTINUOUS_RHYTHMIC:
                note_str = "SEISMIC/TAP DISTRESS: RHYTHMIC KNOCKING DETECTED UNDER RUBBLE"
            else:
                note_str = "SEISMIC/TAP DISTRESS: SURVIVOR IMPACT DETECTED"
        else:
            note_str = note

        return pack_sos_packet(
            device_id=self.device_id,
            timestamp=ts,
            latitude=self.latitude,
            longitude=self.longitude,
            altitude_decimeters=self.altitude_decimeters,
            severity=SEVERITY_RED,
            disaster_type=DISASTER_BUILDING_COLLAPSE,
            is_trapped=True,
            mobility=0,
            adults=1,
            children=0,
            elderly=0,
            critical_cases=1,
            hop_count=self.hop_count,
            battery_pct=self.battery_pct,
            medical_flags=MED_FLAG_CRUSH,
            note=note_str
        )

    def _finalize_emergency_result(
        self,
        result: DetectionResult,
        now: float,
        dual_channel_confirmed: bool = False
    ) -> DetectionResult:
        """
        Generates 120-byte binary SOS packet and triggers CryoSleepManager wake interrupt.
        """
        # 1. Synthesize verified 120-byte packet
        result.sos_packet = self.synthesize_sos_packet(
            pattern_type=result.pattern_type,
            timestamp=int(now)
        )

        # 2. Boost confidence and record sensor modality if cross-modal dual channel confirmed
        if dual_channel_confirmed:
            result.confidence = min(1.0, result.confidence * 1.05 + 0.02)
            result.details["dual_channel_confirmed"] = True
            result.details["sensor_modality"] = "DUAL_SEISMIC_ACOUSTIC"
        else:
            result.details["dual_channel_confirmed"] = False

        # 3. Trigger wake interrupt on CryoSleepManager if attached
        if self.cryo_manager is not None:
            self.cryo_manager.trigger_wake_interrupt(
                reason=f"SAR_TAP_{result.pattern_type.value}",
                current_time=now
            )
            result.wake_triggered = True

        return result

    # -------------------------------------------------------------------------
    # Batch Processing Shortcuts
    # -------------------------------------------------------------------------

    def process_accelerometer_series(
        self,
        timestamps: List[float],
        ax: List[float],
        ay: List[float],
        az: List[float],
        current_time: Optional[float] = None
    ) -> DetectionResult:
        """Processes accelerometer time-series and returns cadence classification."""
        taps = self.extract_taps_from_accel(timestamps, ax, ay, az)
        return self.classify_cadence(taps, current_time=current_time)

    def process_acoustic_series(
        self,
        samples: List[float],
        sample_rate: int = 8000,
        start_time: float = 0.0,
        current_time: Optional[float] = None
    ) -> DetectionResult:
        """Processes raw acoustic audio samples and returns cadence classification."""
        taps = self.extract_taps_from_acoustic(samples, sample_rate, start_time)
        return self.classify_cadence(taps, current_time=current_time)

    def process_dual_channel(
        self,
        accel_timestamps: List[float],
        ax: List[float],
        ay: List[float],
        az: List[float],
        acoustic_samples: List[float],
        sample_rate: int = 8000,
        audio_start_time: float = 0.0,
        current_time: Optional[float] = None
    ) -> DetectionResult:
        """
        Ingests both seismic (3-axis accelerometer) and acoustic (microphone audio) data,
        extracts transients from both modalities, fuses coincident strikes within the
        refractory window into verified dual-channel impacts, and classifies the cadence.
        """
        seismic_taps = self.extract_taps_from_accel(accel_timestamps, ax, ay, az)
        acoustic_taps = self.extract_taps_from_acoustic(acoustic_samples, sample_rate, audio_start_time)
        fused = self.fuse_tap_events(seismic_taps + acoustic_taps)
        return self.classify_cadence(fused, current_time=current_time)

    # -------------------------------------------------------------------------
    # Streaming Real-Time Ingestion
    # -------------------------------------------------------------------------

    def add_accel_sample(
        self,
        t: float,
        ax: float,
        ay: float,
        az: float
    ) -> Optional[DetectionResult]:
        """
        Ingests a single real-time accelerometer sample (e.g. 50Hz sensor callback).
        Evaluates jerk transient with streaming CFAR dynamic thresholding, prunes
        stale taps (> 15s old), and buffers candidate taps for cadence classification.
        """
        if self._last_accel_sample is None:
            self._last_accel_sample = (t, ax, ay, az)
            return None

        prev_t, prev_x, prev_y, prev_z = self._last_accel_sample
        dt = t - prev_t
        if dt <= 0:
            dt = 0.01

        mag_curr = math.sqrt(ax ** 2 + ay ** 2 + az ** 2)
        mag_prev = math.sqrt(prev_x ** 2 + prev_y ** 2 + prev_z ** 2)
        jerk = abs(mag_curr - mag_prev) / dt

        self._last_accel_sample = (t, ax, ay, az)

        # Dynamic CFAR noise floor calculation in streaming mode
        self._recent_jerks.append(jerk)
        if len(self._recent_jerks) >= 10:
            sorted_jerks = sorted(self._recent_jerks)
            trim_k = max(4, int(len(sorted_jerks) * 0.75))
            eff_jerks = sorted_jerks[:trim_k]
            mean_jerk = sum(eff_jerks) / len(eff_jerks)
            var_jerk = sum((j - mean_jerk) ** 2 for j in eff_jerks) / len(eff_jerks)
            std_jerk = math.sqrt(var_jerk)
            dynamic_thresh = max(self.min_jerk_threshold, mean_jerk + self.cfar_k_sigma * std_jerk)
        else:
            dynamic_thresh = self.min_jerk_threshold

        # Check for transient jerk strike exceeding dynamic CFAR threshold
        if jerk >= dynamic_thresh:
            if (t - self._last_tap_time) >= self.refractory_period:
                self._last_tap_time = t
                self._streaming_taps.append(TapEvent(
                    timestamp=t,
                    amplitude=jerk,
                    channel="SEISMIC"
                ))
                # Prune taps older than max history window (15.0s) to prevent memory accumulation
                cutoff_t = t - self._max_tap_history_s
                self._streaming_taps = [tap for tap in self._streaming_taps if tap.timestamp >= cutoff_t]
                # Retain at most 16 taps in sliding buffer
                if len(self._streaming_taps) > 16:
                    self._streaming_taps.pop(0)

                # Check if buffer forms a distress cadence
                res = self.classify_cadence(self._streaming_taps, current_time=t)
                if res.is_emergency:
                    return res

        return None

    def add_acoustic_sample(
        self,
        t: float,
        amplitude: float
    ) -> Optional[DetectionResult]:
        """
        Ingests a real-time acoustic envelope/amplitude sample.
        Evaluates dynamic acoustic CFAR and checks for cadence detection.
        """
        abs_amp = abs(amplitude)
        self._recent_acoustic.append(abs_amp)
        if len(self._recent_acoustic) >= 10:
            sorted_amp = sorted(self._recent_acoustic)
            trim_k = max(4, int(len(sorted_amp) * 0.75))
            eff_amp = sorted_amp[:trim_k]
            mean_amp = sum(eff_amp) / len(eff_amp)
            var_amp = sum((a - mean_amp) ** 2 for a in eff_amp) / len(eff_amp)
            std_amp = math.sqrt(var_amp)
            dynamic_thresh = max(self.min_acoustic_threshold, mean_amp + self.cfar_k_sigma * std_amp)
        else:
            dynamic_thresh = self.min_acoustic_threshold

        if abs_amp >= dynamic_thresh:
            if (t - self._last_tap_time) >= self.refractory_period:
                self._last_tap_time = t
                self._streaming_taps.append(TapEvent(
                    timestamp=t,
                    amplitude=abs_amp,
                    channel="ACOUSTIC"
                ))
                cutoff_t = t - self._max_tap_history_s
                self._streaming_taps = [tap for tap in self._streaming_taps if tap.timestamp >= cutoff_t]
                if len(self._streaming_taps) > 16:
                    self._streaming_taps.pop(0)

                res = self.classify_cadence(self._streaming_taps, current_time=t)
                if res.is_emergency:
                    return res

        return None

    # -------------------------------------------------------------------------
    # Synthetic Waveform Generators (for Simulation and Unit Testing)
    # -------------------------------------------------------------------------

    @staticmethod
    def generate_synthetic_3tap_accel(
        dt1: float = 0.6,
        dt2: float = 0.6,
        sample_rate: float = 50.0,
        tap_duration_s: float = 0.04,
        tap_peak_g: float = 12.0,
        noise_std_g: float = 0.05
    ) -> Tuple[List[float], List[float], List[float], List[float]]:
        """
        Generates realistic 3-axis accelerometer data containing 3 discrete taps.
        Gravity 9.8 m/s^2 on Z-axis, with sharp transient impulses on X/Y axes.
        """
        total_duration = 0.5 + dt1 + dt2 + 1.0
        num_samples = int(total_duration * sample_rate)
        t_list = [i / sample_rate for i in range(num_samples)]

        # Baseline: static phone buried under rubble at 1g gravity on Z
        ax = [0.0] * num_samples
        ay = [0.0] * num_samples
        az = [9.81] * num_samples

        tap_times = [0.5, 0.5 + dt1, 0.5 + dt1 + dt2]

        for t_tap in tap_times:
            idx_start = int(t_tap * sample_rate)
            tap_samples = max(1, int(tap_duration_s * sample_rate))
            for offset in range(tap_samples):
                idx = idx_start + offset
                if idx < num_samples:
                    # Sharp impact pulse
                    phase = math.sin(math.pi * offset / tap_samples)
                    ax[idx] += tap_peak_g * phase
                    ay[idx] += (tap_peak_g * 0.7) * phase
                    az[idx] += (tap_peak_g * 0.5) * phase

        return t_list, ax, ay, az

    @staticmethod
    def generate_synthetic_morse_sos_taps(
        unit_dot_s: float = 0.25,
        tempo_jitter_pct: float = 0.05
    ) -> Tuple[List[float], List[float]]:
        """
        Generates timestamps and durations for Morse SOS (... --- ...).
        Returns (timestamps, durations).
        """
        base_durations = [
            unit_dot_s, unit_dot_s, unit_dot_s,          # S (...)
            unit_dot_s * 3.0, unit_dot_s * 3.0, unit_dot_s * 3.0, # O (---)
            unit_dot_s, unit_dot_s, unit_dot_s           # S (...)
        ]
        # Inter-element gaps
        gap_element = unit_dot_s
        gap_letter = unit_dot_s * 3.0

        durations = []
        for i, d in enumerate(base_durations):
            jitter = 1.0 + (tempo_jitter_pct * (((i * 7) % 5 - 2) / 3.0))
            durations.append(max(0.05, d * jitter))

        timestamps = []
        curr_t = 0.5
        for i in range(9):
            timestamps.append(curr_t)
            curr_t += durations[i]
            gap = gap_letter if i in [2, 5] else gap_element
            jitter = 1.0 + (tempo_jitter_pct * (((i * 3) % 5 - 2) / 3.0))
            curr_t += max(0.05, gap * jitter)

        return timestamps, durations

    @staticmethod
    def generate_synthetic_rhythmic_taps(
        count: int = 7,
        interval_s: float = 0.60
    ) -> List[float]:
        """Generates periodic repeated knocking timestamps."""
        return [1.0 + i * interval_s for i in range(count)]

    @staticmethod
    def generate_synthetic_rumble_accel(
        duration_s: float = 3.0,
        sample_rate: float = 50.0,
        freq_hz: float = 12.0,
        amp_g: float = 2.5
    ) -> Tuple[List[float], List[float], List[float], List[float]]:
        """
        Generates continuous low-frequency aftershock earthquake rumble.
        Continuous sine wave oscillation without discrete transient taps.
        """
        num_samples = int(duration_s * sample_rate)
        t_list = [i / sample_rate for i in range(num_samples)]
        ax = [amp_g * math.sin(2 * math.pi * freq_hz * t) for t in t_list]
        ay = [amp_g * math.cos(2 * math.pi * freq_hz * t) for t in t_list]
        az = [9.81 + (amp_g * 0.5) * math.sin(2 * math.pi * (freq_hz * 0.5) * t) for t in t_list]
        return t_list, ax, ay, az
