package com.example.setudisasterapp.asr

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Robust Zero-Grid On-Device Speech Input Engine.
 * Attempts native on-device speech recognition with graceful fallback
 * and live audio feedback.
 */
class OnDeviceSpeechInput(private val context: Context) {

    companion object {
        private const val TAG = "OnDeviceSpeech"
    }

    private var recognizer: SpeechRecognizer? = null
    var isListening: Boolean = false
        private set

    /** Checks whether on-device or system speech recognition is available on this device */
    fun available(): Boolean {
        return try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                SpeechRecognizer.isOnDeviceRecognitionAvailable(context) ||
                        SpeechRecognizer.isRecognitionAvailable(context)
            } else {
                SpeechRecognizer.isRecognitionAvailable(context)
            }
        } catch (e: Exception) {
            true // Default to enabled so user can attempt speech or fallback
        }
    }

    /** Returns whether high-accuracy Android 12+ on-device recognizer is explicitly installed */
    fun hasDedicatedOfflinePack(): Boolean {
        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
                SpeechRecognizer.isOnDeviceRecognitionAvailable(context)
    }

    fun listen(
        languageTag: String,
        onRms: ((Float) -> Unit)? = null,
        onText: (String) -> Unit,
        onStatus: (String) -> Unit
    ) {
        stop()

        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            onStatus("Microphone permission required. Please grant permission.")
            return
        }

        try {
            val speech = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && SpeechRecognizer.isOnDeviceRecognitionAvailable(context)) {
                Log.i(TAG, "Creating dedicated on-device speech recognizer")
                SpeechRecognizer.createOnDeviceSpeechRecognizer(context)
            } else {
                Log.i(TAG, "Creating standard offline-preferred speech recognizer")
                SpeechRecognizer.createSpeechRecognizer(context)
            }

            recognizer = speech
            isListening = true

            speech.setRecognitionListener(object : RecognitionListener {
                override fun onReadyForSpeech(params: Bundle?) {
                    isListening = true
                    onStatus("🎤 Listening offline… Speak clearly now.")
                }

                override fun onBeginningOfSpeech() {
                    isListening = true
                    onStatus("🎤 Voice detected… Listening offline.")
                }

                override fun onRmsChanged(rmsdB: Float) {
                    onRms?.invoke(rmsdB)
                }

                override fun onBufferReceived(buffer: ByteArray?) {}

                override fun onEndOfSpeech() {
                    isListening = false
                    onStatus("⏳ Transcribing speech on device…")
                }

                override fun onError(error: Int) {
                    isListening = false
                    release()
                    val message = when (error) {
                        SpeechRecognizer.ERROR_NO_MATCH -> "No speech recognized. Try speaking louder or select an emergency preset."
                        SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> "Speech timed out. Tap 'Speak offline' to retry or select a preset."
                        SpeechRecognizer.ERROR_LANGUAGE_NOT_SUPPORTED, SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE ->
                            "Offline language pack not detected for $languageTag. Type your situation or select an emergency preset."
                        SpeechRecognizer.ERROR_AUDIO -> "Audio recording error. Check microphone."
                        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "Microphone permission missing."
                        else -> "Speech recognizer reported code $error. Tap a quick emergency preset below or type."
                    }
                    Log.w(TAG, "Speech error code $error: $message")
                    onStatus(message)
                }

                override fun onResults(results: Bundle?) {
                    isListening = false
                    val textList = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    val text = textList?.firstOrNull()
                    release()
                    if (text.isNullOrBlank()) {
                        onStatus("No speech detected. Please speak louder or select an emergency preset.")
                    } else {
                        onStatus("Speech recognized successfully.")
                        onText(text)
                    }
                }

                override fun onPartialResults(partialResults: Bundle?) {
                    val partial = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                    if (!partial.isNullOrBlank()) {
                        onStatus("Recognizing: $partial")
                    }
                }

                override fun onEvent(eventType: Int, params: Bundle?) {}
            })

            val formattedTag = when (languageTag.lowercase()) {
                "hi" -> "hi-IN"
                "te" -> "te-IN"
                "ta" -> "ta-IN"
                "mr" -> "mr-IN"
                "or" -> "or-IN"
                "en" -> "en-IN"
                else -> languageTag
            }

            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, formattedTag)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, formattedTag)
                putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)
                putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
                putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            }

            speech.startListening(intent)
            onStatus("🎤 Initializing microphone…")
        } catch (e: Exception) {
            isListening = false
            stop()
            Log.e(TAG, "Speech recognizer failure", e)
            onStatus("Microphone initialized. If offline voice pack is missing on your device, use quick presets below or type.")
        }
    }

    fun stop() {
        isListening = false
        val active = recognizer
        recognizer = null
        try {
            active?.cancel()
            active?.destroy()
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping recognizer", e)
        }
    }

    private fun release() {
        isListening = false
        val active = recognizer
        recognizer = null
        try {
            active?.destroy()
        } catch (e: Exception) {
            Log.e(TAG, "Error destroying recognizer", e)
        }
    }
}
