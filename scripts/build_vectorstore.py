"""
벡터 DB 최초 구축 스크립트

사용법:
    python scripts/build_vectorstore.py [--reset]

  --reset: 기존 DB를 초기화하고 재구축 (지식 문서 추가/수정 후 사용)
"""

import sys
import os
import argparse

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def build(reset: bool = False):
    print("=" * 55)
    print("  보험 지식 벡터 DB 구축")
    print("=" * 55)

    # 1. 지식 문서 로드
    from data.knowledge import get_all_knowledge
    docs = get_all_knowledge()
    print(f"\n📄 로드된 지식 문서: {len(docs)}개")
    for d in docs:
        print(f"   [{d['id']}] {d['title']} ({d['category']})")

    # 2. 임베딩 모델 로드
    print(f"\n📦 임베딩 모델 로딩 중...")
    from rag.embeddings import KoreanEmbedder
    embedder = KoreanEmbedder.get_instance()
    print(f"   차원: {embedder.dimension}d")

    # 3. 벡터 스토어 초기화
    from rag.vectorstore import InsuranceVectorStore, CHROMA_PERSIST_DIR
    vs = InsuranceVectorStore.get_instance()

    if reset and vs.is_populated():
        print(f"\n🗑️  기존 DB 초기화...")
        vs.reset()

    if vs.is_populated() and not reset:
        print(f"\n✅ 이미 구축된 DB가 있습니다 ({vs.count()}개 문서)")
        print("   재구축하려면: python scripts/build_vectorstore.py --reset")
        return

    # 4. 임베딩 및 저장
    print(f"\n🔨 임베딩 생성 및 ChromaDB 저장 중...")
    count = vs.add_documents(docs)

    print(f"\n✅ 완료!")
    print(f"   저장 경로: {CHROMA_PERSIST_DIR}")
    print(f"   저장된 문서: {count}개")

    # 5. 검색 테스트
    print("\n🔍 검색 테스트:")
    test_queries = [
        "임플란트 치과보험 대기기간",
        "암보험 면역항암치료 보장",
        "실손보험 3세대 4세대 차이",
    ]
    for q in test_queries:
        results = vs.search(q, top_k=1)
        if results:
            print(f"   [{q}] → {results[0]['title']} (score: {results[0]['score']:.3f})")
        else:
            print(f"   [{q}] → 결과 없음")

    print("\n✨ 벡터 DB 구축 완료. main.py를 실행하세요.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="보험 지식 벡터 DB 구축")
    parser.add_argument("--reset", action="store_true", help="기존 DB 초기화 후 재구축")
    args = parser.parse_args()
    build(reset=args.reset)
