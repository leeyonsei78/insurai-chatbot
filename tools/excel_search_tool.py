"""
보험다모아 엑셀 데이터 검색 도구
로드된 XLS 파일에서 보험사·상품·보험료를 조회합니다.
"""

from __future__ import annotations
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def search_insmarket_products(
    insurance_type: str = None,
    company: str = None,
    gender: str = None,
    age_group: str = None,
    keyword: str = None,
    budget_max: int = None,
    top_n: int = 10,
) -> str:
    """
    보험다모아 공시 엑셀 데이터에서 보험 상품을 검색합니다.

    Args:
        insurance_type: '실손의료보험', '간병·치매보험', '치아보험', '종신보험', '질병보험', '상해보험', '저축보험'
        company: 보험사 이름 일부 (예: '롯데', '한화', 'DB')
        gender: '남' 또는 '여'
        age_group: '30대', '40대', '50대', '60대'
        keyword: 상품명·보장명·비고 내 키워드 검색
        budget_max: BFC 분위 기반 월 최대 보험료 (원). 예: 120000 (12만원)
        top_n: 반환할 최대 상품 수 (기본 10)
    """
    try:
        from data.excel_loader import load_all_excel
        products = load_all_excel()
    except Exception as e:
        return json.dumps({"error": f"엑셀 데이터 로드 실패: {e}"}, ensure_ascii=False)

    if not products:
        return json.dumps({"results": [], "message": "엑셀 데이터가 없습니다."}, ensure_ascii=False)

    filtered = products

    # 보험 유형 필터
    if insurance_type:
        filtered = [p for p in filtered if insurance_type in p.get("insurance_type", "")]

    # 보험사 필터
    if company:
        filtered = [p for p in filtered if company.lower() in p.get("company", "").lower()]

    # 연령대 필터 (파일 컨텍스트 기준)
    # file_context에 age_group이 없는 상품 = 연령 무관 공통 상품 → 필터 통과
    if age_group:
        filtered = [
            p for p in filtered
            if not p.get("file_context", {}).get("age_group")   # 연령 컨텍스트 없음 → 통과
            or p.get("file_context", {}).get("age_group") == age_group
            or age_group in p.get("source_file", "")
        ]

    # 성별 필터
    if gender:
        def _matches_gender(p: dict) -> bool:
            fc = p.get("file_context", {})
            if "gender" in fc:
                return fc["gender"] == gender
            # 실손은 남/여 모두 있음
            if p.get("premium_male") and p.get("premium_female"):
                return True
            return True
        filtered = [p for p in filtered if _matches_gender(p)]

    # 키워드 필터
    if keyword:
        kw = keyword.lower()
        def _kw_match(p: dict) -> bool:
            text = " ".join([
                p.get("company", ""),
                p.get("product_name", ""),
                p.get("notes", ""),
                p.get("insurance_type", ""),
                " ".join(c[0] for c in p.get("coverages", [])),
            ]).lower()
            return kw in text
        filtered = [p for p in filtered if _kw_match(p)]

    # BFC 분위 기반 예산 상한 필터
    if budget_max is not None:
        def _in_budget(p: dict) -> bool:
            pm = p.get("premium_monthly")
            if pm is None:
                pm = p.get("premium_female" if gender == "여" else "premium_male")
            if pm is None:
                pm = p.get("premium_male") or p.get("premium_female")
            if pm is None:
                return True   # 보험료 정보 없으면 통과 (표시는 됨)
            return pm <= budget_max
        filtered = [p for p in filtered if _in_budget(p)]

    # 보험료 기준 정렬
    def _sort_key(p: dict) -> int:
        pm = p.get("premium_monthly")
        if pm:
            return pm
        if gender == "여" and p.get("premium_female"):
            return p["premium_female"]
        if p.get("premium_male"):
            return p["premium_male"]
        if p.get("premium_female"):
            return p["premium_female"]
        return 999999

    filtered.sort(key=_sort_key)

    # 동일 상품명 중복 제거 (여러 연령대 파일에 같은 상품 존재)
    seen_names: set = set()
    deduped = []
    for p in filtered:
        key = (p.get("company", ""), p.get("product_name", ""))
        if key not in seen_names:
            seen_names.add(key)
            deduped.append(p)
    filtered = deduped

    # 결과 포맷
    results = []
    for p in filtered[:top_n]:
        # 보험료 표기 — 없으면 이 상품 제외
        if p.get("premium_monthly"):
            prem_str = f"{p['premium_monthly']:,}원/월"
        elif p.get("premium_male") or p.get("premium_female"):
            parts = []
            if p.get("premium_male"):
                parts.append(f"남 {p['premium_male']:,}원")
            if p.get("premium_female"):
                parts.append(f"여 {p['premium_female']:,}원")
            prem_str = " / ".join(parts) + "/월"
        else:
            continue  # 실제 보험료 없는 상품은 결과에서 제외

        # 상품명: 없으면 첫 번째 보장항목 이름에서 추출
        product_name = p.get("product_name", "").strip()
        coverages_raw = p.get("coverages", [])
        if not product_name and coverages_raw:
            product_name = coverages_raw[0][0]
            coverages_raw = coverages_raw[1:]  # 상품명으로 쓴 항목은 보장 목록에서 제외

        # 주요 보장 요약 (상위 3개)
        covs = [f"{c[0]}: {c[1]}" for c in coverages_raw[:3] if c[0]]

        results.append({
            "company": p["company"],
            "product_name": product_name,
            "insurance_type": p["insurance_type"],
            "premium": prem_str,
            "age_range": p.get("age_range", ""),
            "file_context": p.get("file_context", {}),
            "coverages": covs,
            "notes": p.get("notes", "")[:100],
            "source": p.get("source_file", ""),
        })

    return json.dumps(
        {
            "results": results,
            "total_found": len(filtered),
            "data_source": "보험다모아 공시 엑셀 (2026-06)",
        },
        ensure_ascii=False,
        indent=2,
    )
