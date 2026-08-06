"""
보험 상담 AI 챗봇 v2 - 메인 실행 파일

신규 기능:
  - ChromaDB + sentence-transformers 벡터 RAG
  - FSS(금융감독원) API 실시간 상품 조회
  - 암보험 + 덴탈(치과)보험 추가

사용법:
    python main.py

환경 변수 (.env):
    ANTHROPIC_API_KEY  : Anthropic API 키 (필수)
    FSS_API_KEY        : 금융감독원 API 키 (선택, 없으면 로컬 데이터 사용)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agents.orchestrator import InsuranceChatbot

BANNER = """
╔══════════════════════════════════════════════════════════════╗
║         🏥 보험 상담 AI 어시스턴트 v2                         ║
║                                                              ║
║  생명보험 · 실손의료보험 · 암보험 · 덴탈보험 전문 상담          ║
║  GPT-4o · ChromaDB RAG · FSS API║
╠══════════════════════════════════════════════════════════════╣
║  /reset  대화 초기화  /help  도움말  /quit  종료              ║
╚══════════════════════════════════════════════════════════════╝
"""

HELP_TEXT = """
📋 상담 가능 내용:
  생명보험   종신/정기/변액/CI보험 비교 및 추천
  실손보험   3세대 vs 4세대 실손, 청구 방법
  암보험    진단비/항암치료비, 비갱신 vs 갱신 비교
  덴탈보험   임플란트/크라운/스케일링 보장 안내

💡 예시 질문:
  "40대 직장인 보험 포트폴리오 추천해줘"
  "임플란트 치과보험 어디가 좋아?"
  "암보험 면역항암치료 보장되는 상품 있어?"
  "실손보험 3세대 4세대 뭐가 달라?"
  "월 20만원 예산으로 보험 구성 도와줘"
  "35세 여성 종신보험 보험료 얼마야?"
"""


def check_dependencies():
    """필수 패키지 설치 여부 확인"""
    missing = []
    optional_missing = []

    try:
        import openai
    except ImportError:
        missing.append("openai")

    try:
        import chromadb
    except ImportError:
        optional_missing.append("chromadb (벡터 RAG 비활성화)")

    try:
        import sentence_transformers
    except ImportError:
        optional_missing.append("sentence-transformers (벡터 RAG 비활성화)")

    if missing:
        print(f"❌ 필수 패키지 미설치: {', '.join(missing)}")
        print("   pip install -r requirements.txt")
        sys.exit(1)

    if optional_missing:
        print("⚠️  선택 패키지 미설치 (키워드 검색으로 대체):")
        for m in optional_missing:
            print(f"   - {m}")
        print("   설치 권장: pip install chromadb sentence-transformers")
        print()


def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("   .env 파일을 생성하거나 환경변수를 설정하세요.")
        sys.exit(1)

    check_dependencies()

    fss_key = os.getenv("FSS_API_KEY")
    fss_status = "활성화" if fss_key else "미설정 (로컬 데이터 사용)"

    print(BANNER)
    print(f"  FSS API: {fss_status}")
    print()
    print("안녕하세요! 보험 상담 AI 어시스턴트입니다. 무엇이든 물어보세요! 😊\n")

    chatbot = InsuranceChatbot()

    while True:
        try:
            user_input = input("👤 고객: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n감사합니다. 건강하세요! 👋")
            break

        if not user_input:
            continue

        cmd = user_input.lower()
        if cmd in ("/quit", "/exit", "quit", "exit", "종료"):
            print("감사합니다. 건강하세요! 👋")
            break
        elif cmd == "/reset":
            chatbot.reset()
            continue
        elif cmd == "/help":
            print(HELP_TEXT)
            continue
        elif cmd == "/rebuild":
            print("벡터 DB 재구축 중...")
            from tools.rag_tools import rebuild_vectorstore
            print(rebuild_vectorstore())
            continue
        elif cmd == "/refresh":
            print("보험다모아 실시간 데이터 갱신 중... (수 분 소요)")
            try:
                from api.insmarket_scraper import InsmarketScraper
                scraper = InsmarketScraper()
                result = scraper.refresh()
                total = sum(len(v) for v in result.values())
                print(f"✅ 갱신 완료: 총 {total}개 상품")
            except Exception as e:
                print(f"❌ 갱신 실패: {e}")
            continue

        print("\n🤖 상담사: ", end="", flush=True)
        try:
            response = chatbot.chat(user_input)
            print(response)
        except Exception as e:
            print(f"\n❌ 오류: {e}")

        print()


if __name__ == "__main__":
    main()
