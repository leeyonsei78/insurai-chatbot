"""웹 페이지 본문 추출 도구 — requests 기반, 추가 패키지 불필요"""

from __future__ import annotations
import json
import re
from html.parser import HTMLParser


class _TextExtractor(HTMLParser):
    SKIP_TAGS = {"script", "style", "nav", "footer", "header", "noscript", "iframe", "aside"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.texts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.texts.append(stripped)


def fetch_webpage(url: str, max_chars: int = 4000) -> str:
    """
    URL의 웹페이지 본문 텍스트를 가져옵니다.

    Args:
        url: 가져올 페이지 URL
        max_chars: 반환할 최대 글자 수 (기본 4000)
    """
    try:
        import requests
    except ImportError:
        return json.dumps({"error": "pip install requests 필요"}, ensure_ascii=False)

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        resp.raise_for_status()

        # encoding 보정
        if resp.encoding and resp.encoding.lower() in ("iso-8859-1", "latin-1"):
            resp.encoding = resp.apparent_encoding

        parser = _TextExtractor()
        parser.feed(resp.text)
        raw = " ".join(parser.texts)
        text = re.sub(r"\s{2,}", " ", raw).strip()

        return json.dumps(
            {
                "url": url,
                "content": text[:max_chars],
                "truncated": len(text) > max_chars,
                "total_chars": len(text),
            },
            ensure_ascii=False,
            indent=2,
        )

    except Exception as e:
        return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)
