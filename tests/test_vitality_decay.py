"""
Unit and Integration Tests for Module 4: Dynamic "Golden Hour" Vitality Decay & Tactical Dispatch Engine
Verifies:
1. Physiological trauma profiles (arterial bleeding vs crush vs insulin vs fracture).
2. Demographic and environmental multipliers (infant + hypothermia decays faster than adult).
3. Dynamic dispatch optimizer (deadline-first routing ensures 45-min arterial bleed is dispatched before 12-hour hypothermia).
4. Dashboard REST endpoints (GET /api/v1/vitality_forecast, GET /api/v1/victims, POST /api/v1/dispatch_optimize).
"""

import json
import os
import socket
import sys
import threading
import time
import unittest
import urllib.parse
import urllib.request
from http.server import HTTPServer

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.vitality_decay_engine import (
    VitalityDecayEngine,
    MultiTeamDispatchOptimizer,
    WINDOW_ARTERIAL_BLEED,
    WINDOW_TENSION_PNEUMO_AIRWAY,
    WINDOW_CRUSH_SYNDROME,
    WINDOW_HYPOTHERMIA_SUBMERGED,
    WINDOW_INSULIN_DIALYSIS,
    WINDOW_STABLE_FRACTURE,
    DEMO_MULT_CHILD,
    DEMO_MULT_ELDERLY,
    DEMO_MULT_PREGNANCY,
    ENV_MULT_WET_COLD,
    ENV_MULT_HYPERTHERMIA,
    ENV_MULT_CONCRETE_RUBBLE,
    STATE_STABLE,
    STATE_DEGRADING,
    STATE_CRITICAL_WINDOW,
    STATE_EXTREME_IMMINENT_COLLAPSE,
    STATE_EXPECTANT,
    haversine_distance_meters,
    format_seconds
)
from core.sos_packet import pack_sos_packet, SEVERITY_RED, SEVERITY_YELLOW, SEVERITY_GREEN, DISASTER_FLOOD, MED_FLAG_BLEEDING, MED_FLAG_CRUSH, MED_FLAG_INSULIN, MED_FLAG_FRACTURE
from dashboard.server import TacticalDashboardHandler, GATEWAY


class TestVitalityDecayPhysiologicalProfiles(unittest.TestCase):
    """Tests trauma profiles and base survival horizon calculations."""

    def test_arterial_bleed_window(self):
        """Arterial bleed has ~45 min (2,700s) base window."""
        victim = {
            "medical_flags": {"bleeding": True},
            "demographics": {"adults": 1, "children": 0, "elderly": 0},
            "note": "Severe arterial bleed on left thigh"
        }
        trauma_type, base_window = VitalityDecayEngine.determine_trauma_profile(victim)
        self.assertEqual(trauma_type, "ARTERIAL_BLEED")
        self.assertEqual(base_window, WINDOW_ARTERIAL_BLEED)
        self.assertEqual(base_window, 45 * 60)

    def test_tension_pneumo_airway_window(self):
        """Tension pneumothorax / acute airway has ~90 min (5,400s) base window."""
        victim = {
            "medical_flags": {"oxygen_needed": True},
            "demographics": {"adults": 1},
            "note": "Cannot breathe, tension pneumothorax"
        }
        trauma_type, base_window = VitalityDecayEngine.determine_trauma_profile(victim)
        self.assertEqual(trauma_type, "TENSION_PNEUMO_AIRWAY")
        self.assertEqual(base_window, WINDOW_TENSION_PNEUMO_AIRWAY)
        self.assertEqual(base_window, 90 * 60)

    def test_crush_syndrome_window(self):
        """Crush syndrome has ~4-6 hrs (18,000s) base window."""
        victim = {
            "medical_flags": {"crush_injury": True},
            "is_trapped": True,
            "note": "Leg pinned under concrete slab"
        }
        trauma_type, base_window = VitalityDecayEngine.determine_trauma_profile(victim)
        self.assertEqual(trauma_type, "CRUSH_SYNDROME")
        self.assertEqual(base_window, WINDOW_CRUSH_SYNDROME)
        self.assertTrue(4 * 3600 <= base_window <= 6 * 3600)

    def test_hypothermia_submerged_window(self):
        """Hypothermia / water immersion has ~12 hrs (43,200s) base window."""
        victim = {
            "disaster_type": 0,
            "note": "Trapped in flood waters, hypothermia shivering"
        }
        trauma_type, base_window = VitalityDecayEngine.determine_trauma_profile(victim)
        self.assertEqual(trauma_type, "HYPOTHERMIA_SUBMERGED")
        self.assertEqual(base_window, WINDOW_HYPOTHERMIA_SUBMERGED)
        self.assertEqual(base_window, 12 * 3600)

    def test_insulin_dialysis_window(self):
        """Insulin/Dialysis dependence has ~24 hrs (86,400s) base window."""
        victim = {
            "medical_flags": {"insulin": True},
            "note": "Type 1 diabetic missing insulin dose"
        }
        trauma_type, base_window = VitalityDecayEngine.determine_trauma_profile(victim)
        self.assertEqual(trauma_type, "INSULIN_DIALYSIS")
        self.assertEqual(base_window, WINDOW_INSULIN_DIALYSIS)
        self.assertEqual(base_window, 24 * 3600)

    def test_stable_fracture_window(self):
        """Stable fracture has ~72 hrs (259,200s) base window."""
        victim = {
            "medical_flags": {"fracture": True},
            "note": "Closed hairline fracture of forearm"
        }
        trauma_type, base_window = VitalityDecayEngine.determine_trauma_profile(victim)
        self.assertEqual(trauma_type, "STABLE_FRACTURE")
        self.assertEqual(base_window, WINDOW_STABLE_FRACTURE)
        self.assertEqual(base_window, 72 * 3600)

    def test_decay_progression_and_states(self):
        """Tests continuous vitality decay from 1.0 to 0.0 and survival states."""
        base_window = 1000.0  # seconds

        # At t = 0
        v, t_crit, state, urgency = VitalityDecayEngine.calculate_decay(
            base_window_s=base_window, demo_mult=1.0, env_mult=1.0, elapsed_s=0.0
        )
        self.assertEqual(v, 1.0)
        self.assertEqual(t_crit, 1000.0)
        self.assertEqual(state, STATE_STABLE)

        # At t = 300s (vitality = 0.70 -> DEGRADING)
        v, t_crit, state, urgency = VitalityDecayEngine.calculate_decay(
            base_window_s=base_window, demo_mult=1.0, env_mult=1.0, elapsed_s=300.0
        )
        self.assertAlmostEqual(v, 0.70, places=2)
        self.assertEqual(state, STATE_DEGRADING)

        # At t = 600s (vitality = 0.40 -> CRITICAL_WINDOW)
        v, t_crit, state, urgency = VitalityDecayEngine.calculate_decay(
            base_window_s=base_window, demo_mult=1.0, env_mult=1.0, elapsed_s=600.0
        )
        self.assertAlmostEqual(v, 0.40, places=2)
        self.assertEqual(state, STATE_CRITICAL_WINDOW)

        # At t = 900s (vitality = 0.10 -> EXTREME_IMMINENT_COLLAPSE)
        v, t_crit, state, urgency = VitalityDecayEngine.calculate_decay(
            base_window_s=base_window, demo_mult=1.0, env_mult=1.0, elapsed_s=900.0
        )
        self.assertAlmostEqual(v, 0.10, places=2)
        self.assertEqual(state, STATE_EXTREME_IMMINENT_COLLAPSE)

        # At t = 1000s or beyond (vitality = 0.0 -> EXPECTANT)
        v, t_crit, state, urgency = VitalityDecayEngine.calculate_decay(
            base_window_s=base_window, demo_mult=1.0, env_mult=1.0, elapsed_s=1050.0
        )
        self.assertEqual(v, 0.0)
        self.assertEqual(t_crit, 0.0)
        self.assertEqual(state, STATE_EXPECTANT)


class TestDemographicAndEnvironmentalMultipliers(unittest.TestCase):
    """Tests demographic & environmental multiplier effects on survival horizons."""

    def test_demographic_multipliers(self):
        """Verifies child (0.65x), elderly (0.70x), and pregnancy (0.75x) multipliers."""
        child_victim = {"demographics": {"adults": 1, "children": 1, "elderly": 0}}
        self.assertAlmostEqual(VitalityDecayEngine.calculate_demographic_multiplier(child_victim), DEMO_MULT_CHILD, places=2)

        elderly_victim = {"demographics": {"adults": 0, "children": 0, "elderly": 1}}
        self.assertAlmostEqual(VitalityDecayEngine.calculate_demographic_multiplier(elderly_victim), DEMO_MULT_ELDERLY, places=2)

        pregnant_victim = {"medical_flags": {"pregnancy": True}}
        self.assertAlmostEqual(VitalityDecayEngine.calculate_demographic_multiplier(pregnant_victim), DEMO_MULT_PREGNANCY, places=2)

    def test_environmental_multipliers(self):
        """Verifies wet cold, hyperthermia, and trapped concrete rubble multipliers."""
        # Wet cold (< 15°C)
        cold_victim = {"ambient_temp_c": 8.0, "note": "ambient cold"}
        self.assertAlmostEqual(VitalityDecayEngine.calculate_environmental_multiplier(cold_victim), ENV_MULT_WET_COLD, places=2)

        # Hyperthermia (> 38°C)
        hot_victim = {"ambient_temp_c": 42.0, "note": "heatstroke"}
        self.assertAlmostEqual(VitalityDecayEngine.calculate_environmental_multiplier(hot_victim), ENV_MULT_HYPERTHERMIA, places=2)

        # Trapped under concrete rubble
        rubble_victim = {"is_trapped": True, "note": "pinned under concrete rubble"}
        self.assertAlmostEqual(VitalityDecayEngine.calculate_environmental_multiplier(rubble_victim), ENV_MULT_CONCRETE_RUBBLE, places=2)

    def test_infant_hypothermia_decays_faster_than_adult_ambient(self):
        """
        Core Requirement: Infant + hypothermia decays faster than adult in ambient conditions.
        """
        now = time.time()
        # Adult in ambient conditions (22°C, no trapped, no cold)
        adult_victim = {
            "timestamp": now - 600,  # 10 min elapsed
            "demographics": {"adults": 1, "children": 0, "elderly": 0},
            "ambient_temp_c": 22.0,
            "medical_flags": {"crush_injury": True},  # Base window: 5 hrs (18,000s)
            "note": "Adult in room temperature"
        }
        # Infant in hypothermia (<15°C, 8°C wet cold)
        infant_victim = {
            "timestamp": now - 600,  # same 10 min elapsed
            "demographics": {"adults": 1, "children": 1, "elderly": 0},
            "ambient_temp_c": 8.0,
            "medical_flags": {"crush_injury": True},  # Same injury
            "note": "Infant trapped in freezing wet condition"
        }

        adult_assessment = VitalityDecayEngine.assess_victim(adult_victim, current_time=now)
        infant_assessment = VitalityDecayEngine.assess_victim(infant_victim, current_time=now)

        # Infant's effective survival horizon must be significantly shorter than adult's
        self.assertLess(
            infant_assessment["effective_horizon_seconds"],
            adult_assessment["effective_horizon_seconds"]
        )
        # Ratio check: demo (0.65) * env (0.75) = 0.4875x
        expected_ratio = DEMO_MULT_CHILD * ENV_MULT_WET_COLD
        actual_ratio = infant_assessment["effective_horizon_seconds"] / adult_assessment["effective_horizon_seconds"]
        self.assertAlmostEqual(actual_ratio, expected_ratio, places=2)

        # Remaining seconds to critical must be strictly lower for infant
        self.assertLess(
            infant_assessment["time_to_critical_seconds"],
            adult_assessment["time_to_critical_seconds"]
        )

        # Vitality score for infant must have decayed more than for adult
        self.assertLess(
            infant_assessment["vitality_score"],
            adult_assessment["vitality_score"]
        )

        # Urgency index for infant must be higher
        self.assertGreater(
            infant_assessment["urgency_index"],
            adult_assessment["urgency_index"]
        )


class TestDynamicDispatchOptimizer(unittest.TestCase):
    """Tests multi-team deadline-first dispatch optimization."""

    def test_arterial_bleed_dispatched_before_hypothermia(self):
        """
        Core Requirement: Verifies that victim with 45-minute window is dispatched
        before victim with 12-hour window.
        """
        now = time.time()
        base_lat, base_lon = 20.2900, 85.8200

        # Victim A: Arterial Bleed (45 min window), located 2.5 km away
        victim_arterial = {
            "id": "VICTIM_ARTERIAL_BLEED",
            "device_hash": "A1B2C3",
            "timestamp": now,
            "latitude": 20.3100,
            "longitude": 85.8300,
            "severity": 2,
            "severity_label": "RED",
            "medical_flags": {"bleeding": True},
            "demographics": {"adults": 1, "children": 0, "elderly": 0, "total_headcount": 1},
            "note": "Arterial bleeding from laceration"
        }

        # Victim B: Hypothermia (12 hour window), located 1.0 km away (closer to base station)
        victim_hypothermia = {
            "id": "VICTIM_HYPOTHERMIA",
            "device_hash": "D4E5F6",
            "timestamp": now,
            "latitude": 20.2950,
            "longitude": 85.8250,
            "severity": 1,
            "severity_label": "YELLOW",
            "disaster_type": 0,
            "demographics": {"adults": 1, "children": 0, "elderly": 0, "total_headcount": 1},
            "note": "Hypothermia stranded on roof with safe water level"
        }

        # Single team available
        single_team = [{
            "team_id": "RESCUE_BOAT_ALPHA",
            "team_type": "BOAT",
            "latitude": base_lat,
            "longitude": base_lon,
            "speed_kmh": 35.0,
            "capacity": 6,
            "service_time_seconds": 300.0
        }]

        dispatch_result = MultiTeamDispatchOptimizer.optimize_dispatch(
            victims=[victim_hypothermia, victim_arterial],
            rescue_teams=single_team,
            base_lat=base_lat,
            base_lon=base_lon,
            current_time=now
        )

        team_plan = dispatch_result["team_assignments"]["RESCUE_BOAT_ALPHA"]
        route = team_plan["route"]

        self.assertEqual(len(route), 2)
        # Step 1 MUST be the arterial bleed victim due to 45-min golden hour window!
        self.assertEqual(route[0]["victim_id"], "A1B2C3")
        self.assertEqual(route[0]["trauma_type"], "ARTERIAL_BLEED")
        self.assertTrue(route[0]["saved"])

        # Step 2 is the 12-hour hypothermia victim
        self.assertEqual(route[1]["victim_id"], "D4E5F6")
        self.assertEqual(route[1]["trauma_type"], "HYPOTHERMIA_SUBMERGED")
        self.assertTrue(route[1]["saved"])

        # Both saved
        self.assertEqual(dispatch_result["total_saved"], 2)
        self.assertEqual(dispatch_result["lives_saved_percentage"], 100.0)

    def test_empty_victims_dispatch(self):
        """Verifies handling of empty victim list."""
        result = MultiTeamDispatchOptimizer.optimize_dispatch(victims=[])
        self.assertEqual(result["total_victims"], 0)
        self.assertEqual(result["total_saved"], 0)
        self.assertEqual(result["lives_saved_percentage"], 100.0)

    def test_unreachable_expired_victim_handling(self):
        """Verifies that an unreachable victim whose deadline has elapsed is marked EXPIRED."""
        now = time.time()
        base_lat, base_lon = 20.2900, 85.8200

        # Victim 80 km away with only 60 seconds remaining
        unreachable_victim = {
            "id": "UNREACHABLE_VICTIM",
            "device_hash": "Z9Y8X7",
            "timestamp": now - 2640,  # 44 minutes elapsed of 45 minute window
            "latitude": 21.0000,
            "longitude": 86.5000,
            "severity": 2,
            "medical_flags": {"bleeding": True},
            "demographics": {"adults": 1, "children": 0, "elderly": 0, "total_headcount": 1},
            "note": "Critical arterial bleed far away"
        }

        # Slow team
        slow_team = [{
            "team_id": "SLOW_FOOT_TEAM",
            "team_type": "FOOT_RESCUE",
            "latitude": base_lat,
            "longitude": base_lon,
            "speed_kmh": 5.0,
            "capacity": 2
        }]

        result = MultiTeamDispatchOptimizer.optimize_dispatch(
            victims=[unreachable_victim],
            rescue_teams=slow_team,
            base_lat=base_lat,
            base_lon=base_lon,
            current_time=now
        )
        self.assertEqual(result["total_victims"], 1)
        self.assertEqual(result["total_saved"], 0)
        self.assertEqual(result["total_expired"], 1)
        self.assertEqual(result["lives_saved_percentage"], 0.0)

    def test_expectant_black_severity(self):
        """Verifies that initial SEVERITY_BLACK (3) evaluates to EXPECTANT immediately."""
        black_victim = {
            "severity": 3,
            "timestamp": time.time(),
            "note": "Expectant / non-survivable injury"
        }
        assessment = VitalityDecayEngine.assess_victim(black_victim)
        self.assertEqual(assessment["survival_state"], STATE_EXPECTANT)
        self.assertEqual(assessment["vitality_score"], 0.0)
        self.assertEqual(assessment["time_to_critical_seconds"], 0.0)

    def test_compounded_demographics(self):
        """Verifies compounded child + pregnant demographic risk."""
        compounded = {
            "demographics": {"adults": 1, "children": 1, "elderly": 0},
            "medical_flags": {"pregnancy": True}
        }
        mult = VitalityDecayEngine.calculate_demographic_multiplier(compounded)
        expected = round(DEMO_MULT_CHILD * DEMO_MULT_PREGNANCY, 4)
        self.assertAlmostEqual(mult, expected, places=3)

    def test_format_seconds_utility(self):
        """Verifies format_seconds helper for boundary values."""
        self.assertEqual(format_seconds(0), "00:00:00")
        self.assertEqual(format_seconds(59), "00:00:59")
        self.assertEqual(format_seconds(3600), "01:00:00")
        self.assertEqual(format_seconds(86400), "24:00:00")
        self.assertEqual(format_seconds(259200), "72:00:00")

    def test_unreachable_victim_does_not_starve_reachable_candidate(self):
        """
        Critical Algorithmic Test:
        An unreachable victim far away with an expiring deadline must NOT prevent
        a nearby salvageable victim from being reached and saved.
        """
        now = time.time()
        base_lat, base_lon = 20.2900, 85.8200

        # V1: 100km away, only 60s window left (impossible to save)
        v1_unreachable = {
            "id": "V1_UNREACHABLE",
            "device_hash": "V1HASH",
            "timestamp": now - 2640,  # 44m elapsed of 45m arterial bleed
            "latitude": 21.0000,
            "longitude": 86.5000,
            "severity": 2,
            "medical_flags": {"bleeding": True},
            "total_headcount": 1
        }
        # V2: 1km away, 5 hours remaining (fully salvageable)
        v2_reachable = {
            "id": "V2_REACHABLE",
            "device_hash": "V2HASH",
            "timestamp": now,
            "latitude": 20.2910,
            "longitude": 85.8210,
            "severity": 2,
            "medical_flags": {"crush_injury": True},
            "total_headcount": 1
        }

        team = [{
            "team_id": "RESCUE_BOAT_FAST",
            "team_type": "BOAT",
            "latitude": base_lat,
            "longitude": base_lon,
            "speed_kmh": 40.0,
            "capacity": 4,
            "service_time_seconds": 300.0
        }]

        result = MultiTeamDispatchOptimizer.optimize_dispatch(
            victims=[v1_unreachable, v2_reachable],
            rescue_teams=team,
            base_lat=base_lat,
            base_lon=base_lon,
            current_time=now
        )

        # V2 MUST be saved
        self.assertEqual(result["total_saved"], 1)
        self.assertEqual(result["total_expired"], 1)
        self.assertEqual(result["lives_saved_percentage"], 50.0)

        route = result["team_assignments"]["RESCUE_BOAT_FAST"]["route"]
        # Step 1 must be V2
        self.assertEqual(route[0]["victim_id"], "V2HASH")
        self.assertTrue(route[0]["saved"])
        self.assertEqual(route[0]["survival_status_at_arrival"], "SAVED")

    def test_zero_and_negative_fleet_speed(self):
        """Verifies that immobilized vehicles (speed <= 0) cannot travel to distant victims."""
        now = time.time()
        base_lat, base_lon = 20.2900, 85.8200

        victim = {
            "id": "VICTIM_FAR",
            "timestamp": now,
            "latitude": 20.3500,
            "longitude": 85.9000,
            "medical_flags": {"crush_injury": True}
        }
        broken_team = [{
            "team_id": "BROKEN_TRUCK",
            "latitude": base_lat,
            "longitude": base_lon,
            "speed_kmh": 0.0,
            "capacity": 4
        }]

        result = MultiTeamDispatchOptimizer.optimize_dispatch(
            victims=[victim],
            rescue_teams=broken_team,
            base_lat=base_lat,
            base_lon=base_lon,
            current_time=now
        )
        # Cannot be reached due to 0 speed
        self.assertEqual(result["total_saved"], 0)
        self.assertEqual(result["total_expired"], 1)

    def test_null_island_and_missing_coordinates(self):
        """Verifies that missing or (0.0, 0.0) coordinates fall back safely to base coordinates."""
        now = time.time()
        base_lat, base_lon = 20.2900, 85.8200

        victim = {
            "id": "VICTIM_NULL_ISLAND",
            "timestamp": now,
            "latitude": 0.0,
            "longitude": 0.0,
            "medical_flags": {"bleeding": True}
        }
        team = [{
            "team_id": "TEAM_BASE",
            "latitude": base_lat,
            "longitude": base_lon,
            "speed_kmh": 40.0,
            "capacity": 2
        }]

        result = MultiTeamDispatchOptimizer.optimize_dispatch(
            victims=[victim],
            rescue_teams=team,
            base_lat=base_lat,
            base_lon=base_lon,
            current_time=now
        )
        # Should be rescued at base coords without raising exception or 7500km distance
        route = result["team_assignments"]["TEAM_BASE"]["route"]
        self.assertEqual(len(route), 1)
        self.assertLess(route[0]["leg_distance_m"], 100.0)
        self.assertTrue(route[0]["saved"])

    def test_disaster_label_from_db_records(self):
        """Verifies that SQLite records storing disaster_label ('FLOOD' or 'COLLAPSE') are profiled accurately."""
        flood_db_record = {
            "disaster_label": "FLOOD",
            "is_trapped": 0,
            "note": "Elderly on roof"
        }
        trauma, window = VitalityDecayEngine.determine_trauma_profile(flood_db_record)
        self.assertEqual(trauma, "HYPOTHERMIA_SUBMERGED")
        self.assertEqual(window, WINDOW_HYPOTHERMIA_SUBMERGED)

        collapse_db_record = {
            "disaster_label": "COLLAPSE",
            "is_trapped": 1,
            "note": "Trapped"
        }
        trauma2, window2 = VitalityDecayEngine.determine_trauma_profile(collapse_db_record)
        self.assertEqual(trauma2, "CRUSH_SYNDROME")
        self.assertEqual(window2, WINDOW_CRUSH_SYNDROME)

    def test_format_seconds_non_finite_inputs(self):
        """Verifies format_seconds handles float('inf'), float('nan'), None, and negative values safely."""
        self.assertEqual(format_seconds(float('inf')), "00:00:00")
        self.assertEqual(format_seconds(float('nan')), "00:00:00")
        self.assertEqual(format_seconds(None), "00:00:00")
        self.assertEqual(format_seconds(-100.0), "00:00:00")
        self.assertEqual(format_seconds(3665), "01:01:05")

    def test_multi_team_parallel_routing(self):
        """Verifies that multiple teams divide workload and meet deadlines."""
        now = time.time()
        base_lat, base_lon = 20.2900, 85.8200

        victims = [
            {
                "id": f"V_{i}",
                "device_hash": f"DEV_{i}",
                "timestamp": now,
                "latitude": base_lat + (0.01 * (i + 1)),
                "longitude": base_lon + (0.01 * (i + 1)),
                "severity": 2 if i % 2 == 0 else 1,
                "medical_flags": {"bleeding": True} if i == 0 else {"crush_injury": True},
                "total_headcount": 2
            }
            for i in range(4)
        ]

        teams = [
            {"team_id": "TEAM_1", "latitude": base_lat, "longitude": base_lon, "speed_kmh": 40.0, "capacity": 3},
            {"team_id": "TEAM_2", "latitude": base_lat, "longitude": base_lon, "speed_kmh": 40.0, "capacity": 3}
        ]

        result = MultiTeamDispatchOptimizer.optimize_dispatch(
            victims=victims,
            rescue_teams=teams,
            base_lat=base_lat,
            base_lon=base_lon,
            current_time=now
        )

        self.assertEqual(result["total_victims"], 4)
        self.assertGreaterEqual(result["total_saved"], 3)
        self.assertIn("TEAM_1", result["team_assignments"])
        self.assertIn("TEAM_2", result["team_assignments"])


class TestDashboardEndpointIntegrations(unittest.TestCase):
    """Tests the dashboard REST server integration for Module 4."""

    @classmethod
    def setUpClass(cls):
        # Seed test data in GATEWAY database
        raw_pkt1 = pack_sos_packet(
            device_id="DEV_TEST_ARTERIAL_01",
            timestamp=int(time.time()),
            latitude=20.2980,
            longitude=85.8250,
            altitude_decimeters=100,
            severity=SEVERITY_RED,
            disaster_type=DISASTER_FLOOD,
            is_trapped=True,
            mobility=0,
            adults=1,
            children=1,
            elderly=0,
            critical_cases=1,
            hop_count=1,
            battery_pct=40,
            medical_flags=MED_FLAG_BLEEDING,
            note="Urgent arterial bleed, 1 child"
        )
        GATEWAY.ingest_raw_packet(raw_pkt1, channel="BLE")

        # Pick a free port and launch test server
        cls.server = HTTPServer(('127.0.0.1', 0), TacticalDashboardHandler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_get_vitality_forecast_endpoint(self):
        """Verifies GET /api/v1/vitality_forecast returns dynamic countdowns and dispatch recommendations."""
        url = f"http://127.0.0.1:{self.port}/api/v1/vitality_forecast"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("forecast", data)
            self.assertIn("summary", data)
            self.assertIn("dispatch_recommendation", data)
            self.assertGreater(data["total_victims"], 0)

            # Check individual victim forecast structure
            first_v = data["forecast"][0]
            self.assertIn("vitality_score", first_v)
            self.assertIn("time_to_critical_seconds", first_v)
            self.assertIn("survival_state", first_v)
            self.assertIn("urgency_index", first_v)
            self.assertIn("trauma_type", first_v)

    def test_get_victims_endpoint(self):
        """Verifies GET /api/v1/victims returns real-time vitality scores and urgency ranks."""
        url = f"http://127.0.0.1:{self.port}/api/v1/victims"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("victims", data)
            self.assertIn("total", data)
            self.assertGreater(data["total"], 0)

            first_v = data["victims"][0]
            self.assertIn("vitality_score", first_v)
            self.assertIn("time_to_critical_seconds", first_v)
            self.assertIn("urgency_rank", first_v)
            self.assertEqual(first_v["urgency_rank"], 1)

    def test_post_dispatch_optimize_endpoint(self):
        """Verifies POST /api/v1/dispatch_optimize returns optimal multi-team rescue assignments."""
        url = f"http://127.0.0.1:{self.port}/api/v1/dispatch_optimize"
        body = json.dumps({
            "rescue_teams": [
                {
                    "team_id": "TEST_AMBULANCE_01",
                    "team_type": "AMBULANCE",
                    "latitude": 20.2900,
                    "longitude": 85.8200,
                    "speed_kmh": 50.0,
                    "capacity": 4
                }
            ]
        }).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("team_assignments", data)
            self.assertIn("lives_saved_percentage", data)
            self.assertIn("total_saved", data)
            self.assertIn("TEST_AMBULANCE_01", data["team_assignments"])

    def test_options_cors_preflight(self):
        """Verifies OPTIONS preflight request returns 200 with appropriate CORS headers."""
        url = f"http://127.0.0.1:{self.port}/api/v1/dispatch_optimize"
        req = urllib.request.Request(url, method="OPTIONS")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))


if __name__ == "__main__":
    unittest.main()
