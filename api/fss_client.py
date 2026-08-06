"""
금융감독원(FSS) 금융상품통합비교공시 API 클라이언트

API 발급: https://finlife.fss.or.kr → 회원가입 → API 활용 신청 (무료, 당일~익일)
공식 문서: https://finlife.fss.or.kr/finlifeapi/

지원 범위:
  - 연금저축보험 상품 조회 (공식 지원)
  - 보험사 목록 조회 (공식 지원)
  - 일반 보장성보험(종신/실손/암/덴탈)은 별도 API 미공개
    → 로컬 데이터 + FSS 공시 정보 혼합 전략 사용

Fallback 전략:
  FSS_API_KEY 없음 또는 API 실패 → 로컬 캐시(fss_cache.json) → 정적 products.py
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

_PROJECT_ROOT = Path(__file__).parent.parent
_CACHE_FILE = _PROJECT_ROOT / "data" / "fss_cache.json"
_CACHE_TTL_HOURS = 24  # 캐시 유효 시간

FSS_BASE_URL = "https://finlife.fss.or.kr/finlifeapi"
INSURANCE_GRP_NO = "050000"  # 보험 금융권 코드


class FSSApiError(Exception):
    pass


class FSSApiClient:
    """
    FSS 금융상품통합비교공시 API 클라이언트.
    API 키가 없거나 호출 실패 시 자동으로 로컬 데이터로 fallback.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("FSS_API_KEY")
        self._session = None

    def _get_session(self):
        if not HAS_REQUESTS:
            raise ImportError("requests 패키지가 필요합니다: pip install requests")
        if self._session is None:
            import requests as req
            self._session = req.Session()
            self._session.headers.update({"Accept": "application/json"})
        return self._session

    @property
    def is_available(self) -> bool:
        """API 키가 설정되어 있고 requests 패키지가 있으면 True"""
        return bool(self.api_key and HAS_REQUESTS)

    # ─────────────────────────────────────
    # 공식 API 호출
    # ─────────────────────────────────────

    def _get(self, endpoint: str, params: dict) -> dict:
        """FSS API GET 요청 (공통)"""
        if not self.api_key:
            raise FSSApiError("FSS_API_KEY가 설정되지 않았습니다.")
        params["auth"] = self.api_key
        url = f"{FSS_BASE_URL}/{endpoint}"
        session = self._get_session()
        try:
            resp = session.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            # FSS API 응답 구조: {"result": {"baseList": [...], "optionList": [...]}}
            if "result" not in data:
                raise FSSApiError(f"예상치 못한 응답 형식: {list(data.keys())}")
            return data["result"]
        except Exception as exc:
            raise FSSApiError(f"FSS API 호출 실패: {exc}") from exc

    def get_insurance_companies(self) -> list[dict]:
        """보험사 목록 조회"""
        result = self._get(
            "companySearch.json",
            {"topFinGrpNo": INSURANCE_GRP_NO, "pageNo": 1},
        )
        return result.get("baseList", [])

    def get_annuity_products(self, page: int = 1) -> list[dict]:
        """연금저축보험 상품 목록 조회 — FSS API 엔드포인트 폐지로 빈 리스트 반환"""
        # annuityProductsSearch.json 엔드포인트가 2025년 이후 404로 폐지됨
        # FSS 측에서 연금저축보험 공시 API를 별도 제공하지 않으므로 빈 리스트 반환
        return []

    def get_annuity_product_options(self, fin_prdt_cd: str) -> list[dict]:
        """연금저축보험 상품 세부 옵션 조회"""
        result = self._get(
            "annuityProductsInqire.json",
            {"topFinGrpNo": INSURANCE_GRP_NO, "finPrdtCd": fin_prdt_cd, "pageNo": 1},
        )
        return result.get("optionList", [])

    # ─────────────────────────────────────
    # 데이터 정규화 (FSS → 로컬 포맷)
    # ─────────────────────────────────────

    def normalize_annuity_product(self, fss_product: dict) -> dict:
        """FSS 연금저축보험 응답 → 로컬 products.py 딕셔너리 형식 변환"""
        return {
            "id": f"fss_{fss_product.get('fin_prdt_cd', 'unknown')}",
            "name": fss_product.get("fin_prdt_nm", "FSS 연금보험"),
            "type": "생명보험",
            "subtype": "연금저축보험",
            "company": fss_product.get("kor_co_nm", ""),
            "monthly_premium": {},  # FSS API에 보험료 정보 없음
            "coverage_amount": None,
            "coverage": {
                "연금": fss_product.get("mtrt_int", "상품별 상이"),
            },
            "age_range": {"min": 18, "max": 65},
            "payment_period": fss_product.get("spcl_cnd", "-"),
            "features": _parse_join_way(fss_product.get("join_way", "")),
            "pros": ["FSS 공시 상품", "세제 혜택 (소득공제)"],
            "cons": ["55세 이후 연금 수령", "중도 해지 시 불이익"],
            "rating": None,
            "review_count": 0,
            "tags": ["연금", "저축", "세제혜택", "FSS공시"],
            "_source": "fss_api",
            "_fetched_at": datetime.now().isoformat(),
        }

    # ─────────────────────────────────────
    # 캐시 관리
    # ─────────────────────────────────────

    def _load_cache(self) -> dict | None:
        """캐시 파일 로드 (TTL 초과 시 None 반환)"""
        if not _CACHE_FILE.exists():
            return None
        try:
            with open(_CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)
            fetched_at = datetime.fromisoformat(cache.get("fetched_at", "2000-01-01"))
            if datetime.now() - fetched_at > timedelta(hours=_CACHE_TTL_HOURS):
                return None
            return cache
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def _save_cache(self, products: list[dict]) -> None:
        """API 응답을 캐시 파일에 저장"""
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"fetched_at": datetime.now().isoformat(), "products": products},
                f,
                ensure_ascii=False,
                indent=2,
            )

    # ─────────────────────────────────────
    # 통합 조회 (API → 캐시 → 로컬 fallback)
    # ─────────────────────────────────────

    def fetch_with_fallback(self, product_type: str = "annuity") -> dict:
        """
        API 호출 → 캐시 → 로컬 데이터 순서로 fallback하며 상품 정보 반환.

        Returns:
            {
                "source": "fss_api" | "cache" | "local",
                "products": [정규화된 상품 딕셔너리, ...],
                "fetched_at": ISO datetime string,
                "message": 설명 메시지,
            }
        """
        # 1. FSS API — 연금저축보험 엔드포인트 폐지(2025~), 캐시/로컬로 바로 이동
        # (get_annuity_products는 빈 리스트를 반환하므로 API 호출 자체를 건너뜀)

        # 2. 캐시 시도
        cache = self._load_cache()
        if cache:
            return {
                "source": "cache",
                "products": cache["products"],
                "fetched_at": cache["fetched_at"],
                "message": f"캐시에서 {len(cache['products'])}개 상품을 로드했습니다.",
            }

        # 3. 로컬 정적 데이터 fallback
        from data.products import get_all_products
        local = get_all_products()
        return {
            "source": "local",
            "products": local,
            "fetched_at": datetime.now().isoformat(),
            "message": (
                "FSS API 키가 없거나 연결 실패. 로컬 데이터를 사용합니다.\n"
                "API 키 발급: https://finlife.fss.or.kr"
            ),
        }


def _parse_join_way(join_way_str: str) -> list[str]:
    """FSS join_way 필드 파싱 ('인터넷,전화,방문' → 리스트)"""
    if not join_way_str:
        return []
    return [way.strip() for way in join_way_str.replace("·", ",").split(",") if way.strip()]
