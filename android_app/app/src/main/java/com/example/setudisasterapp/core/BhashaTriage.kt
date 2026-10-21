package com.example.setudisasterapp.core

import org.json.JSONObject

/** Deterministic, fully local extraction. Every field remains editable before transmission. */
data class BhashaTriage(
    val disasterType: Int,
    val disasterLabel: String,
    val immediateThreat: String,
    val adults: Int?,
    val children: Int?,
    val elderly: Int?,
    val trapped: Boolean,
    val vulnerabilities: List<String>,
    val medicalFlags: Int
) {
    val totalPeople: Int
        get() = (adults ?: 0) + (children ?: 0) + (elderly ?: 0)

    fun compactJson(latitude: Double?, longitude: Double?): String {
        val data = JSONObject()
        if (latitude != null && longitude != null) {
            data.put("lat", (latitude * 100000).toLong() / 100000.0)
            data.put("lon", (longitude * 100000).toLong() / 100000.0)
        }
        data.put("d", disasterType)
        data.put("hazard", disasterLabel)
        data.put("threat", immediateThreat)
        if (adults != null) data.put("a", adults)
        if (children != null) data.put("c", children)
        if (elderly != null) data.put("e", elderly)
        if (trapped) data.put("tr", 1)
        if (vulnerabilities.isNotEmpty()) data.put("v", vulnerabilities.joinToString(","))
        if (medicalFlags != 0) data.put("m", medicalFlags)
        return data.toString()
    }
}

object BhashaTriageExtractor {
    private data class Hazard(val code: Int, val label: String, val keys: List<String>)
    private val hazards = listOf(
        Hazard(0, "Flood", listOf("flood", "water rising", "water", "drowning", "pani", "badh", "chhat", "roof", "jal", "बाढ़", "पानी", "डूब", "जल", "छत", "पूर", "వరద", "నీరు", "வெள்ள", "தண்ணீர்", "ବନ୍ୟା", "ପାଣି")),
        Hazard(1, "Earthquake", listOf("earthquake", "quake", "tremor", "bhukamp", "jhatke", "भूकंप", "भूकम्प", "झटके", "భూకంప", "நிலநடுக்க", "ଭୂକମ୍ପ")),
        Hazard(2, "Cyclone", listOf("cyclone", "storm", "hurricane", "toofan", "तूफान", "चक्रीवादळ", "आंधी", "తుఫాను", "புயல்", "ବାତ୍ୟା")),
        Hazard(3, "Landslide", listOf("landslide", "mudslide", "rockfall", "pahad", "भूस्खलन", "दरड", "కొండచరియ", "நிலச்சரிவு", "ଭୂସ୍ଖଳନ")),
        Hazard(4, "Fire / Smoke", listOf("fire", "smoke", "burn", "flame", "aag", "dhuan", "आग", "धुआं", "जलन", "अग्नि", "निప్పు", "நெருப்பு", "ନିଆଁ")),
        Hazard(5, "Building collapse", listOf("collapse", "collapsed", "rubble", "debris", "malba", "gir gaya", "fas gaye", "daba", "मलबा", "इमारत गिरी", "फंसे", "दबे", "शिథిల", "இடிபாடு", "ଭଗ୍ନାବଶେଷ")),
        Hazard(6, "Drought / heat", listOf("drought", "heat", "sunstroke", "loo", "sookha", "garmi", "सूखा", "गर्मी", "लू", "दुष्काळ", "కరువు", "வறட்சி", "ମରୁଡ଼ି"))
    )

    private val numbers = mapOf(
        "one" to 1, "two" to 2, "three" to 3, "four" to 4, "five" to 5,
        "six" to 6, "seven" to 7, "eight" to 8, "nine" to 9, "ten" to 10,
        "एक" to 1, "दो" to 2, "तीन" to 3, "चार" to 4, "पांच" to 5,
        "छह" to 6, "सात" to 7, "आठ" to 8, "नौ" to 9, "दस" to 10,
        "single" to 1, "couple" to 2
    )

    fun extract(text: String): BhashaTriage {
        val lower = text.lowercase()
        val hazard = hazards.firstOrNull { item -> item.keys.any(lower::contains) }
        val vulnerabilities = mutableListOf<String>()
        var flags = 0

        fun detect(label: String, bit: Int, vararg keywords: String) {
            if (keywords.any(lower::contains)) {
                vulnerabilities.add(label)
                flags = flags or bit
            }
        }

        detect("Pregnant", 0x0004, "pregnant", "pregnancy", "garbhwati", "गर्भवती", "ग़र्भवती", "గర్భిణి", "கர்ப்பிணி", "ଗର୍ଭବତୀ")
        detect("Dialysis", 0x0002, "dialysis", "kidney", "डायलिसिस", "किडनी", "డయాలసిస్", "டயாலிசிஸ்", "ଡାଏଲିସିସ୍")
        detect("Insulin", 0x0001, "insulin", "sugar", "diabetes", "इंसुलिन", "शुगर", "डायबिटीज", "ఇన్సులిన్", "இன்சுலின்", "ଇନସୁଲିନ")
        detect("Infant", 0x0100, "infant", "baby", "newborn", "shishu", "bachha", "शिशु", "बाळ", "नवजात", "बच्चा", "శిశువు", "குழந்தை", "ଶିଶୁ")
        detect("Bleeding", 0x0040, "bleeding", "blood", "wound", "cut", "khoon", "chot", "ghav", "खून", "रक्त", "चोट", "घाव", "రక్తం", "இரத்த", "ରକ୍ତ")
        detect("Snakebite", 0x0010, "snakebite", "snake bite", "snake", "saap", "saanp", "सांप", "सर्प", "सర్ప", "பாம்பு", "ସାପ")
        detect("Breathing difficulty", 0x0020, "can't breathe", "cannot breathe", "asthma", "oxygen", "breath", "saans", "shwas", "सांस", "श्वास", "ऑक्सीजन", "दम", "శ్వాస", "மூச்சு", "ନିଶ୍ୱାସ")

        val trapped = listOf(
            "trapped", "stuck", "under rubble", "debris", "collapsed", "fas gaye", "fasa", "daba",
            "फंसे", "फंसा", "दबा", "दबे", "अडक", "చిక్క", "சிக்க", "ଫସି"
        ).any(lower::contains)

        val children = countBefore(lower, listOf("child", "children", "kids", "kid", "bachhe", "बच्चे", "बच्चा", "मुले", "పిల్లలు", "குழந்தைகள்", "ପିଲା"))
            ?: if ("Infant" in vulnerabilities) 1 else null

        val elderly = countBefore(lower, listOf("elderly", "older", "senior", "seniors", "budhe", "bujurg", "बुजुर्ग", "वृद्ध", "बूढ़े", "వృద్ధ", "ముதிய", "ବୃଦ୍ଧ"))

        val adultsExplicit = countBefore(lower, listOf("adult", "adults", "bade", "वयस्क", "प्रौढ", "పెద్దలు", "பெரியவர்கள்", "ବୟସ୍କ"))

        val total = countBefore(lower, listOf("people", "person", "persons", "members", "log", "लोग", "व्यक्ति", "जण", "మంది", "பேர்", "ଲୋକ"))

        val calculatedAdults = adultsExplicit
            ?: total?.let { (it - (children ?: 0) - (elderly ?: 0)).coerceAtLeast(0) }
            ?: if (children == null && elderly == null) 1 else null

        val threat = when {
            listOf("rising water", "pani badh", "पानी बढ़", "छत पर", "drowning", "flood", "बाढ़", "నీరు పెరుగు", "நீர் உயர", "ପାଣି ବଢ").any(lower::contains) -> "Rising water"
            trapped -> "Trapped under structure / rubble"
            "Bleeding" in vulnerabilities -> "Major bleeding"
            "Breathing difficulty" in vulnerabilities -> "Breathing difficulty"
            "Fire / Smoke" == hazard?.label -> "Fire & smoke hazard"
            else -> hazard?.label ?: "Emergency assistance requested"
        }

        return BhashaTriage(
            disasterType = hazard?.code ?: 0, // Default to 0 (General/Flood) rather than unspecified 6
            disasterLabel = hazard?.label ?: "General Emergency",
            immediateThreat = threat,
            adults = calculatedAdults ?: 1,
            children = children ?: 0,
            elderly = elderly ?: 0,
            trapped = trapped,
            vulnerabilities = vulnerabilities,
            medicalFlags = flags
        )
    }

    private fun countBefore(text: String, labels: List<String>): Int? {
        for (label in labels) {
            val match = Regex("([0-9०-९౦-౯௦-௯୦-୯]+|one|two|three|four|five|six|seven|eight|nine|ten|एक|दो|तीन|चार|पांच|छह|सात|आठ|नौ|दस|single|couple)\\s*$label", RegexOption.IGNORE_CASE).find(text)
            if (match != null) {
                val token = match.groupValues[1].lowercase()
                val digits = token.map { Character.getNumericValue(it) }.filter { it in 0..9 }
                if (digits.size == token.length) {
                    return digits.fold(0) { n, digit -> n * 10 + digit }.coerceIn(0, 15)
                }
                numbers[token]?.let { return it.coerceIn(0, 15) }
            }
        }
        return null
    }
}
