"""
Zero-Install Captive Portal & Offline Micro-PWA Gateway Server.
Solves the "Pre-Installation Paradox" for Disaster Mesh Networks.

Components:
1. DNSHijacker: Threaded UDP DNS server answering all queries with gateway IP.
2. CaptivePortalHandler & CaptivePortalServer:
   - Probes detection: Android (/generate_204, /gen_204), Apple (/hotspot-detect.html), Windows (/ncsi.txt, /connecttest.txt).
   - Embedded offline-first Micro-PWA with multilingual support (EN, HI, BN, TA, TE, MR).
   - Ingestion REST API: POST /api/v1/captive_sos -> 120-byte binary packet -> SQLite storage & NDMA RAG advice.
   - Status REST API: GET /api/v1/status -> telemetry, victim count, packet buffer count.
3. ZeroInstallCaptiveGateway: Combined supervisor orchestrating DNS + HTTP captive services.
"""

import http.server
import json
import math
import os
import re
import socket
import struct
import sys
import threading
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple


def _safe_int(val: Any, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    try:
        if val is None:
            res = default
        elif isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                res = default
            else:
                res = int(val)
        elif isinstance(val, str):
            res = int(float(val.strip()))
        else:
            res = default
    except (ValueError, TypeError):
        res = default

    if min_val is not None:
        res = max(min_val, res)
    if max_val is not None:
        res = min(max_val, res)
    return res


def _safe_float(val: Any, default: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    try:
        if val is None:
            res = default
        elif isinstance(val, (int, float)):
            if math.isnan(val) or math.isinf(val):
                res = default
            else:
                res = float(val)
        elif isinstance(val, str):
            res = float(val.strip())
        else:
            res = default
    except (ValueError, TypeError):
        res = default

    if min_val is not None:
        res = max(min_val, res)
    if max_val is not None:
        res = min(max_val, res)
    return res


def _safe_bool(val: Any, default: bool = False) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "y", "t", "on")
    return bool(val)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sos_packet import (
    pack_sos_packet,
    unpack_sos_packet,
    calculate_crc16_ccitt,
    SEVERITY_GREEN,
    SEVERITY_YELLOW,
    SEVERITY_RED,
    SEVERITY_BLACK,
    DISASTER_FLOOD,
    DISASTER_EARTHQUAKE,
    DISASTER_CYCLONE,
    DISASTER_LANDSLIDE,
    DISASTER_FIRE,
    DISASTER_BUILDING_COLLAPSE,
    DISASTER_OTHER,
    MED_FLAG_INSULIN,
    MED_FLAG_DIALYSIS,
    MED_FLAG_PREGNANCY,
    MED_FLAG_CRUSH,
    MED_FLAG_SNAKEBITE,
    MED_FLAG_O2_NEEDED,
    MED_FLAG_BLEEDING,
    MED_FLAG_FRACTURE,
)
from core.offline_rag import OfflineEmergencyRAG
from gateway_mule.setu_mule_service import AndroidSetuMuleGateway, SetuMuleDatabase


# Embedded Offline Micro-PWA HTML/CSS/JS (Zero external dependencies)
CAPTIVE_PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <meta name="theme-color" content="#0f172a">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <title>SETU Emergency SOS (Zero-Grid)</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: #090d16;
      color: #f1f5f9;
      padding: 12px;
      line-height: 1.4;
    }
    .container {
      max-width: 520px;
      margin: 0 auto;
      background: #131b2e;
      border: 1px solid #1e293b;
      border-radius: 14px;
      padding: 18px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    }
    .lang-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 14px;
      justify-content: center;
    }
    .lang-btn {
      background: #1e293b;
      color: #94a3b8;
      border: 1px solid #334155;
      padding: 5px 10px;
      border-radius: 6px;
      font-size: 0.75rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    .lang-btn.active {
      background: #ef4444;
      color: #ffffff;
      border-color: #dc2626;
      font-weight: bold;
    }
    .header {
      text-align: center;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid #1e293b;
    }
    .header h1 {
      color: #ef4444;
      font-size: 1.35rem;
      font-weight: 800;
      letter-spacing: 0.5px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
    }
    .header p {
      color: #94a3b8;
      font-size: 0.8rem;
      margin-top: 4px;
    }
    .mesh-badge {
      display: inline-block;
      background: rgba(16, 185, 129, 0.15);
      color: #10b981;
      border: 1px solid #10b981;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 0.7rem;
      margin-top: 6px;
      font-weight: 600;
    }
    .form-group {
      margin-bottom: 14px;
    }
    label.field-label {
      display: block;
      font-size: 0.82rem;
      font-weight: 600;
      color: #cbd5e1;
      margin-bottom: 6px;
    }
    select, input[type="text"], textarea {
      width: 100%;
      padding: 10px;
      background: #0a0f1d;
      border: 1px solid #334155;
      color: #ffffff;
      border-radius: 8px;
      font-size: 0.9rem;
    }
    select:focus, input:focus, textarea:focus {
      outline: none;
      border-color: #ef4444;
    }
    .toggle-group {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .toggle-btn {
      padding: 10px;
      text-align: center;
      background: #0a0f1d;
      border: 1px solid #334155;
      border-radius: 8px;
      cursor: pointer;
      font-size: 0.85rem;
      font-weight: bold;
      color: #94a3b8;
    }
    .toggle-btn.selected {
      background: #ef4444;
      color: #ffffff;
      border-color: #dc2626;
    }
    .toggle-btn.no.selected {
      background: #334155;
      color: #ffffff;
      border-color: #475569;
    }
    .counter-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 6px;
    }
    .counter-item {
      background: #0a0f1d;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 6px 4px;
      text-align: center;
    }
    .counter-item span {
      display: block;
      font-size: 0.7rem;
      color: #94a3b8;
      margin-bottom: 4px;
    }
    .counter-ctrl {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
    }
    .btn-step {
      background: #1e293b;
      border: 1px solid #475569;
      color: white;
      width: 24px;
      height: 24px;
      border-radius: 4px;
      cursor: pointer;
      font-weight: bold;
    }
    .counter-val {
      font-size: 0.9rem;
      font-weight: bold;
      min-width: 18px;
      text-align: center;
    }
    .checkbox-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .check-label {
      display: flex;
      align-items: center;
      gap: 6px;
      background: #0a0f1d;
      border: 1px solid #334155;
      padding: 8px;
      border-radius: 8px;
      font-size: 0.78rem;
      color: #e2e8f0;
      cursor: pointer;
    }
    .check-label input {
      accent-color: #ef4444;
    }
    .btn-broadcast {
      width: 100%;
      background: linear-gradient(135deg, #ef4444, #b91c1c);
      color: #ffffff;
      border: none;
      padding: 14px;
      font-size: 1.05rem;
      font-weight: 800;
      border-radius: 10px;
      cursor: pointer;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      box-shadow: 0 4px 14px rgba(239, 68, 68, 0.4);
      margin-top: 10px;
    }
    .btn-broadcast:active {
      transform: scale(0.98);
    }
    #resultCard {
      display: none;
      margin-top: 16px;
      padding: 16px;
      background: #064e3b;
      border: 1px solid #059669;
      border-radius: 10px;
    }
    #resultCard h2 {
      color: #34d399;
      font-size: 1.1rem;
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 8px;
    }
    .badge {
      display: inline-block;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: bold;
      text-transform: uppercase;
      margin: 4px 0;
    }
    .badge-red { background: #991b1b; color: #fecaca; }
    .badge-yellow { background: #854d0e; color: #fef08a; }
    .badge-green { background: #065f46; color: #a7f3d0; }
    .advice-box {
      margin-top: 10px;
      background: #062f26;
      border: 1px solid #047857;
      border-radius: 8px;
      padding: 10px;
      font-size: 0.85rem;
      color: #e6fffa;
    }
    .advice-title {
      font-weight: bold;
      color: #34d399;
      margin-bottom: 4px;
      font-size: 0.8rem;
      text-transform: uppercase;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="lang-bar">
      <button class="lang-btn active" onclick="setLanguage('en')">English</button>
      <button class="lang-btn" onclick="setLanguage('hi')">हिन्दी</button>
      <button class="lang-btn" onclick="setLanguage('bn')">বাংলা</button>
      <button class="lang-btn" onclick="setLanguage('ta')">தமிழ்</button>
      <button class="lang-btn" onclick="setLanguage('te')">తెలుగు</button>
      <button class="lang-btn" onclick="setLanguage('mr')">मराठी</button>
    </div>

    <div class="header">
      <h1 id="uiTitle">🚨 SETU EMERGENCY SOS</h1>
      <p id="uiSub">Zero-Grid Disaster Mesh Gateway • No Internet or App Required</p>
      <div class="mesh-badge" id="uiMeshBadge">🟢 Drone / Mule Mesh Hotspot Connected</div>
    </div>

    <form id="sosForm" onsubmit="broadcastSos(event)">
      <div class="form-group">
        <label class="field-label" id="lblDisaster">Disaster Hazard:</label>
        <select id="disasterType">
          <option value="0">Flood (Submerged / Rooftop)</option>
          <option value="5">Building Collapse / Buried</option>
          <option value="4">Fire / Smoke</option>
          <option value="1">Earthquake</option>
          <option value="2">Cyclone / Storm Surge</option>
          <option value="3">Landslide</option>
          <option value="6">Other Emergency</option>
        </select>
      </div>

      <div class="form-group">
        <label class="field-label" id="lblTrapped">Are You Trapped?</label>
        <div class="toggle-group">
          <div id="btnTrappedYes" class="toggle-btn selected" onclick="setTrapped(true)">YES (Trapped)</div>
          <div id="btnTrappedNo" class="toggle-btn no" onclick="setTrapped(false)">NO (Mobile)</div>
        </div>
      </div>

      <div class="form-group">
        <label class="field-label" id="lblDemographics">People Needing Rescue:</label>
        <div class="counter-grid">
          <div class="counter-item">
            <span id="lblAdults">Adults</span>
            <div class="counter-ctrl">
              <button type="button" class="btn-step" onclick="changeCount('adults', -1)">-</button>
              <span id="val_adults" class="counter-val">1</span>
              <button type="button" class="btn-step" onclick="changeCount('adults', 1)">+</button>
            </div>
          </div>
          <div class="counter-item">
            <span id="lblKids">Children</span>
            <div class="counter-ctrl">
              <button type="button" class="btn-step" onclick="changeCount('children', -1)">-</button>
              <span id="val_children" class="counter-val">0</span>
              <button type="button" class="btn-step" onclick="changeCount('children', 1)">+</button>
            </div>
          </div>
          <div class="counter-item">
            <span id="lblElderly">Elderly</span>
            <div class="counter-ctrl">
              <button type="button" class="btn-step" onclick="changeCount('elderly', -1)">-</button>
              <span id="val_elderly" class="counter-val">0</span>
              <button type="button" class="btn-step" onclick="changeCount('elderly', 1)">+</button>
            </div>
          </div>
          <div class="counter-item">
            <span id="lblCritical">Critical</span>
            <div class="counter-ctrl">
              <button type="button" class="btn-step" onclick="changeCount('critical', -1)">-</button>
              <span id="val_critical" class="counter-val">0</span>
              <button type="button" class="btn-step" onclick="changeCount('critical', 1)">+</button>
            </div>
          </div>
        </div>
      </div>

      <div class="form-group">
        <label class="field-label" id="lblInjuries">Injuries & Urgent Medical Needs:</label>
        <div class="checkbox-grid">
          <label class="check-label"><input type="checkbox" id="m_bleed"> <span id="lblBleed">Arterial Bleed</span></label>
          <label class="check-label"><input type="checkbox" id="m_crush"> <span id="lblCrush">Crush Injury</span></label>
          <label class="check-label"><input type="checkbox" id="m_insulin"> <span id="lblInsulin">Insulin Needed</span></label>
          <label class="check-label"><input type="checkbox" id="m_dialysis"> <span id="lblDialysis">Dialysis Needed</span></label>
          <label class="check-label"><input type="checkbox" id="m_fracture"> <span id="lblFracture">Fracture / Bone</span></label>
          <label class="check-label"><input type="checkbox" id="m_pregnant"> <span id="lblPregnant">Pregnancy</span></label>
        </div>
      </div>

      <div class="form-group">
        <label class="field-label" id="lblLocation">Location / Notes / Landmarks:</label>
        <textarea id="noteText" rows="2" placeholder="e.g. 2nd floor under stairs, red water tank nearby..."></textarea>
      </div>

      <button type="submit" id="btnSubmit" class="btn-broadcast">🚨 BROADCAST SOS NOW</button>
    </form>

    <div id="resultCard">
      <h2 id="resTitle">✅ SOS TRANSMITTED & BUFFERED</h2>
      <p style="font-size: 0.8rem; color: #a7f3d0; margin-bottom: 6px;" id="resSub">
        Your distress beacon was packed into 120-byte mesh format and stored in the Setu Mule database.
      </p>
      <div><span id="lblTriageBadge" style="font-size:0.75rem;">Priority:</span> <span id="resSeverity" class="badge badge-red">RED (IMMEDIATE)</span></div>
      <div style="font-size: 0.72rem; color: #94a3b8; margin-top: 4px;">Packet Hash: <span id="resHash" style="font-family: monospace; color: #ffffff;"></span></div>
      
      <div class="advice-box">
        <div class="advice-title" id="lblAdviceTitle">📖 NDMA Offline First-Aid Advice:</div>
        <div id="resAdvice">Loading instructions...</div>
      </div>
    </div>
  </div>

  <script>
    let currentLang = 'en';
    let isTrappedVal = true;
    const counts = { adults: 1, children: 0, elderly: 0, critical: 0 };

    const I18N = {
      en: {
        title: "🚨 SETU EMERGENCY SOS",
        sub: "Zero-Grid Disaster Mesh Gateway • No Internet or App Required",
        badge: "🟢 Drone / Mule Mesh Hotspot Connected",
        disaster: "Disaster Hazard:",
        trapped: "Are You Trapped?",
        trappedYes: "YES (Trapped)",
        trappedNo: "NO (Mobile)",
        demographics: "People Needing Rescue:",
        adults: "Adults", kids: "Children", elderly: "Elderly", critical: "Critical",
        injuries: "Injuries & Urgent Medical Needs:",
        bleed: "Arterial Bleed", crush: "Crush Injury", insulin: "Insulin Needed",
        dialysis: "Dialysis Needed", fracture: "Fracture / Bone", pregnant: "Pregnancy",
        loc: "Location / Notes / Landmarks:",
        locPlaceholder: "e.g. 2nd floor under stairs, red water tank nearby...",
        broadcast: "🚨 BROADCAST SOS NOW",
        resTitle: "✅ SOS TRANSMITTED & BUFFERED",
        resSub: "Your distress beacon was packed into 120-byte mesh format and stored in the Setu Mule database.",
        adviceTitle: "📖 NDMA Offline First-Aid Advice:"
      },
      hi: {
        title: "🚨 सेतु आपातकालीन एसओएस",
        sub: "ऑफलाइन आपदा मेश गेटवे • बिना इंटरनेट या ऐप के कार्यशील",
        badge: "🟢 रेस्क्यू ड्रोन/नाव मेश से जुड़े हैं",
        disaster: "आपदा का प्रकार:",
        trapped: "क्या आप फंसे हुए हैं?",
        trappedYes: "हाँ (फंसे हैं)",
        trappedNo: "नहीं (चल सकते हैं)",
        demographics: "बचाव के लिए कुल लोग:",
        adults: "वयस्क", kids: "बच्चे", elderly: "बुजुर्ग", critical: "गंभीर",
        injuries: "चोट और जरूरी दवाइयाँ:",
        bleed: "खून बह रहा है", crush: "मलबे में दबना", insulin: "इंसुलिन जरूरी",
        dialysis: "डायलिसिस जरूरी", fracture: "हड्डी टूटना", pregnant: "गर्भावस्था",
        loc: "सटीक पता / स्थान / पहचान चिन्ह:",
        locPlaceholder: "उदा. दूसरी मंजिल सीढ़ियों के नीचे, लाल पानी की टंकी के पास...",
        broadcast: "🚨 अभी आपातकालीन SOS भेजें",
        resTitle: "✅ एसओएस सफलतापूर्वक प्रसारित हुआ",
        resSub: "आपका आपातकालीन संदेश 120-बाइट मेश पैकेट में बदलकर सुरक्षित कर लिया गया है।",
        adviceTitle: "📖 एनडीएमए आपातकालीन प्राथमिक चिकित्सा निर्देश:"
      },
      bn: {
        title: "🚨 সেতু জরুরি এসওএস",
        sub: "অফলাইন ডিজাস্টার মেশ গেটওয়ে • কোনো ইন্টারনেট বা অ্যাপের প্রয়োজন নেই",
        badge: "🟢 রেসকিউ ড্রোন/বোট মেশ সংযুক্ত",
        disaster: "বিপর্যয়ের ধরন:",
        trapped: "আপনি কি আটকে আছেন?",
        trappedYes: "হ্যাঁ (আটকে আছি)",
        trappedNo: "না (চলমান)",
        demographics: "উদ্ধারের অপেক্ষায় মোট মানুষ:",
        adults: "প্রাপ্তবয়স্ক", kids: "শিশু", elderly: "বয়োজ্যেষ্ঠ", critical: "সংকটাপন্ন",
        injuries: "আঘাত ও জরুরি চিকিৎসা প্রয়োজন:",
        bleed: "রক্তক্ষরণ", crush: "চাপা পড়া", insulin: "ইনসুলিন প্রয়োজন",
        dialysis: "ডায়ালিসিস প্রয়োজন", fracture: "হাড় ভাঙা", pregnant: "গর্ভবতী",
        loc: "অবস্থান / ল্যান্ডমার্ক / নোট:",
        locPlaceholder: "যেমন: ২য় তলা সিঁড়ির নিচে, লাল জলের ট্যাঙ্কের পাশে...",
        broadcast: "🚨 অবিলম্বে SOS পাঠান",
        resTitle: "✅ এসওএস সংকেত সফলভাবে পাঠানো হয়েছে",
        resSub: "আপনার জরুরি সংকেত সেটুর মেশ ডাটাবেসে সংরক্ষিত হয়েছে।",
        adviceTitle: "📖 এনডিএমএ প্রাথমিক চিকিৎসা পরামর্শ:"
      },
      ta: {
        title: "🚨 சேது அவசர SOS",
        sub: "இணையம் அல்லது ஆப் தேவையில்லை • ஆஃப்லைன் பேரிடர் நெட்வொர்க்",
        badge: "🟢 மீட்பு ட்ரோன்/படகு நெட்வொர்க் இணைக்கப்பட்டது",
        disaster: "பேரிடர் வகை:",
        trapped: "நீங்கள் சிக்கியுள்ளீர்களா?",
        trappedYes: "ஆம் (சிக்கியுள்ளேன்)",
        trappedNo: "இல்லை (நகர முடியும்)",
        demographics: "மீட்கப்பட வேண்டியவர்கள்:",
        adults: "பெரியவர்கள்", kids: "குழந்தைகள்", elderly: "முதியவர்கள்", critical: "கடுமையான",
        injuries: "காயங்கள் மற்றும் அவசர மருத்துவ தேவைகள்:",
        bleed: "இரத்தப்போக்கு", crush: "இடிபாடுகளில் காயம்", insulin: "இன்சுலின் தேவை",
        dialysis: "டயாலிசிஸ் தேவை", fracture: "எலும்பு முறிவு", pregnant: "கர்ப்பம்",
        loc: "இருப்பிடம் / அடையாளங்கள்:",
        locPlaceholder: "எ.கா. 2வது மாடி படிக்கட்டுக்கு கீழ், சிவப்பு நீர் தொட்டி...",
        broadcast: "🚨 அவசர SOS அனுப்புங்கள்",
        resTitle: "✅ அவசர செய்தி பதிவு செய்யப்பட்டது",
        resSub: "உங்கள் செய்தி 120-பைட் பேக்கெட்டாக மாற்றப்பட்டு சேமிக்கப்பட்டது.",
        adviceTitle: "📖 முதலுதவி வழிமுறைகள்:"
      },
      te: {
        title: "🚨 సేతు అత్యవసర SOS",
        sub: "ఇంటర్నెట్ లేదా యాప్ అవసరం లేదు • ఆఫ్‌లైన్ నెట్‌వర్క్",
        badge: "🟢 రెస్క్యూ మెష్ కనెక్ట్ చేయబడింది",
        disaster: "విపత్తు రకం:",
        trapped: "మీరు చిక్కుకున్నారా?",
        trappedYes: "అవును (చిక్కుకున్నాను)",
        trappedNo: "లేదు (నడవగలను)",
        demographics: "రక్షించాల్సిన వ్యక్తులు:",
        adults: "పెద్దలు", kids: "పిల్లలు", elderly: "వృద్ధులు", critical: "తీవ్రమైన",
        injuries: "గాయాలు మరియు అత్యవసర వైద్యం:",
        bleed: "రక్తస్రావం", crush: "శిథిలాల గాయం", insulin: "ఇన్సులిన్ అవసరం",
        dialysis: "డయాలసిస్ అవసరం", fracture: "ఎముక విరిగింది", pregnant: "గర్భవతి",
        loc: "స్థానం / వివరాలు:",
        locPlaceholder: "ఉదా: 2వ అంతస్తు మెట్ల కింద, ఎరుపు నీటి ట్యాంక్ దగ్గర...",
        broadcast: "🚨 ఇప్పుడే SOS పంపండి",
        resTitle: "✅ SOS విజయవంతంగా పంపబడింది",
        resSub: "మీ సమాచారం భద్రపరచబడింది.",
        adviceTitle: "📖 ప్రథమ చికిత్స మార్గదర్శకాలు:"
      },
      mr: {
        title: "🚨 सेतू आपत्कालीन एसओएस",
        sub: "ऑफलाईन आपत्ती मेश गेटवे • इंटरनेट किंवा ॲपची गरज नाही",
        badge: "🟢 रेस्क्यू ड्रोन/बोट मेश कनेक्टेड",
        disaster: "आपत्तीचा प्रकार:",
        trapped: "तुम्ही अडकलेले आहात का?",
        trappedYes: "होय (अडकलो आहोत)",
        trappedNo: "नाही (फिरू शकतो)",
        demographics: "वाचवण्यासाठी एकूण व्यक्ती:",
        adults: "प्रौढ", kids: "मुले", elderly: "वृद्ध", critical: "गंभीर",
        injuries: "जखमा व तातडीची औषधे:",
        bleed: "रक्तस्राव", crush: "मलब्याखाली दबणे", insulin: "इन्सुलिन आवश्यक",
        dialysis: "डायलिसिस आवश्यक", fracture: "हाड मोडणे", pregnant: "गर्भवती",
        loc: "नक्की ठिकाण / खूण:",
        locPlaceholder: "उदा: दुसरा मजला जिन्याखाली, लाल पाण्याच्या टाकीजवळ...",
        broadcast: "🚨 तात्काळ SOS पाठवा",
        resTitle: "✅ एसओएस यशस्वीरीत्या नोंदवला गेला",
        resSub: "आपला संदेश सेतू मेश प्रणालीत साठवला गेला आहे.",
        adviceTitle: "📖 एनडीएमए प्रथमोपचार सूचना:"
      }
    };

    function setLanguage(lang) {
      currentLang = lang;
      document.querySelectorAll('.lang-btn').forEach(btn => btn.classList.remove('active'));
      const activeBtn = Array.from(document.querySelectorAll('.lang-btn')).find(b => b.textContent.includes(lang.toUpperCase()) || b.onclick.toString().includes(lang));
      if (activeBtn) activeBtn.classList.add('active');

      const t = I18N[lang] || I18N.en;
      document.getElementById('uiTitle').textContent = t.title;
      document.getElementById('uiSub').textContent = t.sub;
      document.getElementById('uiMeshBadge').textContent = t.badge;
      document.getElementById('lblDisaster').textContent = t.disaster;
      document.getElementById('lblTrapped').textContent = t.trapped;
      document.getElementById('btnTrappedYes').textContent = t.trappedYes;
      document.getElementById('btnTrappedNo').textContent = t.trappedNo;
      document.getElementById('lblDemographics').textContent = t.demographics;
      document.getElementById('lblAdults').textContent = t.adults;
      document.getElementById('lblKids').textContent = t.kids;
      document.getElementById('lblElderly').textContent = t.elderly;
      document.getElementById('lblCritical').textContent = t.critical;
      document.getElementById('lblInjuries').textContent = t.injuries;
      document.getElementById('lblBleed').textContent = t.bleed;
      document.getElementById('lblCrush').textContent = t.crush;
      document.getElementById('lblInsulin').textContent = t.insulin;
      document.getElementById('lblDialysis').textContent = t.dialysis;
      document.getElementById('lblFracture').textContent = t.fracture;
      document.getElementById('lblPregnant').textContent = t.pregnant;
      document.getElementById('lblLocation').textContent = t.loc;
      document.getElementById('noteText').placeholder = t.locPlaceholder;
      document.getElementById('btnSubmit').textContent = t.broadcast;
      document.getElementById('resTitle').textContent = t.resTitle;
      document.getElementById('resSub').textContent = t.resSub;
      document.getElementById('lblAdviceTitle').textContent = t.adviceTitle;
    }

    function setTrapped(val) {
      isTrappedVal = val;
      const yesBtn = document.getElementById('btnTrappedYes');
      const noBtn = document.getElementById('btnTrappedNo');
      if (val) {
        yesBtn.classList.add('selected');
        noBtn.classList.remove('selected');
      } else {
        yesBtn.classList.remove('selected');
        noBtn.classList.add('selected');
      }
    }

    function changeCount(field, delta) {
      counts[field] = Math.max(0, Math.min(15, counts[field] + delta));
      if (field === 'adults' && counts.adults < 1) counts.adults = 1;
      document.getElementById(`val_${field}`).textContent = counts[field];
    }

    async function broadcastSos(e) {
      e.preventDefault();
      const btn = document.getElementById('btnSubmit');
      btn.disabled = true;
      btn.textContent = "TRANSMITTING OVER ZERO-GRID MESH...";

      const payload = {
        language: currentLang,
        disaster_type: parseInt(document.getElementById('disasterType').value),
        is_trapped: isTrappedVal,
        adults: counts.adults,
        children: counts.children,
        elderly: counts.elderly,
        critical_cases: counts.critical,
        arterial_bleed: document.getElementById('m_bleed').checked,
        crush: document.getElementById('m_crush').checked,
        insulin: document.getElementById('m_insulin').checked,
        dialysis: document.getElementById('m_dialysis').checked,
        fracture: document.getElementById('m_fracture').checked,
        pregnancy: document.getElementById('m_pregnant').checked,
        note: document.getElementById('noteText').value || "Zero-Grid Captive Portal SOS"
      };

      try {
        const res = await fetch('/api/v1/captive_sos', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          const data = await res.json();
          document.getElementById('sosForm').style.display = 'none';
          document.getElementById('resultCard').style.display = 'block';

          const sevBadge = document.getElementById('resSeverity');
          sevBadge.textContent = `${data.severity_label} (Level ${data.severity})`;
          sevBadge.className = 'badge ' + (data.severity >= 2 ? 'badge-red' : (data.severity === 1 ? 'badge-yellow' : 'badge-green'));

          document.getElementById('resHash').textContent = data.packet_hash;
          document.getElementById('resAdvice').textContent = data.first_aid_guidance || data.ndma_advice;
        } else {
          alert("Submission failed. Retrying...");
          btn.disabled = false;
          btn.textContent = I18N[currentLang].broadcast;
        }
      } catch (err) {
        alert("Mesh connection error. Please tap Broadcast again.");
        btn.disabled = false;
        btn.textContent = I18N[currentLang].broadcast;
      }
    }
  </script>
</body>
</html>
"""


class DNSHijacker:
    """
    Asynchronous / Threaded DNS Hijacker.
    Listens on UDP port 53 (or custom port).
    Intercepts all DNS queries (A records) and resolves them to the Captive Gateway IP.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 53, gateway_ip: str = "192.168.4.1"):
        self.host = host
        self.port = port
        self.gateway_ip = gateway_ip
        self.running = False
        self.sock: Optional[socket.socket] = None
        self.thread: Optional[threading.Thread] = None
        self.query_count = 0
        self.queries_log: List[str] = []
        self._lock = threading.Lock()

    def start(self):
        """Binds UDP socket and starts listener thread."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        # Update port in case ephemeral port (0) was supplied
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(0.5)
        self.running = True

        self.thread = threading.Thread(target=self._listen_loop, name=f"DNSHijacker-{self.port}", daemon=True)
        self.thread.start()

    def stop(self):
        """Stops listener thread and closes socket."""
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(512)
                if not data:
                    continue
                response = self.craft_response(data)
                if response:
                    self.sock.sendto(response, addr)
            except socket.timeout:
                continue
            except (OSError, socket.error):
                break
            except Exception as e:
                if not self.running:
                    break

    def parse_domain_name(self, data: bytes, offset: int = 12) -> Tuple[str, int]:
        """Parses QNAME from DNS query packet starting at offset. Returns ("", -1) if malformed."""
        domain_parts = []
        curr = offset
        while curr < len(data):
            length = data[curr]
            if length == 0:
                curr += 1
                break
            if (length & 0xC0) == 0xC0:
                if curr + 2 > len(data):
                    return "", -1
                curr += 2
                break
            curr += 1
            if curr + length > len(data):
                return "", -1
            domain_parts.append(data[curr : curr + length].decode("ascii", errors="replace"))
            curr += length
        else:
            return "", -1
        return ".".join(domain_parts), curr

    def craft_response(self, data: bytes) -> bytes:
        """
        Synthesizes authoritative DNS A record response pointing to self.gateway_ip.
        """
        if len(data) < 17:
            return b""

        domain, end_qname_offset = self.parse_domain_name(data, offset=12)
        if end_qname_offset < 0 or end_qname_offset + 4 > len(data):
            return b""

        with self._lock:
            self.query_count += 1
            self.queries_log.append(domain)

        tx_id = data[:2]
        # Standard query response, No error: 0x8180
        flags = b"\x81\x80"
        qdcount = b"\x00\x01"
        ancount = b"\x00\x01"
        nscount = b"\x00\x00"
        arcount = b"\x00\x00"

        # Question section includes QNAME + QTYPE(2) + QCLASS(2)
        question_bytes = data[12 : end_qname_offset + 4]

        # Answer Section:
        # 0xC00C pointer to QNAME at byte 12
        # Type: 0x0001 (A record)
        # Class: 0x0001 (IN)
        # TTL: 60s (0x0000003C)
        # RDLENGTH: 4 (0x0004)
        # RDATA: IPv4 binary representation
        ip_bytes = socket.inet_aton(self.gateway_ip)
        answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + ip_bytes

        return tx_id + flags + qdcount + ancount + nscount + arcount + question_bytes + answer

    def resolve_query(self, domain: str) -> str:
        """Logical resolution helper returning the gateway IP."""
        return self.gateway_ip


class CaptivePortalHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP Server handling captive probe redirects, serving the offline Micro-PWA,
    and processing REST SOS submissions.
    """

    # Silence standard logging to console in production/test unless debugging
    def log_message(self, format, *args):
        pass

    def _track_client(self):
        try:
            client_ip = self.client_address[0]
            if hasattr(self.server, "connected_victims"):
                lock = getattr(self.server, "_victims_lock", None)
                if lock:
                    with lock:
                        self.server.connected_victims.add(client_ip)
                else:
                    self.server.connected_victims.add(client_ip)
        except Exception:
            pass

    def do_OPTIONS(self):
        """Handles CORS preflight requests for mobile browser / WebView compatibility."""
        self._track_client()
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        """Handles HEAD probes from operating system captive network detectors."""
        self._handle_get(is_head=True)

    def do_GET(self):
        """Handles captive probe redirects, PWA serving, and status telemetry."""
        self._handle_get(is_head=False)

    def _handle_get(self, is_head: bool = False):
        self._track_client()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # 1. Telemetry / Status REST API
        if path == "/api/v1/status":
            mule = getattr(self.server, "mule_service", None)
            if mule and hasattr(mule, "db"):
                if hasattr(mule.db, "get_packet_count"):
                    spooled_count = mule.db.get_packet_count()
                else:
                    spooled_count = len(mule.db.get_all_records())
            else:
                spooled_count = 0
            dev_name = mule.device_name if mule else "SetuMule-Captive-01"

            lock = getattr(self.server, "_victims_lock", None)
            if lock:
                with lock:
                    victim_count = len(self.server.connected_victims)
            else:
                victim_count = len(getattr(self.server, "connected_victims", set()))

            resp = {
                "status": "online",
                "gateway_device": dev_name,
                "connected_victims_count": victim_count,
                "spooled_packets_count": spooled_count,
                "gateway_telemetry": {
                    "device_name": dev_name,
                    "mode": "CAPTIVE_PORTAL_ACTIVE",
                    "battery_pct": 95,
                    "is_gateway": True
                }
            }
            body_bytes = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            if not is_head:
                self.wfile.write(body_bytes)
            return

        # 2. Android Captive Portal Probes
        # /generate_204, /gen_204 -> HTTP 302 Found redirect to /
        if path in ("/generate_204", "/gen_204"):
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        # 3. Apple iOS / macOS Captive Network Assistant (CNA) & Windows NCSI
        # /hotspot-detect.html -> Serves Captive Portal HTML
        if path in ("/hotspot-detect.html", "/ncsi.txt", "/connecttest.txt", "/", "/index.html"):
            body_bytes = CAPTIVE_PORTAL_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            if not is_head:
                self.wfile.write(body_bytes)
            return

        # 4. Generic catch-all redirect to /
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):
        self._track_client()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/api/v1/captive_sos", "/api/submit_portal_sos"):
            try:
                content_length = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                content_length = 0

            if content_length <= 0:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "Missing request payload"}).encode("utf-8"))
                return

            if content_length > 1024 * 1024:
                self.send_response(413)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "Payload too large"}).encode("utf-8"))
                return

            body = self.rfile.read(content_length).decode("utf-8", errors="replace")
            try:
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise ValueError("Payload must be a JSON object")
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": f"Malformed JSON: {str(e)}"}).encode("utf-8"))
                return

            try:
                # Compute Medical Flags bitmask
                flags = _safe_int(data.get("medical_flags", 0), default=0, min_val=0, max_val=0xFFFF)
                if _safe_bool(data.get("arterial_bleed")) or _safe_bool(data.get("med_bleeding")) or _safe_bool(data.get("bleeding")):
                    flags |= MED_FLAG_BLEEDING
                if _safe_bool(data.get("crush")) or _safe_bool(data.get("med_crush")) or _safe_bool(data.get("crush_injury")):
                    flags |= MED_FLAG_CRUSH
                if _safe_bool(data.get("insulin")) or _safe_bool(data.get("med_insulin")):
                    flags |= MED_FLAG_INSULIN
                if _safe_bool(data.get("dialysis")) or _safe_bool(data.get("med_dialysis")):
                    flags |= MED_FLAG_DIALYSIS
                if _safe_bool(data.get("fracture")) or _safe_bool(data.get("med_fracture")):
                    flags |= MED_FLAG_FRACTURE
                if _safe_bool(data.get("pregnancy")) or _safe_bool(data.get("med_pregnant")) or _safe_bool(data.get("pregnant")):
                    flags |= MED_FLAG_PREGNANCY
                if _safe_bool(data.get("o2")) or _safe_bool(data.get("med_o2")) or _safe_bool(data.get("oxygen")):
                    flags |= MED_FLAG_O2_NEEDED
                if _safe_bool(data.get("snakebite")) or _safe_bool(data.get("med_snakebite")):
                    flags |= MED_FLAG_SNAKEBITE

                # Extract Demographics & Clamp safely (4-bit range 0-15)
                adults = _safe_int(data.get("adults"), default=1, min_val=0, max_val=15)
                children = _safe_int(data.get("children"), default=0, min_val=0, max_val=15)
                elderly = _safe_int(data.get("elderly"), default=0, min_val=0, max_val=15)
                critical_cases = _safe_int(data.get("critical_cases"), default=0, min_val=0, max_val=15)

                # Trapped status
                is_trapped = _safe_bool(data.get("is_trapped"), default=False)

                # Severity computation if not explicitly supplied
                if "severity" in data:
                    severity = _safe_int(data["severity"], default=SEVERITY_YELLOW, min_val=0, max_val=3)
                else:
                    # Triage Protocol:
                    # Trapped OR Arterial Bleed OR Crush OR Dialysis OR Insulin OR critical cases > 0 -> RED (Immediate)
                    urgent_flags = MED_FLAG_BLEEDING | MED_FLAG_CRUSH | MED_FLAG_DIALYSIS | MED_FLAG_INSULIN
                    if is_trapped or (flags & urgent_flags) != 0 or critical_cases > 0:
                        severity = SEVERITY_RED
                    elif (flags & (MED_FLAG_FRACTURE | MED_FLAG_PREGNANCY | MED_FLAG_O2_NEEDED)) != 0 or elderly > 0:
                        severity = SEVERITY_YELLOW
                    else:
                        severity = SEVERITY_GREEN

                if severity == SEVERITY_RED and critical_cases == 0:
                    critical_cases = 1

                note = str(data.get("note") or data.get("location_notes") or "Captive portal SOS")
                disaster_type = _safe_int(
                    data.get("disaster_type", data.get("disaster", DISASTER_FLOOD)),
                    default=DISASTER_FLOOD,
                    min_val=0,
                    max_val=6
                )
                lat = _safe_float(data.get("latitude"), default=20.2975, min_val=-90.0, max_val=90.0)
                lon = _safe_float(data.get("longitude"), default=85.8260, min_val=-180.0, max_val=180.0)
                alt_dm = _safe_int(data.get("altitude_decimeters"), default=0, min_val=-32768, max_val=32767)
                batt_pct = _safe_int(data.get("battery_pct"), default=85, min_val=0, max_val=100)

                device_id = str(data.get("device_id") or f"CP_{int(time.time() * 1000) % 1000000:06d}")

                # Pack authentic 120-byte binary packet
                raw_pkt = pack_sos_packet(
                    device_id=device_id,
                    timestamp=int(time.time()),
                    latitude=lat,
                    longitude=lon,
                    altitude_decimeters=alt_dm,
                    severity=severity,
                    disaster_type=disaster_type,
                    is_trapped=is_trapped,
                    mobility=0 if is_trapped else 1,
                    adults=adults,
                    children=children,
                    elderly=elderly,
                    critical_cases=critical_cases,
                    hop_count=5,
                    battery_pct=batt_pct,
                    medical_flags=flags,
                    note=note
                )

                # Validate CRC16 and exact 120-byte length
                assert len(raw_pkt) == 120, "Binary packet must be exactly 120 bytes"
                unpacked = unpack_sos_packet(raw_pkt)
                packet_hash = f"{unpacked['device_hash']}_{unpacked['timestamp']}"

                # Save into Setu Mule SQLite Buffer
                mule = getattr(self.server, "mule_service", None)
                saved = False
                if mule:
                    saved = mule.db.insert_packet(raw_pkt, source_channel="HOTSPOT_CAPTIVE_PORTAL")
                    if hasattr(mule, "mesh_node") and mule.mesh_node:
                        mule.mesh_node.receive_packet(raw_pkt)

                # Query NDMA Offline Emergency RAG for Immediate First-Aid Guidance
                rag = getattr(self.server, "rag", None)
                if not rag:
                    rag = OfflineEmergencyRAG()

                # Build query keywords from triage indicators
                disaster_label = unpacked["disaster_label"].lower()
                query_terms = [disaster_label]
                if is_trapped:
                    query_terms.extend(["trapped", "rubble", "collapse"])
                if flags & MED_FLAG_BLEEDING:
                    query_terms.extend(["bleeding", "wound", "arterial bleed"])
                if flags & MED_FLAG_CRUSH:
                    query_terms.extend(["crush", "fracture", "chot"])
                if flags & MED_FLAG_INSULIN:
                    query_terms.extend(["insulin", "diabetes", "sugar"])
                if flags & MED_FLAG_SNAKEBITE:
                    query_terms.extend(["snake", "bite"])
                if note:
                    query_terms.append(note)

                lang = str(data.get("language") or "en")
                advice_text = rag.get_relief_response(" ".join(query_terms), lang=lang)

                response_payload = {
                    "status": "success",
                    "saved_to_mule": saved,
                    "calculated_triage_severity": severity,
                    "severity": severity,
                    "severity_label": unpacked["severity_label"],
                    "packet_hash": packet_hash,
                    "first_aid_guidance": advice_text,
                    "ndma_advice": advice_text,
                    "packet_size": len(raw_pkt)
                }

                resp_bytes = json.dumps(response_payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store")
                self.send_header("Content-Length", str(len(resp_bytes)))
                self.end_headers()
                self.wfile.write(resp_bytes)
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": f"Server processing error: {str(e)}"}).encode("utf-8"))
                return

        # Drain unread request body so TCP socket is cleanly consumed
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                self.rfile.read(content_length)
        except Exception:
            pass

        self.send_response(404)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()


class CaptivePortalServer(http.server.ThreadingHTTPServer):
    """
    Multithreaded HTTP Captive Portal Server.
    Maintains victim tracking, Setu Mule DB connection, and NDMA RAG model.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8080,
        mule_service: Optional[AndroidSetuMuleGateway] = None,
        gateway_ip: str = "192.168.4.1",
    ):
        self.host = host
        self.gateway_ip = gateway_ip
        self.mule_service = mule_service or AndroidSetuMuleGateway("SetuMule-PortalGateway")
        self.rag = OfflineEmergencyRAG()
        self.connected_victims = set()
        self._victims_lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.is_running = False

        super().__init__((host, port), CaptivePortalHandler)
        self.port = self.server_address[1]

    def start(self):
        """Starts server in a background daemon thread."""
        self.is_running = True
        self.thread = threading.Thread(target=self.serve_forever, daemon=True, name="CaptivePortalHTTP")
        self.thread.start()

    def stop(self):
        """Shuts down server and releases socket."""
        self.is_running = False
        try:
            self.shutdown()
        except Exception:
            pass
        try:
            self.server_close()
        except Exception:
            pass
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)


class ZeroInstallCaptiveGateway:
    """
    Combined Gateway supervisor managing both DNS Hijacker and Captive Portal HTTP Server.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        http_port: int = 8080,
        dns_port: Optional[int] = 5353,
        gateway_ip: str = "192.168.4.1",
        mule_service: Optional[AndroidSetuMuleGateway] = None,
    ):
        self.host = host
        self.gateway_ip = gateway_ip
        self.mule_service = mule_service or AndroidSetuMuleGateway()
        self.http_server = CaptivePortalServer(
            host=host, port=http_port, mule_service=self.mule_service, gateway_ip=gateway_ip
        )
        self.dns_hijacker = (
            DNSHijacker(host=host, port=dns_port, gateway_ip=gateway_ip) if dns_port is not None else None
        )

    @property
    def http_port(self) -> int:
        return self.http_server.port

    @property
    def dns_port(self) -> Optional[int]:
        return self.dns_hijacker.port if self.dns_hijacker else None

    def start(self):
        if self.dns_hijacker:
            self.dns_hijacker.start()
        self.http_server.start()

    def stop(self):
        if self.dns_hijacker:
            self.dns_hijacker.stop()
        self.http_server.stop()
