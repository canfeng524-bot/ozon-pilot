import datetime as dt
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import keywords


class KeywordPlanTests(unittest.TestCase):
    def setUp(self):
        self.cfg = {
            "keyword_policy": {
                "seller_metrics_max_age_days": 90,
                "current_site_max_age_days": 45,
                "title_term_limits": {"core": 2, "attribute": 2, "scene": 1},
                "description_term_limit": 6,
            }
        }
        self.info = {"item_id": "1", "title": "supplier title"}

    def test_missing_research_never_claims_heat(self):
        with tempfile.TemporaryDirectory() as folder:
            plan = keywords.run(self.cfg, folder, self.info)
            self.assertEqual(plan["status"], "no_keyword_research")
            self.assertEqual(plan["title_terms"]["core"], [])
            self.assertTrue(pathlib.Path(folder, "keyword_plan.json").exists())

    def test_evidence_grades_and_placement(self):
        today = dt.date.today().isoformat()
        research = {
            "checked_at": today,
            "category": "Сумки женские",
            "queries": [
                {"query": "сумка женская через плечо", "role": "core", "product_match": "exact",
                 "source": "ozon_seller_queries", "searches": 100, "views": 30, "orders": 3},
                {"query": "кросс-боди", "role": "core", "product_match": "exact",
                 "source": "ozon_category"},
                {"query": "на каждый день", "role": "scene", "product_match": "partial",
                 "source": "ozon_category"},
                {"query": "для учебы", "role": "negative", "product_match": "exclude",
                 "source": "ozon_search_results", "note": "unsupported use"},
            ],
        }
        with tempfile.TemporaryDirectory() as folder:
            pathlib.Path(folder, "keyword_research.json").write_text(
                json.dumps(research, ensure_ascii=False), encoding="utf-8"
            )
            plan = keywords.run(self.cfg, folder, self.info)
        self.assertEqual(plan["status"], "seller_metrics_available")
        self.assertEqual(plan["title_terms"]["core"], ["сумка женская через плечо", "кросс-боди"])
        self.assertIn("на каждый день", plan["description_terms"])
        self.assertEqual(plan["excluded_terms"][0]["query"], "для учебы")
        self.assertEqual(plan["queries"][0]["evidence_tier"], "A")

    def test_stale_seller_metrics_are_not_current_heat(self):
        research = {
            "checked_at": "2020-01-01",
            "queries": [
                {"query": "старый запрос", "role": "core", "product_match": "exact",
                 "source": "ozon_seller_queries", "searches": 99999}
            ],
        }
        with tempfile.TemporaryDirectory() as folder:
            pathlib.Path(folder, "keyword_research.json").write_text(
                json.dumps(research, ensure_ascii=False), encoding="utf-8"
            )
            plan = keywords.run(self.cfg, folder, self.info)
        self.assertEqual(plan["queries"][0]["evidence_tier"], "C")
        self.assertEqual(plan["status"], "hypothesis_only")
        self.assertEqual(plan["title_terms"]["core"], [])

    def test_zero_metrics_do_not_prove_title_demand(self):
        research = {
            "checked_at": dt.date.today().isoformat(),
            "queries": [
                {"query": "запрос без спроса", "role": "core", "product_match": "exact",
                 "source": "ozon_seller_queries", "searches": 0, "views": 0, "orders": 0}
            ],
        }
        with tempfile.TemporaryDirectory() as folder:
            pathlib.Path(folder, "keyword_research.json").write_text(
                json.dumps(research, ensure_ascii=False), encoding="utf-8"
            )
            plan = keywords.run(self.cfg, folder, self.info)
        self.assertEqual(plan["queries"][0]["evidence_tier"], "A")
        self.assertFalse(plan["queries"][0]["positive_demand_signal"])
        self.assertEqual(plan["title_terms"]["core"], [])


if __name__ == "__main__":
    unittest.main()
