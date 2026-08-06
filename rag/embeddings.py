"""
한국어 sentence-transformers 임베딩 모듈

모델: jhgan/ko-sroberta-multitask
- KorSTS 벤치마크 최상위 한국어 문장 임베딩 모델
- 최초 실행 시 HuggingFace에서 자동 다운로드 (~443MB, ~/.cache/huggingface에 캐싱)
- 경량 대안: bongsoo/kpf-sbert-128d-v1 (~120MB)
"""

from __future__ import annotations

import os
from typing import ClassVar

# 텔레메트리 비활성화
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL_NAME = os.getenv("EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")


class KoreanEmbedder:
    """
    싱글톤 임베딩 모델 래퍼.
    SentenceTransformer 모델을 한 번만 로딩하여 재사용합니다.
    """

    _instance: ClassVar[KoreanEmbedder | None] = None
    _model = None

    def __new__(cls) -> KoreanEmbedder:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            print(f"  [load] Embedding model: {MODEL_NAME}", flush=True)
            self._model = SentenceTransformer(MODEL_NAME)
            print("  [load] Embedding model ready", flush=True)
        except ImportError as e:
            raise ImportError(
                "sentence-transformers가 설치되지 않았습니다.\n"
                "pip install sentence-transformers 실행 후 재시도하세요."
            ) from e

    @classmethod
    def get_instance(cls) -> KoreanEmbedder:
        inst = cls()
        inst._load()
        return inst

    def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 리스트를 임베딩 벡터 리스트로 변환 (코사인 유사도용 정규화)"""
        self._load()
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()

    def embed_single(self, text: str) -> list[float]:
        """단일 텍스트를 임베딩 벡터로 변환"""
        return self.embed([text])[0]

    @property
    def dimension(self) -> int:
        """임베딩 차원 수"""
        self._load()
        return self._model.get_sentence_embedding_dimension()
