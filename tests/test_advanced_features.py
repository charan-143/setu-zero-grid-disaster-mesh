import unittest
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.triage_extractor import VernacularTriageExtractor
from core.offline_rag import OfflineEmergencyRAG
from dashboard.safe_path_router import SafePathRouter, haversine_distance_meters
from core.sos_packet import SEVERITY_RED, DISASTER_FLOOD, MED_FLAG_INSULIN


class TestAdvancedCapabilities(unittest.TestCase):

    def test_01_indic_vernacular_entity_extraction(self):
        """Verifies Hindi/Indic transcript extraction into structured triage fields."""
        hindi_transcript = "पानी छत तक आ गया है, मेरे साथ दो बच्चे और एक बुजुर्ग हैं जिन्हें इंसुलिन चाहिए"
        result = VernacularTriageExtractor.parse_transcript(hindi_transcript)

        self.assertEqual(result["disaster_type"], DISASTER_FLOOD)
        self.assertTrue(result["is_trapped"])
        self.assertEqual(result["severity"], SEVERITY_RED)
        self.assertEqual(result["demographics"]["children"], 2)
        self.assertEqual(result["demographics"]["elderly"], 1)
        self.assertTrue(result["medical_flags"] & MED_FLAG_INSULIN)

    def test_02_offline_rag_retrieval(self):
        """Verifies on-device RAG protocol retrieval for life-saving guidance."""
        rag = OfflineEmergencyRAG()
        query = "इंसुलिन की दवा और छत पर पानी"
        results = rag.retrieve(query, top_k=2)

        self.assertGreater(len(results), 0)
        categories = [r["category"] for r in results]
        self.assertTrue("MEDICAL_INSULIN" in categories or "FLOOD" in categories)

        speech_text = rag.get_relief_response(query, lang="hi")
        self.assertIn("इंसुलिन", speech_text)

    def test_03_safe_path_mission_planning(self):
        """Verifies rescue mission prioritization and route calculation."""
        alerts = [
            {
                "device_hash": "survivor_minor",
                "severity": 0, # GREEN
                "severity_label": "GREEN",
                "disaster_label": "FLOOD",
                "is_trapped": False,
                "battery_pct": 80,
                "total_headcount": 1,
                "latitude": 20.3100,
                "longitude": 85.8300,
                "altitude_m": 5.0,
                "medical_flags": {},
                "note": "Minor water"
            },
            {
                "device_hash": "survivor_critical_insulin",
                "severity": 2, # RED
                "severity_label": "RED",
                "disaster_label": "FLOOD",
                "is_trapped": True,
                "battery_pct": 12, # low battery
                "total_headcount": 5,
                "latitude": 20.2950,
                "longitude": 85.8240,
                "altitude_m": 12.0,
                "medical_flags": {"insulin": True},
                "note": "Critical insulin"
            }
        ]

        plan = SafePathRouter.generate_rescue_mission_plan(20.2900, 85.8200, alerts)
        self.assertEqual(len(plan), 2)
        # Critical insulin alert must be stop 1
        self.assertEqual(plan[0]["device_hash"], "survivor_critical_insulin")
        self.assertEqual(plan[0]["stop_order"], 1)
        self.assertGreater(plan[0]["priority_score"], plan[1]["priority_score"])


if __name__ == "__main__":
    unittest.main()
