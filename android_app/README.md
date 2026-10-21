# Setu Android app

The **Bhasha‑SOS** tab accepts typed text and, on Android 12 or newer phones with an installed on-device speech recognizer, offline speech. The speech action uses `SpeechRecognizer.createOnDeviceSpeechRecognizer`; it does not invoke a network recognizer. If the phone lacks one, the screen explains that text entry is available. Language recognition depends on language packs installed on that phone.

`BhashaTriageExtractor` locally detects a small set of disaster terms and vulnerabilities, then suggests editable fields. It is deterministic code, not an LLM. The compact JSON shown on the screen is prepared for Android sharing and capped at 500 UTF-8 bytes; the app does not implement LoRa or satellite transports. SOS radio packets remain the existing 120-byte format, so notes are truncated by that format.

`OnDeviceEmergencyRag` retrieves from a small embedded list of source-linked protocols. It is keyword retrieval, not SQLite-VSS or a vector model. Guidance text is available in English and Hindi. Telugu, Tamil, Marathi, and Odia speech recognition can work where the phone has the corresponding offline recognizer, but guidance for these languages currently falls back to English. Spoken guidance is attempted only with a locally installed TTS voice.

The repository does not contain Whisper, Sherpa-ONNX, Gemma, Llama, Piper, or a reviewed set of regional guidance translations. The old placeholder ASR class was removed because it recorded audio without transcribing it.

Guidance sources are stored beside each instruction in `OnDeviceEmergencyRag.kt`. Medical and disaster content should be reviewed by qualified local experts before field deployment.
