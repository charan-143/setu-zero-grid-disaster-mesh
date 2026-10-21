package com.example.setudisasterapp.transport

import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue

/**
 * Production In-Memory Mesh Cache shared between radio transceivers and the Tactical UI.
 * Strictly consumes genuine zero-grid BLE 5.0 and Wi-Fi Aware NAN packets.
 */
object NearbySosStore {
    val signals = mutableStateListOf<NearbySosSignal>()
    var status by mutableStateOf("Scanning zero-grid mesh...")
        private set

    private val mainHandler = Handler(Looper.getMainLooper())

    fun updateStatus(message: String) {
        if (Looper.myLooper() == Looper.getMainLooper()) {
            status = message
        } else {
            mainHandler.post { status = message }
        }
    }

    /**
     * Upserts an authentic zero-grid SOS distress beacon received from the radio mesh.
     * Deduplicates existing beacons by unique cryptographic device ID, updating telemetry and RSSI.
     */
    fun upsert(signal: NearbySosSignal): Boolean {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            mainHandler.post { upsert(signal) }
            return true
        }
        val index = signals.indexOfFirst { it.id == signal.id }
        if (index >= 0) {
            val previous = signals[index]
            val isNewSos = signal.timestampSeconds > previous.timestampSeconds
            signals[index] = if (signal.timestampSeconds == previous.timestampSeconds) {
                signal.copy(
                    note = if ((previous.note?.length ?: 0) > (signal.note?.length ?: 0)) previous.note else signal.note,
                    medicalFlags = signal.medicalFlags ?: previous.medicalFlags,
                    rssi = signal.rssi ?: previous.rssi,
                    altitudeDecimeters = signal.altitudeDecimeters ?: previous.altitudeDecimeters
                )
            } else signal
            return isNewSos
        }
        signals.add(0, signal) // Place newly discovered distress signals at top of triage
        if (signals.size > 200) signals.removeAt(signals.lastIndex)
        return true
    }

    fun clear() {
        if (Looper.myLooper() == Looper.getMainLooper()) {
            signals.clear()
        } else {
            mainHandler.post { signals.clear() }
        }
    }
}
