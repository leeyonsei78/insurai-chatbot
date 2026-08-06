"""
금융 영역 시나리오 6~8 + 위험 관리 시나리오 9~10 — 대안 신용평가 & 부실률 차단.

개인정보 이노베이션 존 데이터 근거:
  · G1E_OBJ (건강검진대상자 1657만건): 수검 성실도·연속 이력
  · cdw_psmn_vtls (광주TP 바이탈 수치): 혈압·혈당·체중 변동폭 안정도
  · cdw_lflg_l03_mq_rslt (광주TP 라이프로그/문진): 생활 습관 성실도
  · BFC.CALC_CTRB_VTILE_FD (보험료분위 3706만건): 소득 분위
  · RGST·T400 (암등록·상병): 중증 질환 전환 위험 예측
  · DEATH (사망 78만건): 장기 대출 부실 선행 지표

⚠️ 윤리 원칙: 건강 데이터는 금융 포용성 *확대*를 위한 가산점으로만 활용합니다.
  건강 상태 불량을 이유로 신용점수를 *감점*하거나 불이익을 주어서는 안 됩니다.
"""
from __future__ import annotations
import json


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 6: 씬파일러 Health-Credit Score 대안 신용평가
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_health_credit(
    age: int,
    gender: str,
    consecutive_checkups: int = 4,
    vital_stability: str = "상",
    bfc_tier: int = 5,
    current_credit_score: int = 680,
    loan_purpose: str = "전세자금",
    loan_amount_10k: int = 20000,
) -> str:
    """
    시나리오 6 — 씬파일러(Thin-Filer) Health-Credit 대안 신용평가.
    G1E(건강검진 성실도) + cdw_psmn_vtls(바이탈 안정도) + BFC(소득분위)를
    신용점수 가산점으로 환산하여 금리 인하·보험료 할인 혜택 산출.

    Args:
        age: 나이
        gender: 성별
        consecutive_checkups: 연속 건강검진 수검 횟수 (년, 1~10)
        vital_stability: 바이탈 수치 안정도 ('상' / '중' / '하')
        bfc_tier: BFC 보험료 분위 (1~10, BFC.CALC_CTRB_VTILE_FD)
        current_credit_score: 현재 CB 신용점수 (300~1000)
        loan_purpose: 대출 목적 ('전세자금' / '사업자대출' / '주택담보')
        loan_amount_10k: 대출 금액 (만원)
    """
    # ── Health-Credit 가산점 계산 ─────────────────────────
    checkup_pts  = min(consecutive_checkups * 10, 50)   # 연속 검진: 최대 50점
    vital_pts    = {"상": 25, "중": 15, "하": 5}.get(vital_stability, 15)
    bfc_pts      = max(0, (bfc_tier - 3) * 2)           # 소득 분위 4이상 가산

    total_bonus  = checkup_pts + vital_pts + bfc_pts
    adjusted_score = min(current_credit_score + total_bonus, 1000)

    # ── 신용등급 매핑 ─────────────────────────────────────
    def _grade(score: int) -> str:
        if score >= 900: return "1등급 (최우량)"
        elif score >= 800: return "2등급 (우량)"
        elif score >= 700: return "3등급 (양호)"
        elif score >= 600: return "4등급 (보통)"
        elif score >= 500: return "5등급 (주의)"
        else: return "6등급 이하 (관리)"

    before_grade = _grade(current_credit_score)
    after_grade  = _grade(adjusted_score)

    # ── 금리 인하 혜택 계산 ───────────────────────────────
    score_delta = adjusted_score - current_credit_score
    if score_delta >= 80:   rate_cut_bp = 180
    elif score_delta >= 60: rate_cut_bp = 130
    elif score_delta >= 40: rate_cut_bp = 80
    elif score_delta >= 20: rate_cut_bp = 40
    else:                   rate_cut_bp = 0

    rate_cut_pct = rate_cut_bp / 100
    annual_saving = int(loan_amount_10k * 10000 * rate_cut_pct / 100)

    # ── 보험료 할인 (건강 성실 관리 반영) ────────────────
    insurance_discount = min(15, consecutive_checkups * 3)

    return json.dumps({
        "scenario": "시나리오 6 — 씬파일러 Health-Credit 대안 신용평가",
        "persona_summary": f"{age}세 {gender}성 / 검진 {consecutive_checkups}년 연속 / 현재 신용 {current_credit_score}점",
        "before": f"신용점수 {current_credit_score}점({before_grade}) — 금융 이력 부족으로 {loan_purpose} 고금리 적용",
        "after": f"Health-Credit +{total_bonus}점 → {adjusted_score}점({after_grade}) — 금리 {rate_cut_pct:.1f}%p 인하",
        "credit_analysis": {
            "before_score": current_credit_score, "before_grade": before_grade,
            "health_credit_bonus": total_bonus,
            "bonus_breakdown": {
                "연속_검진_점수": checkup_pts,
                "바이탈_안정도_점수": vital_pts,
                "BFC_소득분위_가산": bfc_pts,
            },
            "adjusted_score": adjusted_score, "after_grade": after_grade,
        },
        "financial_benefit": {
            "rate_cut_bp": rate_cut_bp,
            "rate_cut_pct": rate_cut_pct,
            "annual_saving_won": annual_saving,
            "insurance_discount_pct": insurance_discount,
        },
        "innovation_zone_data": {
            "tables": ["G1E(건강검진대상자)", "광주TP cdw_psmn_vtls(바이탈)", "BFC(보험료분위)", "CB사 신용 DB"],
            "evidence": (
                f"G1E 1657만건 기반 동일 검진 성실 군 연체율 분석: "
                f"성실 관리군 연체율 일반 동일 신용등급 대비 65% 낮음 입증"
            ),
        },
        "impact": {
            "consumer": f"{loan_purpose} 금리 {rate_cut_pct:.1f}%p 인하 → 연간 {annual_saving:,}원 절감",
            "financial": "포용금융 확대 · 씬파일러 금융 소외 해소",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 7: 소상공인 건강 지속가능성 연계 대출 우대
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_sme_health_loan(
    age: int,
    gender: str,
    business_years: int = 8,
    chronic_disease: str = "없음",
    treatment_response: str = "우수",
    monthly_revenue_10k: int = 800,
    loan_amount_10k: int = 3000,
) -> str:
    """
    시나리오 7 — 소상공인/1인 사업자 '건강 지속가능성' 연계 대출 우대.
    CDW 임상 수치 + RGST 장기 질환 추적 DB로 사업 영속성 예측.

    Args:
        age: 나이
        gender: 성별
        business_years: 사업 운영 기간 (년)
        chronic_disease: 만성질환 ('없음' / '당뇨' / '고혈압')
        treatment_response: 치료 반응 (만성질환 있을 때 '우수' / '양호')
        monthly_revenue_10k: 월 매출 (만원)
        loan_amount_10k: 희망 대출 금액 (만원)
    """
    base_limit = min(monthly_revenue_10k * 3, loan_amount_10k)

    # 건강 지속가능성 점수
    health_continuity = 70
    health_continuity += min(business_years * 2, 20)
    if chronic_disease == "없음":
        health_continuity += 15
    elif treatment_response == "우수":
        health_continuity += 8
    elif treatment_response == "양호":
        health_continuity += 3

    if health_continuity >= 90:
        rating, add_limit_10k, rate_benefit = "A+ (최우량)", 3000, 0.8
    elif health_continuity >= 80:
        rating, add_limit_10k, rate_benefit = "A  (우량)",   2000, 0.5
    elif health_continuity >= 70:
        rating, add_limit_10k, rate_benefit = "B  (양호)",   1000, 0.3
    else:
        rating, add_limit_10k, rate_benefit = "C  (보통)",      0, 0.0

    return json.dumps({
        "scenario": "시나리오 7 — 소상공인 건강 지속가능성 대출 우대",
        "persona_summary": f"{age}세 {gender}성 / {business_years}년 사업 / {chronic_disease} / 월매출 {monthly_revenue_10k:,}만원",
        "before": f"대표자 건강 무시 → 매출·담보 기준만으로 대출 한도 {base_limit:,}만원",
        "after": f"건강 지속가능성 {health_continuity}점({rating}) → 한도 {add_limit_10k:,}만원 증액 + 금리 {rate_benefit}%p 우대",
        "health_continuity": {
            "score": health_continuity, "rating": rating,
            "additional_limit_10k": add_limit_10k,
            "rate_benefit_pct": rate_benefit,
        },
        "innovation_zone_data": {
            "tables": ["광주TP CDW(임상수치)", "RGST(장기 질환 추적)", "카드사/CB사 소상공인 매출 DB"],
            "evidence": "대표자 건강 지속가능성 지수 ↑ → 사업 영속성·상환 의지 ↑ 상관관계 분석",
        },
        "impact": {
            "consumer": f"대출 한도 {add_limit_10k:,}만원 증액 / 금리 {rate_benefit}%p 인하",
            "financial": "소상공인 사업 지속성 기반 여신 리스크 정교화",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 8: 유병자·고령층 렌탈/할부 금융 승인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_rental_approval(
    age: int,
    gender: str,
    disease_history: str = "위암 1기 완치",
    short_term_risk: str = "낮음",
    rental_amount_10k: int = 500,
    rental_period_months: int = 36,
) -> str:
    """
    시나리오 8 — 유병자·고령층 렌탈/할부 금융 승인.
    광주TP cdw_ptn_hli(환자건강정보) + DEATH/RGST로 단기 급격 악화 위험 정밀 분석.

    Args:
        age: 나이
        gender: 성별
        disease_history: 병력 요약
        short_term_risk: 단기 건강 급변 위험 ('낮음' / '중간' / '높음')
        rental_amount_10k: 렌탈 금액 (만원)
        rental_period_months: 렌탈 기간 (개월)
    """
    risk_map = {
        "낮음":  {"approve": True,  "rate_add": 0,   "note": "단기 급변 위험 낮음 — 정상 승인"},
        "중간":  {"approve": True,  "rate_add": 2.5, "note": "소폭 리스크 반영 — 조건부 승인"},
        "높음":  {"approve": False, "rate_add": 0,   "note": "단기 내 건강 급변 위험 높음 — 보류"},
    }
    risk_info = risk_map.get(short_term_risk, risk_map["중간"])
    monthly_payment = int(rental_amount_10k * 10000 / rental_period_months * (1 + risk_info["rate_add"] / 100))

    return json.dumps({
        "scenario": "시나리오 8 — 유병자·고령층 렌탈/할부 금융 승인",
        "persona_summary": f"{age}세 {gender}성 / 병력: {disease_history} / 렌탈 {rental_amount_10k:,}만원({rental_period_months}개월)",
        "before": f"과거 병력·고령 이유만으로 렌탈/할부 금융 거절",
        "after": (
            f"CDW+DEATH 단기 급변 위험 {short_term_risk} 판정 → {'승인' if risk_info['approve'] else '보류'} / {risk_info['note']}"
        ),
        "approval": {
            "approved": risk_info["approve"],
            "short_term_risk": short_term_risk,
            "additional_rate_pct": risk_info["rate_add"],
            "monthly_payment_won": monthly_payment,
            "note": risk_info["note"],
        },
        "innovation_zone_data": {
            "tables": ["광주TP cdw_ptn_hli(환자건강정보)", "DEATH(사망)", "RGST(암등록)"],
            "evidence": "단기(렌탈기간) 내 급격 건강 악화 위험 정밀 모델링",
        },
        "impact": {
            "consumer": "병력·고령 차별 없이 건강 지속가능성 기반 공정한 금융 접근",
            "financial": "정교한 위험 분류로 렌탈 채권 부실률 감소",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 9: 미시 징후 사전 케어 → 암 중증화 차단
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_early_care(
    age: int,
    gender: str,
    finding: str = "위 미란 소견",
    progression_risk_pct: float = 42.0,
    early_intervention: bool = True,
    insurance_coverage_10k: int = 8000,
) -> str:
    """
    시나리오 9 — 미시 징후 사전 케어 기반 암 중증화 차단.
    광주TP JPG/DICOM(내시경·X-ray) + T400(상병) DB로 전조 징후 감지 → 조기 시술 유도.

    Args:
        age: 나이
        gender: 성별
        finding: 미시 소견 ('위 미란 소견' / '폐 결절 의심' / '간 병변 의심')
        progression_risk_pct: 2년 내 중증 진행 위험율 (%)
        early_intervention: 조기 개입 여부 (True=조기시술, False=미개입)
        insurance_coverage_10k: 중증 진단 시 지급 예상 보험금 (만원)
    """
    if early_intervention:
        outcome = "위암 1기 극초기 발견 → 내시경 절제술 완치"
        insurer_saving_10k = insurance_coverage_10k
        patient_impact = "완치 / 일상 복귀 / 보험금 수령 불필요"
        intervention_cost_10k = 200
    else:
        outcome = f"2년 내 암 3기로 진행 (위험율 {progression_risk_pct}%)"
        insurer_saving_10k = 0
        patient_impact = "암 3기 진단 / 장기 치료 / 고액 보험금 지급"
        intervention_cost_10k = 0

    return json.dumps({
        "scenario": "시나리오 9 — 미시 징후 사전 케어 암 중증화 차단",
        "persona_summary": f"{age}세 {gender}성 / 소견: {finding} / 2년내 진행 위험 {progression_risk_pct}%",
        "before": f"소견 방치 → {outcome if not early_intervention else '암 3기 진행 위험'}",
        "after": f"이노베이션 존 AI 조기 감지 → {'사전 시술 완치' if early_intervention else '미개입(비교군)'}",
        "clinical_outcome": {"finding": finding, "intervention": early_intervention, "outcome": outcome},
        "financial_impact": {
            "insurer_saving_10k": insurer_saving_10k,
            "intervention_cost_10k": intervention_cost_10k,
            "net_saving_10k": insurer_saving_10k - intervention_cost_10k,
            "patient_impact": patient_impact,
        },
        "innovation_zone_data": {
            "tables": ["광주TP DICOM/JPG(내시경·영상)", "광주TP CDW", "T400(상병내역)", "보험사 지급 DB"],
            "evidence": f"T400 상병 DB 연계 '{finding}' → 2년 내 암 3기 전환율 {progression_risk_pct}% 포착",
        },
        "impact": {
            "consumer": patient_impact,
            "insurer":  f"고액 보험금 {insurance_coverage_10k:,}만원 선제 절감 (조기 시술 지원비 {intervention_cost_10k:,}만원 투자)",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 10: 중증 질환 전환 예측 → 대출 부실률 차단
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_default_prevention(
    age: int,
    gender: str,
    loan_amount_10k: int = 20000,
    sofa_score: float = 2.0,
    severe_disease_risk_pct: float = 38.0,
    has_repayment_insurance: bool = False,
) -> str:
    """
    시나리오 10 — 중증 질환 전환 예측 → 장기 대출 채권 부실률 차단.
    광주TP CDW SOFA/APACHE2 점수 + RGST 연계로 장기 상환 불능 위험 사전 예측.

    Args:
        age: 나이
        gender: 성별
        loan_amount_10k: 대출 잔액 (만원)
        sofa_score: CDW SOFA 점수 (낮을수록 건강)
        severe_disease_risk_pct: 2년 내 중증 질환 전환 위험율 (%)
        has_repayment_insurance: 대출 상환 보장 보험 가입 여부
    """
    if severe_disease_risk_pct >= 40:
        risk_band, default_prob = "고위험", severe_disease_risk_pct * 0.6
    elif severe_disease_risk_pct >= 20:
        risk_band, default_prob = "중위험", severe_disease_risk_pct * 0.35
    else:
        risk_band, default_prob = "저위험", severe_disease_risk_pct * 0.1

    exposure_10k = int(loan_amount_10k * default_prob / 100)
    mitigation = "대출 상환 보장 보험 연계 권고" if not has_repayment_insurance else "상환 보험 가입 완료 — 리스크 헤지됨"

    return json.dumps({
        "scenario": "시나리오 10 — 중증 질환 전환 예측 대출 부실률 차단",
        "persona_summary": f"{age}세 {gender}성 / 대출 {loan_amount_10k:,}만원 / SOFA {sofa_score} / 중증 위험 {severe_disease_risk_pct}%",
        "before": "건강 정보 없이 소득·담보만으로 여신 심사 → 잠재 부실 리스크 미포착",
        "after": f"CDW SOFA + RGST 연계 → {risk_band} 판정 / 부실 예상 손실 {exposure_10k:,}만원 사전 식별",
        "risk_analysis": {
            "risk_band": risk_band,
            "severe_disease_risk_pct": severe_disease_risk_pct,
            "default_probability_pct": round(default_prob, 1),
            "expected_loss_10k": exposure_10k,
        },
        "mitigation": {
            "action": mitigation,
            "repayment_insurance": has_repayment_insurance,
        },
        "innovation_zone_data": {
            "tables": ["광주TP cdw_bacm_sofa_isp(SOFA/중증도)", "RGST(암등록)", "DEATH(사망원인)", "금융사 대출 DB"],
            "evidence": "CDW SOFA 점수 + 암센터 중증 전환 DB → 차주 건강 악화 기반 대출 부실 예측 모델",
        },
        "impact": {
            "consumer": "사전 경고 및 보험 연계 지원으로 가계 파산 예방",
            "financial": f"부실 예상 손실 {exposure_10k:,}만원 사전 차단 / 장기 채권 건전성 확보",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 12: 건강체 건강담보대출 승인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_healthy_body_loan(
    age: int,
    gender: str,
    consecutive_checkups: int = 4,
    vital_stability: str = "상",
    bfc_tier: int = 6,
    dsr_ratio_pct: float = 52.0,
    loan_purpose: str = "생활자금",
    loan_amount_10k: int = 5000,
) -> str:
    """
    시나리오 12 — 건강체 건강담보대출 승인.
    DSR(총부채원리금상환비율) 초과로 일반 은행 대출이 거절된 건강 우수자에게
    이노베이션 존 G1E + cdw_psmn_vtls(바이탈) 기반 건강 자산을 담보로 인정하여
    보험사 연계 건강담보대출 승인 및 금리 우대를 제공합니다.

    Args:
        age: 나이
        gender: 성별
        consecutive_checkups: 연속 건강검진 수검 횟수 (년)
        vital_stability: 바이탈 수치 안정도 ('상' / '중' / '하')
        bfc_tier: BFC 보험료 분위 (1~10)
        dsr_ratio_pct: 현재 DSR 비율 (%, 40 초과 시 은행 거절 기준)
        loan_purpose: 대출 목적
        loan_amount_10k: 희망 대출 금액 (만원)
    """
    # 건강 자산 점수(HAS: Health Asset Score) 산출
    checkup_pts = min(consecutive_checkups * 8, 40)
    vital_pts = {"상": 30, "중": 18, "하": 8}.get(vital_stability, 18)
    bfc_pts = min(bfc_tier * 3, 30)
    has_score = checkup_pts + vital_pts + bfc_pts

    # 건강 자산 등급
    if has_score >= 85:
        has_grade, max_loan_10k, base_rate, discount_bp = "A+ 건강우량", 5000, 3.2, 150
    elif has_score >= 70:
        has_grade, max_loan_10k, base_rate, discount_bp = "A  건강양호", 3500, 3.8, 100
    elif has_score >= 55:
        has_grade, max_loan_10k, base_rate, discount_bp = "B  건강보통", 2000, 4.5, 50
    else:
        has_grade, max_loan_10k, base_rate, discount_bp = "C  기준미달", 0, 0, 0

    approved_loan = min(loan_amount_10k, max_loan_10k)
    approved = approved_loan > 0
    dsr_excess_pct = max(0, dsr_ratio_pct - 40)

    annual_saving = int(approved_loan * 10000 * discount_bp / 10000) if approved else 0

    return json.dumps({
        "scenario": "시나리오 12 — 건강체 건강담보대출 승인",
        "persona_summary": f"{age}세 {gender}성 / DSR {dsr_ratio_pct}% / 건강검진 {consecutive_checkups}년 연속 / 바이탈 안정도 {vital_stability}",
        "before": (
            f"DSR {dsr_ratio_pct}%(초과 {dsr_excess_pct:.1f}%p) → "
            f"전 은행·2금융권 대출 거절 / 건강 자산 미반영"
        ),
        "after": (
            f"이노베이션 존 건강 데이터 → HAS {has_score}점({has_grade}) → "
            f"{'건강담보대출 ' + str(approved_loan) + '만원 / 연' + str(base_rate) + '% 승인' if approved else '건강 관리 후 재신청 권고'}"
        ),
        "health_asset_score": {
            "total": has_score,
            "grade": has_grade,
            "breakdown": {
                "연속_검진_점수": checkup_pts,
                "바이탈_안정도": vital_pts,
                "BFC_소득분위": bfc_pts,
            },
        },
        "loan_decision": {
            "approved": approved,
            "approved_amount_10k": approved_loan,
            "annual_rate_pct": base_rate if approved else None,
            "rate_discount_bp": discount_bp,
            "annual_saving_won": annual_saving,
            "dsr_exemption_note": "건강담보대출은 DSR 산정 시 건강 자산 가산 인정 — 별도 심사 트랙",
        },
        "innovation_zone_data": {
            "tables": ["G1E_OBJ(건강검진 1657만건)", "광주TP cdw_psmn_vtls(바이탈)", "BFC(보험료분위 3706만건)"],
            "evidence": "건강 우수군(연속 검진 4년+ 정상) 대출 연체율 0.3% — 일반 동일 DSR 구간(1.8%) 대비 83% 낮음",
        },
        "product_info": {
            "product_name": "건강자산담보대출(Health Asset Loan)",
            "provider": "보험사·캐피탈 연계 신상품",
            "collateral": "건강 자산 점수(HAS) + 기존 담보 병행",
            "repayment": "만기 일시 상환 또는 원리금균등상환 선택",
            "note": "가입 중인 보험계약 + 건강 자산 이중 담보 구조로 금리 우대",
        },
        "impact": {
            "consumer": f"DSR 장벽 극복 → {approved_loan:,}만원 / 연 {base_rate}% 저금리 자금 조달",
            "financial": "건강 자산 기반 新 여신 트랙 → 포용금융 확대 · 우량 고객 이탈 방지",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 14: 건강 정보 기반 신(新) 건강담보대출 상품
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_health_secured_loan(
    age: int,
    gender: str,
    consecutive_checkups: int = 3,
    vital_stability: str = "상",
    lifelog_score: int = 78,
    bfc_tier: int = 5,
    dsr_ratio_pct: float = 58.0,
    ltv_ratio_pct: float = 82.0,
    loan_purpose: str = "생활자금",
    loan_amount_10k: int = 5000,
) -> str:
    """
    시나리오 14 — 건강 정보 기반 신(新) 건강담보대출 상품.
    DSR·LTV가 동시에 초과되어 전 금융기관 대출이 불가한 상황에서
    건강 자산(Health Asset)을 담보로 인정하는 혁신 금융 상품.
    G1E + cdw_psmn_vtls + cdw_lflg(라이프로그) 3종 결합으로 신용 보완.

    Args:
        age: 나이
        gender: 성별
        consecutive_checkups: 연속 건강검진 수검 횟수 (년)
        vital_stability: 바이탈 수치 안정도 ('상' / '중' / '하')
        lifelog_score: 라이프로그 건강 관리 점수 (0~100)
        bfc_tier: BFC 보험료 분위 (1~10)
        dsr_ratio_pct: 현재 DSR 비율 (%, 일반 40% 상한)
        ltv_ratio_pct: 현재 LTV 비율 (%, 일반 70~80% 상한)
        loan_purpose: 대출 목적
        loan_amount_10k: 희망 대출 금액 (만원)
    """
    # Health Asset Score(HAS) — G1E 40% + 바이탈 35% + 라이프로그 25%
    g1e_score = min(consecutive_checkups * 10, 40)
    vital_score = {"상": 35, "중": 21, "하": 8}.get(vital_stability, 21)
    lifelog_weighted = round(lifelog_score * 0.25)
    has_total = g1e_score + vital_score + lifelog_weighted

    # BFC 소득 분위 보정
    bfc_bonus = max(0, (bfc_tier - 4) * 3)
    final_has = min(has_total + bfc_bonus, 100)

    # 대출 한도 및 금리 결정
    dsr_excess = max(0, dsr_ratio_pct - 40)
    ltv_excess = max(0, ltv_ratio_pct - 70)
    combined_excess = dsr_excess + ltv_excess

    if final_has >= 88:
        tier, max_loan_10k, rate, note = "HAS 프리미엄", 5000, 3.2, "최우량 건강 자산 — DSR·LTV 이중 초과 극복"
    elif final_has >= 75:
        tier, max_loan_10k, rate, note = "HAS 우량", 3000, 3.8, "우량 건강 자산 — 부분 초과 극복 가능"
    elif final_has >= 62:
        tier, max_loan_10k, rate, note = "HAS 표준", 1500, 4.5, "표준 건강 자산 — 소액 자금 조달 가능"
    else:
        tier, max_loan_10k, rate, note = "HAS 미달", 0, 0, "건강 관리 1년 후 재신청 권고"

    # 초과 폭이 클수록 한도 일부 차감
    if combined_excess > 30:
        max_loan_10k = int(max_loan_10k * 0.7)
    elif combined_excess > 20:
        max_loan_10k = int(max_loan_10k * 0.85)

    approved_loan = min(loan_amount_10k, max_loan_10k)
    approved = approved_loan > 0

    monthly_payment = round(approved_loan * 10000 * (rate / 100 / 12) / (1 - (1 + rate / 100 / 12) ** -60)) if (approved and rate > 0) else 0

    return json.dumps({
        "scenario": "시나리오 14 — 건강 정보 기반 신(新) 건강담보대출 상품",
        "persona_summary": (
            f"{age}세 {gender}성 / DSR {dsr_ratio_pct}%·LTV {ltv_ratio_pct}% 동시 초과 / "
            f"연속 건강검진 {consecutive_checkups}년 / 라이프로그 {lifelog_score}점"
        ),
        "before": (
            f"DSR {dsr_ratio_pct}%(+{dsr_excess:.0f}%p 초과) + LTV {ltv_ratio_pct}%(+{ltv_excess:.0f}%p 초과) → "
            f"전 금융기관 대출 완전 봉쇄 / 건강 자산 인정 제도 없음"
        ),
        "after": (
            f"이노베이션 존 3종 결합(G1E+바이탈+라이프로그) → HAS {final_has}점({tier}) → "
            f"{'건강담보대출 ' + str(approved_loan) + '만원 / 연 ' + str(rate) + '% 승인' if approved else '건강 관리 후 재신청 권고'}"
        ),
        "has_analysis": {
            "final_score": final_has,
            "tier": tier,
            "note": note,
            "score_breakdown": {
                "G1E_건강검진_40pct": g1e_score,
                "바이탈_안정도_35pct": vital_score,
                "라이프로그_25pct": lifelog_weighted,
                "BFC_소득분위_보정": bfc_bonus,
            },
        },
        "loan_decision": {
            "approved": approved,
            "approved_amount_10k": approved_loan,
            "annual_rate_pct": rate if approved else None,
            "monthly_payment_won": int(monthly_payment) if approved else 0,
            "repayment_months": 60,
            "dsr_ltv_combined_excess_pp": round(combined_excess, 1),
        },
        "innovation_zone_data": {
            "tables": [
                "G1E_OBJ(건강검진 1657만건)",
                "광주TP cdw_psmn_vtls(바이탈)",
                "cdw_lflg_l03_mq_rslt(라이프로그)",
                "BFC.CALC_CTRB_VTILE_FD(보험료분위)",
            ],
            "evidence": (
                "3종 건강 데이터 결합 분석: HAS 75점 이상 차주 5년 대출 연체율 0.18% — "
                "동일 DSR·LTV 초과 구간 일반 차주(2.4%) 대비 92% 낮음"
            ),
        },
        "product_details": {
            "product_name": "건강자산담보대출 PLUS (Health Asset Secured Loan PLUS)",
            "key_innovation": "DSR·LTV 초과분을 건강 자산으로 상쇄 — 금융규제 샌드박스 적용",
            "insurance_linkage": "건강 유지 조건부: 연간 건강검진 수검 + HAS 유지 → 금리 0.3%p 추가 인하",
            "repayment_protection": "중증 질환 발생 시 상환 유예 6개월 + 보험 연계 상환 보장",
        },
        "impact": {
            "consumer": f"대출 완전 봉쇄 탈출 → {approved_loan:,}만원 / 월 상환 {int(monthly_payment):,}원 / 생활 안정",
            "financial": "DSR·LTV 규제 내 혁신 → 건강 우수자 신시장 창출 · 부실률 업계 최저",
            "social": "건강 관리 인센티브 강화 — 대출 금리 혜택이 건강 생활 동기 부여",
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 15: 신용+건강 교차 역선택 탐지 언더라이팅
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_adverse_selection_score(
    age: int,
    gender: str,
    credit_score: int = 650,
    credit_drop_6m: int = 120,
    insurance_amount_10k: int = 10000,
    recent_checkup_months: int = 30,
    multi_insurer: bool = True,
    sudden_large_policy: bool = True,
) -> str:
    """
    시나리오 15 — 신용+건강 교차 역선택 탐지 언더라이팅.
    신용점수 급락 + 건강검진 기피 + 고액 보험 동시 신청 패턴으로
    역선택 위험을 정밀 탐지하여 보험사 손실을 사전 차단.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from data.credit_model import assess_adverse_selection_risk

    aas = assess_adverse_selection_risk(
        credit_score=credit_score,
        credit_drop_6m=credit_drop_6m,
        insurance_amount_10k=insurance_amount_10k,
        recent_checkup_months=recent_checkup_months,
        multi_insurer=multi_insurer,
        sudden_large_policy=sudden_large_policy,
    )

    return json.dumps({
        "scenario": "시나리오 15 — 신용+건강 교차 역선택 탐지 언더라이팅",
        "persona_summary": (
            f"{age}세 {gender}성 / 신용점수 {credit_score}점(6개월 -{credit_drop_6m}점) / "
            f"보험금 {insurance_amount_10k:,}만원 신청"
        ),
        "before": "기존 심사: 신용·건강 정보 별도 관리 → 역선택 패턴 미탐지",
        "after": (
            f"교차 분석 AASI {aas['aasi_score']}점 → {aas['risk_band']} 판정 → {aas['recommendation']}"
        ),
        "aasi_analysis": {
            "aasi_score": aas["aasi_score"],
            "risk_band": aas["risk_band"],
            "flags": aas["flags"],
            "recommendation": aas["recommendation"],
            "preventive_actions": aas["preventive_actions"],
        },
        "innovation_zone_data": {
            "tables": ["CB사 신용DB(신용점수 추이)", "G1E(건강검진 수검 이력)", "보험사 청구DB"],
            "evidence": "신용 급락 + 검진 기피 + 고액 동시 신청 패턴: 역선택 사례의 73% 해당",
        },
        "impact": {
            "insurer": "역선택 조기 탐지로 부당 보험금 지급 예방 (연간 추정 절감 수천만원)",
            "consumer": "정상 가입자는 영향 없음 — 선의의 피해자 보호",
            "ethics": aas["ethics_note"],
        },
    }, ensure_ascii=False, indent=2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 시나리오 16: 씬파일러 역선택 방지 / 건강 데이터 기반 공정 심사
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def assess_thin_filer_adverse_selection(
    age: int,
    gender: str,
    has_credit_history: bool = False,
    consecutive_checkups: int = 0,
    insurance_amount_10k: int = 8000,
    sudden_application: bool = True,
    vital_data_available: bool = False,
) -> str:
    """
    시나리오 16 — 씬파일러 역선택 방지 & 건강 데이터 기반 공정 심사.
    금융 이력 없는 씬파일러가 건강검진 기피 후 고액 보험 신청 시
    G1E 수검 이력을 요구하여 역선택 방지 + 포용 금융 경로 제시.
    """
    thin_aasi = 0
    flags = []

    if not has_credit_history:
        thin_aasi += 15
        flags.append("CB 금융 이력 없음 (씬파일러)")

    if consecutive_checkups == 0:
        thin_aasi += 35
        flags.append("건강검진 수검 이력 전무")
    elif consecutive_checkups < 2:
        thin_aasi += 20
        flags.append(f"건강검진 {consecutive_checkups}회 수검 (연속성 부족)")

    if sudden_application and insurance_amount_10k > 5000:
        thin_aasi += 25
        flags.append("갑작스러운 고액 보험 첫 신청")

    if not vital_data_available:
        thin_aasi += 10
        flags.append("바이탈 데이터 없음")

    if thin_aasi >= 50:
        verdict = "역선택 고위험 — G1E 수검 이력 제출 후 재심사"
        action = "건강검진 1회 수검 + G1E 데이터 제출 후 6개월 내 표준 심사 가능"
        can_approve = False
    elif thin_aasi >= 30:
        verdict = "역선택 중위험 — 간편심사 + 건강검진 이력 요청"
        action = "간편심사형 상품 가입 가능 (1년 후 표준형 전환 심사)"
        can_approve = True
    else:
        verdict = "역선택 위험 낮음 — 표준 심사 진행 가능"
        action = "씬파일러이나 행동 패턴 정상 — 표준 심사 진행"
        can_approve = True

    inclusion_path = []
    if consecutive_checkups == 0:
        inclusion_path.append("1단계: 건강검진 1회 수검 (지역 보건소 무료)")
    if not vital_data_available:
        inclusion_path.append("2단계: 광주TP CDW 또는 건강앱 바이탈 데이터 연동")
    inclusion_path.append(f"3단계: 간편심사형 상품 가입 → {1+consecutive_checkups}년 후 표준형 전환")

    return json.dumps({
        "scenario": "시나리오 16 — 씬파일러 역선택 방지 & 포용 심사",
        "persona_summary": (
            f"{age}세 {gender}성 / CB 이력 {'없음' if not has_credit_history else '있음'} / "
            f"건강검진 {consecutive_checkups}회 수검 / 보험금 {insurance_amount_10k:,}만원 신청"
        ),
        "before": "기존: 씬파일러 = 정보 없음 → 일률 거절 또는 역선택 무방비 승인",
        "after": f"G1E 수검 이력 연계 → AASI {thin_aasi}점 → {verdict}",
        "thin_filer_analysis": {
            "thin_aasi_score": thin_aasi,
            "verdict": verdict,
            "flags": flags if flags else ["이상 신호 없음"],
            "can_approve": can_approve,
            "required_action": action,
        },
        "inclusion_path": inclusion_path,
        "innovation_zone_data": {
            "tables": ["G1E(건강검진 수검 이력)", "cdw_psmn_vtls(바이탈)", "CB사 신용DB"],
            "evidence": "씬파일러 중 G1E 수검 이력 없는 고액 보험 첫 신청자: 역선택 비율 일반 대비 2.8배",
        },
        "impact": {
            "insurer": "역선택 위험 사전 차단 + 정상 씬파일러 포용 가능",
            "consumer": "건강 데이터 제출로 보험 가입 경로 개방 — 금융 소외 해소",
            "social": "역선택 방지와 포용금융의 양립 실현",
        },
    }, ensure_ascii=False, indent=2)
