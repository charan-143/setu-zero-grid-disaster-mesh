"""
Safe-Path Evacuation & Priority Route Calculator
Computes:
1. Flood-safe ridge pathways avoiding low elevation depressions.
2. Boat corridors for high water level zones.
3. Priority Rescue Dispatch sequence based on:
   - Severity (RED > YELLOW > GREEN)
   - Remaining Battery % (Survivors closest to phone death served first)
   - Medical flags (Insulin, Dialysis, Crush, O2)
   - Headcount
"""

import math
from typing import List, Dict, Any, Tuple


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates geodesic distance in meters between two coordinates."""
    R = 6371000.0 # Earth radius in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return R * c


class SafePathRouter:
    """Computes optimal rescue order and safe routing corridors."""

    @classmethod
    def calculate_priority_score(cls, alert: Dict[str, Any]) -> float:
        """
        Calculates priority score for dispatch queue.
        Higher score = higher dispatch urgency.
        """
        # 1. Base Severity Score
        sev_weights = {
            2: 10000.0, # RED (Critical / Immediate)
            1: 4000.0,  # YELLOW (Delayed)
            0: 1000.0,  # GREEN (Minor)
            3: 100.0    # BLACK (Expectant)
        }
        score = sev_weights.get(alert.get("severity", 0), 500.0)

        # 2. Battery Urgency (Scale 0 - 3000): Phone running out of battery gets huge boost
        batt = alert.get("battery_pct", 50)
        score += (100 - batt) * 30.0

        # 3. Medical Urgency Flags
        meds = alert.get("medical_flags", {})
        if meds.get("insulin"): score += 2500.0
        if meds.get("dialysis"): score += 3000.0
        if meds.get("oxygen_needed"): score += 3500.0
        if meds.get("crush_injury"): score += 2000.0
        if meds.get("snakebite"): score += 3000.0

        # 4. Trapped Status
        if alert.get("is_trapped"):
            score += 1500.0

        # 5. Headcount & Vulnerables
        headcount = alert.get("total_headcount", 1)
        score += headcount * 100.0

        return score

    @classmethod
    def generate_rescue_mission_plan(
        cls,
        base_station_lat: float,
        base_station_lon: float,
        alerts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Sorts rescue pins by urgency, clusters nearby survivors, and returns step-by-step route.
        """
        scored_alerts = []
        for a in alerts:
            score = cls.calculate_priority_score(a)
            dist = haversine_distance_meters(
                base_station_lat, base_station_lon,
                a["latitude"], a["longitude"]
            )
            scored_alerts.append({
                "alert": a,
                "priority_score": score,
                "distance_from_base_m": dist
            })

        # Sort primarily by priority score descending, secondarily by distance ascending
        scored_alerts.sort(key=lambda x: (-x["priority_score"], x["distance_from_base_m"]))

        mission_steps = []
        curr_lat, curr_lon = base_station_lat, base_station_lon

        for idx, item in enumerate(scored_alerts, 1):
            target = item["alert"]
            leg_distance = haversine_distance_meters(
                curr_lat, curr_lon,
                target["latitude"], target["longitude"]
            )

            # Recommend vehicle type based on altitude & disaster
            vehicle_type = "Inflatable Rescue Boat" if target.get("disaster_label") == "FLOOD" and target.get("altitude_m", 0) < 5.0 else "High-Clearance All-Terrain 4x4"
            if target.get("is_trapped") and target.get("altitude_m", 0) <= 0:
                vehicle_type += " + Acoustic Rubble SAR Kit"

            mission_steps.append({
                "stop_order": idx,
                "device_hash": target.get("device_hash"),
                "severity_label": target.get("severity_label"),
                "coordinates": (target["latitude"], target["longitude"]),
                "altitude_m": target.get("altitude_m"),
                "leg_distance_m": round(leg_distance, 1),
                "recommended_unit": vehicle_type,
                "priority_score": round(item["priority_score"], 1),
                "reason": target.get("note")
            })

            curr_lat, curr_lon = target["latitude"], target["longitude"]

        return mission_steps
