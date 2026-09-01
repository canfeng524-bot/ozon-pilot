# Ozon keyword research

Read this reference when the user asks for search-demand optimization, supplies Ozon Seller query data, or wants current seasonal/search wording. Do not load it for image-only revisions.

## Evidence levels

- **A — quantitative Ozon evidence:** a dated export or transcription from Ozon Seller `Запросы моего товара`, fresh within `keyword_policy.seller_metrics_max_age_days` and containing at least one of searches, views, orders, revenue, or average position. A row with only zero demand metrics proves measurement, not demand; it is not title-eligible on that evidence alone. Positive numbers still require an exact product match.
- **B — current-site wording:** Ozon autocomplete, category headings, filters, or search-result wording checked within `keyword_policy.current_site_max_age_days`. This proves current marketplace phrasing, not query volume or conversion.
- **C — hypothesis:** other marketplaces, competitor titles, search-engine snippets, or stale Ozon pages. Use only as a description candidate after confirming relevance.
- **U — unsupported:** missing source. Never call it hot, popular, high-volume, or high-converting.

Ozon's own Seller guidance says `Запросы моего товара` exposes queries that brought views or purchases, search volume, average result position, and order revenue. Prefer that evidence over public-title repetition: <https://seller.ozon.ru/media/news/novaya-analitika-po-zaprosam-tovarov/>.

## Input file

Place `keyword_research.json` in the product folder before running the pipeline:

```json
{
  "checked_at": "2026-09-01",
  "category": "Сумки женские",
  "sources": [
    {"type": "ozon_seller_queries", "label": "Запросы моего товара"},
    {"type": "ozon_category", "url": "https://www.ozon.ru/category/sumka-zamsha/"}
  ],
  "queries": [
    {
      "query": "сумка женская через плечо",
      "role": "core",
      "product_match": "exact",
      "source": "ozon_seller_queries",
      "searches": 0,
      "views": 0,
      "orders": 0,
      "revenue_rub": 0,
      "avg_position": null,
      "note": "Replace zeros with the dated Seller export values"
    },
    {
      "query": "повседневная",
      "role": "scene",
      "product_match": "exact",
      "source": "ozon_category",
      "checked_at": "2026-09-01"
    },
    {
      "query": "для учебы",
      "role": "negative",
      "product_match": "exclude",
      "source": "ozon_search_results",
      "checked_at": "2026-09-01",
      "note": "SKU capacity and use case do not support this query"
    }
  ]
}
```

Use `role`: `core`, `attribute`, `scene`, `synonym`, or `negative`. Use `product_match`: `exact`, `partial`, `exclude`, or `unknown`. Zero is a real metric value; omit a metric when it was not measured. Never invent Seller numbers.

The pipeline writes `keyword_plan.json`. Only exact A terms with a positive demand signal, or exact B terms with current Ozon wording evidence, can become title candidates. Partial terms are description-only. Excluded terms are passed to the copy model as hard negatives.

## Placement rules

- Put one primary category phrase first. A second core phrase is allowed only when it is a natural Russian synonym and does not repeat the same root mechanically.
- Use at most two verified differentiating attributes and one relevant scene phrase in the title.
- Put exact dimensions in attributes, description, and the size card—not the title by default.
- Put remaining exact/partial long-tail terms naturally in highlights or description, each at most once.
- Populate Ozon category attributes accurately; query evidence can justify which verified material, colour, form, carrying method, or closure deserves emphasis.
- Do not put SEO strings into carousel image text. Image captions should help conversion, not indexing.

## Dated women's-bag example

Checked 2026-09-01. Current Ozon category/search pages repeatedly use `сумка женская через плечо`, `сумка кросс-боди`, `сумка на плечо`, `повседневная`, and, for matching products, `сумка женская замшевая` or `сумка женская через плечо натуральная замша`:

- <https://www.ozon.ru/category/sumka-zhenskaya-krossbodi-chernaya/>
- <https://www.ozon.ru/category/sumka-zamsha/>
- <https://www.ozon.ru/category/sumki-zhenskie-na-plecho-srednie-kozhanye/>

Treat these as B-level wording, not measured heat. For a natural split-suede product, keep the evidence-bound material name (`натуральный спилок`) in attributes and use `замшевая` only when the visible nap and supplier evidence support that consumer-facing description. Do not add `осенняя`, `в подарок`, `для учебы`, or `для работы` merely because competitors use them; require exact SKU relevance and preferably A-level query data.
