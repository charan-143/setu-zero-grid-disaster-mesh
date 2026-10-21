# Building Setu (Part 4): Penetrating Concrete with Ultrasonic Chirps and Defeating the Pre-Installation Paradox

> **Series**: Building Setu — Zero-Grid Disaster Mesh & Triage System  
> **Tags**: `Networking`, `Acoustics`, `WebDev`, `Android`, `Python`, `Protocols`  
> **Reading Time**: 10 mins  

---

## 1. The Physics of Concrete: The 2.4 GHz RF Blindspot

Software developers accustomed to urban coffee shops often assume Wi-Fi and Bluetooth go everywhere.

In an earthquake or building collapse, **concrete and steel are formidable radio shields**:
- A single 15 cm reinforced concrete slab with steel rebar mesh attenuates 2.4 GHz radio frequency (RF) signals by **15 dB to 30 dB**.
- Wet or flooded concrete increases attenuation to **over 45 dB**.
- Multiple collapsed floor slabs effectively act as a **Faraday cage**, cutting a phone's typical 50-meter Bluetooth range down to **less than 3 meters**.

If a survivor is buried under two collapsed floors, relying purely on 2.4 GHz RF is a fatal gamble.

How did we solve this? **By looking at mechanical waves: Ultrasonic Sound.**

---

## 2. Layer B: The Dual-Modality Acoustic & RF Modem

Sound waves behave completely differently than electromagnetic waves:
- While 2.4 GHz RF is absorbed and reflected by metallic rebar, **mechanical acoustic waves travel through structural voids, air gaps, ventilation shafts, and pipe networks**.
- A high-frequency acoustic chirp emitted by a commodity smartphone speaker can reverberate through concrete cavities and be picked up by surface microphones dozens of meters away.

```
+-----------------------------------------------------------------------------------+
|                        SETU DUAL-MODALITY TRANSMISSION                            |
+-----------------------------------------------------------------------------------+
| 1. ELECTROMAGNETIC MODALITY: Bluetooth Low Energy 5.0 Extended Advertising        |
|    • Carrier: 2.4 GHz RF (LE Coded PHY S=8, 125 kbps)                            |
|    • Strengths: Omnidirectional, fast packet capture (sub-millisecond), no audio  |
|    • Weakness: Heavily shielded by thick wet concrete and rebar cages             |
+-----------------------------------------------------------------------------------+
| 2. ACOUSTIC MODALITY: 18.5 kHz - 20.0 kHz Ultrasonic Acoustic Modem               |
|    • Carrier: Mechanical Longitudinal Sound Waves (Speed ~343 m/s in air)         |
|    • Strengths: Penetrates structural cracks and voids; near-silent to humans     |
|    • Bonus: Enables 3D Hyperbolic Time-Difference-of-Arrival (TDoA) Triangulation |
+-----------------------------------------------------------------------------------+
```

### The Acoustic Modulation Pipeline
In `transport/acoustic_modem.py`, we designed an acoustic modem operating in the near-ultrasound band (**18,500 Hz to 20,000 Hz**):
- **Why 18.5–20 kHz?** Standard consumer smartphone speakers and microphones support up to 22.05 kHz ($44.1\text{ kHz}$ sampling rate). Most adult human hearing drops off sharply above $16\text{ kHz}$, making the beacon virtually silent to trapped survivors, preventing panic while remaining fully decodable by software.
- **Modulation**: We employ **Continuous Phase Frequency Shift Keying (CP-FSK)** combined with **Chirp Spread Spectrum (CSS)** preamble synchronization:
  - Mark Frequency $f_1 = 18,750\text{ Hz}$
  - Space Frequency $f_0 = 19,250\text{ Hz}$
  - Preamble: Linear Up-Chirp from $18.5\text{ kHz}$ to $20.0\text{ kHz}$ over $50\text{ ms}$.

```python
# In transport/acoustic_modem.py
def encode_acoustic_signal(payload: bytes, sample_rate: int = 44100) -> List[float]:
    """Encodes 16-byte compressed beacon into 18.5-20kHz CP-FSK audio waveform."""
    t_preamble = 0.05  # 50ms sync chirp
    preamble = generate_linear_chirp(f_start=18500, f_end=20000, duration=t_preamble, sr=sample_rate)
    
    # Encode binary bits with phase continuity
    phase = 0.0
    audio = list(preamble)
    for byte in payload:
        for bit_idx in range(8):
            bit = (byte >> (7 - bit_idx)) & 1
            freq = 19250.0 if bit == 1 else 18750.0
            for _ in range(SAMPLES_PER_BIT):
                phase += 2.0 * math.pi * freq / sample_rate
                audio.append(0.8 * math.sin(phase))
    return audio
```

By firing both BLE 5.0 and the 18.5 kHz chirp simultaneously during the 200ms wake burst, Setu ensures that if the radio signal is blocked by rebar, the acoustic pulse will find an exit through the rubble voids.

---

## 3. Defeating the "Pre-Installation Paradox"

Now let us tackle the elephant in the room: **What about survivors who do not have the Setu app installed on their phones?**

In a sudden disaster, 99.9% of victims will have an ordinary iPhone, Samsung, or Xiaomi with standard apps (WhatsApp, Instagram, browser), but **zero disaster mesh tools**.

If a rescue system demands: *"Please install our APK first,"* it is useless in a disaster.

We defeated this paradox with the **Zero-Install Captive Gateway & Micro-PWA** (`gateway_mule/captive_portal_server.py`).

---

## 4. How the Zero-Install Gateway Works

A first-responder walking near the disaster zone, or a volunteer with a phone running Setu in **Mule Mode**, turns on their standard Wi-Fi Hotspot:
- **SSID**: `EMERGENCY_SOS_SETU` (Open, No Password)

When a stranded survivor with an unconfigured smartphone turns on Wi-Fi, their phone automatically discovers the open network and attempts to connect.

The moment the survivor connects, three architectural mechanisms fire:

```
  [Survivor's Phone]                                            [Setu Mule Phone]
          |                                                             |
          | ----- 1. Wi-Fi Association (Open SSID) -------------------> |
          |                                                             |
          | ----- 2. OS Captive Probe (DNS Query: google.com) --------> |
          |                                                   [DNS Hijacker (UDP 53)]
          |                                                   Answers: 192.168.4.1 (Mule IP)
          | <---- 3. DNS Answer: 192.168.4.1 -------------------------- |
          |                                                             |
          | ----- 4. HTTP Probe GET /generate_204 --------------------> |
          |                                                   [Captive HTTP Server]
          |                                                   Returns 302 Redirect to /
          | <---- 5. 302 Found: http://192.168.4.1/ ------------------- |
          |                                                             |
          | ----- 6. GET / (Requests Root Page) ----------------------> |
          |                                                   [Embedded Micro-PWA]
          | <---- 7. Serves Standalone Micro-PWA (<40 KB) ------------- |
          |                                                             |
          | === Captive Browser Modal Pops Up Automatically On Phone == |
          |                                                             |
          | ----- 8. POST /api/v1/captive_sos ------------------------> |
          |          (Triage checkboxes, headcount, injury flags)       |
          |                                                   [Local SQLite Ingestion]
          |                                                   • Packs 120-byte packet
          |                                                   • Caches in Mule buffer
          | <---- 9. Returns Status + Offline NDMA First-Aid Advice --- |
```

### 1. Multi-OS Captive Probe Interception
Modern mobile operating systems send silent background HTTP requests when connecting to Wi-Fi to test internet connectivity:
- **Android**: `GET /generate_204` or `/gen_204`
- **Apple iOS & macOS**: `GET /hotspot-detect.html`
- **Windows**: `GET /ncsi.txt` or `/connecttest.txt`

The Setu Mule intercepts all of these endpoints and redirects them to the root (`/`) path, triggering the OS to immediately open the native captive browser modal.

### 2. The 38 KB Zero-Dependency Micro-PWA
The captive portal does not load remote JavaScript from CDNs, Google Fonts, or external stylesheet servers—there is no internet!

The entire UI is a **38 KB standalone, self-contained HTML/CSS/JS application** embedded directly inside the Python and Kotlin runtime binaries:
- **Multilingual selector**: Hindi, Bengali, Tamil, Telugu, English.
- **Trauma triage selectors**: Trapped status, Arterial Bleed, Crush Injury, Fracture, Diabetic/Insulin dependency.
- **Demographics counters**: Adults, Children, Elderly, Critical patients.
- **Location description**: e.g., *"3rd floor under north stairwell."*

### 3. Immediate Offline Relief & First-Aid Feedback
The moment the victim taps **"BROADCAST SOS NOW"**, the Mule's local REST API (`POST /api/v1/captive_sos`) packs the submission into our standard 120-byte binary format and commits it to the local SQLite database.

Simultaneously, the API returns tailored, offline NDMA first-aid instructions based on the victim's selected injuries (e.g., direct-pressure instructions for arterial bleeding, or elevation protocols for crush syndrome).

The survivor is triaged, registered, and provided life-saving guidance in under **30 seconds**—**without ever installing an app or touching the internet**.

---

## The Transport Layer Complete

With BLE 5.0 extended advertising, 18.5 kHz ultrasonic chirps, and the Zero-Install Captive PWA, Setu guarantees that any signal—from an app-equipped device or a raw web browser—reaches the Mule network.

*In Part 5, the finale of our series, we explore what happens when signals reach the surface: **Multi-Receiver 3D Acoustic TDoA Rubble Triangulation** and the **Clinical Golden-Hour Vitality Decay Engine**.*
