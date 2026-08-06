"""
보험다모아(e-insmarket.or.kr) 실시간 보험 상품 스크래퍼
생명보험협회 + 손해보험협회 공동 운영 사이트에서
종신/정기/실손/암/치아 보험 상품 정보를 수집.

설치 (최초 1회):
    pip install playwright
    playwright install chromium

지원 보험 유형 및 URL:
    종신보험  /wholeIns/wholeInsList.knia
    정기보험  /tempIns/tempInsList.knia
    실손보험  /mins/minsInsList.knia
    암보험    /cancerIns/cancerInsList.knia
    치아보험  /guaranteeIns/guaranteeInsList.knia?menuId=C013
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

_CACHE_FILE = Path(__file__).parent.parent / "data" / "insmarket_cache.json"
_CACHE_TTL_HOURS = 24

BASE_URL = "http://203.229.168.79"

# 수집 대상 보험 유형 → URL
INSURANCE_URLS: dict[str, str] = {
    "종신보험": f"{BASE_URL}/wholeIns/wholeInsList.knia",
    "정기보험": f"{BASE_URL}/tempIns/tempInsList.knia",
    "실손의료보험": f"{BASE_URL}/mins/minsInsList.knia?prdtSmlClsCd=G004",
    "암보험": f"{BASE_URL}/cancerIns/cancerInsList.knia",
    "치아보험": f"{BASE_URL}/guaranteeIns/guaranteeInsList.knia?menuId=C013",
}

# products.py 보험 type 매핑
_TYPE_MAP: dict[str, str] = {
    "종신보험": "생명보험",
    "정기보험": "생명보험",
    "실손의료보험": "실손의료보험",
    "암보험": "실손의료보험",
    "치아보험": "덴탈보험",
}

# 사전 수집할 나이/성별 조합
_PROFILES = [
    {"age": 30, "gender": "남", "birth": "19940101"},
    {"age": 40, "gender": "남", "birth": "19840101"},
    {"age": 50, "gender": "남", "birth": "19740101"},
    {"age": 30, "gender": "여", "birth": "19940101"},
    {"age": 40, "gender": "여", "birth": "19840101"},
    {"age": 50, "gender": "여", "birth": "19740101"},
]

# 나이만으로 조회 (성별 기본값=전체, 결과표에 남/여 컬럼이 함께 표시되는 유형)
_PROFILES_AGE_ONLY = [
    {"age": 30, "birth": "19940101"},
    {"age": 40, "birth": "19840101"},
    {"age": 50, "birth": "19740101"},
]

# 성별 선택 불필요 — 결과 테이블에 남/여 보험료가 별도 컬럼으로 표시됨
_GENDER_SKIP_TYPES: set[str] = {"실손의료보험"}

# 폼 입력 없음 — URL 접속만으로 결과 표시 (남자 40세 고정 기본값)
_NO_FORM_TYPES: set[str] = {"치아보험"}
_NO_FORM_DEFAULT_KEY = "40세_남"

# 백그라운드 갱신 실행 여부 추적 (중복 실행 방지)
_refresh_lock = threading.Lock()
_refreshing = False


class InsmarketScraper:
    """보험다모아 Playwright 스크래퍼"""

    def __init__(self, headless: bool = True, debug: bool = False):
        self.headless = headless
        self.debug = debug  # True 시 HTML을 data/debug/ 에 저장

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    @staticmethod
    def is_playwright_available() -> bool:
        try:
            import playwright  # noqa: F401
            return True
        except ImportError:
            return False

    def fetch_all(self, background_refresh: bool = False) -> dict[str, list[dict]] | None:
        """
        캐시가 신선하면 캐시 반환.
        캐시가 만료됐으면:
          - background_refresh=True: 로컬 데이터 반환 + 백그라운드에서 갱신 시작
          - background_refresh=False: 즉시 스크래핑 후 반환 (느림)
        Playwright 미설치 시 None 반환.
        """
        if not self.is_playwright_available():
            return None

        cache = self._load_cache()
        if cache:
            return cache["products"]

        if background_refresh:
            self._start_background_refresh()
            return None  # 호출측이 로컬 데이터로 fallback하도록

        return self.refresh()

    def refresh(
        self,
        cdp_url: str | None = None,
        vpn_rotator=None,
        max_retries: int = 3,
    ) -> dict[str, list[dict]]:
        """
        강제 스크래핑 후 캐시에 저장. {보험유형: [상품, ...]} 반환.
        cdp_url 지정 시 이미 실행 중인 Chrome에 연결 (봇 차단 우회).
        vpn_rotator 지정 시 mbuster 차단 감지 → IP 변경 → 재시도.
        """
        import time

        for attempt in range(max_retries):
            try:
                proxy = vpn_rotator.get_current_proxy() if vpn_rotator else None
                print(
                    f"  [insmarket] 보험다모아 스크래핑 시작"
                    + (f" (시도 {attempt + 1}/{max_retries})" if attempt > 0 else "")
                    + "...",
                    flush=True,
                )
                raw = self._scrape_all(cdp_url=cdp_url, proxy=proxy)
                normalized: dict[str, list[dict]] = {}
                for ins_type, profile_data in raw.items():
                    normalized[ins_type] = _normalize(ins_type, profile_data)
                self._save_cache(normalized)
                total = sum(len(v) for v in normalized.values())
                print(f"  [insmarket] 완료 - 총 {total}개 상품 수집", flush=True)
                return normalized

            except RuntimeError as e:
                if "mbuster" not in str(e):
                    raise
                if vpn_rotator is None or attempt >= max_retries - 1:
                    raise
                print(
                    f"\n[VPN] mbuster 차단 감지 → IP 변경 시도 ({attempt + 1}/{max_retries - 1})",
                    flush=True,
                )
                ok = vpn_rotator.rotate()
                if not ok:
                    raise
                print("[VPN] 새 IP 안정화 대기 (10초)...", flush=True)
                time.sleep(10)

        raise RuntimeError("최대 재시도 횟수 초과")

    # ──────────────────────────────────────────
    # Background refresh
    # ──────────────────────────────────────────

    def _start_background_refresh(self) -> None:
        global _refreshing
        with _refresh_lock:
            if _refreshing:
                return
            _refreshing = True

        def _worker():
            global _refreshing
            try:
                self.refresh()
            except Exception as e:
                print(f"  [insmarket] 백그라운드 갱신 실패: {e}", flush=True)
            finally:
                with _refresh_lock:
                    _refreshing = False

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        print("  [insmarket] 백그라운드 데이터 갱신 시작 (다음 요청부터 적용)", flush=True)

    # ──────────────────────────────────────────
    # Scraping core
    # ──────────────────────────────────────────

    def _scrape_all(
        self,
        cdp_url: str | None = None,
        proxy: dict | None = None,
    ) -> dict[str, dict[str, list[dict]]]:
        """
        모든 보험 유형을 모든 프로필로 스크래핑.
        cdp_url 지정 시 순수 CDP WebSocket 방식 사용 (Playwright JS 주입 없음 → mbuster 우회).
        proxy: {'server': 'socks5://...', ...} (비 CDP 모드 전용)
        """
        if cdp_url:
            return self._scrape_all_raw_cdp(cdp_url)

        # ── 기본 모드: Playwright Chromium ───────────────────────────────
        from playwright.sync_api import sync_playwright

        results: dict[str, dict[str, list[dict]]] = {}

        with sync_playwright() as pw:
            if False:  # placeholder — CDP 분기는 위에서 처리
                pass
            else:
                # ── 기본 모드: Playwright Chromium 실행 ──────────────────
                browser = pw.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                ctx_kwargs: dict = {
                    "user_agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "locale": "ko-KR",
                    "viewport": {"width": 1280, "height": 800},
                }
                if proxy:
                    ctx_kwargs["proxy"] = proxy
                    print(f"  [insmarket] 프록시 사용: {proxy.get('server')}", flush=True)
                ctx = browser.new_context(**ctx_kwargs)

                # stealth 패치 (navigator.webdriver 숨김 등)
                try:
                    from playwright_stealth import stealth_sync
                    page = ctx.new_page()
                    stealth_sync(page)
                except ImportError:
                    page = ctx.new_page()

                # 메인 페이지 먼저 방문하여 세션/쿠키 확립
                try:
                    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20_000)
                    page.wait_for_timeout(2_000)
                except Exception:
                    pass

            for ins_type, url in INSURANCE_URLS.items():
                print(f"  [insmarket] {ins_type} 수집 중...", flush=True)
                profile_data: dict[str, list[dict]] = {}

                # ── 폼 없음 (치아보험 등: 남자 40세 고정 기본값으로 결과 표시) ──
                if ins_type in _NO_FORM_TYPES:
                    try:
                        items = self._scrape_no_form(page, url, ins_type)
                        profile_data[_NO_FORM_DEFAULT_KEY] = items
                        print(f"    {_NO_FORM_DEFAULT_KEY}: {len(items)}개", flush=True)
                    except RuntimeError as e:
                        if "mbuster" in str(e):
                            print(f"    [차단] {e}", flush=True)
                            results[ins_type] = profile_data
                            browser.close()
                            raise
                        print(f"    실패 ({e})", flush=True)
                        profile_data[_NO_FORM_DEFAULT_KEY] = []
                    except Exception as e:
                        print(f"    실패 ({e})", flush=True)
                        profile_data[_NO_FORM_DEFAULT_KEY] = []
                    results[ins_type] = profile_data
                    continue

                skip_gender = ins_type in _GENDER_SKIP_TYPES
                profiles = _PROFILES_AGE_ONLY if skip_gender else _PROFILES

                for profile in profiles:
                    key = f"{profile['age']}세_전체" if skip_gender else f"{profile['age']}세_{profile['gender']}"
                    try:
                        items = self._scrape_one(page, url, profile, ins_type, skip_gender=skip_gender)
                        profile_data[key] = items
                        print(f"    {key}: {len(items)}개", flush=True)
                    except RuntimeError as e:
                        if "mbuster" in str(e):
                            print(f"    [차단] {e}", flush=True)
                            results[ins_type] = profile_data
                            browser.close()
                            raise
                        print(f"    {key}: 실패 ({e})", flush=True)
                        profile_data[key] = []
                    except Exception as e:
                        print(f"    {key}: 실패 ({e})", flush=True)
                        profile_data[key] = []

                results[ins_type] = profile_data

            browser.close()

        return results

    def _scrape_all_raw_cdp(self, cdp_url: str) -> dict[str, dict[str, list[dict]]]:
        """
        Playwright 없이 순수 CDP WebSocket으로 스크래핑.
        Playwright의 JS 바인딩 주입이 없으므로 mbuster 감지 회피.
        """
        import random
        from api.cdp_helper import CdpHelper

        helper = CdpHelper(cdp_url)
        tabs = helper.get_tabs()
        print(f"  [insmarket] Chrome 탭 목록:", flush=True)
        for t in tabs:
            print(f"    [{t.get('type','?')}] {t.get('url','')[:80]}", flush=True)

        tab = helper.find_tab("e-insmarket.or.kr") or helper.find_tab("203.229.168.79")
        if not tab:
            # 탭 없으면 메인 페이지가 있는 탭 사용
            tab = next((t for t in tabs if t.get("type") == "page"), None)
        if not tab:
            raise RuntimeError("Chrome에서 열린 탭을 찾을 수 없습니다.")

        ws_url = tab["webSocketDebuggerUrl"]
        print(f"  [insmarket] CDP 직접 연결: {tab['url'][:70]}", flush=True)

        results: dict[str, dict[str, list[dict]]] = {}

        with CdpHelper(cdp_url) as cdp:
            cdp.connect(ws_url)

            # 현재 탭이 차단 페이지 또는 비관련 페이지면 메인으로 이동
            current_url = tab["url"]
            need_main = (
                ("e-insmarket.or.kr" not in current_url and "203.229.168.79" not in current_url)
                or "mbuster" in current_url.lower()
                or "/js/" in current_url
            )
            if need_main:
                print(f"  [insmarket] 메인 페이지로 이동 (현재: {current_url[:60]})...", flush=True)
                cdp.navigate_js(BASE_URL, wait=5.0)
                html = cdp.get_html()
                if "서비스접속이 차단되었습니다" in html:
                    raise RuntimeError(
                        "mbuster 차단 감지 - IP가 봇 차단 목록에 등록되었습니다. "
                        "VPN 또는 다른 네트워크에서 시도하거나 몇 시간 후 재시도하세요."
                    )
                print(f"  [insmarket] 메인 페이지 정상 로드", flush=True)
            else:
                # 이미 사이트에 있어도 메인 페이지 방문으로 세션/쿠키 확립
                print(f"  [insmarket] 세션 초기화 (메인 페이지 방문)...", flush=True)
                cdp.navigate_js(BASE_URL, wait=4.0)

            for ins_type, url in INSURANCE_URLS.items():
                print(f"  [insmarket] {ins_type} 수집 중...", flush=True)
                profile_data: dict[str, list[dict]] = {}

                # ── 폼 없음 (치아보험 등: 남자 40세 고정 기본값) ──
                if ins_type in _NO_FORM_TYPES:
                    try:
                        cdp.navigate_js(url, wait=4.0)
                        html = cdp.get_html()
                        if "서비스접속이 차단되었습니다" in html or "mbuster" in html.lower():
                            raise RuntimeError(
                                "mbuster 차단 감지 - IP가 봇 차단 목록에 등록되었습니다. "
                                "VPN 또는 다른 네트워크에서 시도하거나 몇 시간 후 재시도하세요."
                            )
                        if self.debug:
                            debug_dir = Path(__file__).parent.parent / "data" / "debug"
                            debug_dir.mkdir(parents=True, exist_ok=True)
                            (debug_dir / f"{ins_type}_기본.html").write_text(html, encoding="utf-8")
                        items = _extract_from_html(html, ins_type)
                        profile_data[_NO_FORM_DEFAULT_KEY] = items
                        print(f"    {_NO_FORM_DEFAULT_KEY}: {len(items)}개", flush=True)
                    except RuntimeError as e:
                        if "mbuster" in str(e):
                            print(f"    [차단] {e}", flush=True)
                            results[ins_type] = profile_data
                            raise
                        print(f"    실패 ({e})", flush=True)
                        profile_data[_NO_FORM_DEFAULT_KEY] = []
                    except Exception as e:
                        print(f"    실패 ({e})", flush=True)
                        profile_data[_NO_FORM_DEFAULT_KEY] = []
                    results[ins_type] = profile_data
                    continue

                skip_gender = ins_type in _GENDER_SKIP_TYPES
                profiles = _PROFILES_AGE_ONLY if skip_gender else _PROFILES

                for i, profile in enumerate(profiles):
                    key = f"{profile['age']}세_전체" if skip_gender else f"{profile['age']}세_{profile['gender']}"
                    try:
                        # JS 방식 이동으로 CDP Page.navigate 감지 우회
                        if i == 0:
                            cdp.navigate_js(url, wait=3.5)
                        else:
                            cdp.navigate_js(url, wait=3.0)

                        html = cdp.get_html()
                        if "서비스접속이 차단되었습니다" in html or "mbuster" in html.lower():
                            raise RuntimeError(
                                "mbuster 차단 감지 - IP가 봇 차단 목록에 등록되었습니다. "
                                "VPN 또는 다른 네트워크에서 시도하거나 몇 시간 후 재시도하세요."
                            )

                        # 폼 입력
                        time.sleep(random.uniform(1.0, 2.0))
                        if not skip_gender:
                            cdp.fill_gender(profile["gender"])
                            time.sleep(random.uniform(0.4, 0.8))
                        cdp.fill_birth(profile["birth"])
                        time.sleep(random.uniform(0.4, 0.8))
                        cdp.click_search()

                        # 결과 대기
                        cdp.wait_for_results(timeout=12.0)

                        # HTML 추출
                        html = cdp.get_html()
                        if self.debug:
                            debug_dir = Path(__file__).parent.parent / "data" / "debug"
                            debug_dir.mkdir(parents=True, exist_ok=True)
                            fname = debug_dir / f"{ins_type}_{profile['age']}세_{profile.get('gender', '전체')}.html"
                            fname.write_text(html, encoding="utf-8")

                        items = _extract_from_html(html, ins_type)
                        profile_data[key] = items
                        print(f"    {key}: {len(items)}개", flush=True)

                    except RuntimeError as e:
                        if "mbuster" in str(e):
                            print(f"    [차단] {e}", flush=True)
                            results[ins_type] = profile_data
                            raise
                        print(f"    {key}: 실패 ({e})", flush=True)
                        profile_data[key] = []
                    except Exception as e:
                        print(f"    {key}: 실패 ({e})", flush=True)
                        profile_data[key] = []

                results[ins_type] = profile_data

        return results

    def _scrape_no_form(self, page, url: str, ins_type: str) -> list[dict]:
        """폼 없이 URL 접속만으로 결과가 표시되는 보험 유형 (치아보험 등)."""
        import time
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        content = page.content()
        if "서비스접속이 차단되었습니다" in content or "mbuster" in content:
            raise RuntimeError(
                "mbuster 차단 감지 - IP가 봇 차단 목록에 등록되었습니다. "
                "VPN 또는 다른 네트워크에서 시도하거나 몇 시간 후 재시도하세요."
            )
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass
        time.sleep(1.5)
        if self.debug:
            debug_dir = Path(__file__).parent.parent / "data" / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            (debug_dir / f"{ins_type}_기본.html").write_text(page.content(), encoding="utf-8")
        return _extract(page, ins_type)

    def _scrape_one(self, page, url: str, profile: dict, ins_type: str, skip_gender: bool = False, js_nav: bool = False) -> list[dict]:
        import random, time

        # 이미 목표 URL에 있으면 네비게이션 스킵 (감지 우회 핵심)
        from urllib.parse import urlparse as _up
        def _path_eq(u1, u2):
            p1, p2 = _up(u1.split("?")[0]), _up(u2.split("?")[0])
            return p1.netloc == p2.netloc and p1.path.rstrip("/") == p2.path.rstrip("/")
        already_there = _path_eq(url, page.url)

        if not already_there:
            if js_nav:
                # CDP 모드: JavaScript로 이동 (Playwright goto 감지 우회)
                page.evaluate(f"window.location.href = '{url}'")
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=30_000)
                except Exception:
                    pass
                time.sleep(random.uniform(1.5, 3.0))
            else:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        else:
            print(f"    (현재 탭 재사용: {page.url[:60]})", flush=True)
            time.sleep(random.uniform(0.5, 1.0))

        # mbuster 차단 감지
        content = page.content()
        if "서비스접속이 차단되었습니다" in content or "mbuster" in content:
            raise RuntimeError(
                "mbuster 차단 감지 - IP가 봇 차단 목록에 등록되었습니다. "
                "VPN 또는 다른 네트워크에서 시도하거나 몇 시간 후 재시도하세요."
            )

        # 인간처럼 보이도록 랜덤 딜레이
        time.sleep(random.uniform(2.0, 4.0))

        if not skip_gender:
            _fill_gender(page, profile["gender"])
            time.sleep(random.uniform(0.5, 1.2))
        _fill_birth(page, profile["birth"])
        time.sleep(random.uniform(0.5, 1.2))
        _click_search(page)

        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:
            pass
        time.sleep(random.uniform(2.0, 3.5))

        if self.debug:
            debug_dir = Path(__file__).parent.parent / "data" / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)
            fname = debug_dir / f"{ins_type}_{profile['age']}세_{profile['gender']}.html"
            fname.write_text(page.content(), encoding="utf-8")

        return _extract(page, ins_type)

    # ──────────────────────────────────────────
    # Cache
    # ──────────────────────────────────────────

    def _load_cache(self) -> dict | None:
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

    def _save_cache(self, products: dict) -> None:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"fetched_at": datetime.now().isoformat(), "products": products},
                f,
                ensure_ascii=False,
                indent=2,
            )


# ──────────────────────────────────────────────────
# Form interaction helpers
# ──────────────────────────────────────────────────

def _fill_gender(page, gender: str) -> None:
    """성별 선택 — 라디오버튼 → 체크박스 → 레이블 순으로 시도.

    사이트별 폼 유형:
      실손보험: 체크박스(전체/남/여), 기본값=전체 → skip_gender로 건너뜀
      암보험:   체크박스(남 ✅ / 여 □), 전체 없음 → 명시적 체크/해제 필요
      종신/정기: 라디오버튼 추정
    """
    male_vals = ["M", "m", "1", "male", "01", "남", "남성", "MAN", "man"]
    female_vals = ["F", "f", "2", "female", "02", "여", "여성", "WOMAN", "woman"]
    target_vals = male_vals if gender == "남" else female_vals
    other_vals = female_vals if gender == "남" else male_vals
    field_names = ["gender", "sex", "sexCd", "genderCd", "sxds", "sexType"]

    # ── 1. 라디오 버튼 ──────────────────────────────────
    for val in target_vals:
        for name in field_names:
            try:
                loc = page.locator(f"input[type='radio'][name='{name}'][value='{val}']")
                if loc.count() > 0:
                    loc.first.click()
                    return
            except Exception:
                pass

    # ── 2. 체크박스 (암보험 등: 남/여 개별 체크박스, 전체 없음) ──
    for val in target_vals:
        for name in field_names:
            try:
                loc = page.locator(f"input[type='checkbox'][name='{name}'][value='{val}']")
                if loc.count() > 0:
                    if not loc.first.is_checked():
                        loc.first.click()
                    # 반대 성별 체크박스 해제
                    for other_val in other_vals:
                        other_loc = page.locator(
                            f"input[type='checkbox'][name='{name}'][value='{other_val}']"
                        )
                        if other_loc.count() > 0 and other_loc.first.is_checked():
                            other_loc.first.click()
                    return
            except Exception:
                pass

    # ── 3. 레이블 텍스트 fallback ──────────────────────
    labels = ["남자", "남성", gender] if gender == "남" else ["여자", "여성", gender]
    for label in labels:
        try:
            loc = page.locator(f"label:has-text('{label}')")
            if loc.count() > 0:
                loc.first.click()
                return
        except Exception:
            pass


def _fill_birth(page, birth: str) -> None:
    """생년월일 입력 (YYYYMMDD) — 단일 필드 또는 년/월/일 분리 필드."""
    single_selectors = [
        "input[name='birthDate']",
        "input[name='birth']",
        "input[name='bdate']",
        "input[name='birthDt']",
        "input[name='brthDt']",
        "input[name='birthday']",
        "input[placeholder*='생년월일']",
        "input[placeholder*='YYYYMMDD']",
        "input[placeholder*='YYYY']",
        "input[id*='birth']",
        "input[id*='Birth']",
    ]
    for sel in single_selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.fill(birth)
                return
        except Exception:
            pass

    # 년/월/일 분리 필드
    try:
        for (name_pat, val) in [("year", birth[:4]), ("month", birth[4:6]), ("day", birth[6:])]:
            loc = page.locator(
                f"input[name*='{name_pat}'], input[id*='{name_pat}'], "
                f"input[placeholder='{name_pat.upper()}'], "
                f"select[name*='{name_pat}']"
            )
            if loc.count() > 0:
                tag = loc.first.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    loc.first.select_option(val)
                else:
                    loc.first.fill(val)
    except Exception:
        pass


def _click_search(page) -> None:
    """조회/비교 버튼 클릭."""
    texts = ["상품비교하기", "상품 비교하기", "비교하기", "조회하기", "조회", "검색", "확인"]
    for text in texts:
        try:
            loc = page.locator(
                f"button:has-text('{text}'), "
                f"a:has-text('{text}'), "
                f"input[type='button'][value*='{text}']"
            )
            if loc.count() > 0:
                loc.first.click()
                return
        except Exception:
            pass

    # submit fallback
    try:
        loc = page.locator("input[type='submit'], button[type='submit']")
        if loc.count() > 0:
            loc.first.click()
    except Exception:
        pass


# ──────────────────────────────────────────────────
# Data extraction
# ──────────────────────────────────────────────────

def _extract_from_html(html: str, ins_type: str) -> list[dict]:
    """HTML 문자열에서 상품 목록 추출 (BeautifulSoup 사용, raw CDP용)."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    products: list[dict] = []

    # 방법 1: <table> 파싱
    for table in soup.find_all("table"):
        tbody = table.find("tbody")
        if not tbody:
            continue
        rows = tbody.find_all("tr")
        if not rows:
            continue
        # 헤더 추출
        thead = table.find("thead")
        headers = []
        if thead:
            headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])]
        elif rows:
            headers = [td.get_text(strip=True) for td in rows[0].find_all(["th", "td"])]
            rows = rows[1:]

        for row in rows[:20]:
            cells = [td.get_text(strip=True) for td in row.find_all("td")]
            if not cells or not any(cells):
                continue
            p = _cells_to_product(cells, headers, ins_type)
            if p:
                products.append(p)

    if products:
        return products

    # 방법 2: 텍스트 기반 카드/리스트
    company_kws = [
        "삼성생명", "한화생명", "교보생명", "현대해상", "농협생명", "롯데손보", "흥국생명",
        "신한라이프", "KB라이프", "동양생명", "라이나생명", "메트라이프", "AIA생명",
        "푸본현대생명", "ABL생명", "DB손보", "삼성화재", "KB손보", "메리츠화재",
    ]
    for tag in soup.find_all(["li", "div", "tr"]):
        text = tag.get_text(strip=True)
        if len(text) < 10:
            continue
        if any(kw in text for kw in ["원/월", "원 /월"]) and any(kw in text for kw in company_kws):
            p = _text_to_product(text, ins_type)
            if p:
                products.append(p)

    return products


def _extract(page, ins_type: str) -> list[dict]:
    """결과 테이블에서 상품 목록 추출."""
    products: list[dict] = []

    # 방법 1: <table> 파싱
    tables = page.locator("table").all()
    for table in tables:
        rows = table.locator("tbody tr").all()
        if len(rows) < 1:
            continue
        headers = [
            th.inner_text().strip()
            for th in table.locator("thead th, thead td, tr:first-child th, tr:first-child td").all()
        ]
        for row in rows[:20]:
            cells = [td.inner_text().strip() for td in row.locator("td").all()]
            if not cells or not any(cells):
                continue
            p = _cells_to_product(cells, headers, ins_type)
            if p:
                products.append(p)

    if products:
        return products

    # 방법 2: 리스트 아이템 (.ins-list li, .product-item 등)
    list_selectors = [
        ".ins-list > li",
        ".product-list > li",
        ".compare-list > li",
        ".result-list > li",
        "[class*='InsList'] li",
        "[class*='productList'] li",
    ]
    for sel in list_selectors:
        items = page.locator(sel).all()
        for item in items[:20]:
            text = item.inner_text().strip()
            p = _text_to_product(text, ins_type)
            if p:
                products.append(p)
        if products:
            return products

    # 방법 3: div 카드형 레이아웃
    card_selectors = [
        "[class*='card']",
        "[class*='item']",
        "[class*='product']",
        "[class*='result']",
    ]
    for sel in card_selectors:
        cards = page.locator(sel).all()
        for card in cards[:20]:
            text = card.inner_text().strip()
            if len(text) > 10 and any(kw in text for kw in ["생명", "화재", "보험", "원/월"]):
                p = _text_to_product(text, ins_type)
                if p:
                    products.append(p)
        if products:
            return products

    return products


def _cells_to_product(cells: list[str], headers: list[str], ins_type: str) -> dict | None:
    if not cells or all(not c for c in cells):
        return None

    mapping = dict(zip(headers, cells)) if (headers and len(headers) == len(cells)) else {}

    company, name, premium, premium_male, premium_female = "", "", "", "", ""
    coverage_name, coverage_amount = "", ""

    for k, v in mapping.items():
        k_strip = k.strip()
        if any(w in k_strip for w in ["회사", "보험사", "company"]):
            company = v
        elif any(w in k_strip for w in ["상품", "상품명", "name", "회사명"]):
            name = v
        elif any(w in k_strip for w in ["보험료", "월납", "premium"]):
            premium = v
        elif k_strip == "남":
            premium_male = v
        elif k_strip == "여":
            premium_female = v
        elif any(w in k_strip for w in ["보장명", "담보명"]):
            coverage_name = v
        elif any(w in k_strip for w in ["보장금액", "보험금액", "가입금액"]):
            coverage_amount = v

    # 헤더 없으면 위치 기반
    if not company and len(cells) > 0:
        company = cells[0]
    if not name and len(cells) > 1:
        name = cells[1]
    if not premium:
        # 남/여 컬럼이 있으면 남 가격을 기본값으로
        premium = premium_male or premium_female
    if not premium:
        for c in cells:
            if "원" in c and re.search(r"\d", c):
                premium = c
                break

    # 헤더 행·합계 행 제거
    skip_words = ["합계", "평균", "선택", "상품명", "보험회사", "월보험료", "보험료"]
    if any(sw in (company + name) for sw in skip_words):
        return None
    if not (company or name):
        return None

    result: dict = {
        "ins_type": ins_type,
        "company": company.strip(),
        "name": name.strip(),
        "premium_str": premium.strip(),
        "premium_int": _parse_premium(premium),
        "premium_male": _parse_premium(premium_male),
        "premium_female": _parse_premium(premium_female),
        "_source": "insmarket",
    }
    if coverage_name:
        result["coverage_name"] = coverage_name.strip()
    if coverage_amount:
        result["coverage_amount_str"] = coverage_amount.strip()
    return result


def _text_to_product(text: str, ins_type: str) -> dict | None:
    if not text or len(text) < 5:
        return None
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return None

    # 회사명 키워드
    company_kws = [
        "삼성생명", "한화생명", "교보생명", "현대해상", "농협생명", "롯데손보", "흥국생명",
        "신한라이프", "KB라이프", "동양생명", "라이나생명", "메트라이프", "AIA생명",
        "푸본현대생명", "ABL생명", "처브라이프", "DB손보", "삼성화재", "현대해상",
        "KB손보", "메리츠화재", "롯데손보", "한화손보", "흥국화재",
    ]
    company = next((kw for kw in company_kws if kw in text), "")
    name = lines[0]
    premium_match = re.search(r"([\d,]+)\s*원", text)
    premium_str = premium_match.group(0) if premium_match else ""

    if not (company or name):
        return None

    return {
        "ins_type": ins_type,
        "company": company,
        "name": name,
        "premium_str": premium_str,
        "premium_int": _parse_premium(premium_str),
        "_source": "insmarket",
    }


# ──────────────────────────────────────────────────
# Normalization → products.py 호환 포맷
# ──────────────────────────────────────────────────

def _normalize(ins_type: str, profile_data: dict[str, list[dict]]) -> list[dict]:
    """
    {나이_성별: [raw_product]} →
    products.py 호환 딕셔너리 리스트
    """
    products_map: dict[str, dict] = {}
    product_type = _TYPE_MAP.get(ins_type, "생명보험")

    for age_gender_key, raw_list in profile_data.items():
        for raw in raw_list:
            company = raw.get("company", "").strip()
            name = raw.get("name", "").strip()
            if not name:
                continue

            pid = re.sub(r"[^\w가-힣]", "_", f"live_{company}_{name}")[:60]

            if pid not in products_map:
                products_map[pid] = {
                    "id": pid,
                    "name": name,
                    "company": company,
                    "type": product_type,
                    "subtype": ins_type,
                    "monthly_premium": {},
                    "coverage_amount": None,
                    "coverage": {},
                    "age_range": {"min": 15, "max": 70},
                    "features": [],
                    "pros": [f"보험다모아 공시 ({datetime.now().strftime('%Y-%m-%d')} 기준)"],
                    "cons": ["세부 보장 내용은 보험사 홈페이지 확인 필요"],
                    "rating": None,
                    "review_count": 0,
                    "tags": [ins_type, "보험다모아", "실시간"],
                    "_source": "insmarket",
                    "_fetched_at": datetime.now().isoformat(),
                }

            prem = raw.get("premium_int", 0)
            prem_male = raw.get("premium_male", 0)
            prem_female = raw.get("premium_female", 0)

            if age_gender_key.endswith("_전체"):
                # 남/여 컬럼이 분리된 경우 각각 저장
                base = age_gender_key[:-3]  # "30세_전체" → "30세"
                if prem_male > 0:
                    products_map[pid]["monthly_premium"][f"{base}_남"] = prem_male
                if prem_female > 0:
                    products_map[pid]["monthly_premium"][f"{base}_여"] = prem_female
                if prem > 0 and not prem_male and not prem_female:
                    products_map[pid]["monthly_premium"][age_gender_key] = prem
            else:
                if prem > 0:
                    products_map[pid]["monthly_premium"][age_gender_key] = prem

    return list(products_map.values())


def _parse_premium(text: str) -> int:
    """'150,000원/월' → 150000. 유효하지 않으면 0."""
    if not text:
        return 0
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return 0
    val = int(digits)
    return val if 1_000 <= val <= 10_000_000 else 0
