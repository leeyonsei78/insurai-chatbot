# -*- coding: utf-8 -*-
"""
신용점수 조회 도구 (CDP 모드)
Chrome CDP로 연결된 나이스지키미 또는 올크레딧 페이지에서 신용점수를 가져옵니다.
"""
from __future__ import annotations

import json
import re
from collections import Counter


def _get_tier(score: int) -> dict:
    if score >= 900:
        return {"tier": "최우량", "grade": "1등급"}
    if score >= 750:
        return {"tier": "우량", "grade": "2~3등급"}
    if score >= 600:
        return {"tier": "보통", "grade": "4~6등급"}
    if score >= 450:
        return {"tier": "주의", "grade": "7~8등급"}
    return {"tier": "불량", "grade": "9~10등급"}


def _get_advice(tier: str) -> str:
    advice_map = {
        "최우량": "신용점수 최우량 등급입니다. 모든 보험 상품에 유리한 조건으로 가입 가능하며, 프리미엄·변액·저축성 보험에서 우대 혜택을 받을 수 있습니다.",
        "우량": "신용점수 우량 등급입니다. 종신보험·실손보험·암보험·치아보험 등 다양한 보험 상품을 일반 표준 조건으로 가입 가능합니다.",
        "보통": "신용점수 보통 등급입니다. 보장성 보험 표준 조건으로 가입 가능합니다. 저축성 보험 가입은 신중하게 검토하세요.",
        "주의": "신용점수 주의 등급입니다. 무심사형 또는 간편심사형 보험을 우선 검토하는 것이 유리합니다. 보장성 보험에 집중하세요.",
        "불량": "신용점수 불량 등급입니다. 무심사 상품 위주로 가입하시고, 신용 관리를 병행하시길 강력 권장합니다.",
    }
    return advice_map.get(tier, "신용점수 기반 맞춤 상담을 제공합니다.")


_SCORE_SELECTORS = [
    ".score-number",
    ".credit-score",
    "#creditScore",
    ".my-score",
    ".score_num",
    "[class*='score']",
]
_SCORE_PATTERN = re.compile(r"\b([3-9]\d{2}|1000)\b")


def get_credit_score(cdp_url: str = "http://localhost:9222") -> str:
    """
    CDP 연결로 나이스지키미 또는 올크레딧에서 신용점수를 조회합니다.

    Returns:
        JSON 문자열.
        성공: {"score": 850, "grade": "2~3등급", "tier": "우량", "source": "NICE", "advice": "..."}
        실패: {"error": "...", "action_required": true}
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return json.dumps(
            {
                "error": "Playwright가 설치되지 않았습니다. 'pip install playwright && playwright install chromium'을 실행하세요.",
                "action_required": True,
            },
            ensure_ascii=False,
        )

    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.connect_over_cdp(cdp_url)
            except Exception as e:
                return json.dumps(
                    {
                        "error": (
                            f"Chrome CDP 연결 실패: {e}. "
                            "Chrome을 원격 디버깅 모드로 실행해주세요: "
                            'chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\\ChromeDebug"'
                        ),
                        "action_required": True,
                    },
                    ensure_ascii=False,
                )

            # 열린 컨텍스트 및 페이지에서 신용 사이트 탭 탐색
            contexts = browser.contexts
            target_page = None
            source_name = "NICE"

            for ctx in contexts:
                for page in ctx.pages:
                    url = page.url
                    if "credit.co.kr" in url:
                        target_page = page
                        source_name = "NICE"
                        break
                    if "allcredit.co.kr" in url:
                        target_page = page
                        source_name = "KCB"
                        break
                if target_page:
                    break

            # 탭 없으면 새 페이지 열고 안내
            if target_page is None:
                if contexts:
                    target_page = contexts[0].new_page()
                else:
                    return json.dumps(
                        {
                            "error": "연결된 Chrome 컨텍스트가 없습니다. Chrome을 CDP 모드로 다시 실행해주세요.",
                            "action_required": True,
                        },
                        ensure_ascii=False,
                    )

                target_page.goto("https://www.credit.co.kr", timeout=15000)
                return json.dumps(
                    {
                        "error": (
                            "나이스지키미(credit.co.kr) 페이지로 이동했습니다. "
                            "로그인 후 신용점수 조회 페이지로 이동한 다음 다시 요청해주세요."
                        ),
                        "action_required": True,
                    },
                    ensure_ascii=False,
                )

            # 점수 추출 — 선택자 순서대로 시도
            score = None
            for selector in _SCORE_SELECTORS:
                try:
                    el = target_page.query_selector(selector)
                    if el:
                        text = (el.inner_text() or "").strip()
                        m = _SCORE_PATTERN.search(text)
                        if m:
                            candidate = int(m.group(1))
                            if 300 <= candidate <= 1000:
                                score = candidate
                                break
                except Exception:
                    continue

            # 선택자 실패 시 페이지 소스에서 정규식으로 추출
            if score is None:
                try:
                    content = target_page.content()
                    matches = _SCORE_PATTERN.findall(content)
                    candidates = [int(v) for v in matches if 300 <= int(v) <= 1000]
                    if candidates:
                        # 빈도가 가장 높은 값 선택 (신용점수는 반복 노출될 가능성 높음)
                        score = Counter(candidates).most_common(1)[0][0]
                except Exception:
                    pass

            if score is None:
                return json.dumps(
                    {
                        "error": (
                            "페이지에서 신용점수를 추출하지 못했습니다. "
                            "나이스지키미 또는 올크레딧에 로그인 후 신용점수 조회 페이지를 열어두세요."
                        ),
                        "action_required": True,
                    },
                    ensure_ascii=False,
                )

            tier_info = _get_tier(score)
            advice = _get_advice(tier_info["tier"])

            return json.dumps(
                {
                    "score": score,
                    "grade": tier_info["grade"],
                    "tier": tier_info["tier"],
                    "source": source_name,
                    "advice": advice,
                },
                ensure_ascii=False,
            )

    except Exception as e:
        return json.dumps(
            {"error": f"신용점수 조회 중 오류 발생: {e}", "action_required": True},
            ensure_ascii=False,
        )
