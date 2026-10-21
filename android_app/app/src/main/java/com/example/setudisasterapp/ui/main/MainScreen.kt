package com.example.setudisasterapp.ui.main

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.setudisasterapp.asr.OnDeviceSpeechInput
import com.example.setudisasterapp.core.BhashaTriage
import com.example.setudisasterapp.core.BhashaTriageExtractor
import com.example.setudisasterapp.core.DeviceIdentity
import com.example.setudisasterapp.core.SosPacketCodec
import com.example.setudisasterapp.rag.OnDeviceEmergencyRag
import com.example.setudisasterapp.service.EmergencyBackgroundService
import com.example.setudisasterapp.transport.AndroidAcousticBeaconTransmitter
import com.example.setudisasterapp.transport.AndroidBleAdvertiser
import com.example.setudisasterapp.transport.NearbySosSignal
import com.example.setudisasterapp.transport.NearbySosStore
import android.os.Handler
import android.os.Looper
import android.content.Intent
import android.net.Uri

private val Ink: Color @Composable get() = MaterialTheme.colorScheme.onSurface
private val Canvas: Color @Composable get() = MaterialTheme.colorScheme.background
private val Surface: Color @Composable get() = MaterialTheme.colorScheme.surface
private val Muted: Color @Composable get() = MaterialTheme.colorScheme.onSurfaceVariant
private val Critical: Color @Composable get() = MaterialTheme.colorScheme.error
private val Blue: Color @Composable get() = MaterialTheme.colorScheme.primary
private val RadarGreen = Color(0xFF00E676)
private val RadarCyan = Color(0xFF00B0FF)

private val supportedLanguages = listOf(
    Triple("hi", "हिन्दी", "Hindi"),
    Triple("en", "English", "English"),
    Triple("te", "తెలుగు", "Telugu"),
    Triple("ta", "தமிழ்", "Tamil"),
    Triple("mr", "मराठी", "Marathi"),
    Triple("or", "ଓଡ଼ିଆ", "Odia")
)

private val emergencyPresetsByLanguage = mapOf(
    "hi" to listOf(
        "🌊 बाढ़: पानी छत तक आ गया है, 2 बच्चे हैं, तुरंत मदद चाहिए" to "पानी छत तक आ गया है, 2 बच्चे हैं, तुरंत मदद चाहिए",
        "🏚️ मलबा: मकान गिरा है, 1 बुजुर्ग फंसे हैं, खून बह रहा है" to "मकान का मलबा गिरा है, 1 बुजुर्ग फंसे हैं, खून बह रहा है",
        "🩺 दवा: इंसुलिन और डायलिसिस की जरूरत है, 3 लोग हैं" to "इंसुलिन और डायलिसिस की जरूरत है, 3 लोग हैं",
        "🔥 आग: इमारत में आग और धुआं फैल रहा है, 4 लोग फंसे हैं" to "इमारत में आग और धुआं फैल रहा है, 4 लोग फंसे हैं"
    ),
    "en" to listOf(
        "🌊 Flood: Water reached roof level, 2 children, need urgent rescue" to "Water reached roof level, 2 children, need urgent rescue",
        "🏚️ Rubble: Building collapsed, 1 elderly trapped, major bleeding" to "Building collapsed, 1 elderly trapped, major bleeding",
        "🩺 Medical: Need insulin and dialysis, 3 people sheltering" to "Need insulin and dialysis, 3 people sheltering",
        "🔥 Fire: Thick smoke and fire spreading, 4 people trapped" to "Thick smoke and fire spreading, 4 people trapped"
    ),
    "te" to listOf(
        "🌊 వరద: నీరు పైకప్పు వరకు వచ్చింది, 2 పిల్లలు ఉన్నారు, తక్షణ సహాయం కావాలి" to "నీరు పైకప్పు వరకు వచ్చింది, 2 పిల్లలు ఉన్నారు, తక్షణ సహాయం కావాలి",
        "🏚️ శిథిలాలు: ఇల్లు కూలిపోయింది, 1 వృద్ధుడు చిక్కుకున్నాడు, రక్తం కారుతోంది" to "ఇల్లు కూలిపోయింది, 1 వృద్ధుడు చిక్కుకున్నాడు, రక్తం కారుతోంది",
        "🩺 మందులు: ఇన్సులిన్ మరియు డయాలసిస్ అవసరం, 3 మంది ఉన్నారు" to "ఇన్సులిన్ మరియు డయాలసిస్ అవసరం, 3 మంది ఉన్నారు",
        "🔥 అగ్ని: భవనంలో మంటలు మరియు పొగ వ్యాపిస్తోంది, 4 మంది చిక్కుకున్నారు" to "భవనంలో మంటలు మరియు పొగ వ్యాపిస్తోంది, 4 మంది చిక్కుకున్నారు"
    ),
    "ta" to listOf(
        "🌊 வெள்ளம்: கூரை வரை தண்ணீர் வந்துவிட்டது, 2 குழந்தைகள் உள்ளனர், உடனடி உதவி தேவை" to "கூரை வரை தண்ணீர் வந்துவிட்டது, 2 குழந்தைகள் உள்ளனர், உடனடி உதவி தேவை",
        "🏚️ இடிபாடு: கட்டிடம் இடிந்துவிட்டது, 1 முதியவர் சிக்கியுள்ளார், இரத்தப்போக்கு உள்ளது" to "கட்டிடம் இடிந்துவிட்டது, 1 முதியவர் சிக்கியுள்ளார், இரத்தப்போக்கு உள்ளது",
        "🩺 மருத்துவம்: இன்சுலின் மற்றும் டயாலிசிஸ் தேவை, 3 பேர் உள்ளனர்" to "இன்சுலின் மற்றும் டயாலிசிస్ தேவை, 3 பேர் உள்ளனர்",
        "🔥 தீ: கட்டிடத்தில் தீ மற்றும் புகை பரவுகிறது, 4 பேர் சிக்கியுள்ளனர்" to "கட்டிடத்தில் தீ மற்றும் புகை பரவுகிறது, 4 பேர் சிக்கியுள்ளனர்"
    ),
    "mr" to listOf(
        "🌊 पूर: पाणी छतापर्यंत आले आहे, 2 मुले आहेत, तातडीने मदत हवी" to "पाणी छतापर्यंत आले आहे, 2 मुले आहेत, तातडीने मदत हवी",
        "🏚️ ढिगारा: घर कोसळले आहे, 1 वृद्ध अडकले आहेत, रक्तस्त्राव होत आहे" to "घर कोसळले आहे, 1 वृद्ध अडकले आहेत, रक्तस्त्राव होत आहे",
        "🩺 औषध: इन्सुलिन आणि डायलिसिसची गरज आहे, 3 लोक आहेत" to "इन्सुलिन आणि डायलिसिसची गरज आहे, 3 लोक आहेत",
        "🔥 आग: इमारतीत आग आणि धूर पसरत आहे, 4 लोक अडकले आहेत" to "इमारतीत आग आणि धूर पसरत आहे, 4 लोक अडकले आहेत"
    ),
    "or" to listOf(
        "🌊 ବନ୍ୟା: ପାଣି ଛାତ ପର୍ଯ୍ୟନ୍ତ ଆସିଗଲାଣି, 2 ପିଲା ଅଛନ୍ତି, ତୁରନ୍ତ ସାହାଯ୍ୟ ଦରକାର" to "ପାଣି ଛାତ ପର୍ଯ୍ୟନ୍ତ ଆସିଗଲାଣି, 2 ପିଲା ଅଛନ୍ତି, ତୁରନ୍ତ ସାହାଯ୍ୟ ଦରକାର",
        "🏚️ ଭଗ୍ନାବଶେଷ: ଘର ଭୁଶୁଡ଼ି ପଡ଼ିଛି, 1 ବୃଦ୍ଧ ଫସି ରହିଛନ୍ତି, ରକ୍ତସ୍ରାବ ହେଉଛି" to "ଘର ଭୁଶୁଡ଼ି ପଡ଼ିଛି, 1 ବୃଦ୍ଧ ଫସି ରହିଛନ୍ତି, ରକ୍ତସ୍ରାବ ହେଉଛି",
        "🩺 ଔଷଧ: ଇନସୁଲିନ ଏବଂ ଡାଏଲିସିସ୍ ଦରକାର, 3 ଲୋକ ଅଛନ୍ତି" to "ଇନସୁଲିନ ଏବଂ ଡାଏଲିସିସ୍ ଦରକାର, 3 ଲୋକ ଅଛନ୍ତି",
        "🔥 ନିଆଁ: କୋଠାରେ ନିଆଁ ଓ ଧୂଆଁ ବ୍ୟାପୁଛି, 4 ଲୋକ ଫସି ରହିଛନ୍ତି" to "କୋଠାରେ ନିଆଁ ଓ ଧୂଆଁ ବ୍ୟାପୁଛି, 4 ଲୋକ ଫସି ରହିଛନ୍ତି"
    )
)

@Composable
fun MainScreen(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val haptic = LocalHapticFeedback.current
    var isBroadcasting by remember { mutableStateOf(false) }
    var selectedLanguage by rememberSaveable { mutableStateOf("hi") }
    var languageMenuOpen by remember { mutableStateOf(false) }
    var voiceInputText by rememberSaveable { mutableStateOf("पानी छत तक आ गया है, 2 बच्चे हैं, इंसुलिन चाहिए") }
    var spokenGuidance by rememberSaveable { mutableStateOf(OnDeviceEmergencyRag.getImmediateGuidance("flood water", "hi")) }
    var englishGuidanceFallback by rememberSaveable { mutableStateOf(OnDeviceEmergencyRag.getImmediateGuidance("flood water", "en")) }
    var guidanceSource by rememberSaveable { mutableStateOf("WHO · Flood Health Advice") }
    var bhashaStatus by remember { mutableStateOf("Ready in all 6 languages: Speak offline, analyze text, or choose an emergency scenario.") }
    var triagePreview by remember { mutableStateOf<BhashaTriage?>(BhashaTriageExtractor.extract("पानी छत तक आ गया है, 2 बच्चे हैं, इंसुलिन चाहिए")) }
    var statusMessage by remember { mutableStateOf("Ready to send an offline SOS") }
    var currentTab by rememberSaveable { mutableIntStateOf(0) }
    var adults by rememberSaveable { mutableStateOf("1") }
    var children by rememberSaveable { mutableStateOf("2") }
    var elderly by rememberSaveable { mutableStateOf("0") }
    var medicalNeed by rememberSaveable { mutableStateOf("Insulin") }
    var personName by rememberSaveable { mutableStateOf("") }
    var isTrapped by rememberSaveable { mutableStateOf(false) }
    var isListening by remember { mutableStateOf(false) }
    var rmsLevel by remember { mutableFloatStateOf(0f) }

    // Selected signal for AirTag precision finding
    var selectedSignalForTracking by remember { mutableStateOf<NearbySosSignal?>(null) }
    var currentCompassHeading by remember { mutableFloatStateOf(0f) }
    var locationRevision by remember { mutableIntStateOf(0) }

    val acoustic = remember { AndroidAcousticBeaconTransmitter() }
    val ble = remember { AndroidBleAdvertiser() }
    val voice = remember { com.example.setudisasterapp.voice.OnDeviceVoiceGuidance(context) }
    val speechInput = remember { OnDeviceSpeechInput(context) }
    val telemetry = remember { com.example.setudisasterapp.telemetry.PassiveSensoryTelemetry(context) }
    val nearbySignals = NearbySosStore.signals
    val mainHandler = remember { Handler(Looper.getMainLooper()) }

    val wifi = remember { com.example.setudisasterapp.transport.AndroidWifiAwareSessionManager(context) { packet ->
        NearbySosSignal.fromPacket(packet, "Wi-Fi Aware")?.let { signal ->
            mainHandler.post { NearbySosStore.upsert(signal) }
        }
    } }
    val tapping = remember { com.example.setudisasterapp.dsp.RubbleTappingSoundClassifier {
        statusMessage = "Rhythmic tapping detected nearby"
    } }

    fun analyzeBhasha(text: String, speakAloud: Boolean = true, lang: String = selectedLanguage) {
        val inputText = text.ifBlank { "Emergency assistance needed" }
        val triage = BhashaTriageExtractor.extract("$inputText $medicalNeed")
        triagePreview = triage
        triage.adults?.let { adults = it.toString() }
        triage.children?.let { children = it.toString() }
        triage.elderly?.let { elderly = it.toString() }
        if (triage.trapped) isTrapped = true
        if (medicalNeed.isBlank() && triage.vulnerabilities.isNotEmpty()) {
            medicalNeed = triage.vulnerabilities.joinToString(", ")
        }

        val guidance = OnDeviceEmergencyRag.retrieve(inputText, lang)
        guidanceSource = guidance.joinToString(" · ") { it.source }

        val (primaryText, fallbackEnglish) = OnDeviceEmergencyRag.getImmediateGuidanceBilingual(inputText, lang)
        spokenGuidance = primaryText
        englishGuidanceFallback = fallbackEnglish

        val langLabel = supportedLanguages.firstOrNull { it.first == lang }?.second ?: lang.uppercase()

        if (speakAloud) {
            val spoken = voice.speakCalmInstructions(primaryText, lang, fallbackEnglish)
            bhashaStatus = if (spoken) {
                "✅ [$langLabel] Extracted details & playing guidance aloud."
            } else {
                "✅ [$langLabel] Extracted details ready. Safety guidance displayed below."
            }
        } else {
            bhashaStatus = "✅ [$langLabel] Extracted triage details updated."
        }
    }

    fun onLanguageSelected(newLang: String) {
        selectedLanguage = newLang
        val presets = emergencyPresetsByLanguage[newLang] ?: emergencyPresetsByLanguage["en"]!!
        val defaultPhrase = presets.first().second
        voiceInputText = defaultPhrase
        analyzeBhasha(defaultPhrase, speakAloud = false, lang = newLang)
    }

    DisposableEffect(Unit) {
        telemetry.startTelemetryMonitoring()
        telemetry.onHeadingChanged = { heading ->
            currentCompassHeading = heading
        }
        telemetry.onLocationUpdated = { locationRevision++ }
        wifi.startWifiAwareMesh()
        tapping.startListening()

        onDispose {
            telemetry.stopTelemetryMonitoring()
            voice.shutdown()
            speechInput.stop()
            wifi.stop()
            tapping.stop()
            ble.stopAdvertising()
        }
    }

    Scaffold(
        modifier = modifier.fillMaxSize().imePadding(),
        containerColor = Canvas,
        bottomBar = {
            NavigationBar(containerColor = Surface, tonalElevation = 0.dp) {
                listOf("Help", "Bhasha", "Nearby").forEachIndexed { index, label ->
                    NavigationBarItem(
                        selected = currentTab == index, onClick = {
                            currentTab = index
                            if (index != 2) selectedSignalForTracking = null
                        },
                        icon = { SetuIcon(index, if (currentTab == index) Blue else Muted) },
                        label = { Text(label, style = MaterialTheme.typography.labelMedium) }
                    )
                }
            }
        }
    ) { contentPadding ->
      Column(
        modifier = Modifier.fillMaxSize().padding(contentPadding).background(Canvas).verticalScroll(rememberScrollState()).padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
      ) {
        // App Header
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(42.dp).background(MaterialTheme.colorScheme.primaryContainer, RoundedCornerShape(14.dp)), contentAlignment = Alignment.Center) { SetuIcon(0, Blue) }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text("setu", color = Ink, fontSize = 26.sp, fontWeight = FontWeight.Bold, letterSpacing = (-1).sp)
                Text("A connection when it matters", color = Muted, style = MaterialTheme.typography.labelSmall)
            }
            Box {
                TextButton(onClick = { languageMenuOpen = true }) {
                    val currentName = supportedLanguages.firstOrNull { it.first == selectedLanguage }?.second ?: "EN"
                    Text(currentName, fontWeight = FontWeight.SemiBold)
                }
                DropdownMenu(expanded = languageMenuOpen, onDismissRequest = { languageMenuOpen = false }) {
                    supportedLanguages.forEach { (tag, label, engName) ->
                        DropdownMenuItem(
                            text = { Text("$label ($engName)") },
                            onClick = {
                                languageMenuOpen = false
                                onLanguageSelected(tag)
                            }
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(4.dp))
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(listOf("Help starts here.", "Bhasha Triage & Languages", "Nearby SOS Finder")[currentTab], style = MaterialTheme.typography.headlineLarge, color = Ink, fontWeight = FontWeight.Bold, letterSpacing = (-1).sp)
            Text(listOf("Reach out to people nearby.", "Offline voice & triage in Hindi, English, Telugu, Tamil, Marathi & Odia.", "Find nearby SOS signals using Bluetooth strength and approximate GPS when available.")[currentTab], style = MaterialTheme.typography.bodyMedium, color = Muted)
        }

        if (currentTab == 0) {
            // TAB 0: SOS BROADCAST
            Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.35f)), shape = RoundedCornerShape(32.dp)) {
                Column(Modifier.fillMaxWidth().padding(20.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("EMERGENCY SOS", color = Critical, style = MaterialTheme.typography.labelMedium, letterSpacing = 2.sp)
                    Text(if (isBroadcasting) "Your signal is active" else "Let someone know.", color = Ink, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                    Box(Modifier.size(224.dp), contentAlignment = Alignment.Center) {
                        Box(Modifier.size(222.dp).border(1.dp, Critical.copy(alpha = 0.12f), CircleShape))
                        Box(Modifier.size(194.dp).border(10.dp, Critical.copy(alpha = 0.08f), CircleShape))
                        Button(
                            onClick = {
                                if (isBroadcasting) {
                                    ble.stopAdvertising()
                                    isBroadcasting = false
                                    statusMessage = "SOS broadcast stopped"
                                } else {
                                    val adultsCount = adults.toIntOrNull()?.coerceIn(0, 15) ?: 1
                                    val childrenCount = children.toIntOrNull()?.coerceIn(0, 15) ?: 0
                                    val elderlyCount = elderly.toIntOrNull()?.coerceIn(0, 15) ?: 0
                                    val triage = triagePreview ?: BhashaTriageExtractor.extract("$voiceInputText $medicalNeed")
                                    val note = listOf(
                                        personName.trim().let { if (it.isNotEmpty()) "Name: $it;" else "" },
                                        voiceInputText.trim(),
                                        medicalNeed.trim().let { if (it.isNotEmpty()) "Medical: $it" else "" },
                                        if (!telemetry.hasLocationFix) "Location unavailable" else ""
                                    ).filter { it.isNotEmpty() }.joinToString(". ").ifEmpty { "Emergency assistance needed" }

                                    val packet = SosPacketCodec.pack(
                                        deviceId = DeviceIdentity.id(context),
                                        timestamp = System.currentTimeMillis() / 1000,
                                        latitude = telemetry.currentLatitude,
                                        longitude = telemetry.currentLongitude,
                                        altitudeDecimeters = telemetry.currentAltitudeDecimeters,
                                        severity = 2,
                                        disasterType = triage.disasterType,
                                        isTrapped = isTrapped || triage.trapped,
                                        mobility = if (isTrapped || triage.trapped) 0 else 1,
                                        adults = adultsCount,
                                        children = childrenCount,
                                        elderly = elderlyCount,
                                        criticalCases = if (triage.medicalFlags == 0) 0 else 1,
                                        hopCount = 0,
                                        batteryPct = telemetry.getBatteryPercentage(),
                                        medicalFlags = triage.medicalFlags,
                                        note = note
                                    )

                                    val (primaryText, fallbackEnglish) = OnDeviceEmergencyRag.getImmediateGuidanceBilingual(note, selectedLanguage)
                                    spokenGuidance = primaryText
                                    englishGuidanceFallback = fallbackEnglish
                                    voice.speakCalmInstructions(primaryText, selectedLanguage, fallbackEnglish)

                                    ble.startAdvertising(packet) { result ->
                                        statusMessage = result
                                        isBroadcasting = result.contains("ACTIVE", ignoreCase = true)
                                    }
                                    if (isTrapped || triage.trapped) acoustic.transmitAcousticBeacon(0xA1B2)
                                }
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Critical, contentColor = MaterialTheme.colorScheme.onError),
                            shape = CircleShape,
                            modifier = Modifier.size(164.dp)
                        ) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(if (isBroadcasting) "STOP" else "SOS", fontSize = 38.sp, fontWeight = FontWeight.Bold)
                                Text(if (isBroadcasting) "BROADCASTING" else "TAP TO SEND", fontSize = 11.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                    Text(statusMessage, color = Muted, style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)
                    Text("Broadcasting on BLE 5.0 mesh · Zero-grid direct radio", color = Muted, style = MaterialTheme.typography.bodySmall, textAlign = TextAlign.Center)
                }
            }

            ElevatedCard(onClick = { currentTab = 1 }, colors = CardDefaults.elevatedCardColors(containerColor = Surface), elevation = CardDefaults.elevatedCardElevation(defaultElevation = 0.dp)) {
                Row(Modifier.fillMaxWidth().padding(20.dp), verticalAlignment = Alignment.CenterVertically) {
                    SetuIcon(1, Blue)
                    Spacer(Modifier.width(16.dp))
                    Column(Modifier.weight(1f)) {
                        Text("Your rescue details", color = Ink, style = MaterialTheme.typography.titleMedium)
                        Text("${(adults.toIntOrNull() ?: 0) + (children.toIntOrNull() ?: 0) + (elderly.toIntOrNull() ?: 0)} people · ${if (isTrapped) "Trapped" else "Situation ready"}", color = Muted, style = MaterialTheme.typography.bodySmall)
                    }
                    Text("Edit / Bhasha", color = Blue, style = MaterialTheme.typography.labelLarge)
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                InfoTile("Zero Internet", "BLE + Wi-Fi Aware Mesh", 2, Modifier.weight(1f))
                InfoTile("Acoustic Beacon", "18.5 kHz Rubble Locator", 1, Modifier.weight(1f))
            }
        } else if (currentTab == 1) {
            // TAB 1: BHASHA, VERNACULAR LANGUAGES, TRIAGE & SAFETY GUIDANCE
            Card(colors = CardDefaults.cardColors(containerColor = Surface), shape = RoundedCornerShape(20.dp)) {
                Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("What’s happening?", color = Ink, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    Text("Select your language, speak naturally, or choose an emergency scenario.", color = Muted, fontSize = 13.sp)

                    // TOP LANGUAGE SWITCHER BAR
                    Text("Choose language:", color = Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    Row(
                        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        supportedLanguages.forEach { (code, nativeName, engName) ->
                            FilterChip(
                                selected = selectedLanguage == code,
                                onClick = { onLanguageSelected(code) },
                                label = {
                                    Text(
                                        text = "$nativeName ($engName)",
                                        fontSize = 12.sp,
                                        fontWeight = if (selectedLanguage == code) FontWeight.Bold else FontWeight.Normal
                                    )
                                }
                            )
                        }
                    }

                    OutlinedTextField(
                        value = personName,
                        onValueChange = { personName = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Name or identifier (optional)") },
                        singleLine = true,
                        shape = RoundedCornerShape(14.dp)
                    )

                    OutlinedTextField(
                        value = voiceInputText,
                        onValueChange = {
                            voiceInputText = it
                            val triage = BhashaTriageExtractor.extract("$it $medicalNeed")
                            triagePreview = triage
                        },
                        modifier = Modifier.fillMaxWidth(),
                        label = {
                            val langName = supportedLanguages.firstOrNull { it.first == selectedLanguage }?.second ?: "Language"
                            Text("Situation Description ($langName)")
                        },
                        placeholder = { Text("Describe emergency in $selectedLanguage") },
                        minLines = 3,
                        shape = RoundedCornerShape(14.dp)
                    )

                    // Speak offline & Analyze Buttons
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(10.dp)
                    ) {
                        Button(
                            onClick = {
                                if (isListening) {
                                    speechInput.stop()
                                    isListening = false
                                    bhashaStatus = "Microphone stopped."
                                } else {
                                    isListening = true
                                    bhashaStatus = "🎤 Listening offline ($selectedLanguage)… Speak now."
                                    speechInput.listen(
                                        languageTag = selectedLanguage,
                                        onRms = { rms -> rmsLevel = rms },
                                        onText = { transcript ->
                                            isListening = false
                                            voiceInputText = transcript
                                            analyzeBhasha(transcript, speakAloud = true, lang = selectedLanguage)
                                        },
                                        onStatus = { status ->
                                            bhashaStatus = status
                                            if (!speechInput.isListening) isListening = false
                                        }
                                    )
                                }
                            },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (isListening) Critical else MaterialTheme.colorScheme.primaryContainer,
                                contentColor = if (isListening) MaterialTheme.colorScheme.onError else MaterialTheme.colorScheme.onPrimaryContainer
                            ),
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text(if (isListening) "⏹ Stop Listening" else "🎤 Speak offline", fontWeight = FontWeight.Bold)
                        }

                        Button(
                            onClick = {
                                analyzeBhasha(voiceInputText, speakAloud = true, lang = selectedLanguage)
                            },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = MaterialTheme.colorScheme.primary,
                                contentColor = MaterialTheme.colorScheme.onPrimary
                            ),
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("⚡ Analyse text", fontWeight = FontWeight.Bold)
                        }
                    }

                    // Live mic indicator when listening
                    AnimatedVisibility(visible = isListening) {
                        Surface(
                            color = MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.5f),
                            shape = RoundedCornerShape(10.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Row(
                                modifier = Modifier.padding(10.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                Text("🔴", fontSize = 14.sp)
                                Text("Listening offline ($selectedLanguage)... Speak your emergency.", color = Ink, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                            }
                        }
                    }

                    // Status display
                    Text(bhashaStatus, color = Blue, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium)

                    // Quick Emergency Voice Presets in the Selected Language
                    val activePresets = emergencyPresetsByLanguage[selectedLanguage] ?: emergencyPresetsByLanguage["en"]!!
                    val activeLangName = supportedLanguages.firstOrNull { it.first == selectedLanguage }?.second ?: selectedLanguage.uppercase()
                    Text("Emergency scenarios ($activeLangName):", color = Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)

                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        activePresets.forEach { (label, phrase) ->
                            Surface(
                                color = MaterialTheme.colorScheme.surfaceContainerHigh,
                                shape = RoundedCornerShape(10.dp),
                                modifier = Modifier.fillMaxWidth().clickable {
                                    voiceInputText = phrase
                                    analyzeBhasha(phrase, speakAloud = true, lang = selectedLanguage)
                                }
                            ) {
                                Text(
                                    text = label,
                                    color = Ink,
                                    fontSize = 13.sp,
                                    lineHeight = 18.sp,
                                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp)
                                )
                            }
                        }
                    }

                    HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp), color = MaterialTheme.colorScheme.outlineVariant)

                    // Editable Headcount & Medical Need
                    OutlinedTextField(
                        value = medicalNeed,
                        onValueChange = {
                            medicalNeed = it
                            triagePreview = BhashaTriageExtractor.extract("$voiceInputText $it")
                        },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Medical condition or need") },
                        placeholder = { Text("e.g. insulin, dialysis, bleeding, fracture") },
                        singleLine = true,
                        shape = RoundedCornerShape(14.dp)
                    )

                    Text("Group Headcount", color = Ink, fontWeight = FontWeight.SemiBold)
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        CountField("Adults", adults, { adults = it }, Modifier.fillMaxWidth())
                        CountField("Children", children, { children = it }, Modifier.fillMaxWidth())
                        CountField("Older adults", elderly, { elderly = it }, Modifier.fillMaxWidth())
                    }

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Switch(checked = isTrapped, onCheckedChange = { isTrapped = it })
                        Spacer(Modifier.width(8.dp))
                        Column {
                            Text("Trapped under structure or rubble", color = Ink, fontWeight = FontWeight.Medium)
                            Text("Activates 18.5 kHz acoustic responder beacon", color = Muted, fontSize = 12.sp)
                        }
                    }
                }
            }

            // FEATURE 3: EXTRACTED TEXT & TRIAGE DETAILS CARD
            val currentTriage = triagePreview ?: BhashaTriageExtractor.extract("$voiceInputText $medicalNeed")
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer),
                shape = RoundedCornerShape(20.dp)
            ) {
                Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text("📋 Extracted Triage Details", color = Ink, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                        Surface(
                            color = MaterialTheme.colorScheme.primary,
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Text("120-Byte Wire Ready", color = MaterialTheme.colorScheme.onPrimary, fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp))
                        }
                    }

                    // Hazard & Threat
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Surface(color = MaterialTheme.colorScheme.surface, shape = RoundedCornerShape(10.dp), modifier = Modifier.weight(1f)) {
                            Column(Modifier.padding(10.dp)) {
                                Text("HAZARD TYPE", color = Muted, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                                Text(currentTriage.disasterLabel, color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                            }
                        }
                        Surface(color = MaterialTheme.colorScheme.surface, shape = RoundedCornerShape(10.dp), modifier = Modifier.weight(1f)) {
                            Column(Modifier.padding(10.dp)) {
                                Text("IMMEDIATE THREAT", color = Muted, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                                Text(currentTriage.immediateThreat, color = Critical, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
                            }
                        }
                    }

                    // Headcount & Trapped Breakdown
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Surface(color = MaterialTheme.colorScheme.surface, shape = RoundedCornerShape(10.dp), modifier = Modifier.weight(1f)) {
                            Column(Modifier.padding(10.dp)) {
                                Text("TOTAL HEADCOUNT", color = Muted, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                                Text("${(adults.toIntOrNull() ?: 1) + (children.toIntOrNull() ?: 0) + (elderly.toIntOrNull() ?: 0)} People", color = Ink, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                Text("Adults: $adults · Kids: $children · Seniors: $elderly", color = Muted, fontSize = 11.sp)
                            }
                        }
                        Surface(color = MaterialTheme.colorScheme.surface, shape = RoundedCornerShape(10.dp), modifier = Modifier.weight(1f)) {
                            Column(Modifier.padding(10.dp)) {
                                Text("TRAPPED STATUS", color = Muted, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                                Text(if (isTrapped || currentTriage.trapped) "⚠️ Trapped" else "Ambulatory", color = if (isTrapped || currentTriage.trapped) Critical else Blue, fontWeight = FontWeight.Bold, fontSize = 14.sp)
                                Text(if (isTrapped || currentTriage.trapped) "Beacon armed" else "Mobile", color = Muted, fontSize = 11.sp)
                            }
                        }
                    }

                    // Vulnerabilities
                    val vulnList = currentTriage.vulnerabilities.ifEmpty {
                        if (medicalNeed.isNotBlank()) listOf(medicalNeed) else emptyList()
                    }
                    if (vulnList.isNotEmpty()) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text("Medical Flags: ", color = Ink, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                            Text(vulnList.joinToString(" · "), color = Critical, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                        }
                    }

                    // Compact Wire Packet Representation
                    val compact = currentTriage.compactJson(
                        telemetry.currentLatitude.takeIf { telemetry.hasLocationFix },
                        telemetry.currentLongitude.takeIf { telemetry.hasLocationFix }
                    )
                    Text("Zero-Grid Payload (${compact.toByteArray(Charsets.UTF_8).size} bytes):", color = Ink, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    Surface(
                        color = MaterialTheme.colorScheme.surface,
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Text(compact, color = Muted, fontSize = 11.sp, modifier = Modifier.padding(8.dp))
                    }

                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(
                            onClick = {
                                context.startActivity(android.content.Intent.createChooser(
                                    android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                        type = "text/plain"
                                        putExtra(android.content.Intent.EXTRA_TEXT, "SETU SOS TRIAGE:\n$compact\nDetails: $voiceInputText")
                                    }, "Share triage summary"
                                ))
                            },
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("📤 Share Summary", fontSize = 12.sp)
                        }

                        Button(
                            onClick = {
                                analyzeBhasha(voiceInputText, speakAloud = false, lang = selectedLanguage)
                            },
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("🔄 Refresh", fontSize = 12.sp)
                        }
                    }
                }
            }

            // FEATURE 4: OFFLINE SAFETY GUIDANCE
            Card(
                colors = CardDefaults.cardColors(containerColor = Surface),
                shape = RoundedCornerShape(20.dp)
            ) {
                Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        val langLabel = supportedLanguages.firstOrNull { it.first == selectedLanguage }?.second ?: selectedLanguage.uppercase()
                        Text("🛡️ Offline Safety Guidance ($langLabel)", color = Ink, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                        Surface(color = MaterialTheme.colorScheme.primaryContainer, shape = RoundedCornerShape(6.dp)) {
                            Text("WHO · NDMA Verified", color = Blue, fontSize = 10.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp))
                        }
                    }

                    // Main Guidance Text
                    Surface(
                        color = MaterialTheme.colorScheme.surfaceContainerLow,
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Text(spokenGuidance, color = Ink, fontSize = 15.sp, lineHeight = 22.sp, fontWeight = FontWeight.Medium)
                            if (guidanceSource.isNotBlank()) {
                                Text("Protocol Source: $guidanceSource", color = Muted, fontSize = 11.sp)
                            }
                        }
                    }

                    // Audio Playback Controls
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Button(
                            onClick = {
                                val spoken = voice.speakCalmInstructions(spokenGuidance, selectedLanguage, englishGuidanceFallback)
                                bhashaStatus = if (spoken) "🔊 Playing guidance in $selectedLanguage aloud…" else "Offline voice audio initialized."
                            },
                            colors = ButtonDefaults.buttonColors(containerColor = Blue),
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("🔊 Play Aloud", fontWeight = FontWeight.Bold)
                        }

                        OutlinedButton(
                            onClick = {
                                voice.stopSpeaking()
                                bhashaStatus = "Voice stopped."
                            },
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.weight(1f)
                        ) {
                            Text("⏹ Stop Audio", fontWeight = FontWeight.Medium)
                        }
                    }

                    // Quick Safety Topic Switcher
                    Text("Select disaster protocol:", color = Ink, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
                    val safetyTopics = listOf(
                        "Floodwater" to "🌊 Flood",
                        "Trapped under rubble" to "🏚️ Rubble",
                        "Fire & Smoke" to "🔥 Fire",
                        "Major bleeding" to "🩸 Bleeding",
                        "Snakebite" to "🐍 Snake",
                        "Earthquake" to "🌍 Quake",
                        "Cyclone" to "🌪️ Cyclone",
                        "Oral rehydration (ORS)" to "💧 ORS"
                    )

                    Row(
                        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        safetyTopics.forEach { (topicKey, chipLabel) ->
                            val isSelected = spokenGuidance.contains(topicKey, ignoreCase = true)
                            FilterChip(
                                selected = isSelected,
                                onClick = {
                                    val (primaryText, enText) = OnDeviceEmergencyRag.getGuidanceByTopic(topicKey, selectedLanguage)
                                    spokenGuidance = primaryText
                                    englishGuidanceFallback = enText
                                    guidanceSource = "WHO / NDMA Official Protocol"
                                    voice.speakCalmInstructions(primaryText, selectedLanguage, enText)
                                    bhashaStatus = "Playing $chipLabel safety guidance in $selectedLanguage."
                                },
                                label = { Text(chipLabel, fontSize = 12.sp) }
                            )
                        }
                    }
                }
            }

            FilledTonalButton(
                onClick = { currentTab = 0 },
                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp),
                shape = RoundedCornerShape(14.dp)
            ) {
                Text("Done · Return to SOS Broadcast", fontWeight = FontWeight.Bold)
            }
        } else {
            // TAB 2: NEARBY SIGNALS & AIRTAG PRECISION FINDER
            if (selectedSignalForTracking != null) {
                val trackingSignal = nearbySignals.firstOrNull { it.id == selectedSignalForTracking!!.id }
                    ?: selectedSignalForTracking!!
                locationRevision // Recalculate when the receiver gets a fresh location.
                val (distanceMeters, bearingDegrees) = telemetry.calculateDistanceAndBearing(
                    trackingSignal.latitude,
                    trackingSignal.longitude
                )
                // The packet has no sender accuracy. GPS cannot resolve a bearing at close range.
                val gpsUncertaintyM = maxOf(30f, telemetry.currentLocationAccuracy * 2f + 20f)
                val hasGps = distanceMeters >= 0f && distanceMeters > gpsUncertaintyM
                val relativeAngle = if (hasGps) (bearingDegrees - currentCompassHeading + 360f) % 360f else 0f
                val isDirectlyAhead = hasGps && (relativeAngle in 348f..360f || relativeAngle in 0f..12f)
                val signalStrength = trackingSignal.rssi?.let {
                    when {
                        it >= -60 -> "Very strong"
                        it >= -75 -> "Strong"
                        it >= -90 -> "Moderate"
                        else -> "Weak"
                    }
                } ?: "Unavailable"

                // Haptic tick when pointing directly ahead
                LaunchedEffect(isDirectlyAhead) {
                    if (isDirectlyAhead) {
                        haptic.performHapticFeedback(HapticFeedbackType.LongPress)
                    }
                }

                Card(
                    colors = CardDefaults.cardColors(containerColor = Surface),
                    shape = RoundedCornerShape(28.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        Modifier.fillMaxWidth().padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        // Header Bar
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            IconButton(onClick = { selectedSignalForTracking = null }) {
                                Text("←", fontSize = 24.sp, fontWeight = FontWeight.Bold, color = Ink)
                            }
                            Column(Modifier.weight(1f)) {
                                val name = trackingSignal.note?.takeIf { it.startsWith("Name: ") }?.substringAfter("Name: ")?.substringBefore(";")?.takeIf { it.isNotBlank() }
                                Text(name ?: "Beacon #${trackingSignal.id.take(6)}", color = Ink, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                                Text(if (hasGps) "GPS DIRECTION · APPROXIMATE" else "NEARBY SIGNAL FINDER", color = Blue, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                            }
                            Surface(
                                color = if (isDirectlyAhead) RadarGreen.copy(alpha = 0.2f) else MaterialTheme.colorScheme.surfaceContainerHigh,
                                shape = RoundedCornerShape(12.dp)
                            ) {
                                Text(
                                    if (isDirectlyAhead) "GPS AHEAD" else if (hasGps) "GPS GUIDANCE" else "DIRECTION UNKNOWN",
                                    color = if (isDirectlyAhead) RadarGreen else Muted,
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                                )
                            }
                        }

                        // AirTag Radar & Compass Pointer HUD
                        val radarBlue = Blue
                        val radarMuted = Muted
                        val radarCritical = Critical
                        Box(Modifier.size(240.dp), contentAlignment = Alignment.Center) {
                            Canvas(Modifier.fillMaxSize()) {
                                val center = Offset(size.width / 2f, size.height / 2f)
                                val radius = size.width / 2f - 8f

                                // Outer radar circle
                                drawCircle(
                                    color = if (isDirectlyAhead) RadarGreen.copy(alpha = 0.6f) else radarBlue.copy(alpha = 0.3f),
                                    radius = radius,
                                    style = Stroke(width = 3f)
                                )

                                // Middle range ring
                                drawCircle(
                                    color = if (isDirectlyAhead) RadarGreen.copy(alpha = 0.35f) else radarBlue.copy(alpha = 0.15f),
                                    radius = radius * 0.65f,
                                    style = Stroke(width = 2f)
                                )

                                // Inner bullseye ring
                                drawCircle(
                                    color = if (isDirectlyAhead) RadarGreen.copy(alpha = 0.25f) else radarBlue.copy(alpha = 0.1f),
                                    radius = radius * 0.32f,
                                    style = Stroke(width = 1.5f)
                                )

                                // Compass Dial & Cardinal Crosshairs rotating with physical phone heading
                                rotate(degrees = -currentCompassHeading, pivot = center) {
                                    drawLine(
                                        color = if (isDirectlyAhead) RadarGreen.copy(alpha = 0.4f) else radarMuted.copy(alpha = 0.25f),
                                        start = Offset(center.x, center.y - radius),
                                        end = Offset(center.x, center.y + radius),
                                        strokeWidth = 1.5f
                                    )
                                    drawLine(
                                        color = if (isDirectlyAhead) RadarGreen.copy(alpha = 0.4f) else radarMuted.copy(alpha = 0.25f),
                                        start = Offset(center.x - radius, center.y),
                                        end = Offset(center.x + radius, center.y),
                                        strokeWidth = 1.5f
                                    )
                                    // North Indicator Dot
                                    drawCircle(
                                        color = radarCritical,
                                        radius = 5f,
                                        center = Offset(center.x, center.y - radius + 8f)
                                    )
                                }

                                if (hasGps) {
                                    // 360° Precision Direction Arrow rotating toward survivor relative to heading
                                    rotate(degrees = relativeAngle, pivot = center) {
                                        val arrowPath = Path().apply {
                                            moveTo(center.x, center.y - radius * 0.85f) // Tip
                                            lineTo(center.x + 28f, center.y + radius * 0.25f) // Right corner
                                            lineTo(center.x, center.y + radius * 0.05f) // Inner notch
                                            lineTo(center.x - 28f, center.y + radius * 0.25f) // Left corner
                                            close()
                                        }
                                        val arrowColor = if (isDirectlyAhead) RadarGreen else RadarCyan
                                        drawPath(arrowPath, color = arrowColor)
                                        drawPath(arrowPath, color = Color.White, style = Stroke(width = 2.5f, cap = StrokeCap.Round))
                                    }
                                } else {
                                    // Concentric RF Ranging Pulse Ring
                                    drawCircle(
                                        color = radarBlue.copy(alpha = 0.45f),
                                        radius = radius * 0.5f,
                                        style = Stroke(width = 3f)
                                    )
                                }

                                // Center bullseye point
                                drawCircle(color = if (isDirectlyAhead) RadarGreen else radarBlue, radius = 6f)
                            }
                        }

                        // Big Distance & Turn Instructions
                        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            if (hasGps) {
                                Text(
                                    text = if (distanceMeters < 1000f) "~${distanceMeters.toInt()} m" else "~${"%.1f".format(distanceMeters / 1000f)} km",
                                    color = if (isDirectlyAhead) RadarGreen else Ink,
                                    fontSize = 42.sp,
                                    fontWeight = FontWeight.ExtraBold,
                                    letterSpacing = (-1).sp
                                )

                                val guidancePrompt = when {
                                    isDirectlyAhead -> "⬆ DIRECTLY AHEAD · WALK FORWARD"
                                    relativeAngle in 12f..180f -> "➔ TURN RIGHT ${relativeAngle.toInt()}°"
                                    else -> "⬅ TURN LEFT ${(360f - relativeAngle).toInt()}°"
                                }

                                Text(
                                    text = guidancePrompt,
                                    color = if (isDirectlyAhead) RadarGreen else Blue,
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Bold
                                )

                                // Compass Azimuth & Bearing readout
                                Text(
                                    text = "Approximate GPS bearing: ${bearingDegrees.toInt()}° · Current fix ±${telemetry.currentLocationAccuracy.toInt()} m",
                                    color = Muted,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Medium
                                )
                            } else {
                                Text(
                                    text = signalStrength,
                                    color = Ink,
                                    fontSize = 42.sp,
                                    fontWeight = FontWeight.ExtraBold,
                                    letterSpacing = (-1).sp
                                )

                                Text(
                                    text = "Bluetooth signal ${trackingSignal.rssi?.let { "· $it dBm" } ?: "unavailable"}",
                                    color = Blue,
                                    fontSize = 14.sp,
                                    fontWeight = FontWeight.Bold
                                )

                                Text(
                                    text = if (distanceMeters >= 0f) "GPS positions are within their uncertainty. Direction cannot be resolved here." else "GPS unavailable. Move a few steps and watch whether signal strength rises.",
                                    color = Muted,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Medium
                                )
                            }

                            // Vertical Floor/Height Offset
                            Text("Bluetooth strength cannot identify a direction or reliably measure metres. Buildings and phone orientation change RSSI.", color = Muted, fontSize = 12.sp, fontWeight = FontWeight.Medium)
                        }

                        HorizontalDivider(color = MaterialTheme.colorScheme.outlineVariant)

                        // Survivor Full Dossier Card
                        Surface(color = MaterialTheme.colorScheme.surfaceContainerLow, shape = RoundedCornerShape(16.dp), modifier = Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                Text("SURVIVOR INCIDENT DOSSIER", color = Critical, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                                Text(
                                    "${trackingSignal.disasterLabel()} · ${if (trackingSignal.isTrapped) "⚠️ Trapped under rubble" else "Ambulatory"} · ${trackingSignal.severityLabel()}",
                                    color = Ink, fontSize = 14.sp, fontWeight = FontWeight.SemiBold
                                )
                                Text(
                                    "People: ${trackingSignal.adults + trackingSignal.children + trackingSignal.elderly} total (${trackingSignal.adults} adults, ${trackingSignal.children} kids, ${trackingSignal.elderly} seniors)",
                                    color = Ink, fontSize = 13.sp
                                )
                                trackingSignal.medicalFlags?.let { flags ->
                                    if (flags != 0) Text("Medical flags: ${medicalLabels(flags)}", color = Critical, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                }
                                val noteMessage = trackingSignal.note?.replace(Regex("^Name: [^;]*;\\s*\\.?\\s*"), "")?.takeIf { it.isNotBlank() }
                                if (noteMessage != null) {
                                    Text("Report: \"$noteMessage\"", color = Ink, fontSize = 13.sp)
                                }
                                Text(if (trackingSignal.latitude == 0.0 && trackingSignal.longitude == 0.0) "Sender location unavailable" else "Sender GPS: ${"%.5f".format(trackingSignal.latitude)}, ${"%.5f".format(trackingSignal.longitude)}", color = Muted, fontSize = 11.sp)
                                Text("Signal: ${trackingSignal.source} · RSSI: ${trackingSignal.rssi?.let { "$it dBm" } ?: "unavailable"} · Battery: ${trackingSignal.batteryPercent}%", color = Muted, fontSize = 11.sp)
                            }
                        }

                        // Tactical Rescue Action Buttons
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(
                                onClick = {
                                    acoustic.transmitAcousticBeacon(0xA1B2)
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = Critical),
                                shape = RoundedCornerShape(12.dp),
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("🔊 Sound Beacon", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                            }

                            OutlinedButton(
                                enabled = trackingSignal.latitude != 0.0 || trackingSignal.longitude != 0.0,
                                onClick = {
                                    val geoUri = Uri.parse("geo:${trackingSignal.latitude},${trackingSignal.longitude}?q=${trackingSignal.latitude},${trackingSignal.longitude}(SOS+Incident)")
                                    val mapIntent = Intent(Intent.ACTION_VIEW, geoUri)
                                    context.startActivity(Intent.createChooser(mapIntent, "Open in Maps"))
                                },
                                shape = RoundedCornerShape(12.dp),
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("🗺️ Open Map", fontWeight = FontWeight.Medium, fontSize = 12.sp)
                            }
                        }

                        FilledTonalButton(
                            onClick = { selectedSignalForTracking = null },
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Text("Done · Back to All Nearby Signals", fontWeight = FontWeight.Bold)
                        }
                    }
                }
            } else {
                // ALL NEARBY SOS SIGNALS LIST (Rendered separately with AirTag Tracker buttons)
                Card(colors = CardDefaults.cardColors(containerColor = Surface), shape = RoundedCornerShape(28.dp)) {
                    Column(Modifier.fillMaxWidth().padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
                        Box(Modifier.size(80.dp).background(MaterialTheme.colorScheme.primaryContainer, CircleShape), contentAlignment = Alignment.Center) {
                            SetuIcon(2, Blue, Modifier.size(38.dp))
                        }
                        Text(
                            text = if (nearbySignals.isEmpty()) "Scanning for mesh beacons…" else "${nearbySignals.size} SOS ${if (nearbySignals.size == 1) "beacon" else "beacons"} detected nearby",
                            color = Ink,
                            style = MaterialTheme.typography.titleLarge,
                            textAlign = TextAlign.Center,
                            fontWeight = FontWeight.Bold
                        )
                        Text(NearbySosStore.status, color = Muted, style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.Center)

                        FilledTonalButton(onClick = {
                            context.startService(Intent(context, EmergencyBackgroundService::class.java).apply {
                                action = EmergencyBackgroundService.ACTION_RESTART_SCAN
                            })
                        }) { Text("Restart mesh scan") }
                    }
                }

                // Render each SOS signal SEPARATELY as an individual clickable tactical card
                nearbySignals.sortedByDescending { it.receivedAtMillis }.forEachIndexed { index, signal ->
                    val (distM, bearDeg) = telemetry.calculateDistanceAndBearing(signal.latitude, signal.longitude)
                    val survivorName = signal.note?.takeIf { it.startsWith("Name: ") }?.substringAfter("Name: ")?.substringBefore(";")?.takeIf { it.isNotBlank() }
                        ?: "SOS Beacon #${signal.id.take(6).uppercase()}"

                    val gpsReliable = distM > maxOf(30f, telemetry.currentLocationAccuracy * 2f + 20f)
                    val distancePillLabel = when {
                        gpsReliable -> "GPS ~${distM.toInt()} m · ${bearDeg.toInt()}°"
                        signal.rssi != null -> "Signal ${signal.rssi} dBm"
                        else -> "Direction unavailable"
                    }

                    Card(
                        colors = CardDefaults.cardColors(containerColor = Surface),
                        shape = RoundedCornerShape(20.dp),
                        modifier = Modifier.fillMaxWidth().clickable {
                            selectedSignalForTracking = signal
                        }
                    ) {
                        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            // Top Row: Hazard Badge & Distance Pill
                            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(survivorName, color = Critical, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                                    Text("${signal.disasterLabel()} · ${if (signal.isTrapped) "⚠️ Trapped" else "Ambulatory"} · ${signal.severityLabel()}", color = Ink, fontSize = 13.sp, fontWeight = FontWeight.Medium)
                                }

                                // Live AirTag Distance Pill
                                Surface(
                                    color = MaterialTheme.colorScheme.primaryContainer,
                                    shape = RoundedCornerShape(12.dp)
                                ) {
                                    Text(
                                        text = distancePillLabel,
                                        color = Blue,
                                        fontSize = 12.sp,
                                        fontWeight = FontWeight.Bold,
                                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)
                                    )
                                }
                            }

                            // Headcount & Medical
                            Text(
                                "${signal.adults + signal.children + signal.elderly} people: ${signal.adults} adults, ${signal.children} kids, ${signal.elderly} seniors",
                                color = Ink, fontSize = 13.sp
                            )
                            signal.medicalFlags?.let { flags ->
                                if (flags != 0) Text("Medical: ${medicalLabels(flags)}", color = Critical, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                            }

                            // Situation message excerpt
                            val message = signal.note?.replace(Regex("^Name: [^;]*;\\s*\\.?\\s*"), "")?.takeIf { it.isNotBlank() }
                            if (message != null) {
                                Text("\"$message\"", color = Muted, fontSize = 12.sp, maxLines = 2)
                            }

                            // Coordinates and Signal Details
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                Text(if (signal.latitude == 0.0 && signal.longitude == 0.0) "Sender GPS unavailable" else "GPS: ${"%.5f".format(signal.latitude)}, ${"%.5f".format(signal.longitude)}", color = Muted, fontSize = 11.sp)
                                Text("RSSI: ${signal.rssi?.let { "$it dBm" } ?: "unavailable"} · ${signal.source}", color = Muted, fontSize = 11.sp)
                            }

                            // Prominent AirTag Direction Action Button
                            Button(
                                onClick = { selectedSignalForTracking = signal },
                                colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
                                shape = RoundedCornerShape(12.dp),
                                modifier = Modifier.fillMaxWidth()
                            ) {
                                Text("🧭 Find nearby signal", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            }
                        }
                    }
                }

                if (nearbySignals.isEmpty()) {
                    InfoTile("Zero-Grid BLE & Wi-Fi Aware Mesh", "Scans for surrounding offline Setu distress beacons across Bluetooth LE 5.0 and Wi-Fi Aware NAN sockets.", 2, Modifier.fillMaxWidth())
                }
            }
        }

        Text("SETU  /  CONNECTION BEYOND CONNECTIVITY", color = Muted, fontSize = 11.sp, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp))
      }
    }
}

private fun NearbySosSignal.disasterLabel(): String = when (disasterType) {
    0 -> "Flood"
    1 -> "Earthquake"
    2 -> "Cyclone"
    3 -> "Landslide"
    4 -> "Fire"
    5 -> "Building collapse"
    else -> "Other emergency"
}

private fun NearbySosSignal.severityLabel(): String = when (severity) {
    0 -> "Low urgency"
    1 -> "Moderate urgency"
    2 -> "High urgency"
    else -> "Critical urgency"
}

private fun medicalLabels(flags: Int): String = listOfNotNull(
    "Insulin".takeIf { flags and 0x0001 != 0 },
    "Dialysis".takeIf { flags and 0x0002 != 0 },
    "Pregnant".takeIf { flags and 0x0004 != 0 },
    "Snakebite".takeIf { flags and 0x0010 != 0 },
    "Breathing difficulty".takeIf { flags and 0x0020 != 0 },
    "Bleeding".takeIf { flags and 0x0040 != 0 },
    "Infant".takeIf { flags and 0x0100 != 0 }
).joinToString(" · ")

@Composable
private fun CountField(label: String, value: String, onValueChange: (String) -> Unit, modifier: Modifier = Modifier) {
    val count = value.toIntOrNull() ?: 0
    Row(modifier.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, color = Ink, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
        OutlinedIconButton(onClick = { onValueChange((count - 1).coerceAtLeast(0).toString()) }, enabled = count > 0, modifier = Modifier.semantics { contentDescription = "Decrease $label" }) { Text("−", fontSize = 22.sp) }
        Text(value, color = Ink, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center, modifier = Modifier.width(36.dp))
        FilledTonalIconButton(onClick = { onValueChange((count + 1).coerceAtMost(15).toString()) }, enabled = count < 15, modifier = Modifier.semantics { contentDescription = "Increase $label" }) { Text("+", fontSize = 22.sp) }
    }
}

@Composable
private fun InfoTile(title: String, description: String, icon: Int, modifier: Modifier = Modifier) {
    Surface(modifier = modifier, color = MaterialTheme.colorScheme.surfaceContainerLow, shape = RoundedCornerShape(20.dp)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            SetuIcon(icon, Blue)
            Text(title, color = Ink, style = MaterialTheme.typography.titleSmall)
            Text(description, color = Muted, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun SetuIcon(kind: Int, color: Color, modifier: Modifier = Modifier.size(24.dp)) {
    Canvas(modifier) {
        val u = size.width / 24f
        val stroke = Stroke(1.8f * u)
        when (kind) {
            0 -> {
                val shield = Path().apply {
                    moveTo(12*u, 2*u); lineTo(21*u, 6*u); lineTo(20*u, 14*u)
                    quadraticTo(18*u, 19*u, 12*u, 22*u)
                    quadraticTo(6*u, 19*u, 4*u, 14*u)
                    lineTo(3*u, 6*u); close()
                }
                drawPath(shield, color, style = stroke)
                drawLine(color, Offset(12*u, 7*u), Offset(12*u, 16*u), 1.8f*u)
                drawLine(color, Offset(8*u, 11.5f*u), Offset(16*u, 11.5f*u), 1.8f*u)
            }
            1 -> {
                drawRoundRect(color, Offset(4*u, 3*u), androidx.compose.ui.geometry.Size(16*u, 18*u), androidx.compose.ui.geometry.CornerRadius(3*u), style = stroke)
                for (y in listOf(8, 12, 16)) drawLine(color, Offset(8*u, y*u), Offset(16*u, y*u), 1.8f*u)
            }
            else -> {
                drawCircle(color, 2.5f*u)
                drawCircle(color.copy(alpha = 0.6f), 6.5f*u, style = stroke)
                drawCircle(color.copy(alpha = 0.3f), 10.5f*u, style = stroke)
            }
        }
    }
}
