"""
Unit and Integration Tests for Cryo-Sleep Battery Stretcher & Power Budgeter
Zero-Grid Disaster Mesh & Triage System (Setu)
"""

import unittest
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cryo_sleep_manager import (
    CryoSleepManager,
    CryoSleepState,
    PowerProfile,
    SurvivalHorizon,
    PowerBudgetRecommendation
)


class TestCryoSleepManager(unittest.TestCase):

    def setUp(self):
        # Deterministic simulated clock
        self.sim_time = 1000.0
        self.clock = lambda: self.sim_time
        self.manager = CryoSleepManager(
            battery_capacity_mah=4000.0,
            nominal_voltage=3.85,
            clock_source=self.clock
        )

    def test_01_initial_state(self):
        """Node starts in ACTIVE_SEARCH by default."""
        self.assertEqual(self.manager.current_state, CryoSleepState.ACTIVE_SEARCH)
        self.assertTrue(self.manager.should_transmit_now())

    def test_02_transition_active_to_cryo_deep_sleep(self):
        """Verifies transition from ACTIVE_SEARCH to CRYO_DEEP_SLEEP in dark, stationary rubble."""
        # Survivor phone buried under dark rubble (lux = 0, stationary motion variance = 0.01)
        new_state = self.manager.update_sensor_readings(
            lux=0.0,
            accel_variance=0.01,
            battery_pct=45.0,
            current_time=self.sim_time
        )
        self.assertEqual(new_state, CryoSleepState.CRYO_DEEP_SLEEP)
        self.assertEqual(self.manager.current_state, CryoSleepState.CRYO_DEEP_SLEEP)

    def test_03_transition_to_critical_reserve_on_low_battery(self):
        """Verifies transition to CRITICAL_RESERVE when battery drops below 10%."""
        # Battery at 9.5% (< 10.0%)
        new_state = self.manager.update_sensor_readings(
            lux=0.0,
            accel_variance=0.01,
            battery_pct=9.5,
            current_time=self.sim_time
        )
        self.assertEqual(new_state, CryoSleepState.CRITICAL_RESERVE)
        self.assertEqual(self.manager.current_state, CryoSleepState.CRITICAL_RESERVE)

        # Even with high light or motion, CRITICAL_RESERVE is maintained to save phone from complete shutdown
        new_state = self.manager.update_sensor_readings(
            lux=500.0,
            accel_variance=0.02,
            battery_pct=8.0,
            current_time=self.sim_time
        )
        self.assertEqual(new_state, CryoSleepState.CRITICAL_RESERVE)

    def test_04_survival_horizon_math_15pct_4000mah(self):
        """
        Verifies mathematical model:
        15% battery on a 4000mAh phone lasts ~7-10 days in CRYO_DEEP_SLEEP
        vs < 4 hours in continuous ACTIVE_SEARCH.
        """
        # 1. Continuous ACTIVE_SEARCH
        horizon_active = self.manager.calculate_survival_horizon(
            battery_pct=15.0,
            state=CryoSleepState.ACTIVE_SEARCH
        )
        self.assertLess(
            horizon_active.hours, 4.0,
            f"Active search should last < 4 hours, got {horizon_active.hours:.2f} hrs"
        )
        self.assertGreater(horizon_active.hours, 1.0)
        # At 400 mA load, 600 mAh / 400 mA = 1.5 hours
        self.assertAlmostEqual(horizon_active.hours, 1.5, delta=0.2)

        # 2. CRYO_DEEP_SLEEP (58s sleep / 200ms wake burst)
        horizon_cryo = self.manager.calculate_survival_horizon(
            battery_pct=15.0,
            state=CryoSleepState.CRYO_DEEP_SLEEP
        )
        self.assertGreaterEqual(
            horizon_cryo.days, 7.0,
            f"Cryo deep sleep should last >= 7 days, got {horizon_cryo.days:.2f} days"
        )
        self.assertLessEqual(
            horizon_cryo.days, 10.0,
            f"Cryo deep sleep should last <= 10 days, got {horizon_cryo.days:.2f} days"
        )

        # 3. CRITICAL_RESERVE (180s sleep / 200ms wake burst)
        horizon_crit = self.manager.calculate_survival_horizon(
            battery_pct=15.0,
            state=CryoSleepState.CRITICAL_RESERVE
        )
        self.assertGreater(horizon_crit.days, horizon_cryo.days)

    def test_05_wake_interrupt_on_aftershock(self):
        """Verifies wake interrupt triggers immediately on seismic motion spike."""
        # Enter CRYO_DEEP_SLEEP
        self.manager.update_sensor_readings(
            lux=0.0,
            accel_variance=0.01,
            battery_pct=50.0,
            current_time=self.sim_time
        )
        self.assertEqual(self.manager.current_state, CryoSleepState.CRYO_DEEP_SLEEP)

        # Advance time into the sleep phase (e.g. 10s into 58s sleep)
        self.sim_time += 10.0
        self.assertFalse(self.manager.should_transmit_now(current_time=self.sim_time))

        # Sudden aftershock triggers motion spike (variance = 0.85 > 0.50 threshold)
        self.manager.update_sensor_readings(
            lux=0.0,
            accel_variance=0.85,
            battery_pct=50.0,
            current_time=self.sim_time
        )
        # Immediate wake interrupt ensures transmission starts immediately
        self.assertTrue(self.manager.should_transmit_now(current_time=self.sim_time))
        # Since motion continued, node transitioned to ACTIVE_SEARCH
        self.assertEqual(self.manager.current_state, CryoSleepState.ACTIVE_SEARCH)

    def test_06_light_threshold_wake(self):
        """Verifies rescue flashlight or sunlight penetration breaks CRYO_DEEP_SLEEP."""
        # Enter CRYO_DEEP_SLEEP
        self.manager.update_sensor_readings(
            lux=0.0,
            accel_variance=0.02,
            battery_pct=60.0,
            current_time=self.sim_time
        )
        self.assertEqual(self.manager.current_state, CryoSleepState.CRYO_DEEP_SLEEP)

        # Flashlight from search and rescue dog / team (lux = 120.0 > 2.0)
        new_state = self.manager.update_sensor_readings(
            lux=120.0,
            accel_variance=0.02,
            battery_pct=60.0,
            current_time=self.sim_time
        )
        self.assertEqual(new_state, CryoSleepState.ACTIVE_SEARCH)

    def test_07_cryo_sleep_timing_cycle(self):
        """Verifies the 58s sleep / 200ms wake burst cycle timing."""
        self.manager.update_sensor_readings(
            lux=0.0,
            accel_variance=0.01,
            battery_pct=80.0,
            current_time=self.sim_time
        )
        self.manager.clear_wake_interrupt()

        # At cycle start (t = 0), wake burst is active (200ms)
        self.assertTrue(self.manager.should_transmit_now(current_time=self.sim_time))

        # At t = 100ms, still in wake burst
        self.assertTrue(self.manager.should_transmit_now(current_time=self.sim_time + 0.100))

        # At t = 250ms, wake burst ended, now in deep sleep
        self.assertFalse(self.manager.should_transmit_now(current_time=self.sim_time + 0.250))

        # At t = 30.0s, deep sleep
        self.assertFalse(self.manager.should_transmit_now(current_time=self.sim_time + 30.0))

        # At t = 58.2s (full cycle: 58.0s + 0.2s = 58.2s), new burst begins
        self.assertTrue(self.manager.should_transmit_now(current_time=self.sim_time + 58.201))

    def test_08_power_budget_recommendation_and_logging(self):
        """Verifies full recommendation report, saving multiplier, and log output."""
        self.manager.update_sensor_readings(
            lux=0.0,
            accel_variance=0.01,
            battery_pct=25.0,
            current_time=self.sim_time
        )
        rec = self.manager.get_power_budget_recommendation(current_time=self.sim_time)
        self.assertEqual(rec.state, CryoSleepState.CRYO_DEEP_SLEEP)
        self.assertEqual(rec.sleep_duration_s, 58.0)
        self.assertEqual(rec.wake_duration_s, 0.2)
        # Power savings factor should be > 100x compared to continuous active search
        self.assertGreater(rec.power_saving_factor, 100.0)

        # Check serialization
        rec_dict = rec.to_dict()
        self.assertIn("survival_horizon", rec_dict)
        self.assertIn("power_saving_factor", rec_dict)

        # Check formatted log string
        log_str = self.manager.log_life_expectancy_projection()
        self.assertIn("[CRYO-SLEEP MANAGER]", log_str)
        self.assertIn("lifespan multiplier", log_str)

    def test_09_battery_zero_or_depleted_edge_case(self):
        """Gracefully handles 0% battery without division by zero."""
        horizon = self.manager.calculate_survival_horizon(battery_pct=0.0)
        self.assertEqual(horizon.seconds, 0.0)
        self.assertEqual(horizon.hours, 0.0)
        self.assertEqual(horizon.days, 0.0)
        self.assertEqual(horizon.remaining_mah, 0.0)

    def test_10_solar_recharge_recovery_from_critical_reserve(self):
        """Verifies node recovers out of CRITICAL_RESERVE if battery increases above threshold."""
        # Depleted to 5%
        self.manager.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=5.0)
        self.assertEqual(self.manager.current_state, CryoSleepState.CRITICAL_RESERVE)

        # Recharged to 25% under rubble
        self.manager.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=25.0)
        self.assertEqual(self.manager.current_state, CryoSleepState.CRITICAL_RESERVE if 25.0 < self.manager.battery_recovery_threshold else CryoSleepState.CRYO_DEEP_SLEEP)

        # Recharged to 25% in sunlight
        self.manager.update_sensor_readings(lux=200.0, accel_variance=0.01, battery_pct=25.0)
        self.assertEqual(self.manager.current_state, CryoSleepState.ACTIVE_SEARCH)

    def test_11_wake_interrupt_auto_expires_after_burst(self):
        """
        Critical bug test: Wake interrupts must automatically expire after the 200ms
        wake burst duration without requiring manual clear_wake_interrupt calls,
        preventing the node from staying permanently stuck transmitting.
        """
        # Node in CRYO_DEEP_SLEEP
        self.manager.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=50.0, current_time=self.sim_time)
        self.assertEqual(self.manager.current_state, CryoSleepState.CRYO_DEEP_SLEEP)

        # Advance 10s into deep sleep
        self.sim_time += 10.0
        self.assertFalse(self.manager.should_transmit_now(current_time=self.sim_time))
        self.assertEqual(self.manager.get_power_budget_recommendation(current_time=self.sim_time).action, "DEEP_SLEEP")

        # External interrupt arrives (e.g. survivor button press)
        self.manager.trigger_wake_interrupt(reason="sos_button", current_time=self.sim_time)
        self.assertTrue(self.manager.should_transmit_now(current_time=self.sim_time))
        self.assertEqual(self.manager.get_power_budget_recommendation(current_time=self.sim_time).action, "TRANSMIT_BURST")

        # During the 200ms burst (t + 100ms)
        self.assertTrue(self.manager.should_transmit_now(current_time=self.sim_time + 0.100))
        self.assertEqual(self.manager.get_power_budget_recommendation(current_time=self.sim_time + 0.100).action, "TRANSMIT_BURST")

        # Immediately after the burst (t + 300ms) - should auto-return to DEEP_SLEEP without manual clear!
        self.assertFalse(self.manager.should_transmit_now(current_time=self.sim_time + 0.300))
        rec = self.manager.get_power_budget_recommendation(current_time=self.sim_time + 0.300)
        self.assertEqual(rec.action, "DEEP_SLEEP")
        self.assertAlmostEqual(rec.time_to_next_burst_s, 58.2 - 0.3, delta=0.05)

    def test_12_ambient_light_hysteresis_prevents_flapping(self):
        """
        Verifies that light sensor hysteresis (2.0 lux dark vs 5.0 lux wake)
        prevents rapid flapping when sensor noise oscillates around 2.0 lux.
        """
        # Enter CRYO_DEEP_SLEEP at 1.0 lux
        self.manager.update_sensor_readings(lux=1.0, accel_variance=0.01, battery_pct=50.0, current_time=self.sim_time)
        self.assertEqual(self.manager.current_state, CryoSleepState.CRYO_DEEP_SLEEP)

        # Sensor noise fluctuates to 2.1 lux (above 2.0, but below 5.0 lux wake threshold)
        self.manager.update_sensor_readings(lux=2.1, accel_variance=0.01, battery_pct=50.0, current_time=self.sim_time + 1.0)
        # MUST remain in CRYO_DEEP_SLEEP, not flap back to ACTIVE_SEARCH!
        self.assertEqual(self.manager.current_state, CryoSleepState.CRYO_DEEP_SLEEP)

        # Sensor noise drops back to 1.9 lux
        self.manager.update_sensor_readings(lux=1.9, accel_variance=0.01, battery_pct=50.0, current_time=self.sim_time + 2.0)
        self.assertEqual(self.manager.current_state, CryoSleepState.CRYO_DEEP_SLEEP)

        # Flashlight illuminates phone to 5.5 lux (>= 5.0 lux wake threshold)
        self.manager.update_sensor_readings(lux=5.5, accel_variance=0.01, battery_pct=50.0, current_time=self.sim_time + 3.0)
        self.assertEqual(self.manager.current_state, CryoSleepState.ACTIVE_SEARCH)

    def test_13_battery_recovery_hysteresis(self):
        """
        Verifies battery recovery hysteresis prevents oscillation between CRITICAL_RESERVE
        and CRYO_DEEP_SLEEP due to cell voltage bounce under load removal.
        """
        # Battery drops to 9.8% -> enters CRITICAL_RESERVE
        self.manager.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=9.8, current_time=self.sim_time)
        self.assertEqual(self.manager.current_state, CryoSleepState.CRITICAL_RESERVE)

        # Voltage recovers slightly to 10.3% when radio powers off (below 12.0% recovery threshold)
        self.manager.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=10.3, current_time=self.sim_time + 1.0)
        self.assertEqual(self.manager.current_state, CryoSleepState.CRITICAL_RESERVE)

        # Steady solar recharge reaches 12.5% (>= 12.0% recovery threshold)
        self.manager.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=12.5, current_time=self.sim_time + 2.0)
        self.assertEqual(self.manager.current_state, CryoSleepState.CRYO_DEEP_SLEEP)

    def test_14_sub_zero_thermal_capacity_derating(self):
        """
        Verifies thermal capacity derating model:
        Cold rubble reduces effective lithium-ion battery capacity.
        """
        # 1. Standard temperature (25°C) -> 100% capacity (factor 1.0)
        h_norm = self.manager.calculate_survival_horizon(battery_pct=50.0, state=CryoSleepState.CRYO_DEEP_SLEEP, temperature_c=25.0)
        self.assertEqual(h_norm.temperature_derating, 1.0)
        self.assertEqual(h_norm.remaining_mah, 2000.0)

        # 2. Rubble at freezing (0°C) -> 80% capacity (factor 0.80)
        h_zero = self.manager.calculate_survival_horizon(battery_pct=50.0, state=CryoSleepState.CRYO_DEEP_SLEEP, temperature_c=0.0)
        self.assertAlmostEqual(h_zero.temperature_derating, 0.80, places=2)
        self.assertAlmostEqual(h_zero.remaining_mah, 1600.0, places=1)
        self.assertAlmostEqual(h_zero.days / h_norm.days, 0.80, places=2)

        # 3. Sub-zero winter rubble (-10°C) -> 60% capacity (factor 0.60)
        h_sub = self.manager.calculate_survival_horizon(battery_pct=50.0, state=CryoSleepState.CRYO_DEEP_SLEEP, temperature_c=-10.0)
        self.assertAlmostEqual(h_sub.temperature_derating, 0.60, places=2)
        self.assertAlmostEqual(h_sub.remaining_mah, 1200.0, places=1)

    def test_15_clock_drift_and_input_hardening(self):
        """Verifies robustness against clock jumping backwards and invalid input values."""
        # Negative clock drift (e.g. NTP backwards step)
        self.manager.update_sensor_readings(lux=0.0, accel_variance=0.01, battery_pct=50.0, current_time=1000.0)
        # Should transmit at t=1000.0
        self.assertTrue(self.manager.should_transmit_now(current_time=1000.0))
        # Clock jumps back to 990.0: should gracefully handle without exception
        self.assertTrue(self.manager.should_transmit_now(current_time=990.0))

        # PowerProfile voltage synchronization
        custom_profile = PowerProfile(sleep_current_ma=2.0, active_listen_current_ma=350.0, burst_transmit_current_ma=200.0, nominal_voltage=3.7)
        custom_mgr = CryoSleepManager(power_profile=custom_profile)
        self.assertEqual(custom_mgr.voltage, 3.7)
        self.assertEqual(custom_mgr.profile.sleep_current_ma, 2.0)

        # Out-of-bounds battery percentages clamp cleanly
        h_over = self.manager.calculate_survival_horizon(battery_pct=150.0)
        self.assertEqual(h_over.remaining_mah, 4000.0)
        h_under = self.manager.calculate_survival_horizon(battery_pct=-20.0)
        self.assertEqual(h_under.remaining_mah, 0.0)


if __name__ == "__main__":
    unittest.main()
