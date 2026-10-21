"""
Ultrasonic Acoustic Modem (18.5 kHz - 20 kHz)
For deep rubble / concrete sub-surface beaconing.

Encodes 32-bit compact beacon payload:
[16b: Truncated Survivor ID][4b: Triage Severity][4b: Disaster Type][8b: Battery & Trapped Status]
Using FSK (Frequency Shift Keying) & CSS (Chirp Spread Spectrum) audio synthesis.
Works via standard smartphone speaker / microphone at 44.1 kHz or 48 kHz.
"""

import math
import struct
import wave
from typing import List, Tuple, Optional


SAMPLE_RATE = 44100
FREQ_BASE = 18500        # 18.5 kHz
FREQ_MARK = 19200        # 19.2 kHz (Bit 1)
FREQ_SPACE = 18600       # 18.6 kHz (Bit 0)
FREQ_SYNC = 19800        # 19.8 kHz (Preamble tone)
SYMBOL_DURATION = 0.04   # 40ms per bit (25 baud for high SNR under rubble)


def generate_tone(freq: float, duration: float, sample_rate: int = SAMPLE_RATE, amplitude: float = 0.8) -> List[float]:
    """Generates sine wave samples with gentle raised-cosine envelope to minimize audible clicks."""
    num_samples = int(duration * sample_rate)
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        # Hann envelope on the edges (first and last 5ms)
        fade_samples = int(0.005 * sample_rate)
        env = 1.0
        if i < fade_samples:
            env = 0.5 * (1.0 - math.cos(math.pi * i / fade_samples))
        elif i > num_samples - fade_samples:
            env = 0.5 * (1.0 - math.cos(math.pi * (num_samples - i) / fade_samples))

        val = amplitude * env * math.sin(2.0 * math.pi * freq * t)
        samples.append(val)
    return samples


def generate_linear_chirp(
    f_start: float = 18500,
    f_end: float = 20000,
    duration: float = 0.1,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.8
) -> List[float]:
    """
    Generates a Linear Chirp Spread Spectrum (CSS) beacon pulse.
    CSS provides high processing gain and multipath resistance through rubble.
    """
    num_samples = int(duration * sample_rate)
    samples = []
    k = (f_end - f_start) / duration  # chirp rate
    for i in range(num_samples):
        t = i / sample_rate
        phase = 2.0 * math.pi * (f_start * t + 0.5 * k * (t ** 2))
        val = amplitude * math.sin(phase)
        samples.append(val)
    return samples


def pack_acoustic_beacon_payload(
    survivor_id_16: int,
    severity: int,
    disaster_type: int,
    is_trapped: bool,
    battery_pct: int
) -> int:
    """
    Packs essential telemetry into a 32-bit integer:
    [16b: survivor_id][4b: severity][4b: disaster_type][1b: trapped][7b: battery %]
    """
    val = (survivor_id_16 & 0xFFFF) << 16
    val |= (severity & 0x0F) << 12
    val |= (disaster_type & 0x0F) << 8
    val |= (1 if is_trapped else 0) << 7
    val |= (min(100, max(0, battery_pct)) & 0x7F)
    return val


def unpack_acoustic_beacon_payload(val: int) -> dict:
    """Unpacks 32-bit acoustic beacon value."""
    survivor_id = (val >> 16) & 0xFFFF
    severity = (val >> 12) & 0x0F
    disaster_type = (val >> 8) & 0x0F
    is_trapped = bool((val >> 7) & 0x01)
    battery_pct = val & 0x7F
    return {
        "survivor_id_hex": f"0x{survivor_id:04X}",
        "survivor_id": survivor_id,
        "severity": severity,
        "severity_label": ["GREEN", "YELLOW", "RED", "BLACK"][severity] if severity < 4 else "UNKNOWN",
        "disaster_type": disaster_type,
        "is_trapped": is_trapped,
        "battery_pct": battery_pct
    }


def encode_acoustic_signal(payload_32bit: int, sample_rate: int = SAMPLE_RATE) -> List[float]:
    """
    Encodes 32-bit payload into ultrasonic audio samples:
    - 2x CSS Chirp (Sync / Wakeup)
    - 32 FSK bits (FREQ_MARK for 1, FREQ_SPACE for 0)
    - 1x CSS Chirp (End of frame)
    """
    audio: List[float] = []

    # 1. Sync Chirp (Preamble)
    chirp = generate_linear_chirp(18500, 20000, duration=0.1, sample_rate=sample_rate)
    audio.extend(chirp)
    audio.extend([0.0] * int(0.02 * sample_rate))  # 20ms guard

    # 2. 32-bit FSK Modulation
    for bit_idx in range(31, -1, -1):
        bit = (payload_32bit >> bit_idx) & 1
        freq = FREQ_MARK if bit == 1 else FREQ_SPACE
        tone = generate_tone(freq, SYMBOL_DURATION, sample_rate=sample_rate)
        audio.extend(tone)

    # 3. Postamble Chirp
    audio.extend([0.0] * int(0.02 * sample_rate))
    audio.extend(chirp)

    return audio


def save_audio_wav(filename: str, samples: List[float], sample_rate: int = SAMPLE_RATE):
    """Saves normalized float samples to a 16-bit PCM WAV file."""
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        raw_bytes = bytearray()
        for s in samples:
            clamped = max(-1.0, min(1.0, s))
            pcm_val = int(clamped * 32767)
            raw_bytes.extend(struct.pack('<h', pcm_val))
        wf.writeframes(raw_bytes)


def decode_fsk_spectrum_slice(samples: List[float], sample_rate: int = SAMPLE_RATE) -> int:
    """
    Goertzel or DFT energy comparator for Mark vs Space frequencies.
    """
    def goertzel_mag(target_freq: float) -> float:
        n = len(samples)
        k = int(0.5 + (n * target_freq / sample_rate))
        w = (2.0 * math.pi / n) * k
        cosine = math.cos(w)
        coeff = 2.0 * cosine
        q1 = 0.0
        q2 = 0.0
        for sample in samples:
            q0 = coeff * q1 - q2 + sample
            q2 = q1
            q1 = q0
        return math.sqrt(q1 * q1 + q2 * q2 - q1 * q2 * coeff)

    mark_power = goertzel_mag(FREQ_MARK)
    space_power = goertzel_mag(FREQ_SPACE)
    return 1 if mark_power >= space_power else 0
