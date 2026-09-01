# -*- coding: utf-8 -*-
"""Build an auditable Ozon keyword plan from optional dated research data."""
import datetime as dt
import json
import os


SELLER_SOURCES = {"ozon_seller_queries", "ozon_seller_analytics"}
CURRENT_SITE_SOURCES = {"ozon_autocomplete", "ozon_category", "ozon_search_results"}
VALID_MATCHES = {"exact", "partial", "exclude", "unknown"}
VALID_ROLES = {"core", "attribute", "scene", "synonym", "negative", "unknown"}


def _number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fresh(checked_at, max_age_days):
    try:
        checked = dt.date.fromisoformat(str(checked_at)[:10])
    except (TypeError, ValueError):
        return False
    return 0 <= (dt.date.today() - checked).days <= max_age_days


def _tier(item, checked_at, max_age_days, seller_max_age_days):
    source = str(item.get("source") or "").strip().lower()
    metrics = [_number(item.get(k)) for k in
               ("searches", "views", "orders", "revenue_rub", "avg_position")]
    evidence_date = item.get("checked_at") or checked_at
    if (source in SELLER_SOURCES and any(v is not None for v in metrics)
            and _fresh(evidence_date, seller_max_age_days)):
        return "A"
    if source in CURRENT_SITE_SOURCES and _fresh(evidence_date, max_age_days):
        return "B"
    if source:
        return "C"
    return "U"


def _sort_key(item):
    tier_order = {"A": 0, "B": 1, "C": 2, "U": 3}
    match_order = {"exact": 0, "partial": 1, "unknown": 2, "exclude": 3}
    return (
        tier_order.get(item["evidence_tier"], 9),
        match_order.get(item["product_match"], 9),
        -(_number(item.get("orders")) or 0),
        -(_number(item.get("views")) or 0),
        -(_number(item.get("searches")) or 0),
        item["query"],
    )


def _unique(values):
    seen = set()
    result = []
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _empty_plan(cfg, info):
    policy = cfg.get("keyword_policy", {})
    return {
        "generated_at": dt.date.today().isoformat(),
        "status": "no_keyword_research",
        "product_context": {
            "item_id": info.get("item_id"),
            "supplier_title": info.get("title"),
        },
        "evidence_legend": {
            "A": "Ozon Seller query metrics; quantitative but still requires product relevance",
            "B": "fresh Ozon autocomplete/category/search wording; current wording, not query volume",
            "C": "other or stale marketplace evidence; hypothesis only",
            "U": "source missing; do not use as a heat claim",
        },
        "policy": policy,
        "title_terms": {"core": [], "attribute": [], "scene": []},
        "description_terms": [],
        "excluded_terms": [],
        "queries": [],
        "research_needed": [
            "Export Ozon Seller 'Запросы моего товара' metrics when available",
            "Otherwise record dated Ozon autocomplete/category/search wording",
            "Mark each query exact, partial, exclude, or unknown for this SKU",
        ],
    }


def run(cfg, folder, info):
    """Read keyword_research.json, normalize evidence, and write keyword_plan.json."""
    policy = cfg.get("keyword_policy", {})
    max_age_days = int(policy.get("current_site_max_age_days", 45))
    seller_max_age_days = int(policy.get("seller_metrics_max_age_days", 90))
    research_path = os.path.join(folder, "keyword_research.json")
    plan_path = os.path.join(folder, "keyword_plan.json")

    if not os.path.exists(research_path):
        plan = _empty_plan(cfg, info)
    else:
        with open(research_path, encoding="utf-8") as f:
            research = json.load(f)
        checked_at = research.get("checked_at")
        normalized = []
        for raw in research.get("queries", []):
            query = " ".join(str(raw.get("query") or "").split())
            if not query:
                continue
            item = dict(raw)
            item["query"] = query
            item["role"] = str(item.get("role") or "unknown").lower()
            item["product_match"] = str(item.get("product_match") or "unknown").lower()
            if item["role"] not in VALID_ROLES:
                item["role"] = "unknown"
            if item["product_match"] not in VALID_MATCHES:
                item["product_match"] = "unknown"
            item["evidence_tier"] = _tier(item, checked_at, max_age_days, seller_max_age_days)
            demand_metrics = [_number(item.get(k)) for k in
                              ("searches", "views", "orders", "revenue_rub")]
            item["positive_demand_signal"] = any((v or 0) > 0 for v in demand_metrics)
            item["title_eligible"] = (
                item["product_match"] == "exact"
                and item["role"] in {"core", "attribute", "scene"}
                and (
                    item["evidence_tier"] == "B"
                    or (item["evidence_tier"] == "A" and item["positive_demand_signal"])
                )
            )
            normalized.append(item)
        normalized.sort(key=_sort_key)

        limits = policy.get("title_term_limits", {"core": 2, "attribute": 2, "scene": 1})
        title_terms = {"core": [], "attribute": [], "scene": []}
        for role in title_terms:
            cap = int(limits.get(role, 0))
            title_terms[role] = _unique([
                x["query"] for x in normalized if x["title_eligible"] and x["role"] == role
            ])[:cap]
        description_terms = _unique([
            x["query"] for x in normalized
            if x["product_match"] in {"exact", "partial"}
            and x["evidence_tier"] in {"A", "B", "C"}
            and x["query"] not in sum(title_terms.values(), [])
        ])[: int(policy.get("description_term_limit", 6))]
        excluded = [
            {"query": x["query"], "reason": x.get("note") or x["product_match"]}
            for x in normalized if x["product_match"] == "exclude" or x["role"] == "negative"
        ]
        has_seller_metrics = any(x["evidence_tier"] == "A" for x in normalized)
        has_current_site_evidence = any(x["evidence_tier"] == "B" for x in normalized)
        if has_seller_metrics:
            status = "seller_metrics_available"
        elif has_current_site_evidence:
            status = "current_site_evidence_only"
        else:
            status = "hypothesis_only"
        plan = {
            "generated_at": dt.date.today().isoformat(),
            "status": status,
            "checked_at": checked_at,
            "category": research.get("category"),
            "product_context": {
                "item_id": info.get("item_id"),
                "supplier_title": info.get("title"),
            },
            "evidence_legend": _empty_plan(cfg, info)["evidence_legend"],
            "policy": policy,
            "sources": research.get("sources", []),
            "title_terms": title_terms,
            "description_terms": description_terms,
            "excluded_terms": excluded,
            "queries": normalized,
        }

    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    status = plan.get("status")
    print(f"  ✓ 关键词计划 → keyword_plan.json（{status}）")
    return plan
