# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

2026 금융 AI Challenge 출품작 — GPT-4o 기반 보험 상담 AI 챗봇.  
생명보험·실손의료보험·암보험·덴탈보험을 대상으로 상품 검색/비교/견적, RAG 지식 검색, 건강위험 예측, 신용점수 연계 추천 기능을 제공한다.

## 실행 방법

```bash
# 웹 인터페이스 (Flask, 권장)
python web_app.py          # http://localhost:5000
run.bat                    # Windows 원클릭 실행 (포트 충돌 자동 처리)

# CLI 인터페이스
python main.py
```

### 필수 환경변수 (`.env`)

```
OPENAI_API_KEY=...         # 필수 (GPT-4o 오케스트레이터)
FSS_API_KEY=...            # 선택 (없으면 로컬 데이터 사용)
```

`.env.example`을 복사해 `.env`를 만든다.

### 의존성 설치

```bash
pip install -r requirements.txt

# Windows CPU 환경에서 PyTorch가 실패할 경우
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Playwright (보험다모아 실시간 스크래핑, 선택)
pip install playwright && playwright install chromium
```

## 지식베이스 & 벡터DB 관리

```bash
# 보험다모아 엑셀 → data/knowledge.py 반영
python scripts/build_knowledge_from_excel.py          # 미리보기
python scripts/build_knowledge_from_excel.py --apply  # 반영
python scripts/build_knowledge_from_excel.py --rebuild # 반영 + ChromaDB 재구축

# ChromaDB 단독 재구축
python scripts/build_vectorstore.py

# 보험다모아 실시간 데이터 갱신
python scripts/fetch_live_data.py

# 실행 중 CLI에서
/rebuild   # ChromaDB 재구축
/refresh   # 보험다모아 스크래핑 갱신
```

벡터 DB는 프로젝트 루트의 `chroma_db/` 디렉터리에 저장된다.

## 건강위험 모델 재학습

```bash
pip install scikit-learn pandas numpy matplotlib
python health_risk/train_risk_model.py
# 학습 완료 시 data/risk_model_params.json 자동 갱신
```

실데이터 사용 시 `train_risk_model.py` 내 합성 데이터 생성 코드를 실제 CSV 로드로 교체 (health_risk/README.md 참고).

## 데모 테스트 시나리오

심사자 검증 순서: ① 배포 URL 접속 → Live/Mock 모드 배지 확인 → ② 아래 순서대로 입력 → ③ 건강위험도·신용점수 별도 테스트

| 시나리오 | 입력값 | 예상 결과 |
|---------|-------|---------|
| 암보험 추천 | `45세 남성, 월 10만원 예산 암보험 추천해줘` | 암보험 3종 추천 카드 (월 보험료·보장 비교표) |
| 실손보험 비교 | `4세대 실손보험 뭐가 좋아? 비갱신형으로 찾아줘` | 4세대 실손 상품 목록 + 갱신/비갱신 차이 설명 |
| 치과보험 | `임플란트 되는 치아보험 어디가 제일 싸?` | 치과보험 보험료 순위표 + 임플란트 대기기간 안내 |
| 보험료 문의 | `35세 여성 종신보험 보험료 얼마야?` | 종신보험 월 보험료 나이·성별 맞춤 계산 결과 |
| 건강위험도 | 흡연: 예 / BMI: 28 / 혈압: 135/85 입력 | 위험지수(0~100) + 등급 + 권장 보험 유형 (암보험 우선 권장) |
| 포트폴리오 설계 | `40대 직장인, 월 30만원 보험 포트폴리오 짜줘` | 생명+실손+암 통합 포트폴리오 추천 리포트 출력 |

## 알려진 제한사항 (MVP)

- ChromaDB 최초 실행 시 임베딩 모델(`jhgan/ko-sroberta`) 다운로드 필요 (~443MB, 약 2~5분)
- FSS API는 연금저축보험 조회만 지원 — 종신/실손/암/치과는 로컬 정적 데이터 사용
- 보험다모아 엑셀 11종 포함 — 갱신 시 재다운로드 후 `scripts/build_knowledge_from_excel.py --rebuild` 재실행 필요
- 세션 종료 시 대화 초기화 (상담 이력 미저장)
- 권장 브라우저: Chrome 120+, Edge 120+, Firefox 115+

## 아키텍처

### 요청 흐름

```
사용자 입력
  │
  ▼
web_app.py (Flask)  또는  main.py (CLI)
  │
  ├─ Live Mode: agents/orchestrator.py → InsuranceChatbot.chat()
  │     │  GPT-4o tool-calling 루프 (최대 10회 반복)
  │     └─ tools/* 각 도구 실행 → 결과 병합 → 최종 응답
  │
  └─ Mock Mode (크레딧 없을 때): web_app.py 내 mock_response() 직접 처리
```

### 핵심 모듈

| 경로 | 역할 |
|------|------|
| `agents/orchestrator.py` | GPT-4o 기반 오케스트레이터. TOOLS 목록 정의 + execute_tool() 디스패치 + 대화 이력 관리 |
| `tools/product_tools.py` | 상품 검색/비교/견적. 데이터 우선순위: 보험다모아 실시간 → FSS API → 로컬 정적 데이터 |
| `tools/rag_tools.py` | ChromaDB 벡터 검색 래퍼 (`retrieve_insurance_knowledge`) |
| `tools/health_risk_tool.py` | 건강검진 수치 → 당뇨·대사 위험 예측 (로지스틱 모델) → 보험 추천 |
| `tools/health_credit_tool.py` | 건강신용점수 기반 대출·보험 연계 심사 (혁신금융존 시나리오) |
| `tools/cancer_risk_tool.py` | 암 위험도 예측 도구 |
| `tools/cancer_survivor_tool.py` | 암 경험자 특약 적용 시뮬레이터 (저위험 할인, PACS 심사 등) |
| `tools/credit_score_tool.py` | 신용점수 → 보험 추천 등급 조정 |
| `tools/excel_search_tool.py` | `data/insmarket_excel_cache.json` 기반 상품 검색 |
| `rag/vectorstore.py` | ChromaDB PersistentClient 싱글톤 래퍼 |
| `rag/embeddings.py` | `sentence-transformers` 한국어 임베더 싱글톤 |
| `api/insmarket_scraper.py` | 보험다모아 Playwright 스크래퍼 (24h 캐시: `data/insmarket_excel_cache.json`) |
| `api/fss_client.py` | 금융감독원 finlife API 클라이언트 (연금저축보험) |
| `api/cdp_helper.py` | CDP(Chrome DevTools Protocol) Playwright 헬퍼 |
| `api/vpn_rotator.py` | 스크래핑용 VPN 로테이터 |
| `data/products.py` | 정적 보험 상품 데이터 (폴백) |
| `data/knowledge.py` | RAG용 보험 지식 베이스 문서 |
| `data/excel_loader.py` | 루트의 `.xls` 파일(보험다모아 엑셀) 로더 |
| `data/credit_model.py` | 신용점수 등급별 추천 로직 |
| `data/innovation_zone_ref.py` | 혁신금융존 참조 데이터 |
| `health_risk/train_risk_model.py` | 건강위험 로지스틱 모델 학습 스크립트 |
| `scripts/build_knowledge_from_excel.py` | 엑셀 → knowledge.py + ChromaDB 업데이트 |

### 데이터 소스 우선순위 (상품 조회)

1. **보험다모아 실시간** — Playwright로 스크래핑, 24h 캐시 (`data/insmarket_excel_cache.json`)
2. **FSS API** — 연금저축보험 전용, `FSS_API_KEY` 필요
3. **로컬 정적 데이터** — `data/products.py`, `data/dental_products.py`

### 도구 등록 방식

`agents/orchestrator.py`의 `TOOLS` 리스트(OpenAI function-calling 형식)에 도구를 선언하고, `execute_tool()` 함수에 분기를 추가하면 GPT-4o가 자동으로 호출한다. 새 도구 추가 시 두 곳 모두 수정 필요.

### Mock Mode

`web_app.py`는 `OPENAI_API_KEY`가 없거나 크레딧이 소진되면 오케스트레이터 없이 `mock_response()` → `detect_intent()` 규칙 기반 응답으로 대체 동작한다. 의도 분류는 키워드 매칭이며 세션별 `MockContext`로 상태를 유지한다.
