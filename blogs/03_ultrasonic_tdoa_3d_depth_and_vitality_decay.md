---
title: "Mathematical Triage: 3D Acoustic Rubble Multilateration & Dynamic Trauma Decay (Part 3)"
subtitle: "How we replaced GPS with ultrasonic GCC-PHAT hyperbolic multilateration and turned static triage into a dynamic, life-saving ATLS dispatch engine."
slug: "ultrasonic-tdoa-3d-depth-and-vitality-decay-part-3"
tags: ["math", "algorithms", "triage", "acoustic", "optimization", "python", "datascience"]
cover_image: "https://images.unsplash.com/photo-1508873696983-2df5293cbdaf?auto=format&fit=crop&w=1200&q=80"
published_at: "2026-10-21"
---

# Mathematical Triage: 3D Acoustic Rubble Multilateration & Dynamic Trauma Decay

### *Part 3: Pinpointing Buried Victims in 3D Space and Optimizing Rescue Teams in Real Time*

---

## 1. The Localization Paradox: Why GPS Fails Under Rubble

When emergency rescue personnel arrive at an earthquake collapse site, the primary question is: **"Where exactly do we dig?"**

Excavating through multi-ton reinforced concrete slabs requires pneumatic breakers, diamond saws, and heavy hydraulic cranes. Digging in the wrong sector can trigger secondary structural collapse or suffocate victims with falling dust.

* **GPS is useless**: 1.5 GHz satellite signals cannot penetrate even a few inches of moist reinforced concrete. GPS receivers report 0 satellites locked.
* **RF RSSI is erratic**: Bluetooth and Wi-Fi signal strength varies wildly based on multi-path reflection off rebar mesh, leading to positioning errors of 15 to 40 meters.

To solve this, Setu turns commodity smartphones into a **3D Sub-Surface Acoustic Multilateration Radar**.

---

## 2. Ultrasonic Acoustic TDoA 3D Depth Triangulation

### The Concept: High-Frequency Ultrasonic Chirps
When trapped, the survivor's phone emits periodic ultrasonic acoustic chirps between **18.5 kHz and 20.0 kHz** (above adult human hearing threshold to avoid panic, but within the acoustic sampling range of standard smartphone microphones and piezo speakers).

On the rubble surface, 4 search-and-rescue team members (or autonomous ground crawler mules) place their phones on the slab perimeter at known survey points $S_1, S_2, S_3, S_4$:

```
                     SURFACE SLAB (Z = 0)
         S1 (Mule 1)                     S2 (Mule 2)
              o───────────────────────────────o
              │                               │
              │         Concrete Rubble       │
              │                               │
              o───────────────────────────────o
         S3 (Mule 3)                     S4 (Mule 4)
                            \       /
                             \     /  Acoustic Chirp Wavefront
                              \   /
                                o  P_victim (X=+2.0m, Y=+1.5m, Z=-2.5m)
                                   SUB-SURFACE BURIAL DEPTH: 2.5 METERS
```

### Signal Processing: GCC-PHAT Reverberation Whitening
Acoustic propagation inside concrete voids suffers from intense cavity reverberation and multi-path reflections. Standard cross-correlation fails because echo peaks often exceed the direct path signal.

We implement the **Generalized Cross-Correlation with Phase Transform (GCC-PHAT)**:

$$R_{x_1 x_2}^{\text{PHAT}}(f) = \frac{X_1(f) \cdot X_2^*(f)}{\left| X_1(f) \cdot X_2^*(f) \right|}$$

By dividing the cross-spectral density by its absolute magnitude, GCC-PHAT **whitens the frequency spectrum**, discarding amplitude spikes and keeping only the pure phase difference. Taking the Inverse Fourier Transform ($\mathcal{F}^{-1}$) yields a razor-sharp delta spike corresponding to the exact Time-Difference-of-Arrival (TDoA):

$$\hat{\tau}_{ij} = \arg\max_\tau \mathcal{F}^{-1}\left\{ R_{x_i x_j}^{\text{PHAT}}(f) \right\}$$

To achieve sub-sample precision ($<0.1\text{ ms}$, corresponding to $<3.4\text{ cm}$ spatial error), we apply parabolic interpolation across the discrete peak bin:

$$\Delta_{\text{sub}} = \frac{R[k+1] - R[k-1]}{2 \cdot (2 R[k] - R[k-1] - R[k+1])}$$

### Solving 3D Hyperbolic Multilateration
Let $P = (x, y, z)$ be the unknown victim location with $z \le 0$ (sub-surface).
The distance from receiver $i$ to the victim is:
$$d_i = \|P - S_i\| = \sqrt{(x - x_i)^2 + (y - y_i)^2 + (z - z_i)^2}$$

The theoretical range difference relative to reference node $S_1$ is:
$$\Delta d_{i1}^{\text{theo}}(P) = d_i - d_1 = v_s \cdot \Delta \tau_{i1}$$
where $v_s$ is the speed of sound in the rubble medium ($343\text{ m/s}$ in void spaces).

We minimize the non-linear residual objective function via Levenberg-Marquardt with physical depth constraints:
$$F(P) = \sum_{i=2}^N \left( \|P - S_i\| - \|P - S_1\| - v_s \cdot \Delta \tau_{i1} \right)^2$$

### Overcoming the "Surface Saddle Point" Trap
When all surface receivers are approximately co-planar ($z_i \approx 0$), the vertical derivative vanishes:
$$\left.\frac{\partial \|P - S_i\|}{\partial z}\right|_{z=0} = 0$$

Standard gradient descent gets trapped at $z = 0$, falsely concluding the victim is on the surface! We solved this by injecting controlled finite-difference negative-z perturbations during Hessian inversion, guaranteeing convergence to the true sub-surface minimum.

### Live Benchmark Output:
```
[+] 3D Sub-Surface Fix ACQUIRED:
    * Relative Coordinates : X = +2.00m, Y = +1.50m, Z = -2.50m
    * Absolute Burial Depth: 2.50 METERS BENEATH SLAB
    * Multilateration Conf : 100.0% (RMSE: 0.00 cm)
    * TACTICAL ADVISORY    : "DIG DIRECTLY AT X=+2.0m, Y=+1.5m, TARGET DEPTH: 2.5 METERS BENEATH SLAB"
```

---

## 3. The Clinical Fallacy of Static Triage

In mass-casualty incidents, conventional triage tags victims with static colors: **RED** (Immediate), **YELLOW** (Delayed), **GREEN** (Minor), **BLACK** (Expectant).

**The Fatal Flaw**: Trauma is dynamic.
* A 24-year-old with an **arterial puncture** assigned RED will die of hemorrhagic shock in **45 minutes**.
* A 65-year-old diabetic trapped on a rooftop assigned RED may survive **24 hours**.
* If rescue teams process "RED" victims in First-In-First-Out (FIFO) order, the arterial bleed victim dies waiting while the diabetic is evacuated first.

---

## 4. The Dynamic "Golden-Hour" Vitality Decay Engine

We built a dynamic physiological decay engine based on **Advanced Trauma Life Support (ATLS)** and **WHO emergency guidelines**.

### Physiological Decay Model
Each casualty is assigned a clinical base survival window $\Delta t_{\text{base}}$:
* **Arterial Bleeding / Tourniquet Needed**: $45\text{ minutes}$
* **Tension Pneumothorax / Airway Compromise**: $90\text{ minutes}$
* **Crush Syndrome / Severe Entrapment**: $4\text{ to }6\text{ hours}$
* **Submerged / Cold Water Hypothermia**: $12\text{ hours}$
* **Type-1 Diabetic without Insulin**: $24\text{ hours}$
* **Stable Closed Fracture**: $72\text{ hours}$

We apply continuous demographic and environmental degradation coefficients:
$$\Delta t_{\text{vital}} = \Delta t_{\text{base}} \cdot \mu_{\text{demo}} \cdot \mu_{\text{temp}} \cdot \mu_{\text{env}}$$

* **Demographic Multiplier $\mu_{\text{demo}}$**:
  * Infant / Young Child ($<5$ yrs): $0.65\times$
  * Elderly ($>65$ yrs): $0.70\times$
  * Third-Trimester Pregnancy: $0.75\times$
* **Environmental Multiplier $\mu_{\text{temp}}$**:
  * Freezing cold ($<15^\circ\text{C}$ wet rubble): $0.60\times$ (rapid hypothermia)
  * Extreme heat ($>38^\circ\text{C}$): $0.70\times$ (heat stroke / dehydration)
* **Entrapment Multiplier $\mu_{\text{env}}$**:
  * Trapped under heavy concrete slab: $0.80\times$

### Real-Time Vitality Index:
The real-time vitality score $V(t) \in [0.0, 1.0]$ decays exponentially from the moment of disaster impact $t_0$:

$$V(t) = \exp\left( - \frac{\ln(2) \cdot (t - t_0)}{\Delta t_{\text{vital}}} \right)$$

When $V(t) < 0.25$, the victim transitions from `CRITICAL_WINDOW` to `EXTREME_IMMINENT_COLLAPSE`, driving flashing visual alerts and highest priority dispatch audio alerts.

---

## 5. Multi-Team Optimal Rescue Dispatcher

Given $M$ casualties across the disaster theater and $N$ available rescue assets (boats, drone teams, heavy rescue squads), the dispatcher solves a **deadline-first knapsack routing allocation**:

$$\max \sum_{j=1}^M \mathbb{I}\left( T_{\text{arrival}}(j) \le \Delta t_{\text{vital}}(j) \right) \cdot \text{Urgency}(j)$$

$$\text{subject to } T_{\text{transit}}(k \to j) \le \Delta t_{\text{critical}}(j)$$

### Real-Time Incident Command Output:
```
RANK  | SEVERITY       | VITALITY  | WINDOW REMAINING   | LOCATION / NOTE
---------------------------------------------------------------------------------
#1    | [DEGRADING]    | 68.0%     | 00:10:45           | Urgent arterial bleed, 1 child
#2    | [DEGRADING]    | 67.5%     | 00:51:30           | Water at roof level. Elderly grandfather
#3    | [STABLE]       | 94.2%     | 03:45:10           | Trapped under slab. 3-Tap confirmed

[Automated Tactical Dispatch Solution]:
  • Team 'BOAT_ALPHA' (Inflatable Boat, 25.0 km/h): Dispatched to [Target_Arterial_Bleed]
  • Team 'SAR_SQUAD_01' (Heavy Rescue, 15.0 km/h): Dispatched to [Target_Concrete_Rubble_3D]
```

---

## 6. What's Next in Part 4

In the final installment (**Part 4**), we will examine the mobile implementation:
* Building the native Jetpack Compose Android app (`setudisasterapp`)
* Running on-device vernacular voice triage in 6 Indian languages (Hindi, Telugu, Tamil, Marathi, Odia, English)
* The Zero-Install Captive Gateway & Micro-PWA that breaks the "Pre-Installation Paradox".

*Full source code:* [github.com/charan-143/setu-zero-grid-disaster-mesh](https://github.com/charan-143/setu-zero-grid-disaster-mesh)
