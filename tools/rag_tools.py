"""
RAG 기반 보험 지식 검색 도구 (ChromaDB 벡터 검색)

첫 실행 시:
  1. jhgan/ko-sroberta-multitask 모델 다운로드 (~443MB, 최초 1회)
  2. 지식 베이스 문서 임베딩 후 ChromaDB에 저장
  이후 실행 시: 저장된 DB 즉시 로드 (수 초)

기존 키워드 검색 대비 개선:
  - "임플란트 어떻게 해야 해요?" → 덴탈보험 문서 검색 (의미 기반)
  - "항암 비용이 걱정돼요" → 암보험 문서 검색 (유사 의미)
  - "보험료 아끼는 방법" → 절약 팁 문서 검색
"""

from __future__ import annotations

import json
import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_vectorstore = None
_vectorstore_ready = False
_vectorstore_loading = False
_vectorstore_lock = threading.Lock()


def _init_vectorstore_background():
    """백그라운드 스레드에서 벡터스토어 초기화 (모델 다운로드 포함)"""
    global _vectorstore, _vectorstore_ready, _vectorstore_loading
    try:
        from rag.vectorstore import InsuranceVectorStore
        from data.knowledge import get_all_knowledge

        vs = InsuranceVectorStore.get_instance()

        if not vs.is_populated():
            print("  [rag] Building vector DB for the first time...", flush=True)
            docs = get_all_knowledge()
            count = vs.add_documents(docs)
            print(f"  [rag] {count} documents indexed", flush=True)

        with _vectorstore_lock:
            _vectorstore = vs
            _vectorstore_ready = True
        print("  [rag] Vector store ready", flush=True)

    except Exception as e:
        print(f"  [rag] Vector RAG unavailable ({e}), falling back to keyword search", flush=True)
        with _vectorstore_lock:
            _vectorstore = None
            _vectorstore_ready = True
    finally:
        _vectorstore_loading = False


def _get_vectorstore():
    """벡터 스토어 반환. 초기화 중이면 None 반환 → 키워드 검색 fallback 사용."""
    global _vectorstore_ready, _vectorstore_loading

    with _vectorstore_lock:
        if _vectorstore_ready:
            return _vectorstore

        if not _vectorstore_loading:
            _vectorstore_loading = True
            t = threading.Thread(target=_init_vectorstore_background, daemon=True)
            t.start()
            print("  [rag] Vector store initializing in background...", flush=True)

    # 초기화 중 → 즉시 None 반환하여 키워드 검색으로 fallback
    return None


def retrieve_insurance_knowledge(query: str, top_k: int = 2) -> str:
    """
    사용자 질문과 의미적으로 유사한 보험 지식 문서를 검색하여 반환.

    ChromaDB + sentence-transformers 기반 시맨틱 검색.
    라이브러리 미설치 시 자동으로 키워드 검색으로 fallback.

    Args:
        query: 검색할 질문 또는 키워드
        top_k: 반환할 문서 수 (기본 2개)
    """
    if not query or not query.strip():
        return json.dumps({"error": "검색어를 입력해주세요."}, ensure_ascii=False)

    top_k = min(top_k, 3)

    vs = _get_vectorstore()

    # ─ 벡터 검색 ─
    if vs is not None:
        results = vs.search(query, top_k=top_k)
        if results:
            formatted = [
                {
                    "title": r["title"],
                    "category": r["category"],
                    "content": r["content"],
                    "tags": r["tags"],
                    "relevance_score": r["score"],
                }
                for r in results
            ]
            return json.dumps(
                {
                    "results": formatted,
                    "total_found": len(formatted),
                    "search_method": "vector",
                },
                ensure_ascii=False,
                indent=2,
            )

    # ─ Fallback: 키워드 검색 ─
    from data.knowledge import search_knowledge
    results = search_knowledge(query, top_k=top_k)

    if not results:
        return json.dumps(
            {"results": [], "message": "관련 정보를 찾지 못했습니다."},
            ensure_ascii=False,
        )

    formatted = [
        {
            "title": doc["title"],
            "category": doc["category"],
            "content": doc["content"].strip(),
            "tags": doc["tags"],
            "relevance_score": None,
        }
        for doc in results
    ]
    return json.dumps(
        {
            "results": formatted,
            "total_found": len(formatted),
            "search_method": "keyword_fallback",
        },
        ensure_ascii=False,
        indent=2,
    )


def rebuild_vectorstore() -> str:
    """
    벡터 DB 강제 재구축 (지식 베이스 업데이트 후 호출).
    Returns: 결과 메시지
    """
    global _vectorstore, _vectorstore_ready
    try:
        from rag.vectorstore import InsuranceVectorStore
        from data.knowledge import get_all_knowledge

        vs = InsuranceVectorStore.get_instance()
        vs.reset()

        docs = get_all_knowledge()
        count = vs.add_documents(docs)

        _vectorstore = vs
        _vectorstore_ready = True
        return f"✅ 벡터 DB 재구축 완료: {count}개 문서 임베딩"
    except Exception as e:
        return f"❌ 재구축 실패: {e}"


def list_knowledge_categories() -> str:
    """지식 베이스의 모든 카테고리 목록 반환"""
    from data.knowledge import get_all_knowledge
    docs = get_all_knowledge()
    categories: dict[str, list[str]] = {}
    for doc in docs:
        cat = doc["category"]
        categories.setdefault(cat, []).append(doc["title"])
    return json.dumps({"categories": categories}, ensure_ascii=False, indent=2)
