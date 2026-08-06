"""
VPN / 프록시 IP 자동 로테이션 모듈

지원 방식:
  nordvpn    - NordVPN 데스크톱 앱 CLI (Windows/Linux/Mac)
  expressvpn - ExpressVPN CLI
  rasdial    - Windows 내장 VPN (네트워크 설정에 등록된 연결)
  proxy      - HTTP/SOCKS5 프록시 목록 순환
  auto       - 위 순서로 자동 감지
"""
from __future__ import annotations

import random
import subprocess
import time
import urllib.request
from pathlib import Path

_NORDVPN_REGIONS = [
    "Japan", "Singapore", "Hong Kong", "Taiwan",
    "United States", "Germany", "Netherlands", "France", "Canada", "Australia",
]

_EXPRESSVPN_LOCATIONS = ["jpyt", "sgju", "hkpo", "usny", "usla", "denu", "nlam"]


class VpnRotator:
    """
    IP 로테이션 통합 인터페이스.

    vpn_type:
        "auto"       - 자동 감지
        "nordvpn"    - NordVPN CLI
        "expressvpn" - ExpressVPN CLI
        "rasdial"    - Windows 내장 VPN (connection_name 필요)
        "proxy"      - 프록시 목록 순환 (proxy_list 필요)
    """

    def __init__(
        self,
        vpn_type: str = "auto",
        connection_name: str | None = None,
        proxy_list: list[str] | None = None,
    ):
        self.vpn_type = vpn_type
        self.connection_name = connection_name
        self.proxy_list = proxy_list or []
        self._proxy_index = 0
        self._detected: str | None = None

    # ── 공개 API ────────────────────────────────────────────────────

    def rotate(self) -> bool:
        """IP를 변경한다. 성공하면 True."""
        method = self._resolve_type()
        if not method:
            return False

        before = self.get_current_ip()
        print(f"[VPN] 현재 IP: {before or '확인 불가'}", flush=True)

        dispatch = {
            "nordvpn": self._rotate_nordvpn,
            "expressvpn": self._rotate_expressvpn,
            "rasdial": self._rotate_rasdial,
            "proxy": self._rotate_proxy,
        }
        ok = dispatch.get(method, lambda: False)()

        if ok:
            after = self.get_current_ip()
            print(f"[VPN] 새 IP: {after or '확인 불가'}", flush=True)
            if before and after and before == after:
                print("[VPN] 경고: IP가 변경되지 않았습니다.", flush=True)
        return ok

    def get_current_proxy(self) -> dict | None:
        """
        proxy 모드에서 Playwright에 전달할 dict 반환.
        {'server': '...', 'username': '...', 'password': '...'}
        """
        if self._resolve_type() != "proxy" or not self.proxy_list:
            return None
        raw = self.proxy_list[self._proxy_index % len(self.proxy_list)]
        return _parse_proxy_url(raw)

    def get_current_ip(self) -> str:
        """공인 IP 주소 확인 (실패 시 빈 문자열)."""
        for url in ["https://api.ipify.org", "https://checkip.amazonaws.com"]:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "curl/7.64.1"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    return r.read().decode().strip()
            except Exception:
                pass
        return ""

    # ── 내부: 타입 결정 ─────────────────────────────────────────────

    def _resolve_type(self) -> str | None:
        if self.vpn_type != "auto":
            return self.vpn_type
        if not self._detected:
            self._detected = self._detect()
        return self._detected

    def _detect(self) -> str | None:
        # NordVPN
        for path in [
            r"C:\Program Files\NordVPN\NordVPN.exe",
            r"C:\Program Files (x86)\NordVPN\NordVPN.exe",
        ]:
            if Path(path).exists():
                print("[VPN] NordVPN 감지", flush=True)
                return "nordvpn"

        # ExpressVPN
        if _cmd_exists("expressvpn"):
            print("[VPN] ExpressVPN 감지", flush=True)
            return "expressvpn"

        # Windows rasdial
        if self.connection_name:
            print(f"[VPN] Windows VPN '{self.connection_name}' 사용", flush=True)
            return "rasdial"

        # 프록시 목록
        if self.proxy_list:
            print("[VPN] 프록시 로테이션 사용", flush=True)
            return "proxy"

        print("[VPN] 지원되는 VPN/프록시를 찾을 수 없습니다.", flush=True)
        return None

    # ── NordVPN ─────────────────────────────────────────────────────

    def _rotate_nordvpn(self) -> bool:
        exe = _nordvpn_exe()
        region = random.choice(_NORDVPN_REGIONS)
        try:
            subprocess.run([exe, "-d"], capture_output=True, timeout=20)
            time.sleep(3)
            subprocess.run(
                [exe, "-c", "-g", region],
                capture_output=True, timeout=45,
                text=True, encoding="utf-8", errors="replace",
            )
            time.sleep(7)
            print(f"[VPN] NordVPN → {region} 연결", flush=True)
            return True
        except FileNotFoundError:
            print(f"[VPN] NordVPN 실행 파일 없음: {exe}", flush=True)
            return False
        except subprocess.TimeoutExpired:
            print("[VPN] NordVPN 연결 타임아웃", flush=True)
            return False
        except Exception as e:
            print(f"[VPN] NordVPN 오류: {e}", flush=True)
            return False

    # ── ExpressVPN ──────────────────────────────────────────────────

    def _rotate_expressvpn(self) -> bool:
        location = random.choice(_EXPRESSVPN_LOCATIONS)
        try:
            subprocess.run(["expressvpn", "disconnect"], capture_output=True, timeout=20)
            time.sleep(2)
            subprocess.run(["expressvpn", "connect", location], capture_output=True, timeout=45)
            time.sleep(6)
            print(f"[VPN] ExpressVPN → {location} 연결", flush=True)
            return True
        except Exception as e:
            print(f"[VPN] ExpressVPN 오류: {e}", flush=True)
            return False

    # ── Windows rasdial ─────────────────────────────────────────────

    def _rotate_rasdial(self) -> bool:
        name = self.connection_name
        if not name:
            print("[VPN] --vpn-name 옵션으로 Windows VPN 연결 이름을 지정하세요.", flush=True)
            return False
        try:
            subprocess.run(["rasdial", name, "/disconnect"], capture_output=True, timeout=20)
            time.sleep(3)
            r = subprocess.run(
                ["rasdial", name],
                capture_output=True, text=True, timeout=45,
                encoding="utf-8", errors="replace",
            )
            time.sleep(4)
            if r.returncode == 0:
                print(f"[VPN] Windows VPN '{name}' 재연결 완료", flush=True)
                return True
            print(f"[VPN] rasdial 실패 (코드 {r.returncode}): {r.stdout.strip()}", flush=True)
            return False
        except Exception as e:
            print(f"[VPN] rasdial 오류: {e}", flush=True)
            return False

    # ── 프록시 로테이션 ─────────────────────────────────────────────

    def _rotate_proxy(self) -> bool:
        if not self.proxy_list:
            print("[VPN] --proxy 옵션으로 프록시 URL을 지정하세요.", flush=True)
            return False
        self._proxy_index = (self._proxy_index + 1) % len(self.proxy_list)
        new_proxy = self.proxy_list[self._proxy_index]
        print(f"[VPN] 프록시 → {_mask_proxy(new_proxy)}", flush=True)
        return True


# ── 유틸리티 ─────────────────────────────────────────────────────────

def _nordvpn_exe() -> str:
    for path in [
        r"C:\Program Files\NordVPN\NordVPN.exe",
        r"C:\Program Files (x86)\NordVPN\NordVPN.exe",
    ]:
        if Path(path).exists():
            return path
    return "nordvpn"


def _cmd_exists(cmd: str) -> bool:
    import os
    check = ["where", cmd] if os.name == "nt" else ["which", cmd]
    try:
        return subprocess.run(check, capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def _parse_proxy_url(url: str) -> dict:
    """
    'socks5://user:pass@host:port' → Playwright proxy dict.
    인증 없는 경우: 'http://host:port'
    """
    result: dict = {"server": url}
    # user:pass@ 추출
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        if p.username:
            result["username"] = p.username
            result["password"] = p.password or ""
            # server에서 인증정보 제거
            netloc_clean = p.hostname + (f":{p.port}" if p.port else "")
            result["server"] = f"{p.scheme}://{netloc_clean}"
    except Exception:
        pass
    return result


def _mask_proxy(url: str) -> str:
    """로그용: 비밀번호 마스킹."""
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        if p.password:
            return url.replace(p.password, "***")
    except Exception:
        pass
    return url
