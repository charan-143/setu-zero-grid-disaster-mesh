# Building Setu (Part 5): 3D Acoustic Rubble Triangulation and the Golden-Hour Vitality Decay Engine

> **Series**: Building Setu — Zero-Grid Disaster Mesh & Triage System  
> **Tags**: `Acoustics`, `Mathematics`, `Optimization`, `Algorithms`, `Python`, `Healthcare`  
> **Reading Time**: 11 mins  

---

## 1. The Sub-Surface Blindspot: When GPS Fails

When emergency dispatchers view a traditional disaster map, they see latitude and longitude pins. 

In a collapsed 8-story apartment complex, **a 2D GPS pin is completely useless**:
1. **GPS Does Not Work Indoors or Underground**: Satellite L-band signals (~1.5 GHz) attenuate immediately upon entering structural rubble. A buried phone's GPS reports a stale, inaccurate horizontal error of $\pm 50\text{ meters}$ and zero vertical accuracy.
2. **The 3rd Dimension is Life or Death**: Knowing a survivor is at `(20.2940° N, 85.8210° E)` does not tell rescue teams whether they are standing on the surface slab or pinned beneath **2.5 meters of collapsed reinforced concrete**. 
   - Digging from the wrong angle or miscalculating burial depth risks triggering secondary structural collapses with heavy hydraulic shears.

To solve this, Setu deploys **Multi-Receiver Ultrasonic Acoustic 3D TDoA Multilateration** (`transport/acoustic_tdoa_triangulator.py`).

---

## 2. Layer C: 3D Sub-Surface Acoustic Multilateration

When a buried phone emits its periodic 18.5 kHz ultrasonic chirp, ground responders or rescue drones place **3 to 4 surface receiver phones** (Mule nodes) across the rubble slab:

```
                               Surface Ground Receivers
                     [Mule 1] (0, 0, 0)          [Mule 2] (4.5, 0, 0)
                         \                            /
                          \                          /
                           \                        /
      ----------------------\----------------------/---------------------- Surface Slab
                             \                    /
                              \                  /
                               \    CONCRETE    /
                                \    RUBBLE    /
                                 \            /
                                  \          /
                                   v        v
                                [BURIED SURVIVOR]
                             Position: (X, Y, Z = -2.5m)
```

Because sound in air travels at a relatively leisurely speed ($v_s \approx 343.0\text{ m/s}$), an acoustic wave takes several milliseconds longer to reach one receiver than another. By measuring the **Time-Difference-of-Arrival (TDoA)** between pairs of receivers with sub-millisecond precision, we can solve non-linear hyperbolic intersection equations to pinpoint the exact 3D coordinates $(x, y, z)$ of the buried survivor.

### The Signal Processing Challenge: Reverberation in Concrete Voids
In a rubble pile, acoustic sound does not travel in an open vacuum; it bounces off slabs, steel pipes, and broken masonry, generating severe multipath reverberation peaks. Standard time-domain cross-correlation ($R_{xy}(\tau)$) fails because reflected echo peaks often exceed the direct line-of-sight arrival.

To overcome this, we implemented **Generalized Cross-Correlation with Phase Transform (GCC-PHAT)**:

$$\hat{G}_{\text{PHAT}}(f) = \frac{X_1(f) \cdot X_2^*(f)}{|X_1(f) \cdot X_2^*(f)|}$$

By dividing the cross-spectral density by its magnitude, GCC-PHAT **whitens the spectrum**, preserving only the pure phase delay information and collapsing multipath reverberation into a sharp, narrow Dirac-like correlation impulse.

We then apply **sub-sample parabolic interpolation** around the maximum peak to achieve sub-sample microsecond timing resolution:

```python
# In transport/acoustic_tdoa_triangulator.py
def parabolic_peak_refinement(corr: np.ndarray, peak_idx: int) -> float:
    """Computes continuous sub-sample offset using 3-point quadratic interpolation."""
    alpha = corr[peak_idx - 1]
    beta  = corr[peak_idx]
    gamma = corr[peak_idx + 1]
    delta = 0.5 * (alpha - gamma) / (alpha - 2.0 * beta + gamma)
    return float(peak_idx) + delta
```

### The 3D Hyperbolic Solver
For $N$ receivers located at known surface coordinates $S_i = (x_i, y_i, z_i)$, the range difference between receiver $i$ and reference receiver $0$ is:

$$d_{i0} = v_s \cdot \Delta \tau_{i0} = \|P - S_i\| - \|P - S_0\|$$

We formulate this as a non-linear optimization problem to minimize the residual root-mean-square error (RMSE):

$$\min_{P=(x, y, z)} \sum_{i=1}^{N-1} \left( \|P - S_i\| - \|P - S_0\| - d_{i0} \right)^2 \quad \text{subject to } z \le 0$$

The depth constraint ($z \le 0$) enforces that the source must lie beneath the surface slab.

### Output: Tactical Excavation Advisory
Rather than presenting raw mathematical matrices to stressed search teams, Setu outputs direct, actionable tactical orders:

> **[+] 3D Sub-Surface Fix ACQUIRED:**  
> **Relative Coordinates**: $X = +2.00\text{ m}, Y = +1.50\text{ m}, Z = -2.50\text{ m}$  
> **Absolute Burial Depth**: **2.50 METERS BENEATH SLAB**  
> **Multilateration Confidence**: **100.0%** (RMSE: $0.00\text{ cm}$)  
> **TACTICAL ADVISORY**: *"DIG DIRECTLY AT X=+2.0m, Y=+1.5m, TARGET DEPTH: 2.5 METERS BENEATH SLAB"*

---

## 3. Layer D: Beyond Static Triage Tags

Traditional disaster medicine relies on the START triage system: colored plastic ribbons attached to victims:
- **Red** (Immediate)
- **Yellow** (Delayed)
- **Green** (Minor)
- **Black** (Expectant)

The critical flaw in static triage is that **human trauma physiology is non-linear and time-decaying**:
- A victim with an uncontrolled femoral arterial bleed triaged as "Red" has a physiological window of **30 to 45 minutes** before hypovolemic cardiac arrest.
- A victim with a closed femoral fracture triaged as "Yellow" can wait **12 to 24 hours** without acute systemic failure.
- A 72-year-old diabetic victim in cold water submerged to the waist degrades from "Yellow" to "Imminent Collapse" in **under 3 hours**.

If an Incident Commander dispatches rescue teams alphabetically or purely by static "Red" tags, **victims with shorter survival windows die while teams attend to victims with longer survival margins**.

---

## 4. The Dynamic "Golden-Hour" Trauma Vitality Decay Engine

In `core/vitality_decay_engine.py`, we engineered a clinical trauma vitality decay engine grounded in Advanced Trauma Life Support (ATLS) and NDMA clinical emergency standards.

### The Mathematical Decay Function
The engine models a continuous vitality score $V(t) \in [1.0, 0.0]$:

$$V(t) = \max\left(0.0, \, 1.0 - \left( \frac{\Delta t}{\tau_{\text{base}} \cdot M_{\text{dem}} \cdot M_{\text{env}}} \right)^\gamma \right)$$

Where:
- $\Delta t$: Elapsed time since injury onset.
- $\tau_{\text{base}}$: Baseline clinical survival horizon:
  - **Arterial Bleeding**: $\sim 45\text{ mins}$ ($\tau = 2,700\text{ s}$)
  - **Tension Pneumothorax / Airway**: $\sim 90\text{ mins}$ ($\tau = 5,400\text{ s}$)
  - **Crush Syndrome / Rubble Pinning**: $\sim 5\text{ hours}$ ($\tau = 18,000\text{ s}$)
  - **Hypothermia / Flood Submergence**: $\sim 12\text{ hours}$ ($\tau = 43,200\text{ s}$)
  - **Insulin Dependency**: $\sim 24\text{ hours}$ ($\tau = 86,400\text{ s}$)
  - **Stable Fracture**: $\sim 72\text{ hours}$ ($\tau = 259,200\text{ s}$)
- $M_{\text{dem}}$: Demographic Vulnerability Multiplier:
  - Infant / Child: $0.65\times$
  - Elderly ($>65$): $0.70\times$
  - Pregnancy: $0.75\times$
- $M_{\text{env}}$: Environmental Penalty Multiplier:
  - Cold Rubble ($<15^\circ\text{C}$): $0.75\times$
  - Extreme Heat ($>38^\circ\text{C}$): $0.80\times$
  - Rubble Entrapment: $0.85\times$
- $\gamma$: Physiological steepness parameter ($\gamma = 1.25$ to $1.5$ reflecting rapid terminal decompensation).

### Real-Time Vitality & Urgency Ranking

Instead of a static list, Setu outputs dynamic, living countdown timers:

```
RANK | SEVERITY    | VITALITY | WINDOW REMAINING | LOCATION / INJURY
-----------------------------------------------------------------------------
#1   | [CRITICAL]  | 56.6%    | 00:09:16         | Urgent arterial bleed, 1 child
#2   | [DEGRADING] | 65.0%    | 00:49:42         | Flood rooftop, diabetic elderly
#3   | [DEGRADING] | 67.3%    | 00:51:28         | Trapped under slab, crush injury
#4   | [STABLE]    | 92.3%    | 14:15:07         | Closed tibia fracture, adult
```

A victim with only 9 minutes remaining is instantly ranked above a victim with 14 hours remaining, regardless of when their packets were received.

---

## 5. Multi-Team Priority Dispatch Optimization

Finally, given a fleet of $M$ available rescue teams (e.g., foot teams, rubber Zodiac boats, extraction vehicles) with varying transit speeds and physical locations, how should rescues be routed?

We formulated the **Multi-Team Dispatch Optimizer** (`MultiTeamDispatchOptimizer`):
- It solves a **deadline-constrained Knapsack/Vehicle Routing Problem (VRP)** using greedy deadline-first heuristic scheduling.
- The solver calculates transit time $t_{\text{transit}} = \frac{\text{Distance}}{\text{Speed}}$ and rescue operation time $t_{\text{op}}$ (e.g., 20 mins for simple evacuation, 45 mins for concrete extraction).
- It allocates targets to the fastest available team whose arrival time $t_{\text{arrival}} \le T_{\text{critical}}$, maximizing total lives saved before physiological collapse.

```python
# Automated Tactical Dispatch Output:
• Team 'ALPHA_BOAT_01' (Boat, 15 km/h): Dispatched to [Survivor_Bleed_01 -> Survivor_Voice_Rooftop]
• Team 'HEAVY_USAR_02' (Rescue Truck, 30 km/h): Dispatched to [Survivor_Rubble_Tap (Depth: -2.5m)]
```

---

## 6. The Complete System: Serverless, Open Source, and Operational

We built Setu not as a theoretical paper, but as a fully functioning, battle-tested codebase:
- **Zero Server Overhead**: The entire system runs 100% serverless peer-to-peer between Android devices via BLE 5.0 and ultrasonic chirps, and in a single CLI master orchestrator (`python main.py`) on PC.
- **Android App Deployed**: Native Jetpack Compose, Kotlin 2.0, Android SDK 36, operating with full hardware access on physical devices.
- **122 Automated Unit Tests**: Comprehensive mathematical, cryptographic, signal processing, and networking verification.

The entire project is open-source under MIT and ready for community contributions, research collaborations, and humanitarian deployment:

👉 **GitHub Repository**: **[https://github.com/charan-143/setu-zero-grid-disaster-mesh](https://github.com/charan-143/setu-zero-grid-disaster-mesh)**

---

*Thank you for following the Building Setu series. If you are working in disaster response, mesh networking, or humanitarian engineering, reach out and build with us.*
