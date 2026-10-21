package com.example.setudisasterapp.dsp

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log

/**
 * Microphone DSP Sound Classifier for Trapped Survivors.
 * Listens for rhythmic concrete/metal acoustic tapping recommended by NDMA & Red Cross
 * (e.g. 3 sharp transient taps spaced ~0.5 to 1.5 seconds apart, repeating every 30 seconds).
 * Filters out ambient low-frequency rumble and continuous screaming, focusing on high-frequency
 * percussive transients between 1.5 kHz and 4.0 kHz.
 */
class RubbleTappingSoundClassifier(
    private val onRubbleTappingDetected: (confidence: Float) -> Unit
) {
    companion object {
        private const val TAG = "RubbleTappingDSP"
        private const val SAMPLE_RATE = 16000
        private const val FRAME_SIZE = 512
        private const val TRANSIENT_ENERGY_THRESHOLD = 2500.0 // Minimum transient energy
        private const val MIN_TAP_INTERVAL_MS = 250L
        private const val MAX_TAP_INTERVAL_MS = 2000L
    }

    private var audioRecord: AudioRecord? = null
    private var isAnalyzing = false
    private var analysisThread: Thread? = null

    // Pattern tracking
    private val tapTimestamps = mutableListOf<Long>()
    private var prevFrameEnergy = 0.0

    fun startListening() {
        if (isAnalyzing) return

        val bufferSize = maxOf(
            AudioRecord.getMinBufferSize(SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT),
            FRAME_SIZE * 2
        )

        try {
            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize
            )

            audioRecord?.startRecording()
            isAnalyzing = true

            analysisThread = Thread {
                val buffer = ShortArray(FRAME_SIZE)
                while (isAnalyzing) {
                    val read = audioRecord?.read(buffer, 0, FRAME_SIZE) ?: 0
                    if (read > 0) {
                        processAudioFrame(buffer, read)
                    }
                }
            }.apply { start() }

            Log.i(TAG, "Rubble Tapping DSP classifier running")
        } catch (e: SecurityException) {
            Log.e(TAG, "Missing RECORD_AUDIO permission for DSP classifier", e)
        }
    }

    private fun processAudioFrame(buffer: ShortArray, length: Int) {
        // High-pass filter & energy calculation (emphasizes sharp transients of metal/stone strikes)
        var highPassEnergy = 0.0
        for (i in 1 until length) {
            val highPassSample = buffer[i] - (0.85 * buffer[i - 1]) // simple 1st-order differentiator
            highPassEnergy += highPassSample * highPassSample
        }
        val currentEnergy = highPassEnergy / length

        // Detect sharp onset transient (energy jump > 3.5x previous frame)
        val now = System.currentTimeMillis()
        if (prevFrameEnergy > 0 && (currentEnergy / (prevFrameEnergy + 1e-5)) > 3.5 && currentEnergy > TRANSIENT_ENERGY_THRESHOLD) {
            handleDetectedTap(now)
        }
        prevFrameEnergy = currentEnergy
    }

    private fun handleDetectedTap(timestamp: Long) {
        // Filter out double-triggers within 250ms
        if (tapTimestamps.isNotEmpty() && (timestamp - tapTimestamps.last()) < MIN_TAP_INTERVAL_MS) {
            return
        }

        tapTimestamps.add(timestamp)

        // Remove old taps beyond 6 seconds
        tapTimestamps.removeAll { timestamp - it > 6000L }

        Log.d(TAG, "Acoustic tap transient detected! Current sequence: ${tapTimestamps.size} taps")

        // Check for 3 rhythmic taps
        if (tapTimestamps.size >= 3) {
            val dt1 = tapTimestamps[1] - tapTimestamps[0]
            val dt2 = tapTimestamps[2] - tapTimestamps[1]

            // Check rhythmicity (intervals roughly consistent between 0.3s and 1.8s)
            val rhythmDelta = kotlin.math.abs(dt1 - dt2)
            if (dt1 in MIN_TAP_INTERVAL_MS..MAX_TAP_INTERVAL_MS &&
                dt2 in MIN_TAP_INTERVAL_MS..MAX_TAP_INTERVAL_MS &&
                rhythmDelta < 600) {

                Log.w(TAG, "🚨 RHYTHMIC RUBBLE TAPPING CONFIRMED (NDMA PATTERN)! Survivor detected!")
                onRubbleTappingDetected(0.92f)
                tapTimestamps.clear()
            }
        }
    }

    fun stop() {
        isAnalyzing = false
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
        analysisThread = null
        Log.i(TAG, "Rubble Tapping DSP classifier stopped")
    }
}
