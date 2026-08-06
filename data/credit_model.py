# -*- coding: utf-8 -*-
"""
신용점수 기반 보험 추천 조정 모델
"""
from __future__ import annotations
import re


def get_insurance_recommendation_by_credit(score: int, insurance_type: str = "") -> dict:
    """
    신용점수에 따른 보험 추천 조정.

    Returns:
        {
            "tier": "우량",
            "preferred_products": [...],
            "avoid_products": [...],
            "advice": "...",
            "discount_eligibility": True
        }
    """
    if score >= 900:
        return {
            "tier": "최우량",
            "preferred_products": ["비갱신형 종신보험", "변액보험", "변액유니버셜보험", "저축성 보험", "프리미엄 실손보험"],
            "avoid_products": [],
            "advice": (
                f"신용점수 {score}점 최우량 등급입니다. "
                "모든 보험 상품에서 유리한 조건으로 가입 가능하며, "
                "프리미엄 종신보험·변액보험·저축성 보험에서 일부 보험사 우대 혜택을 받으실 수 있습니다."
            ),
            "discount_eligibility": True,
        }
    elif score >= 750:
        return {
            "tier": "우량",
            "preferred_products": ["비갱신형 종신보험", "실손의료보험", "암보험", "치아보험", "간병·치매보험"],
            "avoid_products": [],
            "advice": (
                f"신용점수 {score}점 우량 등급입니다. "
                "종신보험·실손보험·암보험·치아보험 등 주요 보험 상품을 일반 표준 조건으로 가입 가능합니다."
            ),
            "discount_eligibility": True,
        }
    elif score >= 600:
        return {
            "tier": "보통",
            "preferred_products": ["실손의료보험", "암보험", "정기보험", "치아보험"],
            "avoid_products": ["변액보험", "고액 저축성 보험"],
            "advice": (
                f"신용점수 {score}점 보통 등급입니다. "
                "보장성 보험(실손·암·치아)은 표준 조건으로 가입 가능합니다. "
                "저축성 보험이나 변액 상품 가입은 신중하게 검토하세요."
            ),
            "discount_eligibility": False,
        }
    elif score >= 450:
        return {
            "tier": "주의",
            "preferred_products": ["무심사형 실손보험", "간편심사형 암보험", "간편심사형 치아보험"],
            "avoid_products": ["변액보험", "저축성 보험", "종신보험 (일반심사)"],
            "advice": (
                f"신용점수 {score}점 주의 등급입니다. "
                "무심사형 또는 간편심사형 보험을 우선 검토하시고, 보장성 보험에 집중하는 것이 유리합니다. "
                "저축성 보험이나 변액 상품은 비추천합니다."
            ),
            "discount_eligibility": False,
        }
    else:
        return {
            "tier": "불량",
            "preferred_products": ["무심사 실손보험", "무심사 암보험"],
            "avoid_products": ["변액보험", "저축성 보험", "종신보험", "일반심사 상품"],
            "advice": (
                f"신용점수 {score}점 불량 등급입니다. "
                "무심사 상품 위주로 가입을 검토하시고, 신용 관리를 병행하시길 강력 권장합니다. "
                "신용 점수가 개선된 후 더 다양한 상품 가입이 가능합니다."
            ),
            "discount_eligibility": False,
        }


def calculate_composite_score(base_score: int, financial_data: dict, alt_data: dict, medical_data: dict = None) -> dict:
    """
    신용점수 + 금융데이터 + 대안데이터를 종합한 보험 가입 적합도 지수 산출.

    Returns dict:
        composite_score, base_score, adjustments (list of {factor, delta, reason}),
        grade, grade_cls, total_delta, underwriting_risk, preferred_products, summary
    """
    adjustments = []

    def adj(factor: str, delta: int, reason: str):
        adjustments.append({"factor": factor, "delta": delta, "reason": reason})

    income   = financial_data.get("income") or 0
    assets   = financial_data.get("assets") or 0
    debt     = financial_data.get("debt") or 0
    cur_prem = financial_data.get("current_premium") or 0

    # ── 금융데이터 조정 ──────────────────────────────────────
    if income:
        monthly = income / 12
        # 연소득 수준
        if income >= 7000:
            adj("연소득 7000만원 이상", +20, "높은 소득 안정성")
        elif income >= 5000:
            adj("연소득 5000~7000만원", +10, "양호한 소득 수준")
        elif income >= 3000:
            adj("연소득 3000~5000만원", 0, "표준 소득 수준")
        elif income >= 2000:
            adj("연소득 2000~3000만원", -10, "소득 다소 낮음")
        else:
            adj("연소득 2000만원 미만", -20, "소득 부족 — 납입 능력 주의")

        # 부채비율
        if debt:
            ratio = debt / income * 100
            if ratio < 50:
                adj(f"부채비율 양호 ({ratio:.0f}%)", +20, "부채 부담 낮음")
            elif ratio < 100:
                adj(f"부채비율 보통 ({ratio:.0f}%)", +8, "관리 가능한 부채")
            elif ratio < 200:
                adj(f"부채비율 주의 ({ratio:.0f}%)", -10, "부채 부담 있음")
            elif ratio < 300:
                adj(f"부채비율 과다 ({ratio:.0f}%)", -20, "높은 부채 부담")
            else:
                adj(f"부채비율 위험 ({ratio:.0f}%)", -35, "심각한 부채 — 보장성 보험 집중 필요")

        # 보험료 부담률
        if cur_prem and monthly:
            prem_ratio = cur_prem / monthly * 100
            if prem_ratio < 10:
                adj(f"보험료 부담 낮음 ({prem_ratio:.1f}%)", +5, "여유로운 납입 여력")
            elif prem_ratio < 15:
                adj(f"보험료 부담 적정 ({prem_ratio:.1f}%)", 0, "적정 보험료 수준")
            elif prem_ratio < 20:
                adj(f"보험료 부담 높음 ({prem_ratio:.1f}%)", -8, "보험료 비중 과도")
            else:
                adj(f"보험료 부담 과도 ({prem_ratio:.1f}%)", -15, "기존 보험 정비 권장")

        # 자산 수준
        if assets:
            if assets >= income * 2:
                adj(f"금융자산 우수 ({assets:,.0f}만원)", +15, "탄탄한 자산 기반")
            elif assets >= income:
                adj(f"금융자산 양호 ({assets:,.0f}만원)", +8, "자산 여유 있음")
            elif assets >= income * 0.5:
                adj(f"금융자산 보통 ({assets:,.0f}만원)", 0, "표준 자산 수준")
            else:
                adj(f"금융자산 부족 ({assets:,.0f}만원)", -5, "자산 형성 필요")

    # ── 대안데이터 조정 ──────────────────────────────────────
    employment = (alt_data.get("employment") or "").strip()
    housing    = (alt_data.get("housing") or "").strip()
    telecom    = (alt_data.get("telecom") or "").strip()
    utility    = (alt_data.get("utility") or "").strip()

    emp_map = {
        "공무원": (+15, "직업 안정성 최우수"),
        "정규직": (+10, "안정적 고용"),
        "비정규직": (-5, "고용 불안정 요소"),
        "자영업": (-5, "소득 변동성 있음"),
        "프리랜서": (-8, "불규칙 소득"),
        "무직": (-20, "납입 능력 불확실"),
    }
    if employment in emp_map:
        d, r = emp_map[employment]
        adj(f"직업: {employment}", d, r)

    housing_map = {
        "자가": (+10, "자산 기반 안정"),
        "전세": (+5, "거주 안정"),
        "가족거주": (+3, "주거 비용 없음"),
        "월세": (0, "주거비 부담 있음"),
        "기타": (0, ""),
    }
    if housing in housing_map:
        d, r = housing_map[housing]
        if d != 0:
            adj(f"거주: {housing}", d, r)

    pay_map = {"정상납부": +5, "지연경험": -10, "연체경험": -25}
    if telecom in pay_map and pay_map[telecom] != 0:
        d = pay_map[telecom]
        r = "정상 납부 이력" if d > 0 else ("지연 이력 있음" if d == -10 else "연체 이력 — 심사 불이익")
        adj(f"통신비 납부: {telecom}", d, r)
    if utility in pay_map and pay_map[utility] != 0:
        d = pay_map[utility]
        r = "정상 납부 이력" if d > 0 else ("지연 이력 있음" if d == -10 else "연체 이력 — 심사 불이익")
        adj(f"공과금 납부: {utility}", d, r)

    # ── 의료이력 — 언더라이팅 위험도 산정 (점수 조정 없음) ──
    medical = medical_data or {}
    conditions = medical.get("conditions", [])
    hospitalization = medical.get("hospitalization", "")
    current_meds = (medical.get("current_medications") or "").strip()

    high_risk = {"암·종양 치료", "심장질환", "뇌질환"}
    mid_risk  = {"당뇨병", "간질환", "신장질환"}
    low_risk  = {"고혈압", "척추·관절질환", "정신건강 질환"}

    has_high = any(c in high_risk for c in conditions)
    has_mid  = any(c in mid_risk  for c in conditions)
    has_hosp = hospitalization in ("2회", "3회 이상")

    if has_high:
        underwriting_risk = "고위험"
    elif has_mid or has_hosp:
        underwriting_risk = "중위험"
    elif conditions or current_meds:
        underwriting_risk = "주의"
    else:
        underwriting_risk = "일반"

    # ── 종합 점수 산출 ────────────────────────────────────────
    total_delta = sum(a["delta"] for a in adjustments)
    composite = max(300, base_score + total_delta)

    # 등급 결정
    if composite >= 900:
        grade, grade_cls = "최우량", "tier1"
    elif composite >= 750:
        grade, grade_cls = "우량", "tier2"
    elif composite >= 600:
        grade, grade_cls = "보통", "tier3"
    elif composite >= 450:
        grade, grade_cls = "주의", "tier4"
    else:
        grade, grade_cls = "불량", "tier5"

    # 의료이력 반영 추천 상품 조정
    rec = get_insurance_recommendation_by_credit(composite)
    preferred = list(rec["preferred_products"])
    avoid     = list(rec["avoid_products"])
    if underwriting_risk == "고위험":
        preferred = ["무심사형 암보험", "무심사 실손보험", "무심사 간병보험"]
        avoid = ["일반심사 종신보험", "변액보험", "저축성 보험"]
    elif underwriting_risk in ("중위험", "주의"):
        preferred = [p.replace("비갱신형", "간편심사형") for p in preferred]
        preferred = ["간편심사형 " + p if "무심사" not in p and "간편" not in p else p for p in preferred[:3]]

    # 요약 텍스트
    dir_str = f"+{total_delta}" if total_delta >= 0 else str(total_delta)
    summary = (
        f"기본 신용점수 {base_score}점에서 재무·대안 데이터 분석으로 {dir_str}점 조정 → "
        f"종합 적합도 **{composite}점 ({grade})**. "
        f"보험 심사 위험도: **{underwriting_risk}**."
    )

    return {
        "composite_score": composite,
        "base_score": base_score,
        "total_delta": total_delta,
        "adjustments": adjustments,
        "grade": grade,
        "grade_cls": grade_cls,
        "underwriting_risk": underwriting_risk,
        "preferred_products": preferred,
        "avoid_products": avoid,
        "summary": summary,
    }


def get_financial_profile_summary(financial_data: dict, alt_data: dict) -> str:
    """금융데이터 + 대안데이터 기반 재무 프로파일 요약 (GPT 프롬프트 삽입용)"""
    if not financial_data and not alt_data:
        return ""

    lines = ["## 재무·대안 데이터 분석"]

    income   = financial_data.get("income") or 0
    assets   = financial_data.get("assets") or 0
    debt     = financial_data.get("debt") or 0
    cur_prem = financial_data.get("current_premium") or 0

    if income:
        monthly_income = income / 12
        lines.append(f"- 연소득: {income:,.0f}만원 (월 {monthly_income:,.0f}만원)")
        if debt:
            debt_ratio = debt / income * 100
            debt_status = "양호" if debt_ratio < 100 else ("보통" if debt_ratio < 300 else "과다")
            lines.append(f"- 부채비율: {debt_ratio:.0f}% ({debt_status}) — 부채 {debt:,.0f}만원 / 연소득 {income:,.0f}만원")
            if debt_ratio >= 300:
                lines.append("  → 부채 부담 과다: 저축성·변액보험보다 보장성 보험 집중 필수")
        if cur_prem:
            prem_ratio = cur_prem / monthly_income * 100
            avail = monthly_income * 0.15 - cur_prem
            lines.append(f"- 현재 납입 보험료: {cur_prem}만원/월 (월소득 대비 {prem_ratio:.1f}%)")
            if avail > 0:
                lines.append(f"- 추가 가입 여력: 약 {avail:.0f}만원/월 (소득의 15% 적정 한도 기준)")
            else:
                lines.append("- 추가 가입 여력: 거의 없음 — 기존 보험 정비 후 재구성 권장")
    if assets:
        lines.append(f"- 금융자산: {assets:,.0f}만원 (예금·적금·주식 등)")
        if income and assets > income:
            lines.append("  → 자산 여유 있음: 연금보험·저축보험 추가 고려 가능")

    employment = (alt_data.get("employment") or "").strip()
    housing    = (alt_data.get("housing") or "").strip()
    telecom    = (alt_data.get("telecom") or "").strip()
    utility    = (alt_data.get("utility") or "").strip()

    if employment:
        lines.append(f"- 직업 유형: {employment}")
        if employment in ("자영업", "프리랜서"):
            lines.append("  → 소득 변동성 높음: 실손보험·소득보장보험 우선, 저축성 비중 낮춰야")
        elif employment == "무직":
            lines.append("  → 납입 여력 제한: 보험료 저렴한 보장성·간편심사 상품 우선")
        elif employment == "공무원":
            lines.append("  → 공무원 단체보험 중복 확인 후 부족한 보장 보완 추천")
    if housing:
        lines.append(f"- 거주 형태: {housing}")
        if housing == "자가":
            lines.append("  → 자산 기반 안정: 연금·저축보험 포함 포트폴리오 가능")
        elif housing == "월세":
            lines.append("  → 주거비 부담 있음: 월 보험료 부담 낮은 상품 우선 설계")

    bad_payments = []
    if "경험" in telecom:
        bad_payments.append(f"통신비 {telecom}")
    if "경험" in utility:
        bad_payments.append(f"공과금 {utility}")
    if bad_payments:
        lines.append(f"- 납부 이력 경고: {', '.join(bad_payments)}")
        lines.append("  → 간편심사형·무심사형 상품 우선 고려, 일반심사 통과 어려울 수 있음")
    elif telecom == "정상납부" or utility == "정상납부":
        goods = []
        if telecom == "정상납부": goods.append("통신비")
        if utility == "정상납부": goods.append("공과금")
        lines.append(f"- 납부 이력 양호: {'+'.join(goods)} 정상납부 — 대안신용 가점 요소")

    return "\n".join(lines) + "\n\n"


def get_credit_summary_for_prompt(score) -> str:
    """
    오케스트레이터 프롬프트에 삽입할 신용 요약 텍스트 생성.
    score가 None이면 빈 문자열 반환.
    """
    if score is None:
        return ""

    try:
        score = int(score)
    except (TypeError, ValueError):
        return ""

    rec = get_insurance_recommendation_by_credit(score)
    preferred = "·".join(rec["preferred_products"][:4]) if rec["preferred_products"] else "없음"
    avoid = "·".join(rec["avoid_products"][:3]) if rec["avoid_products"] else "없음"
    discount_str = "일부 보험사 우대 할인 가능" if rec["discount_eligibility"] else "우대 할인 해당 없음"

    return f"""## 신용점수 정보 (맞춤 추천 반영)
- 신용점수: {score}점 ({rec['tier']} / {rec.get('grade', '')})
- 추천 상품군: {preferred}
- 신중 검토 상품: {avoid}
- 우대 할인: {discount_str}
- 종합 조언: {rec['advice']}

"""


# ── 약관대출 계산 ──────────────────────────────────────────────

# 보험 종류별 해지환급금 적립률(납입 기간별) + 약관대출 비율
_LOAN_CONFIG: dict[str, dict] = {
    "종신보험":  {"csv": {1: 0.30, 3: 0.55, 5: 0.70, 10: 0.85}, "ratio": 0.85, "note": "비갱신형 기준"},
    "연금보험":  {"csv": {1: 0.75, 3: 0.88, 5: 0.92, 10: 0.96}, "ratio": 0.90, "note": "공시이율형 기준"},
    "변액보험":  {"csv": {1: 0.50, 3: 0.70, 5: 0.80, 10: 0.88}, "ratio": 0.80, "note": "수익률 변동 가능"},
    "저축보험":  {"csv": {1: 0.80, 3: 0.90, 5: 0.94, 10: 0.97}, "ratio": 0.90, "note": "저축성 기준"},
    "유니버셜":  {"csv": {1: 0.60, 3: 0.75, 5: 0.83, 10: 0.90}, "ratio": 0.85, "note": "유니버셜형"},
}

_LOAN_YEARS = [1, 3, 5, 10]


_TYPE_FROM_KW: list[tuple[str, str]] = [
    ("종신", "종신보험"), ("연금", "연금보험"), ("저축", "저축보험"),
    ("변액", "변액보험"), ("유니버셜", "유니버셜보험"),
    ("실손", "실손의료보험"), ("암보험", "암보험"), ("치아", "치아보험"),
    ("간병", "간병·치매보험"), ("치매", "간병·치매보험"),
    ("정기보험", "정기보험"), ("정기", "정기보험"),
]


def _infer_ins_type(text: str) -> str:
    for kw, tp in _TYPE_FROM_KW:
        if kw in text:
            return tp
    return ""


def parse_recommended_products(result_text: str) -> list[dict]:
    """
    GPT 포트폴리오 마크다운 테이블에서 추천 상품 목록을 파싱한다.
    5열(순위|유형|상품명|보험료|이유)과 4열(보험사|상품명|보험료|특징) 형식 모두 지원.
    """
    seen: set[str] = set()
    products: list[dict] = []

    # 보험료 숫자 추출: "48,000원", "남 9,353원", "3,864원/월" 등
    _prem_re = re.compile(r'([\d,]+)\s*원')

    def _strip_md(s: str) -> str:
        return re.sub(r'\*+', '', s).strip()

    def _add(ins_type: str, prod_name: str, premium: int, reason: str) -> None:
        ins_type  = _strip_md(ins_type)
        prod_name = _strip_md(prod_name)
        key = f"{prod_name[:30]}"
        if key in seen or premium < 100:
            return
        seen.add(key)
        if not ins_type or len(ins_type) > 12:
            ins_type = _infer_ins_type(prod_name) or ins_type
        products.append({"type": ins_type, "name": prod_name, "monthly_premium": premium, "reason": reason})

    lines = result_text.split('\n')
    current_section_type = ""  # 현재 섹션 헤더에서 추론된 유형

    for line in lines:
        line = line.strip()
        if not line.startswith('|'):
            # 섹션 헤더(##, ###)에서 보험 유형 추적
            if line.startswith('#'):
                t = _infer_ins_type(line)
                if t:
                    current_section_type = t
            continue

        cells = [c.strip() for c in line.split('|')]
        cells = [c for c in cells if c]  # 빈 셀 제거

        if len(cells) < 3:
            continue
        # 구분선 행 건너뜀
        if all(set(c) <= set('-: ') for c in cells):
            continue

        # 5열 형식: 순위(숫자) | 유형 | 상품명 | 보험료 | 이유
        if cells[0].isdigit() and len(cells) >= 5:
            prem_m = _prem_re.search(cells[3])
            if prem_m:
                try:
                    _add(cells[1], cells[2], int(prem_m.group(1).replace(',', '')), cells[4] if len(cells) > 4 else "")
                except ValueError:
                    pass
            continue

        # 4열 형식: 보험사or유형 | 상품명 | 보험료 | 특징
        if len(cells) >= 4:
            prem_m = _prem_re.search(cells[2])
            if prem_m:
                try:
                    ins_type = _infer_ins_type(cells[1]) or current_section_type or _infer_ins_type(cells[0])
                    _add(ins_type, cells[1], int(prem_m.group(1).replace(',', '')), cells[3] if len(cells) > 3 else "")
                except ValueError:
                    pass

    return products


def calculate_policy_loans(products: list[dict]) -> dict:
    """
    추천 상품 목록에서 약관대출 가능 상품을 분류하고 납입 기간별 예상 대출 한도를 산출한다.

    Returns:
        {
            "eligible":   [{"type", "name", "monthly_wan", "loans": {1:int, 3:int, 5:int, 10:int}, "note"}, ...],
            "ineligible": [{"type", "name", "monthly_wan"}, ...],
            "totals":     {"1": int, "3": int, "5": int, "10": int},
            "has_eligible": bool,
        }
    """
    eligible:   list[dict] = []
    ineligible: list[dict] = []
    totals = {y: 0 for y in _LOAN_YEARS}

    for p in products:
        ins_type = p["type"]
        premium  = p["monthly_premium"]   # 원 단위
        annual   = premium * 12

        config = next(
            (cfg for key, cfg in _LOAN_CONFIG.items() if key in ins_type),
            None
        )

        if config:
            loans: dict[int, int] = {}
            for y in _LOAN_YEARS:
                paid = annual * y
                csv  = paid * config["csv"][y]
                loan = int(csv * config["ratio"])
                loans[y] = loan
                totals[y] += loan
            eligible.append({
                "type": ins_type,
                "name": p["name"],
                "monthly_premium": premium,
                "loans": {str(y): loans[y] for y in _LOAN_YEARS},
                "note": config.get("note", ""),
            })
        else:
            ineligible.append({
                "type": ins_type,
                "name": p["name"],
                "monthly_premium": premium,
            })

    return {
        "eligible":   eligible,
        "ineligible": ineligible,
        "totals":     {str(y): totals[y] for y in _LOAN_YEARS},
        "has_eligible": len(eligible) > 0,
    }


def _score_to_grade(score: int) -> str:
    if score >= 900: return "최우량 (1등급)"
    if score >= 750: return "우량 (2~3등급)"
    if score >= 600: return "보통 (4~6등급)"
    if score >= 450: return "주의 (7~8등급)"
    return "불량 (9~10등급)"


def assess_adverse_selection_risk(
    credit_score: int = 700,
    credit_drop_6m: int = 0,
    insurance_amount_10k: int = 5000,
    recent_checkup_months: int = 12,
    multi_insurer: bool = False,
    sudden_large_policy: bool = False,
) -> dict:
    """
    보험 역선택(Adverse Selection) 위험 지수(AASI) 산출.
    신용점수 급락 + 건강검진 기피 + 고액 보험 동시 신청 패턴으로 역선택 탐지.

    ※ 윤리: 행동 패턴 기반 탐지이며, 질환 자체를 역선택 근거로 사용하지 않음.
    """
    aasi = 0
    flags = []

    if credit_drop_6m >= 100:
        aasi += 40
        flags.append(f"신용점수 6개월 내 {credit_drop_6m}점 급락")
    elif credit_drop_6m >= 50:
        aasi += 20
        flags.append(f"신용점수 6개월 내 {credit_drop_6m}점 하락")

    if recent_checkup_months > 36 and insurance_amount_10k > 5000:
        aasi += 40
        flags.append(f"건강검진 {recent_checkup_months}개월 미수검 + 고액 보험 신청")
    elif recent_checkup_months > 24 and insurance_amount_10k > 3000:
        aasi += 25
        flags.append(f"건강검진 {recent_checkup_months}개월 미수검")

    if multi_insurer:
        aasi += 20
        flags.append("복수 보험사 동시 신청")

    if sudden_large_policy:
        aasi += 15
        flags.append("소액->고액 급격한 보험 전환")

    if credit_score < 600 and insurance_amount_10k > 5000:
        aasi += 10
        flags.append("낮은 신용점수 + 고액 보험 조합")

    if aasi >= 60:
        band, recommendation, color = "고위험", "정밀 심사 필요 — 의료 소견서 추가 제출 요청, 언더라이터 검토", "danger"
    elif aasi >= 35:
        band, recommendation, color = "중위험", "주의 관찰 — 건강검진 수검 이력 확인, 추가 서류 요청 가능", "warning"
    elif aasi >= 15:
        band, recommendation, color = "경계", "모니터링 — 계약 후 청구 패턴 관찰 권고", "caution"
    else:
        band, recommendation, color = "정상", "일반 심사 진행", "normal"

    actions_map = {
        "고위험": ["추가 건강진단서 제출 요청", "의사 소견서 필수", "보험금 초기 지급 모니터링"],
        "중위험": ["건강검진 이력 확인", "기존 보험 계약 조회", "전문 언더라이터 검토"],
        "경계":   ["청구 패턴 사후 모니터링", "6개월 후 재평가"],
        "정상":   ["표준 심사 진행"],
    }

    return {
        "aasi_score": aasi,
        "risk_band": band,
        "risk_color": color,
        "flags": flags if flags else ["이상 신호 없음"],
        "recommendation": recommendation,
        "preventive_actions": actions_map[band],
        "score_context": {
            "credit_score": credit_score,
            "credit_drop_6m": credit_drop_6m,
            "checkup_gap_months": recent_checkup_months,
            "insurance_amount_10k": insurance_amount_10k,
        },
        "ethics_note": "행동 패턴 기반 탐지이며 질환 자체를 역선택 근거로 사용하지 않습니다.",
    }


def simulate_credit_score_improvement(current_score: int) -> dict:
    """
    신용점수 개선 시뮬레이션.
    어떤 조건이 달성되면 어떤 보험·금융 혜택이 열리는지 계산.
    """
    improvement_factors = [
        {"action": "보험료 12개월 정상납부",         "score_gain": 15},
        {"action": "통신비·공과금 12개월 정상납부",  "score_gain": 12},
        {"action": "대출 12개월 정상상환",            "score_gain": 20},
        {"action": "카드 연체 이력 소멸(2년 경과)",  "score_gain": 25},
        {"action": "건강검진 2년 연속 수검",          "score_gain": 10},
        {"action": "소액 대출 상환 완료",             "score_gain": 18},
    ]

    tiers = [
        {
            "threshold": 600,
            "grade": "보통 (4~6등급)",
            "benefits": ["실손의료보험 표준 조건 가입", "암보험 표준 조건 가입", "치아보험 표준 조건 가입"],
        },
        {
            "threshold": 750,
            "grade": "우량 (2~3등급)",
            "benefits": ["비갱신형 종신보험 가입 가능", "변액보험 가입 가능", "보험료 우대 할인 적용", "Health-Credit 금리 인하 1.3%p 효과"],
        },
        {
            "threshold": 900,
            "grade": "최우량 (1등급)",
            "benefits": ["프리미엄 종신보험 최우대 조건", "저축성·변액유니버셜 보험 가입", "보험사 VIP 우대 서비스", "Health-Credit 금리 인하 1.8%p 효과"],
        },
    ]

    scenarios = []
    for tier in tiers:
        if tier["threshold"] <= current_score:
            continue
        gap = tier["threshold"] - current_score
        accumulated = 0
        needed = []
        for f in improvement_factors:
            if accumulated >= gap:
                break
            needed.append(f)
            accumulated += f["score_gain"]
        scenarios.append({
            "target_score": tier["threshold"],
            "target_grade": tier["grade"],
            "gap": gap,
            "improvements_needed": needed,
            "total_achievable": accumulated,
            "achievable": accumulated >= gap,
            "benefits": tier["benefits"],
        })

    return {
        "current_score": current_score,
        "current_grade": _score_to_grade(current_score),
        "scenarios": scenarios,
    }
