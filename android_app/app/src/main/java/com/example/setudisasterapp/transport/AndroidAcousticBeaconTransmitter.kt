package com.example.setudisasterapp.transport

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/**
 * Android Native Acoustic Ultrasonic Transmitter (18.5 kHz - 20 kHz).
 * Runs through standard phone speaker using AudioTrack PCM streaming.
 * Provides deep rubble / concrete sub-surface beaconing.
 */
class AndroidAcousticBeaconTransmitter {

    companion object {
        const val SAMPLE_RATE = 44100
        const val FREQ_MARK = 19200.0   // Bit 1: 19.2 kHz
        const val FREQ_SPACE = 18600.0  // Bit 0: 18.6 kHz
        const val SYMBOL_DURATION = 0.04 // 40ms per bit
    }

    private var isTransmitting = false

    fun transmitAcousticBeacon(payload32Bit: Int) {
        if (isTransmitting) return
        isTransmitting = true

        Thread {
            try {
                val samples = generateAudioSignal(payload32Bit)
                playPcmSamples(samples)
            } finally {
                isTransmitting = false
            }
        }.start()
    }

    private fun generateAudioSignal(payload: Int): ShortArray {
        val allPcm = mutableListOf<Short>()

        // 1. Preamble Chirp (18.5 kHz -> 20.0 kHz, 100ms)
        allPcm.addAll(generateLinearChirp(18500.0, 20000.0, 0.1).toList())
        allPcm.addAll(ShortArray((SAMPLE_RATE * 0.02).toInt()).toList()) // 20ms guard

        // 2. 32-bit FSK Modulation
        for (bitIdx in 31 downTo 0) {
            val bit = (payload shr bitIdx) and 1
            val freq = if (bit == 1) FREQ_MARK else FREQ_SPACE
            allPcm.addAll(generateTone(freq, SYMBOL_DURATION).toList())
        }

        // 3. Postamble Chirp
        allPcm.addAll(ShortArray((SAMPLE_RATE * 0.02).toInt()).toList())
        allPcm.addAll(generateLinearChirp(18500.0, 20000.0, 0.1).toList())

        return allPcm.toShortArray()
    }

    private fun generateTone(freq: Double, duration: Double): ShortArray {
        val numSamples = (duration * SAMPLE_RATE).toInt()
        val pcm = ShortArray(numSamples)
        val fadeSamples = (0.005 * SAMPLE_RATE).toInt()

        for (i in 0 until numSamples) {
            val t = i.toDouble() / SAMPLE_RATE
            var env = 1.0
            if (i < fadeSamples) {
                env = 0.5 * (1.0 - cos(PI * i / fadeSamples))
            } else if (i > numSamples - fadeSamples) {
                env = 0.5 * (1.0 - cos(PI * (numSamples - i) / fadeSamples))
            }
            val sample = 0.8 * env * sin(2.0 * PI * freq * t)
            pcm[i] = (sample * 32767).toInt().coerceIn(-32768, 32767).toShort()
        }
        return pcm
    }

    private fun generateLinearChirp(fStart: Double, fEnd: Double, duration: Double): ShortArray {
        val numSamples = (duration * SAMPLE_RATE).toInt()
        val pcm = ShortArray(numSamples)
        val k = (fEnd - fStart) / duration

        for (i in 0 until numSamples) {
            val t = i.toDouble() / SAMPLE_RATE
            val phase = 2.0 * PI * (fStart * t + 0.5 * k * t * t)
            val sample = 0.8 * sin(phase)
            pcm[i] = (sample * 32767).toInt().coerceIn(-32768, 32767).toShort()
        }
        return pcm
    }

    private fun playPcmSamples(samples: ShortArray) {
        val bufferSize = AudioTrack.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )

        val audioTrack = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                    .setSampleRate(SAMPLE_RATE)
                    .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                    .build()
            )
            .setBufferSizeInBytes(maxOf(bufferSize, samples.size * 2))
            .setTransferMode(AudioTrack.MODE_STATIC)
            .build()

        audioTrack.write(samples, 0, samples.size)
        audioTrack.play()
        Thread.sleep(((samples.size.toDouble() / SAMPLE_RATE) * 1000).toLong() + 200)
        audioTrack.release()
    }
}
