package com.example.setudisasterapp.voice

import android.content.Context
import android.speech.tts.TextToSpeech
import android.util.Log
import java.util.Locale

/**
 * On-Device Vernacular Text-to-Speech Engine.
 * Spoken psychological calming and first-aid instructions in:
 * Hindi (hi), Telugu (te), Tamil (ta), Marathi (mr), Odia (or), English (en).
 * Guarantees zero-grid audio playback with graceful queuing, initialization fallback,
 * and automatic English fallback if a regional voice pack is missing on the device.
 */
class OnDeviceVoiceGuidance(
    private val context: Context,
    private val onInitReady: ((Boolean) -> Unit)? = null
) : TextToSpeech.OnInitListener {

    companion object {
        private const val TAG = "VoiceGuidance"
    }

    private var tts: TextToSpeech? = TextToSpeech(context.applicationContext, this)
    var isInitialized = false
        private set

    private var pendingSpeechText: String? = null
    private var pendingSpeechLang: String? = null

    override fun onInit(status: Int) {
        if (status == TextToSpeech.SUCCESS) {
            tts?.setPitch(1.0f)
            tts?.setSpeechRate(0.95f) // Calm, intelligible cadence
            isInitialized = true
            Log.i(TAG, "TTS initialized successfully.")
            onInitReady?.invoke(true)

            // Play any pending speech that was requested before TTS finished initializing
            pendingSpeechText?.let { text ->
                val lang = pendingSpeechLang ?: "hi"
                pendingSpeechText = null
                pendingSpeechLang = null
                speakCalmInstructions(text, lang)
            }
        } else {
            Log.e(TAG, "TTS initialization failed with status $status")
            isInitialized = false
            onInitReady?.invoke(false)
        }
    }

    private fun resolveLocale(lang: String): Locale {
        return when (lang.lowercase()) {
            "hi" -> Locale("hi", "IN")
            "te" -> Locale("te", "IN")
            "ta" -> Locale("ta", "IN")
            "mr" -> Locale("mr", "IN")
            "or" -> Locale("or", "IN")
            else -> Locale.US
        }
    }

    /**
     * Speaks emergency safety instructions aloud in the chosen vernacular language.
     * Automatically falls back to English if vernacular voice data is not present on device.
     */
    fun speakCalmInstructions(
        text: String,
        lang: String = "hi",
        fallbackEnglish: String? = null
    ): Boolean {
        if (text.isBlank()) return false

        if (!isInitialized || tts == null) {
            Log.w(TAG, "TTS not ready yet, queuing speech for lang: $lang")
            pendingSpeechText = text
            pendingSpeechLang = lang
            return true // Queued
        }

        try {
            val targetLocale = resolveLocale(lang)
            val langResult = tts?.setLanguage(targetLocale)

            val textToSpeak: String
            if (langResult == TextToSpeech.LANG_MISSING_DATA || langResult == TextToSpeech.LANG_NOT_SUPPORTED) {
                // If vernacular language voice is missing on device, fallback to English
                Log.w(TAG, "Voice data missing for $lang, falling back to US English")
                tts?.setLanguage(Locale.US)
                textToSpeak = fallbackEnglish ?: text
            } else {
                textToSpeak = text
            }

            // Prefer an explicitly offline voice if tagged
            try {
                val offlineVoice = tts?.voices?.firstOrNull { voice ->
                    voice.locale.language == targetLocale.language && !voice.isNetworkConnectionRequired
                }
                if (offlineVoice != null) {
                    tts?.voice = offlineVoice
                }
            } catch (e: Throwable) {
                // Ignore voice filtering issues on certain vendor ROMs
            }

            val speakResult = tts?.speak(textToSpeak, TextToSpeech.QUEUE_FLUSH, null, "SetuReliefUtterance")
            return speakResult == TextToSpeech.SUCCESS
        } catch (e: Exception) {
            Log.e(TAG, "TTS speak failed", e)
            return false
        }
    }

    fun isSpeaking(): Boolean {
        return try {
            tts?.isSpeaking == true
        } catch (e: Exception) {
            false
        }
    }

    fun stopSpeaking() {
        try {
            pendingSpeechText = null
            tts?.stop()
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping TTS", e)
        }
    }

    fun shutdown() {
        stopSpeaking()
        try {
            tts?.shutdown()
            tts = null
            isInitialized = false
        } catch (e: Exception) {
            Log.e(TAG, "Error shutting down TTS", e)
        }
    }
}
