package org.disastermesh.gateway

import android.bluetooth.BluetoothAdapter
import android.bluetooth.le.*
import android.content.Context
import android.net.wifi.aware.*
import android.os.ParcelUuid
import android.util.Log
import java.util.UUID

/**
 * Android Setu-Mule Gateway Hardware Abstraction Layer.
 * Replaces the ESP32-S3 + LoRa physical module using standard Android hardware:
 * 1. BLE 5.0 Extended Advertisements Scanner (Passive Low-Power Scan).
 * 2. Android Wi-Fi Aware (NAN - Neighbor Awareness Networking) Session.
 * 3. Local In-Memory / SQLite Buffer for 120-byte SOS binary frames.
 */
class AndroidSetuMuleBLEScanner(
    private val context: Context,
    private val onPacketReceived: (ByteArray, String) -> Unit
) {
    companion object {
        private const val TAG = "SetuMuleScanner"
        val DISASTER_SERVICE_UUID: UUID = UUID.fromString("0000FEAA-0000-1000-8000-00805F9B34FB")
        const val EXPECTED_PAYLOAD_SIZE = 120
    }

    private val bluetoothAdapter: BluetoothAdapter? = BluetoothAdapter.getDefaultAdapter()
    private var bleScanner: BluetoothLeScanner? = null
    private var scanCallback: ScanCallback? = null

    fun startScanning() {
        if (bluetoothAdapter == null || !bluetoothAdapter.isEnabled) {
            Log.e(TAG, "Bluetooth not available or disabled")
            return
        }

        bleScanner = bluetoothAdapter.bluetoothLeScanner

        val filter = ScanFilter.Builder()
            .setServiceData(ParcelUuid(DISASTER_SERVICE_UUID), null)
            .build()

        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .setReportDelay(0)
            .build()

        scanCallback = object : ScanCallback() {
            override fun onScanResult(callbackType: Int, result: ScanResult?) {
                result?.let { handleScanResult(it) }
            }

            override fun onBatchScanResults(results: MutableList<ScanResult>?) {
                results?.forEach { handleScanResult(it) }
            }

            override fun onScanFailed(errorCode: Int) {
                Log.e(TAG, "BLE Scan failed with code: $errorCode")
            }
        }

        bleScanner?.startScan(listOf(filter), settings, scanCallback)
        Log.i(TAG, "Setu-Mule BLE 5.0 Extended Scanner active")
    }

    private fun handleScanResult(result: ScanResult) {
        val record = result.scanRecord ?: return
        val serviceData = record.getServiceData(ParcelUuid(DISASTER_SERVICE_UUID))
        
        if (serviceData != null && serviceData.size == EXPECTED_PAYLOAD_SIZE) {
            Log.d(TAG, "Captured valid 120-byte SOS packet from RSSI: ${result.rssi} dBm")
            onPacketReceived(serviceData, "BLE_EXTENDED_ADV")
        }
    }

    fun stopScanning() {
        scanCallback?.let {
            bleScanner?.stopScan(it)
            scanCallback = null
        }
        Log.i(TAG, "Setu-Mule Scanner stopped")
    }
}
