"""
보험 상품 검색 및 비교 도구

데이터 소스 우선순위:
  1. FSS API (금융감독원 공시, FSS_API_KEY 설정 시)
  2. 로컬 캐시 (data/fss_cache.json)
  3. 로컬 정적 데이터 (data/products.py)
"""

from __future__ import annotations

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.products import get_all_products, get_product_by_id


def _get_products_with_api_fallback() -> list[dict]:
    """
    데이터 소스 우선순위:
      1. 보험다모아 실시간 (Playwright, 캐시 24h) — 종신/정기/실손/암/치아
      2. FSS API (연금저축보험 전용)
      3. 로컬 정적 데이터 (data/products.py)

    insmarket 데이터와 로컬 데이터를 병합:
      - insmarket에 있는 상품 → insmarket 우선
      - insmarket에 없는 상품 → 로컬 유지
    """
    local = get_all_products()

    # 1. 보험다모아 실시간 데이터
    insmarket_products: list[dict] = []
    try:
        from api.insmarket_scraper import InsmarketScraper
        scraper = InsmarketScraper()
        cached = scraper.fetch_all(background_refresh=True)
        if cached:
            # 모든 유형의 상품을 평탄화
            for products in cached.values():
                insmarket_products.extend(products)
    except Exception:
        pass

    # 2. FSS API (연금저축보험)
    fss_products: list[dict] = []
    try:
        from api.fss_client import FSSApiClient
        client = FSSApiClient()
        if client.is_available:
            result = client.fetch_with_fallback("annuity")
            fss_products = result.get("products", [])
    except Exception:
        pass

    # 병합: insmarket + FSS + 로컬(중복 제외)
    if not insmarket_products and not fss_products:
        return local

    live_ids = {p["id"] for p in insmarket_products}
    fss_ids = {p["id"] for p in fss_products}
    local_only = [p for p in local if p["id"] not in live_ids and p["id"] not in fss_ids]
    fss_only = [p for p in fss_products if p["id"] not in live_ids]

    return insmarket_products + fss_only + local_only


def search_products(
    insurance_type: str = None,
    budget_min: int = 0,
    budget_max: int = 999999,
    age: int = None,
    needs: list = None,
    subtype: str = None,
) -> str:
    """
    조건에 맞는 보험 상품 검색

    Args:
        insurance_type: '생명보험', '실손의료보험', '덴탈보험' (None이면 전체)
        budget_min: 월 최소 보험료 (원)
        budget_max: 월 최대 보험료 (원)
        age: 가입자 나이
        needs: 필요 태그 목록 (예: ['임플란트', '비갱신'])
        subtype: 세부 유형 (예: '종신보험', '4세대실손', '치과보험', '암보험')
    """
    products = _get_products_with_api_fallback()

    if insurance_type:
        products = [p for p in products if p["type"] == insurance_type]

    if subtype:
        products = [p for p in products if subtype in p.get("subtype", "")]

    if age is not None:
        products = [
            p for p in products
            if p["age_range"]["min"] <= age <= p["age_range"]["max"]
        ]

    def get_reference_premium(product: dict, req_age: int = None, req_gender: str = None) -> int:
        premiums = product.get("monthly_premium", {})
        if not premiums:
            return 0
        # 나이/성별이 있으면 가장 가까운 구간 키를 먼저 시도
        if req_age is not None and req_gender:
            if req_age < 35:
                grp = "30세"
            elif req_age < 45:
                grp = "40세"
            elif req_age < 55:
                grp = "50세"
            else:
                grp = "60세"
            for key in [f"{grp}_{req_gender}", f"{grp}_남", f"{grp}_여"]:
                if key in premiums:
                    return premiums[key]
        # fallback: 임의 첫 번째 값
        for key in ["30세_남", "40세_남", "30세_여", "40세_여"]:
            if key in premiums:
                return premiums[key]
        return list(premiums.values())[0]

    if budget_min > 0 or budget_max < 999999:
        products = [
            p for p in products
            if budget_min <= get_reference_premium(p, age, None) <= budget_max
        ]

    if needs:
        scored = []
        for p in products:
            tags = p.get("tags", [])
            score = sum(1 for need in needs if any(need in tag for tag in tags))
            scored.append((score, p))
        scored.sort(key=lambda x: x[0], reverse=True)
        products = [p for _, p in scored]

    if not products:
        return json.dumps(
            {"results": [], "message": "조건에 맞는 상품이 없습니다."},
            ensure_ascii=False,
        )

    results = []
    for p in products[:5]:
        ref_premium = get_reference_premium(p)
        results.append({
            "id": p["id"],
            "name": p["name"],
            "company": p["company"],
            "type": p["type"],
            "subtype": p.get("subtype", ""),
            "monthly_premium_reference": ref_premium,
            "coverage_amount": p.get("coverage_amount"),
            "key_coverage": list(p.get("coverage", {}).keys())[:4],
            "key_features": p.get("features", [])[:3],
            "pros": p.get("pros", [])[:2],
            "cons": p.get("cons", [])[:2],
            "rating": p.get("rating"),
            "tags": p.get("tags", []),
            "data_source": p.get("_source", "local"),
        })

    return json.dumps(
        {"results": results, "total_found": len(products)},
        ensure_ascii=False,
        indent=2,
    )


def compare_products(product_ids: list) -> str:
    """
    특정 상품들을 상세 비교

    Args:
        product_ids: 비교할 상품 ID 목록 (최대 4개)
    """
    if not product_ids:
        return json.dumps({"error": "비교할 상품 ID를 입력해주세요."}, ensure_ascii=False)

    product_ids = product_ids[:4]
    products = [get_product_by_id(pid) for pid in product_ids]
    products = [p for p in products if p is not None]

    if not products:
        return json.dumps({"error": "유효한 상품을 찾을 수 없습니다."}, ensure_ascii=False)

    comparison = {
        "products": [],
        "comparison_table": {
            "항목": [], "보험료(30세남)": [], "보장금액": [],
            "가입연령": [], "갱신여부": [], "평점": [],
        },
    }

    for p in products:
        premiums = p.get("monthly_premium", {})
        ref_premium = premiums.get("30세_남", list(premiums.values())[0] if premiums else 0)

        product_detail = {
            "id": p["id"],
            "name": p["name"],
            "company": p["company"],
            "type": p["type"],
            "subtype": p.get("subtype", ""),
            "monthly_premiums": premiums,
            "coverage": p.get("coverage", {}),
            "deductible": p.get("deductible", {}),
            "waiting_period": p.get("waiting_period", {}),
            "features": p.get("features", []),
            "pros": p.get("pros", []),
            "cons": p.get("cons", []),
            "age_range": p["age_range"],
            "payment_period": p.get("payment_period") or p.get("renewal_period", "-"),
            "rating": p.get("rating"),
            "review_count": p.get("review_count", 0),
        }
        comparison["products"].append(product_detail)

        renewal = p.get("renewal_period", p.get("payment_period", "-"))
        comparison["comparison_table"]["항목"].append(p["name"])
        comparison["comparison_table"]["보험료(30세남)"].append(f"{ref_premium:,}원")
        cov_amount = p.get("coverage_amount")
        comparison["comparison_table"]["보장금액"].append(
            f"{cov_amount // 10000:,}만원" if cov_amount else "항목별 상이"
        )
        comparison["comparison_table"]["가입연령"].append(
            f"{p['age_range']['min']}~{p['age_range']['max']}세"
        )
        comparison["comparison_table"]["갱신여부"].append(renewal)
        comparison["comparison_table"]["평점"].append(
            f"{p['rating']}/5.0" if p.get("rating") else "-"
        )

    return json.dumps(comparison, ensure_ascii=False, indent=2)


def get_premium_estimate(product_id: str, age: int, gender: str) -> str:
    """
    특정 상품의 보험료 견적 조회

    Args:
        product_id: 상품 ID
        age: 나이
        gender: '남' or '여'
    """
    product = get_product_by_id(product_id)
    if not product:
        return json.dumps(
            {"error": f"상품 ID '{product_id}'를 찾을 수 없습니다."},
            ensure_ascii=False,
        )

    premiums = product.get("monthly_premium", {})
    if age < 35:
        age_group = "30세"
    elif age < 45:
        age_group = "40세"
    elif age < 55:
        age_group = "50세"
    else:
        age_group = "60세"
    key = f"{age_group}_{gender}"

    note = None
    if key in premiums:
        premium = premiums[key]
    else:
        # 가장 가까운 키 찾기
        fallback_keys = [f"{g}_{gender}" for g in ["30세", "40세", "50세"]]
        premium = next((premiums[k] for k in fallback_keys if k in premiums), None)
        if premium is None:
            premium = list(premiums.values())[0] if premiums else 0
        note = "정확한 견적은 보험사 상담을 통해 확인하세요."

    return json.dumps(
        {
            "product_name": product["name"],
            "company": product["company"],
            "type": product["type"],
            "age": age,
            "gender": gender,
            "estimated_monthly_premium": premium,
            "premium_formatted": f"{premium:,}원/월",
            "annual_premium": f"{premium * 12:,}원/년",
            "note": note or "실제 보험료는 건강 상태, 직업 등에 따라 다를 수 있습니다.",
        },
        ensure_ascii=False,
        indent=2,
    )


def fetch_fss_realtime(product_type: str = "annuity") -> str:
    """
    FSS API에서 실시간 보험 상품 정보 조회

    Args:
        product_type: 'annuity' (연금저축보험 - FSS 공식 지원)
    """
    try:
        from api.fss_client import FSSApiClient
        client = FSSApiClient()
        result = client.fetch_with_fallback(product_type)
        return json.dumps(
            {
                "source": result["source"],
                "fetched_at": result["fetched_at"],
                "message": result["message"],
                "product_count": len(result["products"]),
                "sample_products": result["products"][:3],  # 샘플 3개만 반환
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        return json.dumps(
            {"error": str(e), "note": "FSS_API_KEY를 .env 파일에 설정하세요."},
            ensure_ascii=False,
        )
