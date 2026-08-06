"""
개인정보 이노베이션 존 RGST/DEATH/BFC 기반 암 위험 분석 도구.

- RGST(국립암센터 암등록 261만 건) 패턴 → 연령·성별별 암 발생 기저율
- DEATH(사망 78만 건) 연계 → 암종별 5년 생존율
- BFC(자격및보험료 3706만 건) → 소득 분위 기반 납부 가능 보험료 범위
- T400(상병내역) 임상 플래그(흡연·비만·간수치이상 등) → 암 위험 배율 보정

⚠️ 윤리: 예측 결과는 예방·보장 강화 목적이며, 보험 가입 거절·불이익 근거로
  사용되어서는 안 됩니다.
"""
from __future__ import annotations
import json


def _age_group(age: int) -> str:
    if age < 40:
        return "30대"
    elif age < 50:
        return "40대"
    elif age < 60:
        return "50대"
    elif age < 70:
        return "60대"
    else:
        return "70대"


def assess_cancer_risk(
    age: int,
    gender: str,
    flags: list[str] | None = None,
    bfc_tier: int | None = None,
) -> str:
    """
    RGST 패턴 기반 암 위험을 분석하고 BFC 분위 기반 보험료 예산을 제안.

    Args:
        age: 나이 (20~80)
        gender: '남' or '여'
        flags: 임상 플래그 리스트 (assess_health_risk 결과에서 전달)
        bfc_tier: BFC 보험료 분위 (1~10, BFC.CALC_CTRB_VTILE_FD, 없으면 None)

    Returns:
        JSON 문자열 — cancer_risk, bfc_info 포함
    """
    from data.innovation_zone_ref import (
        CANCER_INCIDENCE, CANCER_5YR_SURVIVAL,
        CANCER_RISK_MULTIPLIERS, BFC_TIERS, CANCER_TO_INSURANCE,
    )

    flags = flags or []
    g_key = "남" if str(gender).startswith("남") else "여"
    ag    = _age_group(age)

    base_rates: dict[str, float] = dict(CANCER_INCIDENCE[g_key].get(ag, {}))
    if not base_rates:
        return json.dumps({"error": "해당 연령대 데이터 없음"}, ensure_ascii=False)

    # ── 위험 배율 적용 ─────────────────────────────────────────────────
    adjusted: dict[str, float] = dict(base_rates)
    for flag in flags:
        flag_key = flag.split("(")[0]
        for mkey, mmap in CANCER_RISK_MULTIPLIERS.items():
            if flag_key in mkey or mkey.startswith(flag_key):
                for cancer, mult in mmap.items():
                    if cancer in adjusted:
                        adjusted[cancer] = adjusted[cancer] * mult

    # ── 인구 평균 대비 위험도 ──────────────────────────────────────────
    pop_total = sum(base_rates.values())
    ind_total = sum(adjusted.values())
    risk_ratio = ind_total / pop_total if pop_total > 0 else 1.0

    if risk_ratio >= 1.3:
        band = "고위험"
    elif risk_ratio >= 1.1:
        band = "중위험"
    else:
        band = "저위험"

    # ── 상위 3개 암종 (절대 발생률 기준) ──────────────────────────────
    top3 = sorted(adjusted.items(), key=lambda x: x[1], reverse=True)[:3]

    cancer_list = []
    for cancer, rate in top3:
        surv = CANCER_5YR_SURVIVAL.get(cancer)
        base = base_rates.get(cancer, 0)
        mult = round(rate / base, 2) if base > 0 else 1.0
        cancer_list.append({
            "type":             cancer,
            "rate_per_100k":    round(rate, 1),
            "base_per_100k":    round(base, 1),
            "risk_multiplier":  mult,
            "5yr_survival_pct": surv,
        })

    # ── BFC 분위 정보 ─────────────────────────────────────────────────
    bfc_info = None
    if bfc_tier and 1 <= bfc_tier <= 10:
        t = BFC_TIERS[bfc_tier]
        bfc_info = {
            "tier":           bfc_tier,
            "label":          t["label"],
            "desc":           t["desc"],
            "budget_min_10k": t["min_10k"],
            "budget_max_10k": t["max_10k"],
            "color":          t["color"],
            "guidance": (
                f"월 {t['min_10k']}~{t['max_10k']}만원 범위 내 보험료 상품을 우선 추천합니다."
                if t["max_10k"] < 50
                else f"월 {t['min_10k']}만원 이상 프리미엄 상품도 고려 가능합니다."
            ),
        }

    # ── 추천 보험 유형 (암 위험 기반) ────────────────────────────────
    rec_types = list(CANCER_TO_INSURANCE.get(band, []))

    # DEATH 데이터 연계: 5년 생존율 < 50% 암종이 상위에 있으면 종신·간병보험 추가
    # (간암 38%, 폐암 36%, 췌장암 15% → 사망 위험 높아 종신·간병 필요)
    low_surv = [c for c in cancer_list if (c.get("5yr_survival_pct") or 100) < 50]
    if low_surv:
        for t in ["종신보험", "간병·치매보험"]:
            if t not in rec_types:
                rec_types.append(t)

    return json.dumps({
        "cancer_risk": {
            "band":               band,
            "risk_ratio":         round(risk_ratio, 2),
            "age_group":          ag,
            "gender":             g_key,
            "top3_cancers":       cancer_list,
            "pop_total_per_100k": round(pop_total, 1),
            "ind_total_per_100k": round(ind_total, 1),
            "data_source":        "개인정보 이노베이션 존 — 국립암센터 RGST(암등록 261만건)·DEATH(사망 78만건)",
        },
        "bfc_info":        bfc_info,
        "cancer_rec_types": rec_types,
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    print(assess_cancer_risk(
        age=48, gender="남",
        flags=["비만(BMI≥25)", "간수치 이상", "현재 흡연"],
        bfc_tier=3,
    ))
