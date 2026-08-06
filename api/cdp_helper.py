"""
순수 CDP WebSocket 기반 Chrome 조작 모듈.
Playwright의 JS 바인딩 주입 없이 Chrome에 직접 접근 → mbuster 감지 우회.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_chrome() -> str | None:
    for p in _CHROME_PATHS:
        if Path(p).exists():
            return p
    return None


def is_cdp_ready(cdp_url: str = "http://localhost:9222", timeout: float = 2.0) -> bool:
    try:
        urllib.request.urlopen(f"{cdp_url}/json/version", timeout=timeout)
        return True
    except Exception:
        return False


def _ws_connectable(cdp_url: str) -> bool:
    """WebSocket 연결이 실제로 되는지 확인 (origin 헤더 포함)."""
    try:
        import websocket
        tabs = json.loads(urllib.request.urlopen(f"{cdp_url}/json", timeout=5).read())
        if not tabs:
            return False
        ws_url = tabs[0].get("webSocketDebuggerUrl", "")
        if not ws_url:
            return False
        ws = websocket.WebSocket()
        ws.connect(ws_url, timeout=5, origin="http://localhost")
        ws.close()
        return True
    except Exception:
        return False


def _kill_chrome_on_port(port: int) -> None:
    """해당 포트를 Listen 중인 Chrome 프로세스만 종료."""
    try:
        r = subprocess.run(
            ["netstat", "-ano"], capture_output=True, timeout=10,
            text=True, encoding="utf-8", errors="replace"
        )
        for line in r.stdout.splitlines():
            if f":{port} " in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/PID", pid, "/F"],
                               capture_output=True, timeout=5)
                print(f"  [Chrome] 기존 프로세스 (PID {pid}) 종료", flush=True)
                time.sleep(2)
                break
    except Exception:
        pass


def launch_chrome(
    url: str = "http://203.229.168.79",
    cdp_port: int = 9222,
    wait: float = 18.0,
    real_profile: bool = False,
) -> bool:
    """
    Chrome을 CDP 디버그 모드로 자동 실행.
    이미 실행 중이고 WebSocket도 정상이면 재사용.
    WebSocket 연결이 거부되면 해당 프로세스만 종료 후 재시작.
    real_profile=True 시 기본 대기 18s → 40s로 자동 연장.
    """
    cdp_url = f"http://localhost:{cdp_port}"
    # 실제 프로필은 확장/동기화 로드 시간이 길어 더 오래 기다린다
    effective_wait = max(wait, 40.0) if real_profile else wait

    if is_cdp_ready(cdp_url):
        if _ws_connectable(cdp_url):
            print(f"  [Chrome] 이미 실행 중 (port {cdp_port})", flush=True)
            return True
        # --remote-allow-origins 없이 실행된 경우 → 재시작
        print(f"  [Chrome] WebSocket 거부됨 → Chrome 재시작 (--remote-allow-origins=*)", flush=True)
        _kill_chrome_on_port(cdp_port)

    chrome_exe = find_chrome()
    if not chrome_exe:
        print("  [Chrome] 설치 경로를 찾을 수 없습니다.", flush=True)
        return False

    if real_profile:
        # 실제 사용자 Chrome 프로필 사용 (기존 쿠키/세션 유지)
        # --user-data-dir을 실제 경로로 명시해야 Chrome singleton이 올바른 인스턴스를 사용
        real_user_data = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Google", "Chrome", "User Data",
        )
        cmd = [
            chrome_exe,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={real_user_data}",
            "--profile-directory=Default",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--restore-last-session=false",
            "--disable-session-crashed-bubble",
            "--noerrdialogs",
            url,
        ]
    else:
        user_data_dir = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "ChromeDebug")
        cmd = [
            chrome_exe,
            f"--remote-debugging-port={cdp_port}",
            f"--user-data-dir={user_data_dir}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=AutomationControlled",
            url,
        ]
    print(f"  [Chrome] 실행 중... (port {cdp_port}, 최대 {effective_wait:.0f}초 대기)", flush=True)
    # CREATE_NEW_CONSOLE: Chrome을 독립 프로세스 그룹으로 실행 (Python 프로세스 종료 시 Chrome이 살아있도록)
    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=creation_flags)

    deadline = time.time() + effective_wait
    while time.time() < deadline:
        time.sleep(1.5)
        cdp_ok = is_cdp_ready(cdp_url)
        ws_ok = cdp_ok and _ws_connectable(cdp_url)
        if ws_ok:
            print(f"  [Chrome] 준비 완료", flush=True)
            time.sleep(4)  # 보험다모아 초기 로드 여유
            return True
        if cdp_ok:
            print(f"  [Chrome] CDP 응답 중, WebSocket 대기...", flush=True)

    print(f"  [Chrome] 시작 타임아웃 ({effective_wait:.0f}초)", flush=True)
    return False


class CdpHelper:
    """Chrome DevTools Protocol 직접 접근 (Playwright 없음)"""

    def __init__(self, cdp_url: str = "http://localhost:9222"):
        self.cdp_url = cdp_url
        self._ws = None
        self._msg_id = 0

    # ── 탭 목록 ────────────────────────────────────────────────

    def get_tabs(self) -> list[dict]:
        resp = urllib.request.urlopen(f"{self.cdp_url}/json", timeout=5)
        return json.loads(resp.read())

    def find_tab(self, url_contains: str, exclude: str = "mbuster") -> dict | None:
        for t in self.get_tabs():
            u = t.get("url", "")
            if t.get("type") == "page" and url_contains in u and exclude not in u.lower():
                return t
        return None

    # ── 연결/해제 ───────────────────────────────────────────────

    def connect(self, ws_url: str) -> None:
        import websocket
        self._ws = websocket.WebSocket()
        # Origin을 http://localhost 로 고정 (Chrome이 포트 번호 포함 Origin을 거부함)
        self._ws.connect(ws_url, timeout=30, origin="http://localhost")
        self._send("Page.enable", {})
        self._send("Runtime.enable", {})

    def close(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # ── CDP 명령 ────────────────────────────────────────────────

    def _send(self, method: str, params: dict | None = None) -> int:
        self._msg_id += 1
        msg = json.dumps({"id": self._msg_id, "method": method, "params": params or {}})
        self._ws.send(msg)
        return self._msg_id

    def _recv_until(self, msg_id: int, timeout: float = 30.0) -> dict:
        import websocket as _ws_mod
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self._ws.settimeout(min(2.0, deadline - time.time()))
                raw = self._ws.recv()
                msg = json.loads(raw)
                if msg.get("id") == msg_id:
                    return msg
            except _ws_mod.WebSocketTimeoutException:
                pass
            except Exception:
                break
        return {}

    def navigate(self, url: str, wait: float = 4.0) -> None:
        """페이지 이동 후 로드 완료 대기."""
        import websocket as _ws_mod
        mid = self._send("Page.navigate", {"url": url})
        deadline = time.time() + 20.0
        while time.time() < deadline:
            try:
                self._ws.settimeout(2.0)
                raw = self._ws.recv()
                msg = json.loads(raw)
                if msg.get("id") == mid:
                    break
                if msg.get("method") in ("Page.loadEventFired", "Page.domContentEventFired"):
                    break
            except _ws_mod.WebSocketTimeoutException:
                pass
            except Exception:
                break
        time.sleep(wait)

    def navigate_js(self, url: str, wait: float = 4.0) -> None:
        """JavaScript 방식 페이지 이동 (CDP Page.navigate 감지 우회)."""
        self.evaluate(f"window.location.href = '{url}'")
        time.sleep(wait)

    def evaluate(self, expression: str, timeout: float = 15.0):
        """JavaScript 실행 후 결과 반환."""
        mid = self._send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": False,
        })
        result = self._recv_until(mid, timeout=timeout)
        return result.get("result", {}).get("result", {}).get("value")

    def get_html(self) -> str:
        return self.evaluate("document.documentElement.outerHTML") or ""

    # ── 폼 조작 (JavaScript 실행 방식) ─────────────────────────

    def fill_gender(self, gender: str) -> None:
        """성별 체크박스/라디오 선택."""
        keyword = "남" if gender == "남" else "여"
        exclude = "여" if gender == "남" else "남"
        self.evaluate(f"""
        (() => {{
            const inputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
            for (const el of inputs) {{
                const lbl = document.querySelector('label[for="' + el.id + '"]') || el.closest('label') || el.parentElement;
                const txt = (lbl ? lbl.textContent : '') + el.value;
                if (txt.includes('{keyword}') && !txt.includes('{exclude}')) {{
                    el.checked = true;
                    el.click();
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return;
                }}
            }}
        }})()
        """)

    def fill_birth(self, birth: str) -> None:
        """생년월일 입력 (YYYYMMDD)."""
        self.evaluate(f"""
        (() => {{
            const candidates = [
                'input[placeholder*="19900101"]',
                'input[placeholder*="YYYYMMDD"]',
                'input[placeholder*="생년월일"]',
                'input[name*="birth"]',
                'input[name*="Birth"]',
                'input[id*="birth"]',
            ];
            for (const sel of candidates) {{
                const el = document.querySelector(sel);
                if (el) {{
                    el.value = '{birth}';
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return;
                }}
            }}
        }})()
        """)

    def click_search(self) -> None:
        """검색/비교하기 버튼 클릭."""
        self.evaluate("""
        (() => {
            const keywords = ['비교하기', '상품비교', '조회하기', '검색', '확인'];
            const els = [...document.querySelectorAll('button, a, input[type="button"], input[type="submit"]')];
            for (const kw of keywords) {
                const el = els.find(e => e.textContent.includes(kw) || (e.value || '').includes(kw));
                if (el) { el.click(); return; }
            }
        })()
        """)

    def wait_for_results(self, timeout: float = 12.0) -> None:
        """검색 결과 로딩 대기 (table 또는 결과 div 나타날 때까지)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self.evaluate("""
            (() => {
                const t = document.querySelector('table tbody tr');
                const l = document.querySelector('.ins-list li, .product-list li, .result-list li');
                return !!(t || l);
            })()
            """)
            if found:
                break
            time.sleep(1.0)
        time.sleep(1.5)
