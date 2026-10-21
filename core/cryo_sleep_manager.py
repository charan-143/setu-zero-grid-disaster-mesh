"""
Cryo-Sleep Battery Stretcher & Ultra-Low-Duty-Cycle Power Budgeter
Zero-Grid Disaster Mesh & Triage System (Setu)

Implements dynamic power management for survivor edge nodes trapped under disaster rubble.
Key features:
1. Three-state power state machine:
   - ACTIVE_SEARCH: Continuous radio listening / high-frequency beaconing.
   - CRYO_DEEP_SLEEP: Buried in dark/stationary rubble (58s deep sleep / 200ms wake burst).
   - CRITICAL_RESERVE: Battery <= 10% (180s deep sleep / 200ms wake burst).
2. Sensor ingestion & automated triage (ambient light lux, accelerometer variance, battery status, temperature).
3. Hysteresis on ambient light and battery recovery to prevent flapping from noisy sensors.
4. Physics-grounded survival horizon mathematical modeling:
   T_remain = (C_batt * V_batt * 3600) / (P_sleep * (1 - D) + P_burst * D)
5. Thermal capacity derating modeling for cold rubble and sub-zero conditions.
6. Self-expiring wake interrupt triggers for aftershocks, debris movement, or rescue flashlights.
"""

from dataclasses import dataclass
from enum import Enum
import time
from typing import Optional, Dict, Any


class CryoSleepState(str, Enum):
    """Operational power states for disaster survivor edge nodes."""
    ACTIVE_SEARCH = "ACTIVE_SEARCH"
    CRYO_DEEP_SLEEP = "CRYO_DEEP_SLEEP"
    CRITICAL_RESERVE = "CRITICAL_RESERVE"


@dataclass
class PowerProfile:
    """
    Standard mobile smartphone hardware power profile.
    Values represent real-world consumption for ARM mobile SoC + BLE 5.0 + audio codec.
    """
    sleep_current_ma: float = 2.5           # Deep CPU sleep / suspend-to-RAM (~2.5 - 5.0 mA)
    active_listen_current_ma: float = 400.0  # Radios scanning, CPU active listening (~350 - 450 mA)
    burst_transmit_current_ma: float = 250.0 # BLE Extended Adv + 18.5kHz chirp burst (~250 mA)
    nominal_voltage: float = 3.85            # Standard Li-Po/Li-ion nominal voltage (3.7 - 3.85 V)

    def __post_init__(self):
        self.sleep_current_ma = max(0.01, float(self.sleep_current_ma))
        self.active_listen_current_ma = max(0.01, float(self.active_listen_current_ma))
        self.burst_transmit_current_ma = max(0.01, float(self.burst_transmit_current_ma))
        self.nominal_voltage = max(1.0, float(self.nominal_voltage))


@dataclass
class SurvivalHorizon:
    """Calculated life expectancy and power projections for the node."""
    seconds: float
    hours: float
    days: float
    duty_cycle: float
    avg_power_w: float
    avg_current_ma: float
    remaining_mah: float
    temperature_c: float = 25.0
    temperature_derating: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seconds": round(self.seconds, 1),
            "hours": round(self.hours, 2),
            "days": round(self.days, 2),
            "duty_cycle": round(self.duty_cycle, 6),
            "avg_power_w": round(self.avg_power_w, 5),
            "avg_current_ma": round(self.avg_current_ma, 3),
            "remaining_mah": round(self.remaining_mah, 1),
            "temperature_c": round(self.temperature_c, 1),
            "temperature_derating": round(self.temperature_derating, 3),
        }


@dataclass
class PowerBudgetRecommendation:
    """Recommended duty cycle, sleep timings, and action for the next cycle."""
    state: CryoSleepState
    sleep_duration_s: float
    wake_duration_s: float
    duty_cycle: float
    action: str  # "TRANSMIT_BURST", "DEEP_SLEEP", or "ACTIVE_SCAN"
    time_to_next_burst_s: float
    survival_horizon: SurvivalHorizon
    power_saving_factor: float  # Multiplier vs continuous active listening

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "sleep_duration_s": round(self.sleep_duration_s, 2),
            "wake_duration_s": round(self.wake_duration_s, 3),
            "duty_cycle": round(self.duty_cycle, 6),
            "action": self.action,
            "time_to_next_burst_s": round(self.time_to_next_burst_s, 2),
            "survival_horizon": self.survival_horizon.to_dict(),
            "power_saving_factor": round(self.power_saving_factor, 1),
        }


class CryoSleepManager:
    """
    Manages autonomous power state transitions and survival horizon budgeting
    for edge nodes trapped in disaster zones.
    """

    # Default environmental and hardware thresholds
    LUX_DARK_THRESHOLD: float = 2.0           # Below 2 lux is dark / buried in rubble
    LUX_WAKE_THRESHOLD: float = 5.0           # Hysteresis: requires >= 5 lux to exit dark sleep
    MOTION_STATIONARY_THRESHOLD: float = 0.05  # Low accelerometer variance indicates stationary trapped phone
    MOTION_WAKE_THRESHOLD: float = 0.50        # Higher variance indicates aftershock, digging, or survivor movement
    BATTERY_CRITICAL_THRESHOLD: float = 10.0   # Sub-10% battery enforces CRITICAL_RESERVE
    BATTERY_RECOVERY_THRESHOLD: float = 12.0   # Hysteresis: requires >= 12% to recover from CRITICAL_RESERVE

    # Standard duty cycle timing definitions (in seconds)
    CRYO_SLEEP_DURATION: float = 58.0          # 58 seconds deep sleep
    CRYO_WAKE_BURST_DURATION: float = 0.200    # 200 ms wake burst
    CRITICAL_SLEEP_DURATION: float = 180.0     # 180 seconds sleep for ultra-critical conservation
    CRITICAL_WAKE_BURST_DURATION: float = 0.200

    def __init__(
        self,
        battery_capacity_mah: float = 4000.0,
        nominal_voltage: float = 3.85,
        power_profile: Optional[PowerProfile] = None,
        initial_state: CryoSleepState = CryoSleepState.ACTIVE_SEARCH,
        lux_dark_threshold: float = LUX_DARK_THRESHOLD,
        lux_wake_threshold: float = LUX_WAKE_THRESHOLD,
        motion_stationary_threshold: float = MOTION_STATIONARY_THRESHOLD,
        motion_wake_threshold: float = MOTION_WAKE_THRESHOLD,
        battery_critical_threshold: float = BATTERY_CRITICAL_THRESHOLD,
        battery_recovery_threshold: float = BATTERY_RECOVERY_THRESHOLD,
        clock_source=None
    ):
        self.capacity_mah = max(0.0, float(battery_capacity_mah))

        if power_profile is not None:
            self.profile = power_profile
            self.voltage = self.profile.nominal_voltage
        else:
            self.voltage = max(1.0, float(nominal_voltage))
            self.profile = PowerProfile(nominal_voltage=self.voltage)

        self.lux_dark_threshold = float(lux_dark_threshold)
        self.lux_wake_threshold = max(self.lux_dark_threshold, float(lux_wake_threshold))
        self.motion_stationary_threshold = float(motion_stationary_threshold)
        self.motion_wake_threshold = max(self.motion_stationary_threshold, float(motion_wake_threshold))
        self.battery_critical_threshold = float(battery_critical_threshold)
        self.battery_recovery_threshold = max(self.battery_critical_threshold, float(battery_recovery_threshold))

        self._clock = clock_source or time.time
        self.state: CryoSleepState = initial_state

        # Sensor memory
        self.last_lux: float = 100.0
        self.last_accel_variance: float = 1.0
        self.last_battery_pct: float = 100.0
        self.last_temperature_c: float = 25.0

        # Cycle management
        self._cycle_start_time: float = self._clock()
        self._wake_interrupt_flag: bool = False
        self._wake_interrupt_time: float = 0.0
        self._wake_interrupt_reason: str = ""

    @property
    def current_state(self) -> CryoSleepState:
        return self.state

    def trigger_wake_interrupt(self, reason: str = "aftershock", current_time: Optional[float] = None) -> None:
        """
        Forces an immediate wake interrupt (e.g. from seismic aftershock accelerometer spike,
        survivor button press, or rescue flashlight detection).
        Begins an immediate wake burst.
        """
        now = self._clock() if current_time is None else current_time
        self._wake_interrupt_flag = True
        self._wake_interrupt_time = now
        self._wake_interrupt_reason = reason
        # Reset cycle start to now so an immediate wake burst begins
        self._cycle_start_time = now

    def clear_wake_interrupt(self) -> None:
        """Clears the pending wake interrupt flag."""
        self._wake_interrupt_flag = False
        self._wake_interrupt_time = 0.0
        self._wake_interrupt_reason = ""

    def _is_wake_interrupt_active(self, current_time: float) -> bool:
        """
        Checks if an interrupt wake burst is currently active.
        Auto-expires the interrupt once the wake burst duration has elapsed,
        allowing the node to resume its scheduled deep sleep rather than
        remaining stuck in continuous transmission.
        """
        if not self._wake_interrupt_flag:
            return False
        _, wake_s, _ = self.get_cycle_timings(self.state)
        elapsed_since_trigger = current_time - self._wake_interrupt_time
        if 0.0 <= elapsed_since_trigger < wake_s:
            return True
        # Wake burst has finished; clear flag
        self._wake_interrupt_flag = False
        self._wake_interrupt_reason = ""
        return False

    @staticmethod
    def calculate_temperature_derating(temp_c: float) -> float:
        """
        Models lithium-ion usable capacity degradation due to low ambient rubble temperature.
        - Room temp (>= 20°C): 100% capacity factor (1.0).
        - 0°C to 20°C: Linear derating down to 80% (0.80).
        - Sub-zero rubble (-20°C to 0°C): Steeper derating down to 40% (0.40).
        - Extreme freeze (<-20°C): Clamped to minimum 10% (0.10).
        """
        if temp_c >= 20.0:
            return 1.0
        elif temp_c >= 0.0:
            return 0.80 + (temp_c / 20.0) * 0.20
        elif temp_c >= -20.0:
            return max(0.10, 0.40 + ((temp_c + 20.0) / 20.0) * 0.40)
        else:
            return 0.10

    def update_sensor_readings(
        self,
        lux: float,
        accel_variance: float,
        battery_pct: float,
        current_time: Optional[float] = None,
        temperature_c: Optional[float] = None
    ) -> CryoSleepState:
        """
        Ingests real-time sensor measurements and updates the power state machine.

        State transition rules:
        1. battery_pct <= battery_critical_threshold -> CRITICAL_RESERVE
        2. From ACTIVE_SEARCH:
           If lux <= dark_threshold and accel_variance <= stationary_threshold:
               -> CRYO_DEEP_SLEEP
        3. From CRYO_DEEP_SLEEP:
           If accel_variance >= motion_wake_threshold or lux >= lux_wake_threshold:
               -> ACTIVE_SEARCH (woken up by aftershock, flashlight, or digging)
               (Hysteresis: requires >= lux_wake_threshold rather than dark_threshold to prevent flapping)
        4. From CRITICAL_RESERVE:
           Remains in CRITICAL_RESERVE unless battery_pct recovers above recovery_threshold
           (Hysteresis: requires >= battery_recovery_threshold to prevent battery voltage bounce oscillation).
        """
        now = self._clock() if current_time is None else current_time
        self.last_lux = max(0.0, float(lux))
        self.last_accel_variance = max(0.0, float(accel_variance))
        self.last_battery_pct = max(0.0, min(100.0, float(battery_pct)))
        if temperature_c is not None:
            self.last_temperature_c = float(temperature_c)

        previous_state = self.state

        # Check for seismic or sudden motion interrupt
        if self.last_accel_variance >= self.motion_wake_threshold:
            self.trigger_wake_interrupt(reason="motion_spike", current_time=now)

        # 1. Critical Reserve Check (highest priority when battery is depleted)
        if self.last_battery_pct <= self.battery_critical_threshold:
            self.state = CryoSleepState.CRITICAL_RESERVE

        # 2. Transition from ACTIVE_SEARCH to CRYO_DEEP_SLEEP
        elif self.state == CryoSleepState.ACTIVE_SEARCH:
            is_dark = self.last_lux <= self.lux_dark_threshold
            is_stationary = self.last_accel_variance <= self.motion_stationary_threshold
            if is_dark and is_stationary:
                self.state = CryoSleepState.CRYO_DEEP_SLEEP

        # 3. Transition from CRYO_DEEP_SLEEP to ACTIVE_SEARCH (with hysteresis)
        elif self.state == CryoSleepState.CRYO_DEEP_SLEEP:
            is_illuminated = self.last_lux >= self.lux_wake_threshold
            has_motion = self.last_accel_variance >= self.motion_wake_threshold
            if is_illuminated or has_motion:
                self.state = CryoSleepState.ACTIVE_SEARCH

        # 4. Transition out of CRITICAL_RESERVE if battery restored (with hysteresis)
        elif self.state == CryoSleepState.CRITICAL_RESERVE:
            if self.last_battery_pct >= self.battery_recovery_threshold:
                is_dark = self.last_lux <= self.lux_dark_threshold
                is_stationary = self.last_accel_variance <= self.motion_stationary_threshold
                if is_dark and is_stationary:
                    self.state = CryoSleepState.CRYO_DEEP_SLEEP
                else:
                    self.state = CryoSleepState.ACTIVE_SEARCH

        # If state transitioned, reset cycle timer
        if self.state != previous_state:
            self._cycle_start_time = now

        return self.state

    def get_cycle_timings(self, state: Optional[CryoSleepState] = None) -> tuple[float, float, float]:
        """
        Returns (sleep_duration_s, wake_burst_s, duty_cycle_fraction) for a given state.
        """
        target_state = state or self.state
        if target_state == CryoSleepState.ACTIVE_SEARCH:
            # Continuous active listening / scanning (duty cycle = 1.0)
            return 0.0, 1.0, 1.0
        elif target_state == CryoSleepState.CRYO_DEEP_SLEEP:
            sleep_s = self.CRYO_SLEEP_DURATION
            wake_s = self.CRYO_WAKE_BURST_DURATION
            total_cycle = sleep_s + wake_s
            return sleep_s, wake_s, (wake_s / total_cycle)
        elif target_state == CryoSleepState.CRITICAL_RESERVE:
            sleep_s = self.CRITICAL_SLEEP_DURATION
            wake_s = self.CRITICAL_WAKE_BURST_DURATION
            total_cycle = sleep_s + wake_s
            return sleep_s, wake_s, (wake_s / total_cycle)
        else:
            return 0.0, 1.0, 1.0

    def calculate_survival_horizon(
        self,
        battery_pct: Optional[float] = None,
        state: Optional[CryoSleepState] = None,
        temperature_c: Optional[float] = None
    ) -> SurvivalHorizon:
        """
        Computes remaining node survival horizon using the physical model:
        
        T_remain = (C_batt * V_batt * 3600) / (P_sleep * (1 - D) + P_burst * D)

        Where:
        - C_batt: remaining usable battery capacity in Ampere-hours (Ah),
                  adjusted for low-temperature derating.
        - V_batt: nominal battery voltage (V)
        - D: duty cycle fraction = wake_burst_s / (sleep_s + wake_burst_s)
        - P_sleep: deep sleep power (W) = V_batt * (I_sleep_ma / 1000)
        - P_burst: wake burst or active scan power (W) = V_batt * (I_burst_ma / 1000)
        """
        pct = self.last_battery_pct if battery_pct is None else max(0.0, min(100.0, float(battery_pct)))
        temp = self.last_temperature_c if temperature_c is None else float(temperature_c)
        target_state = state or self.state

        temp_factor = self.calculate_temperature_derating(temp)
        effective_capacity_mah = self.capacity_mah * temp_factor
        remaining_mah = effective_capacity_mah * (pct / 100.0)

        if remaining_mah <= 0.0 or effective_capacity_mah <= 0.0:
            return SurvivalHorizon(
                seconds=0.0,
                hours=0.0,
                days=0.0,
                duty_cycle=0.0,
                avg_power_w=0.0,
                avg_current_ma=0.0,
                remaining_mah=0.0,
                temperature_c=temp,
                temperature_derating=temp_factor
            )

        c_batt_ah = remaining_mah / 1000.0
        v_batt = self.voltage

        # Total energy in Joules (Watt-seconds)
        e_joules = c_batt_ah * v_batt * 3600.0

        sleep_s, wake_s, duty_cycle = self.get_cycle_timings(target_state)

        p_sleep = v_batt * (self.profile.sleep_current_ma / 1000.0)

        if target_state == CryoSleepState.ACTIVE_SEARCH:
            p_burst = v_batt * (self.profile.active_listen_current_ma / 1000.0)
            avg_power_w = p_burst
            avg_current_ma = self.profile.active_listen_current_ma
        else:
            p_burst = v_batt * (self.profile.burst_transmit_current_ma / 1000.0)
            avg_power_w = (p_sleep * (1.0 - duty_cycle)) + (p_burst * duty_cycle)
            avg_current_ma = (
                self.profile.sleep_current_ma * (1.0 - duty_cycle)
                + self.profile.burst_transmit_current_ma * duty_cycle
            )

        if avg_power_w > 0.0:
            t_seconds = e_joules / avg_power_w
        else:
            t_seconds = 0.0

        t_hours = t_seconds / 3600.0
        t_days = t_seconds / 86400.0

        return SurvivalHorizon(
            seconds=t_seconds,
            hours=t_hours,
            days=t_days,
            duty_cycle=duty_cycle,
            avg_power_w=avg_power_w,
            avg_current_ma=avg_current_ma,
            remaining_mah=remaining_mah,
            temperature_c=temp,
            temperature_derating=temp_factor
        )

    def should_transmit_now(self, current_time: Optional[float] = None) -> bool:
        """
        Determines if the edge node should currently be transmitting its wake burst
        (ultrasonic chirp + BLE advertisement) or sleeping.
        """
        now = self._clock() if current_time is None else current_time

        if self._is_wake_interrupt_active(now):
            return True

        if self.state == CryoSleepState.ACTIVE_SEARCH:
            return True

        sleep_s, wake_s, _ = self.get_cycle_timings(self.state)
        total_cycle = sleep_s + wake_s
        if total_cycle <= 0.0:
            return True

        elapsed = max(0.0, now - self._cycle_start_time) % total_cycle
        # The wake burst occurs at the start of each cycle for wake_s seconds
        return elapsed < wake_s

    def get_power_budget_recommendation(
        self,
        current_time: Optional[float] = None
    ) -> PowerBudgetRecommendation:
        """
        Returns full recommendation for current cycle action, sleep timing,
        and projected life expectancy.
        """
        now = self._clock() if current_time is None else current_time
        sleep_s, wake_s, duty_cycle = self.get_cycle_timings(self.state)
        horizon = self.calculate_survival_horizon(self.last_battery_pct, self.state, self.last_temperature_c)
        active_horizon = self.calculate_survival_horizon(self.last_battery_pct, CryoSleepState.ACTIVE_SEARCH, self.last_temperature_c)

        # Power saving factor is the ratio of active listening power vs current mode average power
        if horizon.avg_power_w > 0:
            saving_factor = active_horizon.avg_power_w / horizon.avg_power_w
        else:
            saving_factor = 1.0

        interrupt_active = self._is_wake_interrupt_active(now)

        if self.state == CryoSleepState.ACTIVE_SEARCH:
            action = "ACTIVE_SCAN"
            time_to_next = 0.0
        else:
            total_cycle = sleep_s + wake_s
            if total_cycle <= 0.0:
                elapsed = 0.0
            else:
                elapsed = max(0.0, now - self._cycle_start_time) % total_cycle

            if interrupt_active or elapsed < wake_s:
                action = "TRANSMIT_BURST"
                time_to_next = 0.0
            else:
                action = "DEEP_SLEEP"
                time_to_next = total_cycle - elapsed

        return PowerBudgetRecommendation(
            state=self.state,
            sleep_duration_s=sleep_s,
            wake_duration_s=wake_s,
            duty_cycle=duty_cycle,
            action=action,
            time_to_next_burst_s=max(0.0, time_to_next),
            survival_horizon=horizon,
            power_saving_factor=saving_factor
        )

    def log_life_expectancy_projection(self) -> str:
        """
        Returns a formatted diagnostic telemetry log of the power budgeter state.
        """
        rec = self.get_power_budget_recommendation()
        h = rec.survival_horizon
        temp_str = f" | Temp: {h.temperature_c:.1f}°C" if h.temperature_c != 25.0 else ""
        derate_str = f" (Cold Derated: {h.temperature_derating*100:.0f}%)" if h.temperature_derating < 1.0 else ""
        lines = [
            f"[CRYO-SLEEP MANAGER] State: {self.state.value} | Battery: {self.last_battery_pct:.1f}% ({h.remaining_mah:.0f} mAh{derate_str}){temp_str}",
            f"  - Sensors       : Lux: {self.last_lux:.1f} lx | Motion Variance: {self.last_accel_variance:.3f}",
            f"  - Cycle Profile : Sleep: {rec.sleep_duration_s:.1f}s | Burst: {rec.wake_duration_s*1000:.0f}ms | Duty Cycle: {rec.duty_cycle*100:.3f}%",
            f"  - Average Load  : {h.avg_current_ma:.2f} mA ({h.avg_power_w*1000:.1f} mW)",
            f"  - Horizon       : {h.hours:.1f} hours ({h.days:.2f} days of zero-grid rescue beaconing)",
            f"  - Battery Gain  : {rec.power_saving_factor:.1f}x lifespan multiplier vs active listening",
            f"  - Current Action: {rec.action} (Next burst in {rec.time_to_next_burst_s:.1f}s)"
        ]
        return "\n".join(lines)
