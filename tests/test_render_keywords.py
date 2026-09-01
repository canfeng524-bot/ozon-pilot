import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import render


class KeywordReviewTests(unittest.TestCase):
    def test_review_shows_keyword_evidence(self):
        cfg = {
            "carousel_plan": [],
            "pricing": {"suggested_price_rub": 1000},
        }
        listing = {
            "listing": {
                "title_ru": "Сумка женская через плечо",
                "description_ru": "Описание",
                "search_terms_used": [
                    {
                        "term": "сумка женская через плечо",
                        "placement": "title",
                        "evidence_tier": "A",
                        "reason": "Ozon Seller query metrics",
                    }
                ],
                "search_terms_excluded": [
                    {"term": "для учебы", "reason": "unsupported use"}
                ],
            }
        }
        keyword_plan = {"status": "seller_metrics_available"}
        with tempfile.TemporaryDirectory() as folder:
            path = pathlib.Path(folder)
            (path / "listing.json").write_text(
                json.dumps(listing, ensure_ascii=False), encoding="utf-8"
            )
            (path / "keyword_plan.json").write_text(
                json.dumps(keyword_plan, ensure_ascii=False), encoding="utf-8"
            )
            render.run(cfg, folder, {"item_id": "1", "platform": "1688"})
            review = (path / "review.html").read_text(encoding="utf-8")

        self.assertIn("seller_metrics_available", review)
        self.assertIn("сумка женская через плечо", review)
        self.assertIn("для учебы", review)


if __name__ == "__main__":
    unittest.main()
