"""
ChromaDB 벡터 스토어 모듈

- 보험 지식 베이스 문서를 벡터 DB에 저장/검색
- PersistentClient: 앱 재시작 후에도 데이터 유지
- 코사인 유사도 기반 시맨틱 검색
"""

from __future__ import annotations

import os

import chromadb
from chromadb.config import Settings

from rag.embeddings import KoreanEmbedder

# DB 저장 경로 (프로젝트 루트 기준 절대 경로)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_PERSIST_DIR = os.path.join(_PROJECT_ROOT, "chroma_db")
COLLECTION_NAME = "insurance_knowledge"


class InsuranceVectorStore:
    """ChromaDB 기반 보험 지식 벡터 스토어 (싱글톤)"""

    _instance: InsuranceVectorStore | None = None

    def __new__(cls) -> InsuranceVectorStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _init_db(self) -> None:
        if self._initialized:
            return
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._embedder = KoreanEmbedder.get_instance()
        self._initialized = True

    @classmethod
    def get_instance(cls) -> InsuranceVectorStore:
        inst = cls()
        inst._init_db()
        return inst

    # ─────────────────────────────────────
    # 문서 관리
    # ─────────────────────────────────────

    def add_documents(self, docs: list[dict]) -> int:
        """
        지식 베이스 문서를 임베딩하여 ChromaDB에 upsert.
        docs 구조: knowledge.py의 KNOWLEDGE_BASE와 동일

        Returns:
            추가/업데이트된 문서 수
        """
        self._init_db()
        if not docs:
            return 0

        ids = [doc["id"] for doc in docs]

        # 제목 + 내용 + 태그를 결합하여 임베딩 품질 향상
        texts = [
            f"{doc['title']}\n{doc['content'].strip()}\n{' '.join(doc.get('tags', []))}"
            for doc in docs
        ]

        embeddings = self._embedder.embed(texts)

        metadatas = [
            {
                "title": doc["title"],
                "category": doc["category"],
                "tags": ",".join(doc.get("tags", [])),
                "content": doc["content"].strip()[:2000],  # ChromaDB metadata size limit
            }
            for doc in docs
        ]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        return len(docs)

    def count(self) -> int:
        """저장된 문서 수"""
        self._init_db()
        return self._collection.count()

    def is_populated(self) -> bool:
        return self.count() > 0

    def reset(self) -> None:
        """컬렉션 초기화 (재구축 시 사용)"""
        self._init_db()
        self._client.delete_collection(COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    # ─────────────────────────────────────
    # 검색
    # ─────────────────────────────────────

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """
        시맨틱 검색 (코사인 유사도 기반)

        Returns:
            [{"title", "category", "content", "tags", "score"}, ...]
            score: 0~1 (1에 가까울수록 유사)
        """
        self._init_db()
        if self.count() == 0:
            return []

        query_embedding = self._embedder.embed_single(query)

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self.count()),
            include=["metadatas", "distances"],
        )

        docs = []
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for meta, dist in zip(metadatas, distances):
            # ChromaDB cosine distance: 0=동일, 2=정반대 → 유사도 = 1 - dist/2
            similarity = round(1.0 - dist / 2.0, 4)
            docs.append({
                "title": meta["title"],
                "category": meta["category"],
                "content": meta["content"],
                "tags": meta["tags"].split(",") if meta.get("tags") else [],
                "score": similarity,
            })

        return docs
