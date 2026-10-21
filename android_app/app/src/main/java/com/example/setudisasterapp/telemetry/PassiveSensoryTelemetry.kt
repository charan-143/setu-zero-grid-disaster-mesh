package com.example.setudisasterapp.telemetry

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.hardware.GeomagneticField
import android.os.BatteryManager
import android.os.Build
import android.os.Bundle
import android.util.Log

/**
 * Production Passive Sensory Ingestion & Tactical AirTag Navigation Engine.
 * 1. Satellite GPS & Network positioning with real-time distance & bearing calculation.
 * 2. Low-pass filtered 6-DOF Gyro-stabilized Compass for smooth directional tracking.
 * 3. Log-distance Path Loss RF estimator for zero-GPS indoor/rubble proximity.
 * 4. Barometric pressure altimeter for multi-floor elevation differentiation.
 * 5. Accelerometer micro-vibration analysis (rubble detection).
 */
class PassiveSensoryTelemetry(private val context: Context) : SensorEventListener, LocationListener {

    companion object {
        private const val TAG = "SensoryTelemetry"
        private const val STANDARD_SEA_LEVEL_PRESSURE = 1013.25f // hPa
    }

    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as? SensorManager
    private val locationManager = context.getSystemService(Context.LOCATION_SERVICE) as? LocationManager
    private val mainHandler = android.os.Handler(android.os.Looper.getMainLooper())

    // Current Location State
    var currentLatitude: Double = 0.0
        private set
    var currentLongitude: Double = 0.0
        private set
    var hasLocationFix: Boolean = false
        private set
    var currentLocationAccuracy: Float = 0f
        private set
    var currentLocationTimeMillis: Long = 0L
        private set
    var currentAltitudeDecimeters: Short = 0
        private set
    var isStaticUnderRubble: Boolean = false
        private set

    // Compass Heading (0° = North, 90° = East, 180° = South, 270° = West)
    var currentHeading: Float = 0f
        private set

    var onHeadingChanged: ((Float) -> Unit)? = null
    var onLocationUpdated: ((Location) -> Unit)? = null

    private var pressureSensor: Sensor? = null
    private var accelSensor: Sensor? = null
    private var rotationSensor: Sensor? = null
    private var geoMagSensor: Sensor? = null
    private var magneticSensor: Sensor? = null

    private var lastAccelMagnitude: Float = 9.8f
    private var staticVibeCount: Int = 0

    private val rotationMatrix = FloatArray(9)
    private val orientationAngles = FloatArray(3)
    private val accelReading = FloatArray(3)
    private val magnetReading = FloatArray(3)
    private var hasAccel = false
    private var hasMagnet = false

    init {
        pressureSensor = sensorManager?.getDefaultSensor(Sensor.TYPE_PRESSURE)
        accelSensor = sensorManager?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        rotationSensor = sensorManager?.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
        geoMagSensor = sensorManager?.getDefaultSensor(Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR)
        magneticSensor = sensorManager?.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)
    }

    fun startTelemetryMonitoring() {
        // Register sensor listeners:
        // Pick exactly ONE orientation sensor to prevent conflicting updates and sensor jitter
        pressureSensor?.let {
            sensorManager?.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
        }
        accelSensor?.let {
            sensorManager?.registerListener(this, it, SensorManager.SENSOR_DELAY_UI)
        }

        val hasVectorSensor = when {
            rotationSensor != null -> {
                sensorManager?.registerListener(this, rotationSensor, SensorManager.SENSOR_DELAY_UI) == true
            }
            geoMagSensor != null -> {
                sensorManager?.registerListener(this, geoMagSensor, SensorManager.SENSOR_DELAY_UI) == true
            }
            else -> false
        }

        if (!hasVectorSensor && magneticSensor != null) {
            sensorManager?.registerListener(this, magneticSensor, SensorManager.SENSOR_DELAY_UI)
        }

        // Fetch location with active updates from Fused, GPS and Network
        try {
            locationManager?.let { lm ->
                val fusedLoc = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    runCatching { lm.getLastKnownLocation(LocationManager.FUSED_PROVIDER) }.getOrNull()
                } else null
                val gpsLoc = runCatching { lm.getLastKnownLocation(LocationManager.GPS_PROVIDER) }.getOrNull()
                val netLoc = runCatching { lm.getLastKnownLocation(LocationManager.NETWORK_PROVIDER) }.getOrNull()
                val passiveLoc = runCatching { lm.getLastKnownLocation(LocationManager.PASSIVE_PROVIDER) }.getOrNull()

                val best = listOfNotNull(fusedLoc, gpsLoc, netLoc, passiveLoc)
                    .filter { it.hasAccuracy() && System.currentTimeMillis() - it.time in 0..30_000L }
                    .minByOrNull { it.accuracy }
                best?.let {
                    currentLatitude = it.latitude
                    currentLongitude = it.longitude
                    currentLocationAccuracy = it.accuracy
                    currentLocationTimeMillis = it.time
                    hasLocationFix = it.latitude != 0.0 || it.longitude != 0.0
                }

                // Active GPS polling (every 1000ms with 0.5 meter threshold)
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && lm.isProviderEnabled(LocationManager.FUSED_PROVIDER)) {
                    runCatching { lm.requestLocationUpdates(LocationManager.FUSED_PROVIDER, 1000L, 0.5f, this) }
                }
                if (lm.isProviderEnabled(LocationManager.GPS_PROVIDER)) {
                    runCatching { lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000L, 0.5f, this) }
                }
                if (lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER)) {
                    runCatching { lm.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 1000L, 0.5f, this) }
                }
                runCatching { lm.requestLocationUpdates(LocationManager.PASSIVE_PROVIDER, 2000L, 1.0f, this) }
            }
        } catch (e: SecurityException) {
            Log.w(TAG, "Location permission missing or disabled", e)
        } catch (e: Exception) {
            Log.w(TAG, "Error starting location updates", e)
        }
    }

    fun stopTelemetryMonitoring() {
        sensorManager?.unregisterListener(this)
        try {
            locationManager?.removeUpdates(this)
        } catch (e: SecurityException) {
            Log.w(TAG, "Error removing location updates", e)
        }
    }

    fun getBatteryPercentage(): Int {
        return try {
            val batteryIntent = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            val level = batteryIntent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
            val scale = batteryIntent?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
            if (level >= 0 && scale > 0) {
                ((level.toFloat() / scale.toFloat()) * 100).toInt()
            } else 50
        } catch (e: Exception) {
            50
        }
    }

    /**
     * Calculates genuine WGS84 distance in meters and bearing in degrees (0..360°) to the target coordinates.
     * Returns Pair(-1f, -1f) if authentic satellite coordinates are not yet available on both devices.
     */
    fun calculateDistanceAndBearing(targetLat: Double, targetLon: Double): Pair<Float, Float> {
        if (targetLat == 0.0 && targetLon == 0.0) return Pair(-1f, -1f)
        if (!hasLocationFix || System.currentTimeMillis() - currentLocationTimeMillis !in 0..30_000L) return Pair(-1f, -1f)

        val results = FloatArray(2)
        Location.distanceBetween(currentLatitude, currentLongitude, targetLat, targetLon, results)
        val distanceMeters = results[0]
        val bearingDegrees = (results[1] + 360f) % 360f
        return Pair(distanceMeters, bearingDegrees)
    }

    /**
     * Estimates proximity distance in meters from Radio RSSI using Log-Distance Path Loss
     * when GPS coordinates are unavailable (e.g. underground or collapsed basements).
     */
    fun estimateDistanceByRssi(rssi: Int?): Float {
        if (rssi == null || rssi >= 0) return -1f
        val txPower = -65.0 // calibrated 1m BLE RSSI
        val pathLossExponent = 2.4 // disaster structural debris attenuation
        val ratio = (txPower - rssi) / (10 * pathLossExponent)
        return kotlin.math.max(0.5, kotlin.math.min(120.0, Math.pow(10.0, ratio))).toFloat()
    }

    /**
     * Computes the relative angle between the responder's current compass heading and the target.
     * 0° / 360° = directly ahead
     * 90° = turn right
     * 270° = turn left
     * 180° = directly behind
     */
    fun calculateRelativeAngle(targetLat: Double, targetLon: Double): Float {
        val (_, bearing) = calculateDistanceAndBearing(targetLat, targetLon)
        if (bearing < 0f) return 0f
        return (bearing - currentHeading + 360f) % 360f
    }

    override fun onSensorChanged(event: SensorEvent?) {
        if (event == null) return

        when (event.sensor.type) {
            Sensor.TYPE_ROTATION_VECTOR,
            Sensor.TYPE_GEOMAGNETIC_ROTATION_VECTOR -> {
                SensorManager.getRotationMatrixFromVector(rotationMatrix, event.values)
                SensorManager.getOrientation(rotationMatrix, orientationAngles)
                val pitch = kotlin.math.abs(orientationAngles[1])
                val azimuthRad = if (pitch > Math.PI / 4) {
                    val remapped = FloatArray(9)
                    SensorManager.remapCoordinateSystem(rotationMatrix, SensorManager.AXIS_X, SensorManager.AXIS_Z, remapped)
                    val angles = FloatArray(3)
                    SensorManager.getOrientation(remapped, angles)
                    angles[0]
                } else {
                    orientationAngles[0]
                }
                val azimuthDeg = (Math.toDegrees(azimuthRad.toDouble()).toFloat() + 360f) % 360f
                smoothHeading(azimuthDeg)
            }
            Sensor.TYPE_ACCELEROMETER -> {
                System.arraycopy(event.values, 0, accelReading, 0, 3)
                hasAccel = true
                updateCompassFromSensors()

                // Rubble micro-vibration detection
                val x = event.values[0]
                val y = event.values[1]
                val z = event.values[2]
                val mag = kotlin.math.sqrt((x * x + y * y + z * z).toDouble()).toFloat()
                val delta = kotlin.math.abs(mag - lastAccelMagnitude)
                lastAccelMagnitude = mag

                if (delta < 0.05f) {
                    staticVibeCount++
                    if (staticVibeCount > 50) isStaticUnderRubble = true
                } else {
                    staticVibeCount = 0
                    isStaticUnderRubble = false
                }
            }
            Sensor.TYPE_MAGNETIC_FIELD -> {
                System.arraycopy(event.values, 0, magnetReading, 0, 3)
                hasMagnet = true
                updateCompassFromSensors()
            }
            Sensor.TYPE_PRESSURE -> {
                val pressureHpa = event.values[0]
                val altitudeM = SensorManager.getAltitude(STANDARD_SEA_LEVEL_PRESSURE, pressureHpa)
                currentAltitudeDecimeters = (altitudeM * 10).toInt().coerceIn(-32768, 32767).toShort()
            }
        }
    }

    private fun updateCompassFromSensors() {
        if (rotationSensor == null && geoMagSensor == null && hasAccel && hasMagnet) {
            val success = SensorManager.getRotationMatrix(rotationMatrix, null, accelReading, magnetReading)
            if (success) {
                SensorManager.getOrientation(rotationMatrix, orientationAngles)
                val pitch = kotlin.math.abs(orientationAngles[1])
                val azimuthRad = if (pitch > Math.PI / 4) {
                    val remapped = FloatArray(9)
                    SensorManager.remapCoordinateSystem(rotationMatrix, SensorManager.AXIS_X, SensorManager.AXIS_Z, remapped)
                    val angles = FloatArray(3)
                    SensorManager.getOrientation(remapped, angles)
                    angles[0]
                } else {
                    orientationAngles[0]
                }
                val azimuthDeg = (Math.toDegrees(azimuthRad.toDouble()).toFloat() + 360f) % 360f
                smoothHeading(azimuthDeg)
            }
        }
    }

    /**
     * Applies an adaptive smoothing filter across the 0-360° circular boundary
     * to eliminate magnetic jitter while keeping pointer response instant on body turns.
     */
    private fun smoothHeading(newHeadingDeg: Float) {
        val declination = if (hasLocationFix) GeomagneticField(
            currentLatitude.toFloat(), currentLongitude.toFloat(),
            currentAltitudeDecimeters / 10f, System.currentTimeMillis()
        ).declination else 0f
        val trueHeading = (newHeadingDeg + declination + 360f) % 360f
        var diff = (trueHeading - currentHeading + 180f) % 360f - 180f
        if (diff < -180f) diff += 360f
        val alpha = if (kotlin.math.abs(diff) > 25f) 0.85f else 0.45f
        currentHeading = (currentHeading + diff * alpha + 360f) % 360f
        mainHandler.post {
            onHeadingChanged?.invoke(currentHeading)
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    override fun onLocationChanged(location: Location) {
        if (!location.hasAccuracy() || System.currentTimeMillis() - location.time !in 0..30_000L) return
        if (hasLocationFix && System.currentTimeMillis() - currentLocationTimeMillis in 0..30_000L &&
            location.accuracy > currentLocationAccuracy * 2f) return
        currentLatitude = location.latitude
        currentLongitude = location.longitude
        currentLocationAccuracy = location.accuracy
        currentLocationTimeMillis = location.time
        hasLocationFix = location.latitude != 0.0 || location.longitude != 0.0
        mainHandler.post {
            onLocationUpdated?.invoke(location)
        }
    }

    override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}
    override fun onProviderEnabled(provider: String) {}
    override fun onProviderDisabled(provider: String) {}
}
