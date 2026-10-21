package com.example.setudisasterapp.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Intent
import android.util.Log
import android.view.KeyEvent
import android.view.accessibility.AccessibilityEvent
import com.example.setudisasterapp.core.SosPacketCodec
import com.example.setudisasterapp.telemetry.PassiveSensoryTelemetry
import com.example.setudisasterapp.transport.AndroidAcousticBeaconTransmitter
import com.example.setudisasterapp.transport.AndroidBleAdvertiser

/**
 * Android Accessibility Service for Deep Sleep / Lockscreen Hardware Power & Volume Key Capture.
 * By implementing AccessibilityService with flagRequestFilterKeyEvents, this service intercepts
 * raw hardware key events (e.g. Power button or Volume Down 3x) even when the screen is locked,
 * dark, and the CPU is in low-power deep sleep mode.
 */
class HardwareEmergencyKeyService : AccessibilityService() {

    companion object {
        private const val TAG = "HardwareKeySOS"
        private const val MULTI_CLICK_TIMEOUT_MS = 2000L
        private const val TARGET_CLICK_COUNT = 3
    }

    private var clickCount = 0
    private var lastClickTime = 0L

    private lateinit var telemetry: PassiveSensoryTelemetry
    private val acousticTransmitter = AndroidAcousticBeaconTransmitter()
    private val bleAdvertiser = AndroidBleAdvertiser()

    override fun onServiceConnected() {
        super.onServiceConnected()
        telemetry = PassiveSensoryTelemetry(this)
        telemetry.startTelemetryMonitoring()

        val info = AccessibilityServiceInfo().apply {
            flags = AccessibilityServiceInfo.FLAG_REQUEST_FILTER_KEY_EVENTS or
                    AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
            eventTypes = AccessibilityEvent.TYPES_ALL_MASK
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
        }
        serviceInfo = info
        Log.i(TAG, "Hardware Key Accessibility Service connected and intercepting key events")
    }

    override fun onKeyEvent(event: KeyEvent?): Boolean {
        if (event == null) return false

        val keyCode = event.keyCode
        val action = event.action

        // Intercept Power Button (KEYCODE_POWER) or Volume Down (KEYCODE_VOLUME_DOWN) for emergency
        if (action == KeyEvent.ACTION_DOWN && 
            (keyCode == KeyEvent.KEYCODE_POWER || keyCode == KeyEvent.KEYCODE_VOLUME_DOWN)) {
            val now = System.currentTimeMillis()
            if (now - lastClickTime < MULTI_CLICK_TIMEOUT_MS) {
                clickCount++
                Log.d(TAG, "Rapid Hardware Key Press Detected! Count = $clickCount")
                if (clickCount >= TARGET_CLICK_COUNT) {
                    Log.w(TAG, "🚨 TRIPLE HARDWARE KEY DETECTED! DISPATCHING ZERO-GRID SOS!")
                    triggerImmediateZeroGridSos()
                    clickCount = 0
                }
            } else {
                clickCount = 1
            }
            lastClickTime = now
        }

        // Return false to allow system default action (e.g. power toggle) unless 3rd press
        return false
    }

    private fun triggerImmediateZeroGridSos() {
        val lat = telemetry.currentLatitude
        val lon = telemetry.currentLongitude
        val altDm = telemetry.currentAltitudeDecimeters
        val batt = telemetry.getBatteryPercentage()
        val trapped = telemetry.isStaticUnderRubble

        val packet = SosPacketCodec.pack(
            deviceId = "HardwareKeyTriggeredSurvivor_${System.currentTimeMillis() % 10000}",
            timestamp = System.currentTimeMillis() / 1000,
            latitude = lat,
            longitude = lon,
            altitudeDecimeters = altDm,
            severity = 2, // RED Critical
            disasterType = if (trapped) 5 else 0,
            isTrapped = trapped,
            mobility = if (trapped) 0 else 1,
            adults = 1,
            children = 0,
            elderly = 0,
            criticalCases = 1,
            hopCount = 5,
            batteryPct = batt,
            medicalFlags = 0,
            note = "Hardware Triple-Key Emergency SOS Triggered"
        )

        // 1. Broadcast over BLE Extended Advertisements
        bleAdvertiser.startAdvertising(packet) { status ->
            Log.i(TAG, "Hardware SOS BLE Status: $status")
        }

        // 2. Emit 18.5 kHz Ultrasonic Rubble Chirp
        acousticTransmitter.transmitAcousticBeacon(0xFACE)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() {
        Log.w(TAG, "Hardware Key Accessibility Service interrupted")
    }

    override fun onDestroy() {
        telemetry.stopTelemetryMonitoring()
        bleAdvertiser.stopAdvertising()
        super.onDestroy()
    }
}
