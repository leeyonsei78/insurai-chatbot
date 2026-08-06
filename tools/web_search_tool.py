"""실시간 웹 검색 도구 — DuckDuckGo 기반, API 키 불필요"""

from __future__ import annotations
import json


def search_web(query: str, max_results: int = 5) -> str:
    """
    DuckDuckGo로 실시간 웹 검색을 수행하고 결과를 반환합니다.

    Args:
        query: 검색 쿼리
        max_results: 반환할 결과 수 (기본 5, 최대 10)
    """
    max_results = min(max_results, 10)
    try:
        from ddgs import DDGS
    except ImportError:
        return json.dumps(
            {"error": "웹 검색 패키지 미설치. pip install ddgs"},
            ensure_ascii=False,
        )

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, region="kr-kr", max_results=max_results))

        if not raw:
            return json.dumps(
                {"results": [], "message": "검색 결과가 없습니다.", "query": query},
                ensure_ascii=False,
            )

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in raw
        ]
        return json.dumps({"results": results, "query": query, "count": len(results)}, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"error": f"검색 오류: {str(e)}", "query": query}, ensure_ascii=False)
