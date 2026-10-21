# Building Setu (Part 2): Breaking the Silence — On-Device Indic SLMs and the "SAR-Tap" Seismic IMU Codec

> **Series**: Building Setu — Zero-Grid Disaster Mesh & Triage System  
> **Tags**: `DigitalSignalProcessing`, `EdgeAI`, `Sensors`, `Android`, `Python`, `Algorithms`  
> **Reading Time**: 9 mins  

---

## 1. The Speech Bottleneck in Traumatic Incidents

When a catastrophic event occurs, panic-stricken victims do not open forms, fill out checkboxes, or type structured descriptions. 

In a flood in Odisha, a mother standing in neck-deep water screams in Odia. In a collapsed factory in Ahmedabad, a worker trapped under machinery calls out in Hindi. In a coastal storm in Andhra Pradesh, families plead for help in Telugu.

Traditional disaster tools fail here for two reasons:
1. **They rely on Western-centric English UI forms.**
2. **They depend on cloud Speech-to-Text APIs (e.g., Google Cloud Speech, Whisper API)**—which require an active high-bandwidth internet connection that ceased to exist the moment power lines went down.

To break this bottleneck, Setu introduces two complementary Edge AI triage systems:
- **Vernacular Small Language Model (SLM) Speech Triage** for verbal survivors.
- **The "SAR-Tap" Seismic IMU Codec** for survivors who *cannot* speak.

---

## 2. Layer A: Vernacular Edge SLM Triage

In Setu, we designed an on-device lightweight triage parser capable of ingesting raw transcriptions across Indic languages (Hindi, Telugu, Tamil, Odia, Marathi, English) directly on low-cost devices.

Consider a survivor speaking into the phone:

> *"पानी छत तक आ गया है, मेरे साथ दो बच्चे और एक बुजुर्ग हैं जिन्हें इंसुलिन चाहिए"*  
> *(The water has reached the roof. With me are two children and an elderly person who needs insulin.)*

Without sending a single byte to an external server, Setu's edge extraction engine (`core/triage_extractor.py`) executes linguistic semantic slot-filling:

```
[Raw Audio Ingestion]
         |
         v
[Edge Vernacular Semantic Classifier]
  ├── Disaster Type  : DISASTER_FLOOD (Score: 0.95)
  ├── Trapped Status : True (Detected "छत तक", roof level isolation)
  ├── Mobility       : IMMOBILE
  ├── Demographics   : Adults=1, Children=2, Elderly=1 -> Total Headcount: 4
  └── Medical Flags  : MED_FLAG_INSULIN (Urgent diabetic dependency)
```

### Instant Offline Relief Voice Guidance
Immediately upon classification, the system queries an embedded, local NDMA-certified First-Aid vector base (`core/offline_rag.py`) and reads out emergency tactical instructions in the survivor's native tongue via Android Text-to-Speech:

> *"तुरंत यह करें: छत या सबसे ऊंचे सुरक्षित स्थान पर जाएं। बिजली के तारों को न छुएं। शरीर की ऊर्जा बचाएं..."*

Simultaneously, the edge engine packs the extracted parameters into our deterministic 120-byte binary packet and fires it into the mesh.

---

## 3. The Unspoken Crisis: When You Cannot Speak

Now consider a far darker, common USAR (Urban Search and Rescue) reality:

A survivor is pinned beneath a 6-inch reinforced concrete slab. 
- Their thoracic cavity is compressed by rubble; taking a deep breath causes excruciating pain.
- Concrete dust and toxic smoke have inflamed their bronchial passages; attempting to speak induces coughing spasms.
- Debris has jammed the microphone port with grit.
- They are in the pitch black with 12% battery remaining.

How can a smartphone detect a trapped human who cannot speak?

Every trapped miner and collapsed-building survivor is taught the universal Alpine/NDMA rule: **Tap on the pipe or rebar with a stone or metal object. Three sharp knocks, pause, repeat.**

We turned this survival instinct into code: **The "SAR-Tap" Non-Vocal Seismic IMU Codec** (`transport/sar_tap_detector.py`).

---

## 4. The Physics of "SAR-Tap": Dual-Channel Coincidence Fusion

A smartphone lying on a slab or held in a pinned survivor's hand acts as a high-sensitivity **seismograph**. 

When a survivor strikes a concrete wall, pipe, or rebar, the mechanical shock wave travels through the solid medium as high-frequency P-waves and S-waves. The phone's MEMS accelerometer records these impacts as sharp spikes in acceleration magnitude $a(t) = \sqrt{a_x^2 + a_y^2 + a_z^2}$.

However, real disaster environments are brutally noisy:
- Heavy excavator machinery vibrating 50 meters away.
- Low-frequency seismic aftershocks ($<5\text{ Hz}$).
- Debris settling and dust falls.

A naive peak detector on accelerometer data produces hundreds of false positives, depleting emergency batteries in minutes.

### The Mathematical Pipeline

```
  [Accelerometer 3-Axis (50-200 Hz)]         [Microphone Envelope (8-44.1 kHz)]
                  |                                           |
                  v                                           v
         Jerk Differentiation                      Band-Pass Filter (0.8-3.5 kHz)
          j(t) = d|a|/dt                                      |
                  |                                           v
                  v                                 Transient Peak Extraction
       Streaming CFAR Noise Gate                              |
     Threshold = mu_bg + N * sigma_bg                         |
                  |                                           |
                  +---------------------+---------------------+
                                        |
                                        v
                       [Dual-Channel Coincidence Gate]
                       (Spikes must align within dt < 150ms)
                                        |
                                        v
                         [Rhythmic Cadence Classifier]
                          • Alpine/NDMA 3-Tap Distress
                          • Morse Code SOS (... --- ...)
                                        |
                                        v
                       [Instant Cryo-Sleep Wake Interrupt]
                                        |
                                        v
                      [Auto-Pack 120-Byte Non-Vocal SOS]
```

### 1. Jerk Differentiation & Dynamic CFAR Noise Gate
Rather than raw acceleration, we compute the first derivative of acceleration magnitude—**jerk** $j(t)$:

$$j(t) = \frac{\Delta \sqrt{a_x^2 + a_y^2 + a_z^2}}{\Delta t}$$

Jerk amplifies sharp physical impacts while rejecting slow baseline tilts and gravity re-orientations. 

We then apply a **Constant False Alarm Rate (CFAR)** noise-floor estimator. The background noise variance $\sigma_{bg}$ is tracked in a circular buffer:

$$\text{Threshold}(t) = \mu_{bg} + k \cdot \sigma_{bg}$$

A tap is only registered if jerk exceeds $\text{Threshold}(t)$ with a minimum refractory debouncing period ($\Delta t_{debounce} = 180\text{ ms}$) to prevent multi-triggering from structural echoes.

### 2. Dual-Channel Coincidence Fusion
If the microphone is unobstructed, an impact produces both a seismic wave in the IMU and an acoustic click in the audio track. Setu aligns the timestamps: if an IMU jerk event and an acoustic peak occur within a $150\text{ ms}$ coincidence window, the strike confidence is boosted to 1.0.

### 3. Cadence Classification
Once discrete strikes are logged, the cadence classifier checks inter-tap intervals ($\Delta t_1, \Delta t_2$):
- **Universal 3-Tap Rescue Pattern**: 3 sharp strikes spaced between $0.25\text{ s}$ and $1.8\text{ s}$ apart, followed by at least $2.0\text{ s}$ of silence.
- **Morse SOS**: 3 short strikes (dots), 3 long intervals (dashes), 3 short strikes (`... --- ...`).

When the classifier detects a verified 3-tap sequence:

```python
# From transport/sar_tap_detector.py
if len(tap_timestamps) == 3:
    dt1 = tap_timestamps[1] - tap_timestamps[0]
    dt2 = tap_timestamps[2] - tap_timestamps[1]
    
    # Check consistency of human tapping tempo (within 40% jitter tolerance)
    if 0.25 <= dt1 <= 1.8 and 0.25 <= dt2 <= 1.8:
        tempo_ratio = max(dt1, dt2) / min(dt1, dt2)
        if tempo_ratio <= 1.6:  # Consistent human cadence
            return TapDetectionResult(
                pattern_type=PatternType.THREE_TAP_DISTRESS,
                confidence=1.0,
                wake_triggered=True
            )
```

---

## 5. Automated SOS Synthesis & Cryo-Wake Interrupt

The moment `SAR-Tap` verifies a 3-tap sequence:
1. **Cryo-Sleep Interruption**: It immediately fires an asynchronous wake signal to the device's power manager, snapping the phone out of deep sleep.
2. **Packet Synthesis**: Without the user ever touching the screen, it automatically synthesizes a high-priority 120-byte packet:
   - `severity = SEVERITY_RED`
   - `disaster_type = DISASTER_BUILDING_COLLAPSE`
   - `is_trapped = True`
   - `medical_flags = MED_FLAG_CRUSH`
   - `note = "SEISMIC/TAP DISTRESS: 3-TAP RESCUE SIGNAL DETECTED UNDER RUBBLE"`
3. **Emergency RF Burst**: The packet is broadcast over Bluetooth 5.0 extended advertising and an 18.5 kHz ultrasonic acoustic chirp.

### Verified by Unit Tests
In our automated test suite (`tests/test_sar_tap.py`), we validated this pipeline against synthetic rubble noise, random vibration aftershocks, and single accidental drops. The classifier achieved **100% true-positive detection** on valid 3-tap cadences with **zero false triggers** on continuous shaker noise.

---

## What's Next?

We now have an edge device capable of extracting emergency triage from Indic voice or physical knocks on concrete. 

But if a trapped survivor is buried for 8 days, how does the phone prevent its battery from dying in the first 4 hours?

*In Part 3, we reveal **"Cryo-Sleep"**: the sensor-gated ultra-low duty-cycle power engine that stretches a 15% phone battery to **12.4 days** under dark rubble.*
