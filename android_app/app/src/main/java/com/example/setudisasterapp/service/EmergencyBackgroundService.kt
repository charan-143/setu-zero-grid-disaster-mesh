package com.example.setudisasterapp.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.Build
import android.os.IBinder
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import com.example.setudisasterapp.core.SosPacketCodec
import com.example.setudisasterapp.core.DeviceIdentity
import com.example.setudisasterapp.rag.OnDeviceEmergencyRag
import com.example.setudisasterapp.telemetry.PassiveSensoryTelemetry
import com.example.setudisasterapp.transport.AndroidAcousticBeaconTransmitter
import com.example.setudisasterapp.transport.AndroidBleAdvertiser
import com.example.setudisasterapp.transport.NearbySosScanner
import com.example.setudisasterapp.transport.NearbySosSignal
import com.example.setudisasterapp.transport.NearbySosStore
import com.example.setudisasterapp.MainActivity

/**
 * Background Emergency Trigger Service.
 * Listens for 3 rapid screen on/off presses (Power Button triggers) or broadcast intents
 * even when the app is backgrounded or screen is turned off.
 */
class EmergencyBackgroundService : Service() {

    companion object {
        private const val TAG = "EmergencyService"
        private const val CHANNEL_ID = "SetuEmergencyChannel"
        private const val ALERT_CHANNEL_ID = "SetuNearbyAlerts"
        private const val TRIPLE_TAP_THRESHOLD_MS = 2500L
        const val ACTION_RESTART_SCAN = "com.example.setudisasterapp.RESTART_SCAN"
    }

    private var screenOffCount = 0
    private var lastScreenOffTime = 0L

    private lateinit var telemetry: PassiveSensoryTelemetry
    private val acousticTransmitter = AndroidAcousticBeaconTransmitter()
    private val bleAdvertiser = AndroidBleAdvertiser()
    private lateinit var nearbyScanner: NearbySosScanner
    private val handler = Handler(Looper.getMainLooper())
    private val scanRetry = object : Runnable {
        override fun run() {
            if (!NearbySosStore.status.startsWith("Scanning")) startNearbyScan()
            handler.postDelayed(this, 30_000L)
        }
    }

    private val screenStateReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val action = intent?.action
            if (action == Intent.ACTION_SCREEN_OFF || action == Intent.ACTION_SCREEN_ON) {
                val now = System.currentTimeMillis()
                if (now - lastScreenOffTime < TRIPLE_TAP_THRESHOLD_MS) {
                    screenOffCount++
                    Log.d(TAG, "Rapid Power Press Count: $screenOffCount")
                    if (screenOffCount >= 3) {
                        Log.w(TAG, "🚨 TRIPLE POWER BUTTON TRIGGER DETECTED! INITIATING ZERO-GRID SOS!")
                        triggerEmergencySosBroadcast()
                        screenOffCount = 0
                    }
                } else {
                    screenOffCount = 1
                }
                lastScreenOffTime = now
            }
        }
    }

    override fun onCreate() {
        super.onCreate()
        telemetry = PassiveSensoryTelemetry(this)
        telemetry.startTelemetryMonitoring()

        createNotificationChannel()
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Setu Zero-Grid Safety Active")
            .setContentText("Continuously scanning for nearby SOS signals")
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
        startForeground(1001, notification)
        nearbyScanner = NearbySosScanner(this)
        startNearbyScan()
        handler.postDelayed(scanRetry, 30_000L)

        val filter = IntentFilter().apply {
            addAction(Intent.ACTION_SCREEN_OFF)
            addAction(Intent.ACTION_SCREEN_ON)
        }
        registerReceiver(screenStateReceiver, filter)
        Log.i(TAG, "Emergency background service active")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_RESTART_SCAN) startNearbyScan()
        return START_STICKY
    }

    private fun startNearbyScan() {
        nearbyScanner.start(::onNearbySignal) { status ->
            NearbySosStore.updateStatus(status)
            Log.i(TAG, status)
        }
    }

    private fun onNearbySignal(signal: NearbySosSignal) {
        if (!NearbySosStore.upsert(signal)) return
        val openApp = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        val message = "${signal.adults + signal.children + signal.elderly} people near ${"%.5f".format(signal.latitude)}, ${"%.5f".format(signal.longitude)}"
        val alert = NotificationCompat.Builder(this, ALERT_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle("Nearby SOS detected")
            .setContentText(message)
            .setContentIntent(openApp)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build()
        try {
            (getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager)
                .notify(signal.id.hashCode(), alert)
        } catch (e: SecurityException) {
            Log.w(TAG, "Nearby SOS notification permission denied", e)
        }
    }

    private fun triggerEmergencySosBroadcast() {
        val lat = telemetry.currentLatitude
        val lon = telemetry.currentLongitude
        val altDm = telemetry.currentAltitudeDecimeters
        val batt = telemetry.getBatteryPercentage()
        val trapped = telemetry.isStaticUnderRubble

        val packet = SosPacketCodec.pack(
            deviceId = DeviceIdentity.id(this),
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
            note = "Emergency Power Button 3x Trigger"
        )

        // 1. Broadcast BLE
        bleAdvertiser.startAdvertising(packet) { status ->
            Log.d(TAG, "BLE Status: $status")
        }

        // 2. Transmit Ultrasonic Chirp
        acousticTransmitter.transmitAcousticBeacon(0xDEAD)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Setu Emergency Service",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager?.createNotificationChannel(channel)
            manager?.createNotificationChannel(NotificationChannel(
                ALERT_CHANNEL_ID, "Nearby SOS alerts", NotificationManager.IMPORTANCE_HIGH
            ))
        }
    }

    override fun onDestroy() {
        unregisterReceiver(screenStateReceiver)
        telemetry.stopTelemetryMonitoring()
        handler.removeCallbacks(scanRetry)
        nearbyScanner.stop()
        NearbySosStore.updateStatus("Nearby scanning stopped")
        bleAdvertiser.stopAdvertising()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
