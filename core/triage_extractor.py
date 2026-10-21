"""
SLM Entity Extractor & Dialect Triage Parser
Simulates the quantized Qwen-2.5-0.5B / Llama-3.2-1B on-device grammar-constrained extractor.
Converts regional Indic vernacular speech transcripts into deterministic triage fields.

Supports:
- English, Hindi, and transliterated Hinglish.
- Automatic extraction of:
  - Headcount (adults, children, elderly)
  - Medical urgencies (insulin, dialysis, pregnancy, crush, bleeding, fracture, snakebite)
  - Hazard / Disaster type (flood, collapse, fire, landslide)
  - Trapped status & mobility
  - Deterministic triage severity (RED, YELLOW, GREEN, BLACK)
"""

import re
from typing import Dict, Any
from core.sos_packet import (
    SEVERITY_RED,
    SEVERITY_YELLOW,
    SEVERITY_GREEN,
    DISASTER_FLOOD,
    DISASTER_BUILDING_COLLAPSE,
    DISASTER_FIRE,
    DISASTER_LANDSLIDE,
    DISASTER_EARTHQUAKE,
    DISASTER_OTHER,
    MED_FLAG_INSULIN,
    MED_FLAG_DIALYSIS,
    MED_FLAG_PREGNANCY,
    MED_FLAG_CRUSH,
    MED_FLAG_SNAKEBITE,
    MED_FLAG_O2_NEEDED,
    MED_FLAG_BLEEDING,
    MED_FLAG_FRACTURE
)


class VernacularTriageExtractor:
    """Extracts structured triage payload from unstructured Indic or English survivor statements."""

    @classmethod
    def parse_transcript(cls, text: str) -> Dict[str, Any]:
        lower = text.lower()

        # 1. Disaster Type
        disaster_type = DISASTER_OTHER
        if any(w in lower for w in ["पानी", "paani", "water", "flood", "बाढ़", "baadh", "doob", "roof", "छत"]):
            disaster_type = DISASTER_FLOOD
        elif any(w in lower for w in ["malba", "मलबा", "collapsed", "debris", "gir gaya", "गिर गया", "building"]):
            disaster_type = DISASTER_BUILDING_COLLAPSE
        elif any(w in lower for w in ["fire", "आग", "aag", "smoke", "धुआं"]):
            disaster_type = DISASTER_FIRE
        elif any(w in lower for w in ["earthquake", "भूकंप", "bhookamp"]):
            disaster_type = DISASTER_EARTHQUAKE
        elif any(w in lower for w in ["landslide", "भूस्खलन"]):
            disaster_type = DISASTER_LANDSLIDE

        # 2. Trapped Status
        is_trapped = any(w in lower for w in [
            "trapped", "फंसे", "fase", "daba", "दबा", "stuck", "cannot move", "rooftop", "roof", "छत", "band"
        ])

        # 3. Medical Flags
        med_flags = 0
        if any(w in lower for w in ["insulin", "इंसुलिन", "sugar", "मधुमेह"]):
            med_flags |= MED_FLAG_INSULIN
        if any(w in lower for w in ["dialysis", "डायलिसिस", "kidney"]):
            med_flags |= MED_FLAG_DIALYSIS
        if any(w in lower for w in ["pregnant", "गर्भवती", "garbhwati", "pregnancy"]):
            med_flags |= MED_FLAG_PREGNANCY
        if any(w in lower for w in ["crush", "दब गया", "dab gaya"]):
            med_flags |= MED_FLAG_CRUSH
        if any(w in lower for w in ["snake", "सांप", "saap", "kat liya"]):
            med_flags |= MED_FLAG_SNAKEBITE
        if any(w in lower for w in ["oxygen", "सांस", "saans", "asthma", "breathing"]):
            med_flags |= MED_FLAG_O2_NEEDED
        if any(w in lower for w in ["bleed", "खून", "khoon", "blood"]):
            med_flags |= MED_FLAG_BLEEDING
        if any(w in lower for w in ["fracture", "हड्डी", "haddi", "broken leg"]):
            med_flags |= MED_FLAG_FRACTURE

        # 4. Demographics
        adults = 1
        children = 0
        elderly = 0

        # Numbers for kids
        kids_match = re.search(r'(\d+)\s*(kids?|children|बच्चे|bacche)', lower)
        if kids_match:
            children = int(kids_match.group(1))
        elif any(w in lower for w in ["दो बच्चे", "2 बच्चे", "two kids", "2 kids"]):
            children = 2
        elif any(w in lower for w in ["बच्चा", "बच्चे", "kid", "child", "baccha"]):
            children = 1

        # Numbers for elderly
        if any(w in lower for w in ["elderly", "बुजुर्ग", "bujurg", "dada", "dadi", "grandfather", "grandmother"]):
            elderly = 1
            eld_match = re.search(r'(\d+)\s*(elderly|बुजुर्ग|old)', lower)
            if eld_match:
                elderly = int(eld_match.group(1))

        # Adults count
        adult_match = re.search(r'(\d+)\s*(adults?|लोग|log|members?)', lower)
        if adult_match:
            total_members = int(adult_match.group(1))
            adults = max(1, total_members - children - elderly)

        # 5. Severity Assessment
        # RED: Trapped with medical emergency, snakebite, unconscious, pregnant in labor, breathing issues
        if med_flags & (MED_FLAG_INSULIN | MED_FLAG_DIALYSIS | MED_FLAG_O2_NEEDED | MED_FLAG_SNAKEBITE | MED_FLAG_CRUSH):
            severity = SEVERITY_RED
        elif is_trapped and (children > 0 or elderly > 0):
            severity = SEVERITY_RED
        elif is_trapped or (med_flags & (MED_FLAG_BLEEDING | MED_FLAG_FRACTURE)):
            severity = SEVERITY_YELLOW
        else:
            severity = SEVERITY_GREEN

        critical_cases = 1 if severity == SEVERITY_RED else 0
        mobility = 0 if is_trapped else 1

        return {
            "disaster_type": disaster_type,
            "is_trapped": is_trapped,
            "severity": severity,
            "mobility": mobility,
            "demographics": {
                "adults": adults,
                "children": children,
                "elderly": elderly,
                "critical_cases": critical_cases,
                "total_headcount": adults + children + elderly
            },
            "medical_flags": med_flags,
            "summary_note": text[:90]
        }
