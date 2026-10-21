package com.example.setudisasterapp.transport

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.ParcelUuid
import androidx.core.content.ContextCompat
import com.example.setudisasterapp.core.SosPacketCodec
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Locale

data class NearbySosSignal(
    val id: String,
    val timestampSeconds: Long,
    val latitude: Double,
    val longitude: Double,
    val severity: Int,
    val disasterType: Int,
    val isTrapped: Boolean,
    val adults: Int,
    val children: Int,
    val elderly: Int,
    val criticalCases: Int,
    val batteryPercent: Int,
    val medicalFlags: Int?,
    val note: String?,
    val rssi: Int?,
    val source: String,
    val altitudeDecimeters: Int? = null,
    val receivedAtMillis: Long = System.currentTimeMillis()
) {
    companion object {
        fun fromPacket(bytes: ByteArray, source: String, rssi: Int? = null, detailBytes: ByteArray? = null): NearbySosSignal? {
            if (bytes.size != 24 && bytes.size != SosPacketCodec.PACKET_SIZE) return null
            if (bytes.size == SosPacketCodec.PACKET_SIZE) {
                val checksum = ByteBuffer.wrap(bytes, 118, 2).order(ByteOrder.BIG_ENDIAN).short.toInt() and 0xffff
                if (SosPacketCodec.calculateCrc16Ccitt(bytes.copyOfRange(0, 118)) != checksum) return null
            }
            val data = ByteBuffer.wrap(bytes).order(ByteOrder.BIG_ENDIAN)
            val hash = ByteArray(6)
            data.get(hash)
            val timestamp = data.int.toLong() and 0xffffffffL
            val latitude = data.int / 1e7
            val longitude = data.int / 1e7
            if (latitude !in -90.0..90.0 || longitude !in -180.0..180.0 || timestamp == 0L) return null
            val altitude = data.short.toInt()
            val triage = data.get().toInt() and 0xff
            val demographics1 = data.get().toInt() and 0xff
            val demographics2 = data.get().toInt() and 0xff
            val mesh = data.get().toInt() and 0xff
            val note = if (bytes.size == SosPacketCodec.PACKET_SIZE) {
                bytes.copyOfRange(26, 118).takeWhile { it != 0.toByte() }.toByteArray()
                    .toString(Charsets.UTF_8).takeIf { it.isNotBlank() }
            } else detailBytes?.drop(2)?.takeWhile { it != 0.toByte() }?.toByteArray()
                ?.toString(Charsets.UTF_8)?.takeIf { it.isNotBlank() }
            val medicalFlags = when {
                bytes.size == SosPacketCodec.PACKET_SIZE -> ByteBuffer.wrap(bytes, 24, 2).order(ByteOrder.BIG_ENDIAN).short.toInt() and 0xffff
                detailBytes != null && detailBytes.size >= 2 -> ByteBuffer.wrap(detailBytes, 0, 2).order(ByteOrder.BIG_ENDIAN).short.toInt() and 0xffff
                else -> null
            }
            return NearbySosSignal(
                id = hash.joinToString("") { String.format(Locale.US, "%02x", it.toInt() and 0xff) },
                timestampSeconds = timestamp,
                latitude = latitude,
                longitude = longitude,
                severity = (triage shr 6) and 0x03,
                disasterType = (triage shr 3) and 0x07,
                isTrapped = triage and 0x04 != 0,
                adults = (demographics1 shr 4) and 0x0f,
                children = demographics1 and 0x0f,
                elderly = (demographics2 shr 4) and 0x0f,
                criticalCases = demographics2 and 0x0f,
                batteryPercent = (mesh and 0x0f) * 10,
                medicalFlags = medicalFlags,
                note = note,
                rssi = rssi,
                source = source,
                altitudeDecimeters = altitude
            )
        }
    }
}

class NearbySosScanner(private val context: Context) {
    private val adapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    private var callback: ScanCallback? = null

    fun start(onSignal: (NearbySosSignal) -> Unit, onStatus: (String) -> Unit) {
        stop()
        val permission = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) Manifest.permission.BLUETOOTH_SCAN else Manifest.permission.ACCESS_FINE_LOCATION
        if (ContextCompat.checkSelfPermission(context, permission) != PackageManager.PERMISSION_GRANTED) {
            onStatus("Bluetooth scan permission required")
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
            onStatus("Bluetooth connect permission required")
            return
        }
        if (runCatching { adapter?.isEnabled }.getOrNull() != true) {
            onStatus("Turn on Bluetooth to find nearby SOS signals")
            return
        }
        val scanner = runCatching { adapter?.bluetoothLeScanner }.getOrNull()
        if (scanner == null) {
            onStatus("BLE scanning is unavailable on this device")
            return
        }
        val scanCallback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult) {
                val packet = result.scanRecord?.getServiceData(ParcelUuid(AndroidBleAdvertiser.SERVICE_UUID)) ?: return
                val details = result.scanRecord?.getServiceData(ParcelUuid(AndroidBleAdvertiser.DETAILS_UUID))
                NearbySosSignal.fromPacket(packet, "Bluetooth", result.rssi, details)?.let(onSignal)
            }

            override fun onBatchScanResults(results: MutableList<ScanResult>) {
                results.forEach { onScanResult(ScanSettings.CALLBACK_TYPE_ALL_MATCHES, it) }
            }

            override fun onScanFailed(errorCode: Int) {
                onStatus("Bluetooth scan failed (code $errorCode)")
                callback = null
            }
        }
        try {
            val settings = ScanSettings.Builder()
                .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
                .setReportDelay(0)
                .build()
            scanner.startScan(null, settings, scanCallback)
            callback = scanCallback
            onStatus("Scanning for nearby SOS signals")
        } catch (_: SecurityException) {
            onStatus("Bluetooth scan permission required")
        } catch (e: IllegalStateException) {
            onStatus("Bluetooth scan could not start: ${e.message ?: "unavailable"}")
        }
    }

    fun stop() {
        val active = callback ?: return
        callback = null
        try { adapter?.bluetoothLeScanner?.stopScan(active) } catch (_: SecurityException) { }
    }
}
