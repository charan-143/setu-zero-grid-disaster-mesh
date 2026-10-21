package com.example.setudisasterapp.transport

import android.bluetooth.BluetoothAdapter
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.bluetooth.le.AdvertisingSet
import android.bluetooth.le.AdvertisingSetCallback
import android.bluetooth.le.AdvertisingSetParameters
import android.bluetooth.le.BluetoothLeAdvertiser
import android.os.Build
import android.os.ParcelUuid
import android.util.Log
import java.util.UUID

/**
 * Android Native BLE 5.0 Extended Advertiser.
 * Broadcasts 120-byte SOS packets periodically when buried or on surface.
 */
class AndroidBleAdvertiser {

    companion object {
        private const val TAG = "SetuBleAdvertiser"
        val SERVICE_UUID: UUID = UUID.fromString("0000FEAA-0000-1000-8000-00805F9B34FB")
        val DETAILS_UUID: UUID = UUID.fromString("0000FEAB-0000-1000-8000-00805F9B34FB")
    }

    private val bluetoothAdapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    private var advertiser: BluetoothLeAdvertiser? = null
    private var callback: AdvertiseCallback? = null
    private var extendedCallback: AdvertisingSetCallback? = null

    fun startAdvertising(packet120Bytes: ByteArray, onStatus: (String) -> Unit) {
        stopAdvertising()
        if (runCatching { bluetoothAdapter?.isEnabled }.getOrNull() != true) {
            onStatus("Bluetooth is off, unavailable, or permission is missing")
            return
        }

        advertiser = runCatching { bluetoothAdapter?.bluetoothLeAdvertiser }.getOrNull()
        if (advertiser == null) {
            onStatus("BLE Advertiser not supported on this chipset")
            return
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && runCatching { bluetoothAdapter?.isLeExtendedAdvertisingSupported == true }.getOrDefault(false)) {
            val extendedData = AdvertiseData.Builder()
                .setIncludeDeviceName(false)
                .addServiceData(ParcelUuid(SERVICE_UUID), packet120Bytes)
                .build()
            val parameters = AdvertisingSetParameters.Builder()
                .setLegacyMode(false)
                .setConnectable(false)
                .setScannable(false)
                .setInterval(AdvertisingSetParameters.INTERVAL_MEDIUM)
                .setTxPowerLevel(AdvertisingSetParameters.TX_POWER_HIGH)
                .build()
            val extended = object : AdvertisingSetCallback() {
                override fun onAdvertisingSetStarted(advertisingSet: AdvertisingSet?, txPower: Int, status: Int) {
                    if (status == ADVERTISE_SUCCESS) {
                        onStatus("SOS ACTIVE · full details over Bluetooth")
                    } else {
                        extendedCallback = null
                        startLegacyAdvertising(packet120Bytes, onStatus)
                    }
                }
            }
            extendedCallback = extended
            try {
                advertiser?.startAdvertisingSet(parameters, extendedData, null, null, null, extended)
                return
            } catch (_: SecurityException) {
                extendedCallback = null
                onStatus("Missing Bluetooth advertise permission")
                return
            } catch (_: IllegalArgumentException) {
                extendedCallback = null
            }
        }
        startLegacyAdvertising(packet120Bytes, onStatus)
    }

    private fun startLegacyAdvertising(packet120Bytes: ByteArray, onStatus: (String) -> Unit) {
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setTxPowerLevel(AdvertiseSettings.ADVERTISE_TX_POWER_HIGH)
            .setConnectable(false)
            .setTimeout(0)
            .build()

        // Legacy advertisements carry the 24-byte summary. Extended advertisements carry all 120 bytes.
        val broadcastChunk = if (packet120Bytes.size > 24) packet120Bytes.copyOfRange(0, 24) else packet120Bytes

        val data = AdvertiseData.Builder()
            .setIncludeDeviceName(false)
            .setIncludeTxPowerLevel(false)
            .addServiceData(ParcelUuid(SERVICE_UUID), broadcastChunk)
            .build()
        val note = packet120Bytes.copyOfRange(26, 118).takeWhile { it != 0.toByte() }.toByteArray().toString(Charsets.UTF_8)
        val noteBytes = note.codePoints().toArray().fold(ByteArray(0)) { prefix, codePoint ->
            val next = prefix + String(Character.toChars(codePoint)).toByteArray(Charsets.UTF_8)
            if (next.size <= 22) next else prefix
        }
        val scanResponse = AdvertiseData.Builder()
            .addServiceData(ParcelUuid(DETAILS_UUID), packet120Bytes.copyOfRange(24, 26) + noteBytes)
            .build()

        callback = object : AdvertiseCallback() {
            override fun onStartSuccess(settingsInEffect: AdvertiseSettings?) {
                Log.i(TAG, "BLE SOS Beacon broadcast active")
                onStatus("SOS ACTIVE · incident summary over Bluetooth")
            }

            override fun onStartFailure(errorCode: Int) {
                Log.e(TAG, "BLE Advertising failed: $errorCode")
                onStatus("BLE Beacon Failed (Code: $errorCode)")
            }
        }

        try {
            advertiser?.startAdvertising(settings, data, scanResponse, callback)
        } catch (e: SecurityException) {
            onStatus("Missing BLUETOOTH_ADVERTISE permission")
        } catch (e: IllegalArgumentException) {
            onStatus("Bluetooth advertisement is too large for this device")
        }
    }

    fun stopAdvertising() {
        extendedCallback?.let {
            try { advertiser?.stopAdvertisingSet(it) } catch (_: SecurityException) { }
            extendedCallback = null
        }
        callback?.let {
            try {
                advertiser?.stopAdvertising(it)
            } catch (e: SecurityException) {
                Log.w(TAG, "SecurityException stopping BLE advertiser", e)
            }
            callback = null
        }
    }
}
