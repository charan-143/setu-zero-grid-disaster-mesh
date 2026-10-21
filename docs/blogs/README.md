# Building Setu: The Zero-Grid Disaster Mesh & Triage System
## Complete 5-Part Technical Engineering Blog Series

Welcome to the official technical publication series documenting the architecture, mathematical models, signal processing algorithms, and hardware integration behind **Setu (सेतु)** — an open-source, zero-hardware-cost, offline-first disaster response mesh for smartphones.

---

## 📚 Table of Contents

| Part | Title | Focus Areas | Read Time |
| :--- | :--- | :--- | :--- |
| **[Part 1](01_why_mesh_apps_fail_and_building_setu.md)** | **Why Existing Disaster Mesh Apps Fail and How We Built a Zero-Grid Infrastructure** | The 3 disaster paradoxes, 4-layer architecture, 120-byte binary protocol | 8 mins |
| **[Part 2](02_breaking_the_silence_slm_and_sar_tap.md)** | **Breaking the Silence — On-Device Indic SLMs and the "SAR-Tap" Seismic IMU Codec** | Vernacular edge NLP, IMU jerk differentiation, CFAR noise filtering, 3-tap distress detection | 9 mins |
| **[Part 3](03_cryo_sleep_12_days_under_rubble.md)** | **12.4 Days Under Dark Rubble — The "Cryo-Sleep" Battery Stretcher** | Photometric & kinetic sensor gating, duty cycle math, 119.4x power gain, thermal derating | 9 mins |
| **[Part 4](04_acoustic_modem_and_zero_install_pwa.md)** | **Penetrating Concrete with Ultrasonic Chirps and Defeating the Pre-Installation Paradox** | 18.5-20 kHz CP-FSK acoustic modem, BLE 5.0 Coded PHY, DNS hijacking, 38KB embedded micro-PWA | 10 mins |
| **[Part 5](05_3d_acoustic_tdoa_and_golden_hour_dispatch.md)** | **3D Acoustic Rubble Triangulation and the Golden-Hour Vitality Decay Engine** | GCC-PHAT sub-sample TDoA multilateration, clinical trauma decay models, deadline-first dispatch | 11 mins |

---

## 🏷️ Publication Metadata (for Hashnode / Dev.to)

### Part 1:
- **Title**: *Building Setu (Part 1): Why Existing Disaster Mesh Apps Fail and How We Built a Zero-Grid Infrastructure for Smartphones*
- **Subtitle**: *Why Bridgefy and Meshtastic fail during real crises, and the architecture of a 100% serverless disaster response mesh.*
- **Tags**: `DisasterResponse`, `MeshNetworking`, `Android`, `OpenSource`, `EdgeAI`, `Python`
- **Canonical URL**: `https://github.com/charan-143/setu-zero-grid-disaster-mesh`

### Part 2:
- **Title**: *Building Setu (Part 2): Breaking the Silence — On-Device Indic SLMs and the "SAR-Tap" Seismic IMU Codec*
- **Subtitle**: *Turning phone accelerometers and microphones into seismic detectors to rescue trapped survivors who cannot speak.*
- **Tags**: `DigitalSignalProcessing`, `EdgeAI`, `Sensors`, `Android`, `Python`, `Algorithms`

### Part 3:
- **Title**: *Building Setu (Part 3): 12.4 Days Under Dark Rubble — The "Cryo-Sleep" Battery Stretcher*
- **Subtitle**: *How sensor-gated ultra-low duty cycling stretches a 15% phone battery to 12.4 days under collapsed concrete.*
- **Tags**: `EmbeddedSystems`, `BatteryOptimization`, `Mathematics`, `Android`, `Python`

### Part 4:
- **Title**: *Building Setu (Part 4): Penetrating Concrete with Ultrasonic Chirps and Defeating the Pre-Installation Paradox*
- **Subtitle**: *Bypassing 2.4 GHz RF shielding with 18.5 kHz sound waves and serving instant zero-install offline emergency PWAs.*
- **Tags**: `Networking`, `Acoustics`, `WebDev`, `Android`, `Python`, `Protocols`

### Part 5:
- **Title**: *Building Setu (Part 5): 3D Acoustic Rubble Triangulation and the Golden-Hour Vitality Decay Engine*
- **Subtitle**: *Pinpointing sub-surface burial depth in 3D using GCC-PHAT TDoA and optimizing rescue routes with physiological trauma decay.*
- **Tags**: `Acoustics`, `Mathematics`, `Optimization`, `Algorithms`, `Python`, `Healthcare`

---

## 💻 Source Code & Verification
All source code, test suites, and Android applications referenced in this series are open-source and verified:
- **Repository**: [https://github.com/charan-143/setu-zero-grid-disaster-mesh](https://github.com/charan-143/setu-zero-grid-disaster-mesh)
- **Unit Tests**: 122/122 passing (`python -m unittest discover tests`)
- **Android Target**: Android 8.0+ (API 26 to 36), Jetpack Compose, Kotlin 2.0
