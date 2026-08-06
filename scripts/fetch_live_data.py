"""
보험다모아 실시간 데이터 갱신 스크립트

━━━━ 일반 실행 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    python scripts/fetch_live_data.py

━━━━ VPN 자동 IP 로테이션 (mbuster 차단 우회) ━━━━━━━━━━━━━
    # NordVPN / ExpressVPN 설치된 경우 (자동 감지)
    python scripts/fetch_live_data.py --vpn

    # 프록시 목록 지정 (쉼표 구분)
    python scripts/fetch_live_data.py --vpn --proxy socks5://user:pass@host:port

    # Windows 내장 VPN 사용 (네트워크 설정에 VPN 연결 이름)
    python scripts/fetch_live_data.py --vpn --vpn-type rasdial --vpn-name "MyVPN"

    # 최대 재시도 횟수 지정 (기본 3)
    python scripts/fetch_live_data.py --vpn --max-retries 5

━━━━ CDP 모드 (실제 Chrome 연결) ━━━━━━━━━━━━━━━━━━━━━━━━━
  1단계: Chrome을 원격 디버깅 모드로 실행 (한 번만)
      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^
          --remote-debugging-port=9222 ^
          --user-data-dir="%TEMP%\\ChromeDebug"

  2단계: 열린 Chrome에서 보험다모아 접속
      http://203.229.168.79

  3단계: 이 스크립트를 별도 터미널에서 실행
      python scripts/fetch_live_data.py --cdp

━━━━ CDP + VPN 조합 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    python scripts/fetch_live_data.py --cdp --vpn

━━━━ 기타 옵션 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    --debug    data/debug/ 에 HTML 저장 (선택자 디버깅)
    --visible  브라우저 창 표시 (CDP 없이)
    --type     특정 보험 종류만 수집 (예: --type 종신보험)
    --cdp-url  CDP 엔드포인트 URL (기본: http://localhost:9222)

━━━━ Windows 작업 스케줄러 자동화 ━━━━━━━━━━━━━━━━━━━━━━━━━
    - 프로그램: python.exe
    - 인수: C:\\path\\to\\insurance_agent\\scripts\\fetch_live_data.py --cdp --vpn
    - 시작 위치: C:\\path\\to\\insurance_agent
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()


def main():
    parser = argparse.ArgumentParser(description="보험다모아 실시간 데이터 수집")
    parser.add_argument("--debug", action="store_true", help="HTML 파일 저장 (선택자 디버깅)")
    parser.add_argument("--visible", action="store_true", help="브라우저 창 표시 (비헤드리스)")
    parser.add_argument("--cdp", action="store_true", help="실행 중인 Chrome에 CDP로 연결")
    parser.add_argument("--cdp-url", default="http://localhost:9222", help="CDP 엔드포인트 URL")
    parser.add_argument("--type",
                        choices=["종신보험", "정기보험", "실손의료보험", "암보험", "치아보험"],
                        help="특정 보험 유형만 수집")
    # VPN / 프록시 옵션
    parser.add_argument("--vpn", action="store_true",
                        help="mbuster 차단 시 VPN/프록시로 IP 변경 후 재시도")
    parser.add_argument("--vpn-type",
                        choices=["auto", "nordvpn", "expressvpn", "rasdial", "proxy"],
                        default="auto",
                        help="VPN 종류 (기본: auto 자동 감지)")
    parser.add_argument("--vpn-name", default=None,
                        help="Windows 내장 VPN 연결 이름 (--vpn-type rasdial 사용 시)")
    parser.add_argument("--proxy", default=None,
                        help="프록시 URL, 쉼표로 여러 개 지정 (예: socks5://user:pass@host:1080)")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="IP 변경 후 최대 재시도 횟수 (기본: 3)")
    parser.add_argument("--real-chrome", action="store_true",
                        help="사용자 실제 Chrome 프로필 사용 (기존 쿠키/세션 유지, Chrome 종료 후 자동 재시작)")
    args = parser.parse_args()

    try:
        from api.insmarket_scraper import InsmarketScraper, INSURANCE_URLS
    except ImportError as e:
        print(f"[ERROR] 임포트 오류: {e}")
        sys.exit(1)

    if not InsmarketScraper.is_playwright_available():
        print("[ERROR] Playwright가 설치되어 있지 않습니다.")
        print()
        print("설치 방법:")
        print("  pip install playwright")
        print("  playwright install chromium")
        sys.exit(1)

    # ── VPN 로테이터 초기화 ─────────────────────────────────────────
    vpn_rotator = None
    if args.vpn:
        try:
            from api.vpn_rotator import VpnRotator
            proxy_list = [p.strip() for p in args.proxy.split(",")] if args.proxy else []
            vpn_rotator = VpnRotator(
                vpn_type=args.vpn_type,
                connection_name=args.vpn_name,
                proxy_list=proxy_list,
            )
        except ImportError as e:
            print(f"[ERROR] VPN 모듈 로드 실패: {e}")
            sys.exit(1)

    # ── 실행 모드 안내 ─────────────────────────────────────────────
    if args.cdp:
        print("=" * 55)
        print("  보험다모아 실시간 데이터 수집 (CDP 모드)")
        print("=" * 55)
        print(f"  Chrome CDP 연결: {args.cdp_url}")
        if vpn_rotator:
            print(f"  VPN 로테이션: 활성 (최대 {args.max_retries}회 재시도)")
        print()

        # Chrome 자동 실행 (미실행 시)
        try:
            from api.cdp_helper import launch_chrome, _kill_chrome_on_port
            cdp_port = int(args.cdp_url.rstrip("/").rsplit(":", 1)[-1])

            if args.real_chrome:
                # 실제 프로필 모드: 기존 Chrome 종료 후 실제 프로필로 재시작
                print("  [Chrome] 실제 프로필 모드 - 기존 Chrome 종료 중...", flush=True)
                import subprocess, time
                subprocess.run(["taskkill", "/f", "/im", "chrome.exe"],
                               capture_output=True, timeout=10)
                time.sleep(5)  # 프로필 잠금 해제 대기

            ok = launch_chrome(
                url="http://203.229.168.79",
                cdp_port=cdp_port,
                real_profile=getattr(args, "real_chrome", False),
            )
            if not ok:
                print("[ERROR] Chrome 자동 실행 실패.")
                print("  수동으로 실행하세요:")
                print('  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"')
                print(f'      --remote-debugging-port={cdp_port}')
                print(f'      --user-data-dir="%TEMP%\\ChromeDebug"')
                print(f'      --remote-allow-origins=*')
                sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Chrome 실행 오류: {e}")
            sys.exit(1)
        print()
    else:
        print("=" * 55)
        print("  보험다모아 실시간 데이터 수집")
        print("=" * 55)
        if vpn_rotator:
            print(f"  VPN 로테이션: 활성 (최대 {args.max_retries}회 재시도)")
        print()
        if not vpn_rotator:
            print("[안내] 봇 차단 시 --vpn 옵션 또는 --cdp 옵션 사용")
        print()

    # 특정 보험 유형만 수집
    if args.type:
        original = dict(INSURANCE_URLS)
        INSURANCE_URLS.clear()
        if args.type in original:
            INSURANCE_URLS[args.type] = original[args.type]

    scraper = InsmarketScraper(
        headless=not args.visible,
        debug=args.debug,
    )

    cdp_url = args.cdp_url if args.cdp else None

    try:
        result = scraper.refresh(
            cdp_url=cdp_url,
            vpn_rotator=vpn_rotator,
            max_retries=args.max_retries,
        )

        print()
        print("수집 결과:")
        total = 0
        for ins_type, products in result.items():
            count = len(products)
            total += count
            status = "OK" if count > 0 else "--"
            print(f"  [{status}] {ins_type:15s}: {count}개")
        print(f"  {'합계':20s}: {total}개")
        print()

        if total == 0:
            print("[경고] 수집된 상품이 없습니다.")
            print()
            print("원인 및 해결 방법:")
            print("  1. 봇 차단(mbuster): --cdp 옵션으로 실제 Chrome 사용")
            print("  2. 선택자 불일치: --debug 옵션으로 HTML 저장 후 확인")
            print("  3. 사이트 접속 오류: 인터넷 연결 확인")
        else:
            print("OK  data/insmarket_cache.json 저장 완료")
            print("    다음 챗봇 실행 시 자동으로 사용됩니다.")

        if args.debug:
            print()
            print("[DEBUG] HTML 파일: data/debug/ 디렉터리 확인")

    except ConnectionRefusedError:
        print()
        print("[ERROR] Chrome CDP에 연결할 수 없습니다.")
        print()
        print("Chrome을 다음 명령으로 실행하세요:")
        print('  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"')
        print('      --remote-debugging-port=9222')
        print('      --user-data-dir="%TEMP%\\ChromeDebug"')
        sys.exit(1)

    except RuntimeError as e:
        if "mbuster" in str(e) or "최대 재시도" in str(e):
            print()
            print("=" * 55)
            print("[IP 차단] 보험다모아 mbuster 봇 차단 — 모든 IP 소진")
            print("=" * 55)
            print()
            print("해결 방법:")
            print("  1. --vpn 옵션으로 VPN 자동 IP 변경 활성화")
            print("       python scripts/fetch_live_data.py --vpn")
            print("  2. 프록시 목록 지정")
            print("       python scripts/fetch_live_data.py --vpn --proxy socks5://user:pass@host:port")
            print("  3. 수 시간 후 동일 IP에서 재시도 (자동 해제)")
            print("  4. 다른 PC(다른 IP)에서 --cdp 모드로 실행")
            print()
            print("임시 조치: 로컬 정적 데이터로 챗봇은 정상 동작합니다.")
            sys.exit(1)
        print(f"[ERROR] 수집 실패: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"[ERROR] 수집 실패: {e}")
        if "playwright" in str(e).lower() or "chromium" in str(e).lower():
            print()
            print("Chromium 브라우저 설치가 필요합니다:")
            print("  playwright install chromium")
        sys.exit(1)


if __name__ == "__main__":
    main()
