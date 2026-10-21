"""
Dynamic 'Golden Hour' Vitality Decay & Tactical Dispatch Engine
Based on WHO / ATLS (Advanced Trauma Life Support) & NDMA Emergency Guidelines.

Models continuous physiological trauma degradation under disaster conditions
and solves deadline-first multi-team rescue dispatch optimization.
"""

import math
import time
from typing import Dict, Any, List, Optional, Tuple


# =============================================================================
# Trauma Profiles & Base Survival Horizons (in seconds)
# =============================================================================
# WHO/ATLS Golden Hour standards:
# - Arterial Bleed / Massive Hemorrhage: ~45 min (2,700s)
# - Tension Pneumothorax / Airway Obstruction / O2 failure: ~90 min (5,400s)
# - Snakebite Envenomation: ~4 hrs (14,400s)
# - Crush Syndrome (Rhabdomyolysis / Compartment): ~5 hrs (4-6 hrs: 18,000s)
# - Hypothermia / Submerged / Flood Immersion: ~12 hrs (43,200s)
# - Insulin / Dialysis Dependence: ~24 hrs (86,400s)
# - Stable Fracture / Closed Orthopedic Trauma: ~72 hrs (259,200s)
# - Minor / Default Trauma Horizon: ~72 hrs (259,200s)

WINDOW_ARTERIAL_BLEED = 45 * 60          # 2,700 s
WINDOW_TENSION_PNEUMO_AIRWAY = 90 * 60   # 5,400 s
WINDOW_SNAKEBITE = 4 * 3600              # 14,400 s
WINDOW_CRUSH_SYNDROME = 5 * 3600         # 18,000 s (4-6 hours)
WINDOW_HYPOTHERMIA_SUBMERGED = 12 * 3600 # 43,200 s
WINDOW_INSULIN_DIALYSIS = 24 * 3600      # 86,400 s
WINDOW_STABLE_FRACTURE = 72 * 3600       # 259,200 s
WINDOW_DEFAULT = 72 * 3600              # 259,200 s

# =============================================================================
# Demographic Multipliers (Accelerated Metabolic / Decompensation Rates)
# =============================================================================
DEMO_MULT_CHILD = 0.65       # Infants & Children (<12 yrs): faster shock / heat loss
DEMO_MULT_ELDERLY = 0.70     # Geriatric (>65 yrs): compromised cardiovascular reserve
DEMO_MULT_PREGNANCY = 0.75   # Pregnancy: increased cardiac output, dual oxygen demand

# =============================================================================
# Environmental Multipliers
# =============================================================================
ENV_MULT_WET_COLD = 0.75      # Ambient temp < 15°C (Wet Cold / Hypothermia risk)
ENV_MULT_HYPERTHERMIA = 0.80  # Ambient temp > 38°C (Extreme Heat / Heatstroke risk)
ENV_MULT_SUBMERGED = 0.70     # Partial or complete immersion in water
ENV_MULT_FLOOD_ROOF = 0.80    # Flood rooftop / water ingress surrounding
ENV_MULT_CONCRETE_RUBBLE = 0.70  # Trapped under structural concrete rubble / debris

# =============================================================================
# Survival States
# =============================================================================
STATE_STABLE = "STABLE"
STATE_DEGRADING = "DEGRADING"
STATE_CRITICAL_WINDOW = "CRITICAL_WINDOW"
STATE_EXTREME_IMMINENT_COLLAPSE = "EXTREME_IMMINENT_COLLAPSE"
STATE_EXPECTANT = "EXPECTANT"


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates geodesic distance in meters between two lat/lon coordinates."""
    R = 6371000.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2 - lat1))
    delta_lambda = math.radians(float(lon2 - lon1))

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2))
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return R * c


def format_seconds(seconds: Optional[float]) -> str:
    """Formats seconds into human-readable HH:MM:SS or MM:SS."""
    if seconds is None or not isinstance(seconds, (int, float)):
        return "00:00:00"
    if math.isnan(seconds) or math.isinf(seconds) or seconds <= 0:
        return "00:00:00"
    secs = int(round(seconds))
    hours = secs // 3600
    minutes = (secs % 3600) // 60
    s = secs % 60
    return f"{hours:02d}:{minutes:02d}:{s:02d}"


class VitalityDecayEngine:
    """
    Physiological trauma decay engine implementing WHO/ATLS/NDMA emergency golden-hour curves.
    Evaluates real-time survivability horizons and global rescue urgency scores.
    """

    @classmethod
    def determine_trauma_profile(cls, victim_data: Dict[str, Any]) -> Tuple[str, float]:
        """
        Determines the most critical trauma profile and its base survival window.
        Returns: (trauma_label, base_window_seconds)
        """
        med_flags = victim_data.get("medical_flags", {})
        note = str(victim_data.get("note", "")).lower()
        disaster_type = victim_data.get("disaster_type", -1)
        disaster_label = str(victim_data.get("disaster_label", "")).upper()

        # 1. Arterial Bleeding / Massive Hemorrhage (~45 min)
        if (isinstance(med_flags, dict) and med_flags.get("bleeding")) or \
           any(w in note for w in ["arterial", "artery", "severe bleed", "gushing", "khoon", "bleeding profusely"]):
            return "ARTERIAL_BLEED", float(WINDOW_ARTERIAL_BLEED)

        # 2. Tension Pneumothorax / Acute Airway Obstruction (~90 min)
        if (isinstance(med_flags, dict) and med_flags.get("oxygen_needed")) or \
           any(w in note for w in ["tension pneumo", "airway", "choking", "suffocating", "cyanosis", "cannot breathe", "stridor"]):
            return "TENSION_PNEUMO_AIRWAY", float(WINDOW_TENSION_PNEUMO_AIRWAY)

        # 3. Snakebite Envenomation (~4 hrs)
        if (isinstance(med_flags, dict) and med_flags.get("snakebite")) or \
           any(w in note for w in ["snake", "saap", "bite", "venom"]):
            return "SNAKEBITE", float(WINDOW_SNAKEBITE)

        # 4. Crush Syndrome / Trapped Debris (~5 hrs: 4-6 hrs)
        if (isinstance(med_flags, dict) and med_flags.get("crush_injury")) or \
           victim_data.get("is_trapped") or \
           disaster_type == 5 or disaster_label in ["COLLAPSE", "BUILDING_COLLAPSE", "EARTHQUAKE"] or \
           any(w in note for w in ["crush", "compartment", "pinned under", "malba", "debris"]):
            return "CRUSH_SYNDROME", float(WINDOW_CRUSH_SYNDROME)

        # 5. Hypothermia / Submerged / Flood Ingress (~12 hrs)
        if disaster_type == 0 or disaster_label == "FLOOD" or \
           any(w in note for w in ["submerged", "hypothermia", "freezing", "water", "flood", "doob", "roof", "shivering"]):
            return "HYPOTHERMIA_SUBMERGED", float(WINDOW_HYPOTHERMIA_SUBMERGED)

        # 6. Insulin / Dialysis Dependence (~24 hrs)
        if isinstance(med_flags, dict) and (med_flags.get("insulin") or med_flags.get("dialysis")):
            return "INSULIN_DIALYSIS", float(WINDOW_INSULIN_DIALYSIS)
        if any(w in note for w in ["insulin", "dialysis", "kidney", "sugar", "diabetic"]):
            return "INSULIN_DIALYSIS", float(WINDOW_INSULIN_DIALYSIS)

        # 7. Stable Fracture (~72 hrs)
        if (isinstance(med_flags, dict) and med_flags.get("fracture")) or \
           any(w in note for w in ["fracture", "broken leg", "broken arm", "haddi", "bone"]):
            return "STABLE_FRACTURE", float(WINDOW_STABLE_FRACTURE)

        # Default / Minor Trauma
        severity = victim_data.get("severity", 0)
        if severity == 2:  # RED without specified flags
            return "CRITICAL_UNSPECIFIED", float(WINDOW_TENSION_PNEUMO_AIRWAY)
        elif severity == 1:  # YELLOW
            return "DELAYED_UNSPECIFIED", float(WINDOW_INSULIN_DIALYSIS)

        return "DEFAULT_TRAUMA", float(WINDOW_DEFAULT)

    @classmethod
    def calculate_demographic_multiplier(cls, victim_data: Dict[str, Any]) -> float:
        """
        Calculates demographic multiplier:
        - Children/Infants: 0.65x
        - Elderly: 0.70x
        - Pregnancy: 0.75x
        If multiple factors exist, applies compounded multiplier with a safe clinical floor (0.35).
        """
        demo = victim_data.get("demographics")
        if demo is None and "raw_binary_hex" in victim_data:
            try:
                from core.sos_packet import unpack_sos_packet
                raw_b = bytes.fromhex(victim_data["raw_binary_hex"])
                if len(raw_b) == 120:
                    unp = unpack_sos_packet(raw_b)
                    demo = unp.get("demographics", {})
            except Exception:
                demo = {}
        if not isinstance(demo, dict):
            demo = {}

        med_flags = victim_data.get("medical_flags", {})
        note = str(victim_data.get("note", "")).lower()

        factors = []
        # Children / Infant
        has_children = False
        if demo.get("children", 0) > 0 or victim_data.get("children", 0) > 0:
            has_children = True
        elif any(w in note for w in ["child", "children", "baby", "infant", "kid", "baccha", "bacche"]):
            has_children = True
        if has_children:
            factors.append(DEMO_MULT_CHILD)

        # Elderly
        has_elderly = False
        if demo.get("elderly", 0) > 0 or victim_data.get("elderly", 0) > 0:
            has_elderly = True
        elif any(w in note for w in ["elderly", "bujurg", "old", "grandfather", "grandmother"]):
            has_elderly = True
        if has_elderly:
            factors.append(DEMO_MULT_ELDERLY)

        # Pregnancy
        is_pregnant = False
        if isinstance(med_flags, dict) and med_flags.get("pregnancy"):
            is_pregnant = True
        elif any(w in note for w in ["pregnant", "pregnancy", "garbhwati", "labor"]):
            is_pregnant = True
        if is_pregnant:
            factors.append(DEMO_MULT_PREGNANCY)

        if not factors:
            return 1.0

        # Composite product of all applicable factors, floored at 0.35
        multiplier = 1.0
        for f in factors:
            multiplier *= f
        return round(max(0.35, multiplier), 4)

    @classmethod
    def calculate_environmental_multiplier(
        cls,
        victim_data: Dict[str, Any],
        ambient_temp_c: float = 25.0,
        water_ingress: bool = False
    ) -> float:
        """
        Calculates environmental multiplier:
        - Ambient temp: <15°C wet cold (0.75x) or >38°C hyperthermia (0.80x)
        - Water ingress / flood rooftop status: (0.80x, submerged 0.70x)
        - Trapped under concrete rubble: (0.70x)
        """
        multiplier = 1.0
        note = str(victim_data.get("note", "")).lower()
        disaster_type = victim_data.get("disaster_type", -1)
        disaster_label = str(victim_data.get("disaster_label", "")).upper()

        # 1. Temperature Multiplier
        temp = victim_data.get("ambient_temp_c", ambient_temp_c)
        if temp < 15.0 or any(w in note for w in ["freezing", "hypothermia", "cold", "shivering"]):
            multiplier *= ENV_MULT_WET_COLD
        elif temp > 38.0 or any(w in note for w in ["heatstroke", "burning", "hyperthermia", "scorching"]):
            multiplier *= ENV_MULT_HYPERTHERMIA

        # 2. Water Ingress / Submerged Status
        is_submerged = any(w in note for w in ["submerged", "underwater", "in water", "drowning"])
        has_water = water_ingress or victim_data.get("water_ingress", False) or \
                    disaster_type == 0 or disaster_label == "FLOOD" or \
                    any(w in note for w in ["flood", "water", "paani", "doob", "roof", "rooftop"])
        if is_submerged:
            multiplier *= ENV_MULT_SUBMERGED
        elif has_water:
            multiplier *= ENV_MULT_FLOOD_ROOF

        # 3. Trapped Concrete Rubble Debris
        is_trapped_rubble = bool(victim_data.get("is_trapped")) or \
                            disaster_type == 5 or disaster_label in ["COLLAPSE", "BUILDING_COLLAPSE", "EARTHQUAKE"] or \
                            any(w in note for w in ["rubble", "concrete", "malba", "pinned under", "collapsed building", "debris"])
        if is_trapped_rubble:
            multiplier *= ENV_MULT_CONCRETE_RUBBLE

        return round(max(0.20, multiplier), 4)

    @classmethod
    def calculate_decay(
        cls,
        base_window_s: float,
        demo_mult: float,
        env_mult: float,
        elapsed_s: float,
        severity: int = 0
    ) -> Tuple[float, float, str, float]:
        """
        Calculates (vitality_score, time_to_critical_seconds, survival_state, urgency_index).
        """
        # If victim was flagged EXPECTANT / BLACK originally
        if severity == 3:
            return 0.0, 0.0, STATE_EXPECTANT, 5.0

        effective_horizon = max(60.0, base_window_s * demo_mult * env_mult)
        time_to_critical = max(0.0, effective_horizon - elapsed_s)

        # Vitality score: 1.0 (peak) continuous decay to 0.0
        if effective_horizon > 0:
            fraction_remaining = time_to_critical / effective_horizon
            vitality = round(max(0.0, min(1.0, fraction_remaining)), 4)
        else:
            vitality = 0.0

        # Survival State
        if vitality <= 0.0 or time_to_critical <= 0.0:
            survival_state = STATE_EXPECTANT
        elif vitality < 0.20:
            survival_state = STATE_EXTREME_IMMINENT_COLLAPSE
        elif vitality < 0.50:
            survival_state = STATE_CRITICAL_WINDOW
        elif vitality < 0.80:
            survival_state = STATE_DEGRADING
        else:
            survival_state = STATE_STABLE

        # Urgency Index (0 to 100)
        urgency = cls._compute_urgency_index(
            vitality=vitality,
            time_to_critical_s=time_to_critical,
            effective_horizon_s=effective_horizon,
            survival_state=survival_state,
            base_window_s=base_window_s
        )

        return vitality, round(time_to_critical, 1), survival_state, urgency

    @classmethod
    def _compute_urgency_index(
        cls,
        vitality: float,
        time_to_critical_s: float,
        effective_horizon_s: float,
        survival_state: str,
        base_window_s: float
    ) -> float:
        """
        Computes dynamic numerical urgency score (0.0 to 100.0).
        High values indicate high priority for immediate dispatch.
        """
        if survival_state == STATE_EXPECTANT:
            # In mass triage, non-salvageable deceased/expectant are deprioritized relative to salvageable critical
            return 5.0

        score = 0.0

        # 1. Absolute Window Urgency (0 - 45 pts)
        if time_to_critical_s <= 1800:     # <= 30 min
            score += 45.0
        elif time_to_critical_s <= 3600:   # <= 1 hr
            score += 38.0
        elif time_to_critical_s <= 7200:   # <= 2 hrs
            score += 30.0
        elif time_to_critical_s <= 18000:  # <= 5 hrs
            score += 22.0
        elif time_to_critical_s <= 43200:  # <= 12 hrs
            score += 15.0
        elif time_to_critical_s <= 86400:  # <= 24 hrs
            score += 8.0
        else:
            score += 3.0

        # 2. Trauma Acuteness Weight (0 - 30 pts)
        if base_window_s <= WINDOW_ARTERIAL_BLEED:
            score += 30.0
        elif base_window_s <= WINDOW_TENSION_PNEUMO_AIRWAY:
            score += 25.0
        elif base_window_s <= WINDOW_SNAKEBITE:
            score += 20.0
        elif base_window_s <= WINDOW_CRUSH_SYNDROME:
            score += 18.0
        elif base_window_s <= WINDOW_HYPOTHERMIA_SUBMERGED:
            score += 12.0
        elif base_window_s <= WINDOW_INSULIN_DIALYSIS:
            score += 8.0
        else:
            score += 3.0

        # 3. Vitality Depletion / Proximity to Collapse (0 - 25 pts)
        deficit = 1.0 - vitality
        score += deficit * 25.0

        return round(max(0.0, min(100.0, score)), 1)

    @classmethod
    def assess_victim(
        cls,
        victim_data: Dict[str, Any],
        current_time: Optional[float] = None,
        ambient_temp_c: float = 25.0,
        water_ingress: bool = False
    ) -> Dict[str, Any]:
        """
        Runs complete vitality assessment on a victim record or SOS packet.
        """
        now = time.time() if current_time is None else current_time
        pkt_time = victim_data.get("timestamp", now)
        elapsed_s = max(0.0, now - pkt_time)

        trauma_label, base_window = cls.determine_trauma_profile(victim_data)
        demo_mult = cls.calculate_demographic_multiplier(victim_data)
        env_mult = cls.calculate_environmental_multiplier(
            victim_data,
            ambient_temp_c=ambient_temp_c,
            water_ingress=water_ingress
        )

        severity = victim_data.get("severity", 0)
        effective_horizon = round(base_window * demo_mult * env_mult, 1)

        # Respect explicit time_to_critical_seconds if caller provided it without a timestamp
        if "time_to_critical_seconds" in victim_data and "timestamp" not in victim_data:
            time_to_critical = max(0.0, float(victim_data["time_to_critical_seconds"]))
            if effective_horizon > 0:
                vitality = victim_data.get("vitality_score", round(max(0.0, min(1.0, time_to_critical / effective_horizon)), 4))
            else:
                vitality = 0.0
            if vitality <= 0.0 or time_to_critical <= 0.0 or severity == 3:
                state = STATE_EXPECTANT
            elif vitality < 0.20:
                state = STATE_EXTREME_IMMINENT_COLLAPSE
            elif vitality < 0.50:
                state = STATE_CRITICAL_WINDOW
            elif vitality < 0.80:
                state = STATE_DEGRADING
            else:
                state = STATE_STABLE
            urgency = victim_data.get("urgency_index", cls._compute_urgency_index(
                vitality=vitality,
                time_to_critical_s=time_to_critical,
                effective_horizon_s=effective_horizon,
                survival_state=state,
                base_window_s=base_window
            ))
        else:
            vitality, time_to_critical, state, urgency = cls.calculate_decay(
                base_window_s=base_window,
                demo_mult=demo_mult,
                env_mult=env_mult,
                elapsed_s=elapsed_s,
                severity=severity
            )

        result = dict(victim_data)
        result.update({
            "trauma_type": trauma_label,
            "base_window_seconds": base_window,
            "demographic_multiplier": demo_mult,
            "environmental_multiplier": env_mult,
            "effective_horizon_seconds": effective_horizon,
            "elapsed_seconds": round(elapsed_s, 1),
            "vitality_score": vitality,
            "time_to_critical_seconds": time_to_critical,
            "time_to_critical_formatted": format_seconds(time_to_critical),
            "survival_state": state,
            "urgency_index": urgency
        })
        return result

    @classmethod
    def rank_victims(
        cls,
        victims: List[Dict[str, Any]],
        current_time: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Assesses and ranks all victims by urgency index descending,
        and assigns real-time urgency rank.
        """
        assessed = [cls.assess_victim(v, current_time=current_time) for v in victims]
        # Sort primarily by urgency_index descending, secondarily by time_to_critical ascending
        assessed.sort(key=lambda x: (-x["urgency_index"], x["time_to_critical_seconds"]))

        for rank, v in enumerate(assessed, start=1):
            v["urgency_rank"] = rank

        return assessed


# =============================================================================
# Dynamic Multi-Team Priority Dispatch Optimizer
# =============================================================================

class MultiTeamDispatchOptimizer:
    """
    Deadline-first vehicle routing & knapsack allocation optimizer.
    Assigns N rescue teams (boats, ambulances, drones) to victims to maximize
    lives saved before their individual golden-hour deadlines expire.
    """

    @classmethod
    def default_rescue_fleet(cls, base_lat: float = 20.2900, base_lon: float = 85.8200) -> List[Dict[str, Any]]:
        """Returns standard emergency rescue teams if none specified."""
        return [
            {
                "team_id": "NDRF-QuickResponse-Boat-1",
                "team_type": "BOAT",
                "latitude": base_lat,
                "longitude": base_lon,
                "speed_kmh": 35.0,
                "capacity": 8,
                "service_time_seconds": 300.0
            },
            {
                "team_id": "SDRF-Paramedic-Ambulance-1",
                "team_type": "AMBULANCE",
                "latitude": base_lat,
                "longitude": base_lon,
                "speed_kmh": 45.0,
                "capacity": 4,
                "service_time_seconds": 300.0
            },
            {
                "team_id": "SAR-Triage-Drone-Alpha",
                "team_type": "DRONE",
                "latitude": base_lat,
                "longitude": base_lon,
                "speed_kmh": 60.0,
                "capacity": 2,
                "service_time_seconds": 120.0
            }
        ]

    @classmethod
    def optimize_dispatch(
        cls,
        victims: List[Dict[str, Any]],
        rescue_teams: Optional[List[Dict[str, Any]]] = None,
        base_lat: float = 20.2900,
        base_lon: float = 85.8200,
        current_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Solves multi-team rescue assignment:
        - Prioritizes victims by earliest critical deadline and urgency index.
        - Routes teams so that victims with critical windows are reached before expiry.
        - Generates step-by-step waypoint assignments with ETA, distance, and survival status.
        """
        if current_time is None:
            current_time = time.time()

        if rescue_teams is None or len(rescue_teams) == 0:
            teams_pool = cls.default_rescue_fleet(base_lat, base_lon)
        else:
            teams_pool = [dict(t) for t in rescue_teams]

        # 1. Assess and rank all victims
        assessed_victims = VitalityDecayEngine.rank_victims(victims, current_time=current_time)

        if not assessed_victims:
            return {
                "total_victims": 0,
                "total_saved": 0,
                "total_expired": 0,
                "lives_saved_percentage": 100.0,
                "team_assignments": {},
                "unassigned_victims": []
            }

        # 2. Partition into salvageable candidates vs expectant/non-urgent
        # Sort salvageable candidates strictly by deadline (time_to_critical_seconds ascending), then urgency
        salvageable = [v for v in assessed_victims if v["survival_state"] != STATE_EXPECTANT and v["time_to_critical_seconds"] > 0]
        salvageable.sort(key=lambda x: (x["time_to_critical_seconds"], -x["urgency_index"]))

        expectant_or_expired = [v for v in assessed_victims if v not in salvageable]

        # Setup tracking state for each team
        teams_state: Dict[str, Dict[str, Any]] = {}
        for t in teams_pool:
            t_id = t["team_id"]
            speed_kmh = float(t.get("speed_kmh", 30.0))
            if speed_kmh <= 0.0:
                speed_mps = 0.0
            else:
                speed_mps = speed_kmh * 1000.0 / 3600.0

            teams_state[t_id] = {
                "config": t,
                "team_id": t_id,
                "team_type": t.get("team_type", "RESCUE_UNIT"),
                "curr_lat": float(t.get("latitude", base_lat)),
                "curr_lon": float(t.get("longitude", base_lon)),
                "curr_time_s": 0.0,
                "speed_mps": speed_mps,
                "capacity": max(0, int(t.get("capacity", 6))),
                "service_time_s": float(t.get("service_time_seconds", 300.0)),
                "route": [],
                "total_distance_m": 0.0,
                "saved_count": 0,
                "expired_count": 0
            }

        unassigned = []
        assigned_ids = set()
        unreachable_salvageable = []

        # 3. Greedy Deadline-First Multi-Team Allocation
        # Iterate over salvageable victims in order of their urgency deadline
        for victim in salvageable:
            v_id = victim.get("device_hash") or victim.get("id") or f"victim_{victim.get('latitude')}_{victim.get('longitude')}"
            v_lat = float(victim.get("latitude") if victim.get("latitude") is not None else base_lat)
            v_lon = float(victim.get("longitude") if victim.get("longitude") is not None else base_lon)
            if v_lat == 0.0 and v_lon == 0.0:
                v_lat, v_lon = base_lat, base_lon

            v_deadline = float(victim["time_to_critical_seconds"])
            headcount = victim.get("total_headcount", victim.get("demographics", {}).get("total_headcount", 1)) if isinstance(victim.get("demographics"), dict) else victim.get("total_headcount", 1)

            best_team_id = None
            best_eta = float("inf")
            best_dist = 0.0

            # Find the best team that can reach this victim before their deadline
            for t_id, state in teams_state.items():
                if len(state["route"]) >= state["capacity"]:
                    continue

                dist_m = haversine_distance_meters(state["curr_lat"], state["curr_lon"], v_lat, v_lon)
                if state["speed_mps"] <= 0.0:
                    transit_s = float("inf") if dist_m > 10.0 else 0.0
                else:
                    transit_s = dist_m / state["speed_mps"]
                arrival_s = state["curr_time_s"] + transit_s

                # Check deadline feasibility
                if arrival_s <= v_deadline:
                    # Prefer the team that arrives earliest (or with best margin)
                    if arrival_s < best_eta:
                        best_eta = arrival_s
                        best_team_id = t_id
                        best_dist = dist_m

            # If a team can reach in time, assign to maximize lives saved!
            if best_team_id is not None:
                state = teams_state[best_team_id]
                transit_s = (best_dist / state["speed_mps"]) if state["speed_mps"] > 0 else 0.0
                arrival_s = state["curr_time_s"] + transit_s
                status = "SAVED"

                # Estimated vitality score at arrival
                eff_horizon = victim.get("effective_horizon_seconds", v_deadline)
                elapsed_at_arrival = victim.get("elapsed_seconds", 0.0) + arrival_s
                if eff_horizon > 0:
                    vitality_at_arrival = round(max(0.0, min(1.0, 1.0 - (elapsed_at_arrival / eff_horizon))), 4)
                else:
                    vitality_at_arrival = 0.0

                step_num = len(state["route"]) + 1
                waypoint = {
                    "step_number": step_num,
                    "victim_id": v_id,
                    "latitude": v_lat,
                    "longitude": v_lon,
                    "coordinates": [v_lat, v_lon],
                    "leg_distance_m": round(best_dist, 1),
                    "transit_time_seconds": round(transit_s, 1),
                    "eta_seconds": round(arrival_s, 1),
                    "eta_formatted": format_seconds(arrival_s),
                    "time_to_critical_at_arrival": round(max(0.0, v_deadline - arrival_s), 1),
                    "vitality_at_arrival": vitality_at_arrival,
                    "survival_status_at_arrival": status,
                    "saved": True,
                    "headcount": headcount,
                    "trauma_type": victim.get("trauma_type", "UNKNOWN"),
                    "severity_label": victim.get("severity_label", "RED"),
                    "disaster_label": victim.get("disaster_label", "DISASTER"),
                    "urgency_index": victim.get("urgency_index", 50.0),
                    "note": victim.get("note", "")
                }

                state["route"].append(waypoint)
                state["curr_lat"] = v_lat
                state["curr_lon"] = v_lon
                state["curr_time_s"] = arrival_s + state["service_time_s"]
                state["total_distance_m"] += best_dist
                state["saved_count"] += 1
                assigned_ids.add(v_id)
            else:
                # Crucial: Do NOT divert an active team to an unreachable victim in Step 3!
                # Keep teams available for other reachable salvageable victims first.
                unreachable_salvageable.append(victim)

        # 4. Handle remaining unreachable salvageable and expectant cases
        # Assign to teams with remaining capacity
        remaining_candidates = unreachable_salvageable + expectant_or_expired
        for victim in remaining_candidates:
            v_id = victim.get("device_hash") or victim.get("id") or f"victim_{victim.get('latitude')}_{victim.get('longitude')}"
            if v_id in assigned_ids:
                continue

            v_lat = float(victim.get("latitude") if victim.get("latitude") is not None else base_lat)
            v_lon = float(victim.get("longitude") if victim.get("longitude") is not None else base_lon)
            if v_lat == 0.0 and v_lon == 0.0:
                v_lat, v_lon = base_lat, base_lon

            headcount = victim.get("total_headcount", 1)

            # Assign to team with smallest route if capacity remains
            candidate_teams = [t for t in teams_state.values() if len(t["route"]) < t["capacity"]]
            if candidate_teams:
                candidate_teams.sort(key=lambda t: (len(t["route"]), t["curr_time_s"]))
                state = candidate_teams[0]
                dist_m = haversine_distance_meters(state["curr_lat"], state["curr_lon"], v_lat, v_lon)
                transit_s = (dist_m / state["speed_mps"]) if state["speed_mps"] > 0 else 0.0
                arrival_s = state["curr_time_s"] + transit_s

                is_expectant = (victim.get("survival_state") == STATE_EXPECTANT)
                status_label = "EXPECTANT" if is_expectant else "EXPIRED"

                step_num = len(state["route"]) + 1
                waypoint = {
                    "step_number": step_num,
                    "victim_id": v_id,
                    "latitude": v_lat,
                    "longitude": v_lon,
                    "coordinates": [v_lat, v_lon],
                    "leg_distance_m": round(dist_m, 1),
                    "transit_time_seconds": round(transit_s, 1),
                    "eta_seconds": round(arrival_s, 1),
                    "eta_formatted": format_seconds(arrival_s),
                    "time_to_critical_at_arrival": 0.0,
                    "vitality_at_arrival": 0.0,
                    "survival_status_at_arrival": status_label,
                    "saved": False,
                    "headcount": headcount,
                    "trauma_type": victim.get("trauma_type", status_label),
                    "severity_label": victim.get("severity_label", "BLACK" if is_expectant else "RED"),
                    "disaster_label": victim.get("disaster_label", "DISASTER"),
                    "urgency_index": victim.get("urgency_index", 5.0),
                    "note": victim.get("note", "")
                }
                state["route"].append(waypoint)
                state["curr_lat"] = v_lat
                state["curr_lon"] = v_lon
                state["curr_time_s"] = arrival_s + state["service_time_s"]
                state["total_distance_m"] += dist_m
                state["expired_count"] += 1
                assigned_ids.add(v_id)
            else:
                unassigned.append(victim)

        # 5. Format Output
        total_assigned = len(assigned_ids)
        total_saved = sum(s["saved_count"] for s in teams_state.values())
        total_expired = sum(s["expired_count"] for s in teams_state.values()) + len(unassigned)
        total_victims = len(assessed_victims)

        lives_saved_pct = round((total_saved / total_victims) * 100.0, 1) if total_victims > 0 else 100.0

        team_assignments = {}
        for t_id, s in teams_state.items():
            team_assignments[t_id] = {
                "team_id": t_id,
                "team_type": s["team_type"],
                "total_assigned": len(s["route"]),
                "saved_count": s["saved_count"],
                "expired_count": s["expired_count"],
                "total_distance_meters": round(s["total_distance_m"], 1),
                "total_duration_seconds": round(s["curr_time_s"], 1),
                "total_duration_formatted": format_seconds(s["curr_time_s"]),
                "route": s["route"]
            }

        return {
            "timestamp": int(current_time),
            "total_victims": total_victims,
            "total_assigned": total_assigned,
            "total_saved": total_saved,
            "total_expired": total_expired,
            "lives_saved_percentage": lives_saved_pct,
            "team_assignments": team_assignments,
            "unassigned_victims": [v.get("device_hash") or v.get("id") or f"victim_{v.get('latitude')}_{v.get('longitude')}" for v in unassigned]
        }
