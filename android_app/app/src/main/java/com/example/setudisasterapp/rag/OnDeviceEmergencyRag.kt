package com.example.setudisasterapp.rag

/**
 * Small, embedded retrieval library. No network access or generated medical claims.
 * Contains verified WHO, NDMA (India), and USGS disaster first-aid and safety protocols
 * in all 6 supported vernacular languages: Hindi, Telugu, Tamil, Marathi, Odia, and English.
 */
object OnDeviceEmergencyRag {
    data class Guidance(
        val topic: String,
        val instruction: String,
        val source: String,
        val sourceUrl: String,
        val englishInstruction: String
    )

    private data class MultilingualEntry(
        val topic: String,
        val keywords: List<String>,
        val en: String,
        val hi: String,
        val te: String,
        val ta: String,
        val mr: String,
        val `or`: String,
        val source: String,
        val sourceUrl: String
    ) {
        fun getTranslation(lang: String): String = when (lang.lowercase()) {
            "hi" -> hi
            "te" -> te
            "ta" -> ta
            "mr" -> mr
            "or" -> `or`
            else -> en
        }
    }

    private val entries = listOf(
        MultilingualEntry(
            topic = "Floodwater",
            keywords = listOf("flood", "water", "drowning", "pani", "badh", "chhat", "roof", "jal", "बाढ़", "पानी", "डूब", "जल", "छत", "पूर", "पाणी", "వరద", "నీరు", "వెள்ள", "தண்ணீர்", "ବନ୍ୟା", "ପାଣି"),
            en = "Avoid moving floodwater. Do not drink contaminated water; boil drinking water if possible. Move to highest safe elevation and keep warm.",
            hi = "बाढ़ के बहते पानी से दूर रहें। दूषित पानी न पिएं; संभव हो तो पानी उबालें। सबसे ऊंचे सुरक्षित स्थान पर जाएं और शरीर गर्म रखें।",
            te = "ప్రవహించే వరద నీటికి దూరంగా ఉండండి. కలుషిత నీటిని త్రాగవద్దు; సాధ్యమైతే నీటిని మరిగించండి. ఎత్తైన సురక్షిత ప్రదేశానికి వెళ్లి వెచ్చగా ఉండండి.",
            ta = "வெள்ள நீரில் செல்ல வேண்டாம். அசுத்தமான தண்ணீரைக் குடிக்காதீர்கள்; முடிந்தால் நீரைக் கொதிக்க வைத்து குடிக்கவும். உயரமான இடத்திற்குச் செல்லவும்.",
            mr = "पुराच्या वाहत्या पाण्यापासून दूर राहा. दूषित पाणी पिऊ नका; शक्य असल्यास पाणी उकळून प्या. सर्वात उंच सुरक्षित ठिकाणी जा आणि उबदार राहा.",
            `or` = "ବନ୍ୟା ଜଳଠାରୁ ଦୂରରେ ରୁହନ୍ତୁ। ଦୂଷିତ ପାଣି ପିଅନ୍ତୁ ନାହିଁ; ସମ୍ଭବ ହେଲେ ପାଣି ଫୁଟାଇ ପିଅନ୍ତୁ। ସୁରକ୍ଷିତ ଉଚ୍ଚ ସ୍ଥାନକୁ ଯାଆନ୍ତୁ।",
            source = "WHO · Flood Health Advice",
            sourceUrl = "https://www.who.int/news-room/questions-and-answers/item/how-do-i-protect-my-health-in-a-flood/"
        ),
        MultilingualEntry(
            topic = "Trapped under rubble",
            keywords = listOf("trapped", "stuck", "rubble", "collapse", "debris", "मलबा", "फंसे", "दबा", "इमारत", "ढिगारा", "अडकले", "శిథిల", "చిక్కు", "இடிபாடு", "சிக்கிய", "ଫସି", "ଭଗ୍ନାବଶେଷ"),
            en = "Cover your mouth and nose with cloth. Tap rhythmically 3 times on a pipe or wall every minute so acoustic sensors can locate you. Avoid shouting to conserve oxygen.",
            hi = "मुंह और नाक को कपड़े से ढकें। हर मिनट पाइप या दीवार पर 3 बार लगातार थपथपाएं ताकि बचाव दल सुन सके। सांस बचाने के लिए बेवजह न चिल्लाएं।",
            te = "నోరు, ముక్కును గుడ్డతో కప్పుకోండి. రెస్క్యూ బృందం వినడానికి ప్రతి నిమిషానికి పైపు లేదా గోడపై 3 సార్లు శబ్దం చేయండి. ఆక్సిజన్ ఆదా చేయడానికి అరవకండి.",
            ta = "வாய் மற்றும் மூக்கை துணியால் மூடவும். மீட்புக் குழுவினர் கேட்க ஒவ்வொரு நிமிடமும் குழாய் அல்லது சுவரில் 3 முறை தட்டவும். கூச்சலிடுவதைத் தவிர்க்கவும்.",
            mr = "तोंड आणि नाक कापडाने झाका. बचाव पथकाला ऐकू येण्यासाठी दर मिनिटाला पाईप किंवा भिंतीवर ३ वेळा ठोका. श्वास वाचवण्यासाठी ओरडू नका.",
            `or` = "ମୁହଁ ଏବଂ ନାକକୁ କପଡ଼ାରେ ଘୋଡ଼ାନ୍ତୁ। ଉଦ୍ଧାରକାରୀଙ୍କ ଧ୍ୟାନ ଆକର୍ଷଣ ପାଇଁ ପ୍ରତି ମିନିଟରେ ପାଇପ୍ ବା କାନ୍ଥରେ ୩ ଥର ଠକ୍ ଠକ୍ କରନ୍ତୁ।",
            source = "NDMA · Search & Rescue Protocol",
            sourceUrl = "https://ndma.gov.in/Resources/guidelines"
        ),
        MultilingualEntry(
            topic = "Fire & Smoke",
            keywords = listOf("fire", "smoke", "burn", "flame", "aag", "dhuan", "आग", "धुआं", "जलन", "अग्नि", "धूर", "निప్పు", "మంటలు", "పొగ", "நெருப்பு", "புகை", "ନିଆଁ", "ଧୂଆଁ"),
            en = "Stay low under smoke where air is cleaner. Cover mouth with a damp cloth. Feel doors before opening. If clothes catch fire: Stop, Drop, and Roll.",
            hi = "धुएं में नीचे झुककर रेंगें क्योंकि नीचे हवा साफ होती है। गीले कपड़े से मुंह ढकें। दरवाजे खोलने से पहले छूकर देखें। कपड़े में आग लगे तो: रुकें, लेटें और लुढ़कें।",
            te = "పొగ ఉన్నప్పుడు కిందకి వంగి ఉండండి, అక్కడ గాలి స్వచ్ఛంగా ఉంటుంది. తడి గుడ్డతో ముఖం కప్పుకోండి. బట్టలకు మంటలు అంటుకుంటే: ఆగండి, పడుకోండి, దొర్లండి.",
            ta = "புகைக்கு கீழே குனிந்து செல்லவும். ஈரத்துணியால் வாயை மூடவும். கதவுகளைத் திறக்கும் முன் தொட்டுப் பார்க்கவும். ஆடையில் தீப்பிடித்தால்: நில், விழு, உருளு.",
            mr = "धुरामध्ये खाली वाकून राहा. ओल्या कापडाने तोंड झाका. दार उघडण्यापूर्वी हाताने तपासा. कपड्यांना आग लागल्यास: थांबा, खाली पडा आणि लोळा.",
            `or` = "ଧୂଆଁ ତଳେ ବସି ରୁହନ୍ତୁ। ଓଦା କପଡ଼ାରେ ମୁହଁ ଘୋଡ଼ାନ୍ତୁ। କବାଟ ଖୋଲିବା ଆଗରୁ ଛୁଇଁ ଦେଖନ୍ତୁ। ପୋଷାକରେ ନିଆଁ ଲାଗିଲେ: ରୁହନ୍ତୁ, ତଳେ ଶୁଅନ୍ତୁ ଓ ଗଡ଼ନ୍ତୁ।",
            source = "NDMA · Fire Safety Guidelines",
            sourceUrl = "https://ndma.gov.in/Natural-Hazards/Fire"
        ),
        MultilingualEntry(
            topic = "Major bleeding",
            keywords = listOf("bleed", "blood", "wound", "cut", "khoon", "chot", "ghav", "खून", "रक्त", "चोट", "घाव", "रक्तस्त्राव", "రక్తం", "గాయం", "இரத்த", "காயம்", "ରକ୍ତ", "କ୍ଷତ"),
            en = "Apply firm direct pressure to the bleeding wound using a clean cloth. Keep the injured part elevated above heart level if possible. Do not remove soaked cloths; add more layers.",
            hi = "साफ कपड़े से घाव पर लगातार सीधा तेज दबाव डालें। संभव हो तो घायल हिस्से को दिल की ऊंचाई से ऊपर रखें। भीगा कपड़ा न हटाएं, उसके ऊपर और कपड़ा लगाएं।",
            te = "గాయంపై శుభ్రమైన గుడ్డతో గట్టిగా ఒత్తిడి ఉంచండి. వీలైతే గాయపడిన భాగాన్ని గుండె కంటే ఎత్తులో ఉంచండి. రక్తంతో తడిసిన గుడ్డను తీయకండి, పైన మరిన్ని పొరలు వేయండి.",
            ta = "சுத்தமான துணியால் காயத்தின் மீது உறுதியான நேரடி அழுத்தத்தைப் பயன்படுத்துங்கள். முடிந்தால் காயமடைந்த பகுதியை இதயத்திற்கு மேலே உயர்த்தவும்.",
            mr = "स्वच्छ कापडाने जखमेवर थेट दाब द्या. शक्य असल्यास जखमी भाग हृदयाच्या पातळीपेक्षा उंच ठेवा. भिजलेले कापड काढू नका, त्यावर आणखी थर लावा.",
            `or` = "ସଫା କପଡ଼ାରେ କ୍ଷତ ସ୍ଥାନ ଉପରେ ଜୋରରେ ଚାପି ଧରନ୍ତୁ। ସମ୍ଭବ ହେଲେ ଆଘାତ ସ୍ଥାନକୁ ଉପରକୁ ରଖନ୍ତୁ। ରକ୍ତ ଭିଜା କପଡ଼ା କାଢ଼ନ୍ତୁ ନାହିଁ।",
            source = "WHO · First Aid Response",
            sourceUrl = "https://cdn.who.int/media/docs/default-source/integrated-health-services-(ihs)/csy/cfar-pocketguide.pdf"
        ),
        MultilingualEntry(
            topic = "Snakebite",
            keywords = listOf("snake", "bite", "venom", "सांप", "काटा", "सर्प", "चावला", "పాము", "సర్ప", "பாம்பு", "கடி", "ସାପ", "କାମୁଡ଼ା"),
            en = "Keep the victim completely calm and still. Immobilize the bitten limb below heart level. Do not cut wound, suck venom, or apply tight tourniquet.",
            hi = "पीड़ित को बिल्कुल शांत और स्थिर रखें। अंग को दिल के स्तर से नीचे रखें। घाव को न काटें, जहर न चूसें और कसकर पट्टी न बांधें।",
            te = "బాధితుడిని ప్రశాంతంగా మరియు కదలకుండా ఉంచండి. కాటు వేసిన భాగాన్ని గుండె కంటే కింద ఉంచండి. గాయాన్ని కోయవద్దు లేదా విషాన్ని పీల్చవద్దు.",
            ta = "பாதிக்கப்பட்டவரை முற்றிலும் அமைதியாகவும் அசையாமலும் வைக்கவும். கடித்த மூட்டை இதய நிலைக்கு கீழே வைக்கவும். காயத்தை வெட்டவோ அல்லது விஷத்தை உறிஞ்சவோ வேண்டாம்.",
            mr = "बाधित व्यक्तीला शांत आणि स्थिर ठेवा. चावलेला भाग हृदयाच्या पातळीखाली ठेवा. जखम कापू नका किंवा विष चोखू नका.",
            `or` = "ରୋଗୀଙ୍କୁ ସମ୍ପୂର୍ଣ୍ଣ ଶାନ୍ତ ଓ ସ୍ଥିର ରଖନ୍ତୁ। କାମୁଡ଼ା ସ୍ଥାନକୁ ଛାତିଠାରୁ ତଳକୁ ରଖନ୍ତୁ। କ୍ଷତକୁ କାଟନ୍ତୁ ନାହିଁ ବା ବିଷ ଶୋଷନ୍ତୁ ନାହିଁ।",
            source = "WHO · Snakebite Envenoming",
            sourceUrl = "https://www.who.int/news-room/questions-and-answers/item/snakebite-envenoming"
        ),
        MultilingualEntry(
            topic = "Oral rehydration (ORS)",
            keywords = listOf("diarrhea", "diarrhoea", "dehydration", "ors", "vomit", "दस्त", "उल्टी", "निर्जलीकरण", "జులాబులు", "విరేచనాలు", "வயிற்றுப்போக்கு", "ଝାଡ଼ା", "ବାନ୍ତି"),
            en = "Mix 1 litre safe water with 6 level teaspoons sugar and half level teaspoon salt. Sip continuously. Seek urgent help for extreme weakness.",
            hi = "1 लीटर सुरक्षित पानी में 6 समतल चम्मच चीनी और आधा समतल चम्मच नमक मिलाएं। धीरे-धीरे पिएं। तेज कमजोरी में तुरंत मदद लें।",
            te = "1 లీటరు తాగునీటిలో 6 టీస్పూన్ల చక్కెర, అర టీస్పూన్ ఉప్పు కలపండి. కొద్దికొద్దిగా త్రాగండి. తీవ్ర బలహీనత ఉంటే వైద్య సహాయం తీసుకోండి.",
            ta = "1 லிட்டர் சுத்தமான தண்ணீரில் 6 தேக்கரண்டி சர்க்கரை மற்றும் அரை தேக்கரண்டி உப்பு கலக்கவும். தொடர்ந்து குடிக்கவும்.",
            mr = "१ लिटर पाण्यात ६ चमचे साखर आणि अर्धा चमचा मीठ मिसळा. थोडे थोडे पाणी पीत राहा. तीव्र अशक्तपणा असल्यास त्वरित मदत घ्या.",
            `or` = "୧ ଲିଟର ପାଣିରେ ୬ ଚାମଚ ଚିନି ଏବଂ ଅଧା ଚାମଚ ଲୁଣ ମିଶାନ୍ତୁ। ଧୀରେ ଧୀରେ ପିଅନ୍ତୁ। ଅତ୍ୟଧିକ ଦୁର୍ବଳତା ଲାଗିଲେ ତୁରନ୍ତ ସାହାଯ୍ୟ ନିଅନ୍ତୁ।",
            source = "WHO · Cholera & Rehydration",
            sourceUrl = "https://www.who.int/news-room/questions-and-answers/item/cholera-outbreaks"
        ),
        MultilingualEntry(
            topic = "Earthquake",
            keywords = listOf("earthquake", "tremor", "quake", "भूकंप", "भूकम्प", "झटके", "धरणीकंप", "భూకంప", "நிலநடுக்க", "ଭୂକମ୍ପ"),
            en = "During tremors: Drop, Cover under sturdy furniture, and Hold On. Move away from glass and heavy walls. Do not run outside until shaking stops.",
            hi = "झटकों के समय: जमीन पर बैठें, मजबूत मेज के नीचे सिर ढकें और पकड़कर रहें। खिड़कियों से दूर रहें। झटके रुकने तक बाहर न भागें।",
            te = "భూకంపం వచ్చినప్పుడు: కింద కూర్చోండి, దృఢమైన బల్ల కింద తల కప్పుకోండి మరియు పట్టుకోండి. కిటికీలు మరియు గోడలకు దూరంగా ఉండండి.",
            ta = "நிலநடுக்கத்தின் போது: கீழே அமர்ந்து, உறுதியான மேசையின் கீழ் தலையை மூடிப் பிடிக்கவும். ஜன்னல்களை விட்டு விலகி இருங்கள்.",
            mr = "भूकंपाचे झटके बसत असताना: खाली बसा, मजबूत टेबलखाली डोके झाका आणि घट्ट धरा. खिडक्यांपासून दूर राहा. झटके थांबल्याशिवाय बाहेर पडू नका.",
            `or` = "ଭୂକମ୍ପ ବେଳେ: ତଳେ ବସନ୍ତୁ, ମଜବୁତ ଟେବୁଲ ତଳେ ମୁଣ୍ଡ ଘୋଡ଼ାନ୍ତୁ ଏବଂ ଧରି ରୁହନ୍ତୁ। ଝରକାଠାରୁ ଦୂରେଇ ରୁହନ୍ତୁ।",
            source = "NDMA · Aapda Mitra Earthquake",
            sourceUrl = "https://aapdamitra.ndma.gov.in/training-updates"
        ),
        MultilingualEntry(
            topic = "Cyclone",
            keywords = listOf("cyclone", "storm", "hurricane", "wind", "तूफान", "चक्रीवादळ", "आंधी", "తుఫాను", "గాలివాన", "புயல்", "ବାତ୍ୟା"),
            en = "Switch off electrical mains. Stay inside the strongest central part of a concrete building away from windows until all-clear is issued.",
            hi = "बिजली का मुख्य स्विच बंद करें। पक्के मकान के सबसे मजबूत अंदरूनी हिस्से में रहें। सुरक्षित घोषणा होने तक बाहर न निकलें।",
            te = "విద్యుత్ మెయిన్స్ స్విచ్ ఆఫ్ చేయండి. కిటికీలకు దూరంగా బలమైన కాంక్రీట్ గదిలో ఉండండి. తుఫాను తగ్గే వరకు బయటకు రావద్దు.",
            ta = "மின்சார மெயினை அணைக்கவும். ஜன்னல்களை விட்டு விலகி உறுதியான கட்டிடத்தின் நடுப்பகுதியில் இருங்கள்.",
            mr = "विजेचा मेन स्विच बंद करा. खिडक्यांपासून दूर पक्क्या इमारतीच्या मध्यभागी सुरक्षित राहा. अधिकृत सूचना मिळेपर्यंत बाहेर पडू नका.",
            `or` = "ମୁଖ୍ୟ ବିଦ୍ୟୁତ ସୁଇଚ୍ ବନ୍ଦ କରନ୍ତୁ। ଝରକାଠାରୁ ଦୂରରେ ପକ୍କା ଘରର ମଝି ଭାଗରେ ସୁରକ୍ଷିତ ରୁହନ୍ତୁ।",
            source = "Ready.gov / NDMA Cyclone",
            sourceUrl = "https://www.ready.gov/sites/default/files/2024-03/ready.gov_hurricane_hazard-info-sheet.pdf"
        ),
        MultilingualEntry(
            topic = "Heat & Dehydration",
            keywords = listOf("heat", "hot", "sunstroke", "loo", "गर्मी", "लू", "उष्ण", "उन्हाळा", "వేడి", "ఎండదెబ్బ", "வெயில்", "ଗରମ", "ଅଂଶୁଘାତ"),
            en = "Move to shade or breeze immediately. Apply cool wet cloths to neck and armpits. Sip cool water. If confused or unconscious, seek evacuation.",
            hi = "तुरंत छायादार जगह जाएं। गर्दन और बगलों पर ठंडे पानी की पट्टी रखें। ठंडा पानी पिएं। बेहोशी में तुरंत बचाव दल को सूचित करें।",
            te = "వెంటనే నీడ లేదా గాలి ఉన్న ప్రదేశానికి వెళ్ళండి. మెడ మరియు చంకలపై చల్లని తడి గుడ్డను ఉంచండి. చల్లని నీరు త్రాగండి.",
            ta = "உடனடியாக நிழலான இடத்திற்குச் செல்லவும். கழுத்து மற்றும் அக்குள்களில் குளிர்ந்த ஈரத்துணியை வைக்கவும். தண்ணீர் குடிக்கவும்.",
            mr = "त्वरित सावलीत जा. मान आणि बगलेवर गार पाण्याच्या पट्ट्या ठेवा. गार पाणी प्या. चक्कर आल्यास त्वरित मदत घ्या.",
            `or` = "ତୁରନ୍ତ ଛାଇ ଜାଗାକୁ ଯାଆନ୍ତୁ। ବେକ ଓ କାଖରେ ଓଦା କପଡ଼ା ରଖନ୍ତୁ। ଥଣ୍ଡା ପାଣି ପିଅନ୍ତୁ। ଅଚେତ ହେଲେ ତୁରନ୍ତ ଡାକ୍ତରୀ ସାହାଯ୍ୟ ନିଅନ୍ତୁ।",
            source = "WHO · Heatwaves & Safety",
            sourceUrl = "https://www.who.int/news-room/questions-and-answers/item/heatwaves-how-to-stay-cool"
        )
    )

    fun retrieve(query: String, languageTag: String): List<Guidance> {
        val lower = query.lowercase()
        val matches = entries.filter { entry -> entry.keywords.any { lower.contains(it) } }
        val results = if (matches.isNotEmpty()) matches else entries.take(1)
        return results.take(2).map { entry ->
            Guidance(
                topic = entry.topic,
                instruction = entry.getTranslation(languageTag),
                source = entry.source,
                sourceUrl = entry.sourceUrl,
                englishInstruction = entry.en
            )
        }
    }

    fun getImmediateGuidance(query: String, lang: String = "hi"): String {
        return getImmediateGuidanceBilingual(query, lang).first
    }

    fun getImmediateGuidanceBilingual(query: String, lang: String = "hi"): Pair<String, String> {
        val found = retrieve(query, lang)
        if (found.isNotEmpty()) {
            val primary = found.joinToString(" ") { it.instruction }
            val english = found.joinToString(" ") { it.englishInstruction }
            return Pair(primary, english)
        }
        val defaultTexts = mapOf(
            "hi" to "सुरक्षित स्थान पर रहें। अपनी स्थिति की जानकारी साझा करें और स्थानीय बचाव निर्देशों का पालन करें।",
            "te" to "సురక్షిత ప్రదేశంలో ఉండండి. మీ సహాయ వివరాలను పంచుకోండి మరియు స్థానిక రెస్క్యూ సూచనలను అనుసరించండి.",
            "ta" to "பாதுகாப்பான இடத்தில் இருங்கள். உங்கள் மீட்பு விவரங்களைப் பகிர்ந்து, உள்ளூர் அவசர வழிமுறைகளைப் பின்பற்றவும்.",
            "mr" to "सुरक्षित ठिकाणी राहा. तुमची परिस्थिती कळवा आणि स्थानिक बचाव पथकाच्या सूचनांचे पालन करा.",
            "or" to "ସୁରକ୍ଷିତ ସ୍ଥାନରେ ରୁହନ୍ତୁ। ନିଜର ପରିସ୍ଥିତି ଜଣାନ୍ତୁ ଏବଂ ସ୍ଥାନୀୟ ଉଦ୍ଧାରକାରୀଙ୍କ ନିର୍ଦ୍ଦେଶ ପାଳନ କରନ୍ତୁ।",
            "en" to "Move to a safe place if you can. Share your rescue details and follow local emergency instructions."
        )
        val primary = defaultTexts[lang.lowercase()] ?: defaultTexts["en"]!!
        val en = defaultTexts["en"]!!
        return Pair(primary, en)
    }

    fun getAllTopics(): List<String> = entries.map { it.topic }

    fun getGuidanceByTopic(topic: String, lang: String = "hi"): Pair<String, String> {
        val entry = entries.firstOrNull { it.topic.equals(topic, ignoreCase = true) } ?: entries.first()
        return Pair(entry.getTranslation(lang), entry.en)
    }
}
