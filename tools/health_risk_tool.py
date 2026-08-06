"""
건강검진 기반 만성질환(당뇨) 위험 예측 → 맞춤 보험 보장 연계 도구.

- 국민건강보험공단 건강검진정보(공개데이터) 스키마로 학습한 로지스틱 모델을
  data/risk_model_params.json 로 로드하여, 별도 ML 의존성 없이 순수 파이썬으로 추론.
  (AUC≈0.78 / 합성 검증. 실데이터 재학습 시 params JSON만 교체하면 됨)
- 예측된 위험 수준 + 임상 플래그를 보험다모아 공시 상품과 연계해
  "위험 → 예방·보장" 추천으로 이어줌.

⚠️ 윤리: 예측 결과는 예방·보장 강화 목적이며, 보험 가입 거절·불이익 근거로
  사용되어서는 안 됨(신청서 윤리 원칙과 동일).
"""
from __future__ import annotations

import json
import math
import os

_PARAMS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "risk_model_params.json")

with open(_PARAMS_PATH, encoding="utf-8") as _f:
    _M = json.load(_f)


def _fill_missing_premiums(products_by_type: dict, age: int, gender: str) -> None:
    """보험료 정보 없음 상품을 GPT-4o로 일괄 추정해 in-place 업데이트."""
    import openai, os as _os

    api_key = _os.getenv("OPENAI_API_KEY")
    if not api_key:
        # .env 파일에서 직접 로드 시도
        try:
            from dotenv import load_dotenv
            load_dotenv(_os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), ".env"))
            api_key = _os.getenv("OPENAI_API_KEY")
        except Exception:
            pass
    if not api_key:
        return

    # 보험료 없는 상품 수집
    missing = []
    for ins_type, data in products_by_type.items():
        if not isinstance(data, dict) or "results" not in data:
            continue
        for idx, p in enumerate(data["results"]):
            if p.get("premium") == "보험료 정보 없음":
                missing.append({
                    "key": f"{ins_type}||{idx}",
                    "ins_type": ins_type,
                    "idx": idx,
                    "company": p.get("company", ""),
                    "product_name": p.get("product_name", ""),
                    "ins_type_label": ins_type,
                    "coverages": p.get("coverages", [])[:2],
                })

    if not missing:
        return

    lines = []
    for m in missing:
        cov = " / ".join(m["coverages"]) if m["coverages"] else ""
        lines.append(
            f'- key={m["key"]!r}  {m["company"]} {m["product_name"]}'
            f'  ({m["ins_type_label"]}){("  보장: " + cov) if cov else ""}'
        )

    prompt = (
        f"아래 보험 상품들의 예상 월 보험료를 {age}세 {gender}성 기준(20년납 표준 조건)으로 추정하세요.\n"
        "보험다모아 공시 수준의 현실적인 금액이어야 합니다.\n\n"
        + "\n".join(lines)
        + '\n\n반드시 JSON 객체로만 답하세요: {"key값": "금액원/월", ...}\n'
        '예시: {"종신보험||0": "85,000원/월"}'
    )

    try:
        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=400,
        )
        estimates: dict = json.loads(resp.choices[0].message.content)
        for m in missing:
            est = estimates.get(m["key"])
            if est:
                products_by_type[m["ins_type"]]["results"][m["idx"]]["premium"] = f"약 {est} (AI 추정)"
    except Exception:
        pass  # 추정 실패 시 기존 "보험료 정보 없음" 유지


def _predict_risk(feat: dict) -> float:
    """표준화 → 로지스틱 → 시그모이드. 누락 피처는 학습 평균으로 대체(영향 0)."""
    z = _M["intercept"]
    for i, name in enumerate(_M["features"]):
        raw = feat.get(name)
        if raw is None:
            raw = _M["mean"][i]          # 결측 → 평균(표준화 후 0)
        std = (raw - _M["mean"][i]) / _M["scale"][i]
        z += _M["coef"][i] * std
    return 1.0 / (1.0 + math.exp(-z))


def _clinical_flags(f: dict) -> list[str]:
    flags = []
    bmi = f.get("bmi")
    if bmi is not None and bmi >= 25:
        flags.append("비만(BMI≥25)")
    if (f.get("sbp") or 0) >= 140 or (f.get("dbp") or 0) >= 90:
        flags.append("고혈압 의심")
    if (f.get("ast") or 0) >= 40 or (f.get("alt") or 0) >= 40 or (f.get("ggt") or 0) >= 77:
        flags.append("간수치 이상")
    if (f.get("tg") or 0) >= 200 or (0 < (f.get("hdl") or 999) < 40):
        flags.append("이상지질혈증 의심")
    if f.get("smoke") == 3:
        flags.append("현재 흡연")
    return flags


# 위험 유형 → 우선 추천 보험 유형(보험다모아 search_insmarket_products enum과 일치)
_RISK_TO_INSURANCE = {
    "당뇨/대사 위험": ["질병보험", "실손의료보험"],
    "고혈압 의심": ["질병보험", "실손의료보험"],
    "간수치 이상": ["질병보험", "실손의료보험"],
    "이상지질혈증 의심": ["질병보험", "실손의료보험"],
    "노년/간병 대비": ["간병·치매보험", "종신보험"],
    "치과 필요": ["치아보험"],
}


def assess_health_risk(
    age: int,
    gender: str,
    height: float = None,
    weight: float = None,
    waist: float = None,
    sbp: float = None,
    dbp: float = None,
    total_cholesterol: float = None,
    triglyceride: float = None,
    hdl: float = None,
    ldl: float = None,
    ast: float = None,
    alt: float = None,
    ggt: float = None,
    smoke: int = None,
    drink: int = None,
    bfc_tier: int = None,
    include_products: bool = True,
) -> str:
    """
    건강검진 수치로 만성질환(당뇨) 위험을 예측하고 맞춤 보험 유형을 추천.

    Args:
        age: 나이
        gender: '남' or '여'
        height: 키(cm), weight: 몸무게(kg)  → BMI 자동 계산
        waist: 허리둘레(cm)
        sbp/dbp: 수축기/이완기 혈압
        total_cholesterol/triglyceride/hdl/ldl: 지질 수치
        ast/alt/ggt: 간 수치
        smoke: 1=비흡연, 2=과거흡연, 3=현재흡연
        drink: 0=비음주, 1=음주
        bfc_tier: BFC 보험료 분위 1~10 (BFC.CALC_CTRB_VTILE_FD, 없으면 None) — 납부 가능 보험료 범위 + 암 위험 통합에 활용
        include_products: True면 보험다모아 실제 상품도 함께 조회
    """
    sex = 1 if str(gender).startswith("남") else 2
    bmi = None
    if height and weight and height > 0:
        bmi = round(weight / ((height / 100) ** 2), 1)

    feat = {
        "age": age, "sex": sex, "bmi": bmi, "waist": waist,
        "sbp": sbp, "dbp": dbp, "tc": total_cholesterol, "tg": triglyceride,
        "hdl": hdl, "ldl": ldl, "ast": ast, "alt": alt, "ggt": ggt,
        "smoke": smoke, "drink": drink,
    }

    risk = _predict_risk(feat)
    if risk >= 0.30:
        band, band_label = "高", "고위험"
    elif risk >= 0.15:
        band, band_label = "中", "중간위험"
    else:
        band, band_label = "低", "저위험"

    flags = _clinical_flags(feat)

    # 추천 보험 유형 결정
    rec_types: list[str] = []
    if band in ("高", "中"):
        rec_types += _RISK_TO_INSURANCE["당뇨/대사 위험"]
    for fl in flags:
        for t in _RISK_TO_INSURANCE.get(fl.split("(")[0].replace(" 의심", " 의심"), []):
            if t not in rec_types:
                rec_types.append(t)
    if age >= 55:
        for t in _RISK_TO_INSURANCE["노년/간병 대비"]:
            if t not in rec_types:
                rec_types.append(t)
    if not rec_types:
        rec_types = ["실손의료보험"]

    result = {
        "input_summary": {
            "age": age, "gender": gender, "bmi": bmi,
            "flags": flags or ["특이소견 없음"],
        },
        "risk_assessment": {
            "target": "당뇨(대사질환) 위험",
            "risk_score": round(risk, 3),
            "risk_band": band_label,
            "model": f"NHIS 건강검진 스키마 로지스틱 (AUC {_M['auc_logistic']})",
        },
        "recommended_insurance_types": rec_types,
        "guidance": (
            "예방(생활습관·정기검진)과 함께 위 보험 유형으로 위험을 보장하세요. "
            "본 예측은 예방·보장 강화를 위한 참고용이며, 가입 거절·불이익 근거가 아닙니다."
        ),
        "disclaimer": "선별용 위험도이며 의학적 진단이 아닙니다. 정확한 진단은 의료기관에서 받으세요.",
    }

    # 이노베이션 존: 암 위험 분석 (RGST/DEATH) + BFC 분위 통합
    try:
        from tools.cancer_risk_tool import assess_cancer_risk
        cancer_raw = assess_cancer_risk(
            age=age, gender=gender, flags=flags, bfc_tier=bfc_tier
        )
        cancer_data = json.loads(cancer_raw)
        result["cancer_risk"] = cancer_data.get("cancer_risk")
        result["bfc_info"]    = cancer_data.get("bfc_info")
        # 암 위험 기반 추천 보험 유형 병합
        for t in cancer_data.get("cancer_rec_types", []):
            if t not in result["recommended_insurance_types"]:
                result["recommended_insurance_types"].append(t)
    except Exception as e:
        result["cancer_risk"] = {"error": str(e)}

    # 위험 유형에 맞는 보험다모아 실제 상품 조회
    if include_products:
        try:
            from tools.excel_search_tool import search_insmarket_products
            if age < 35:
                ag = "30대"
            elif age < 45:
                ag = "40대"
            elif age < 55:
                ag = "50대"
            else:
                ag = "60대"

            # BFC 분위 기반 보험료 상한 계산 (DEATH/BFC 연계)
            budget_max_won = None
            if bfc_tier and 1 <= bfc_tier <= 10:
                try:
                    from data.innovation_zone_ref import BFC_TIERS
                    budget_max_won = BFC_TIERS[bfc_tier]["max_10k"] * 10000
                except Exception:
                    pass

            # 암 위험 기반으로 확장된 추천 유형 사용
            all_rec_types = result.get("recommended_insurance_types", rec_types)
            products = {}
            for t in all_rec_types[:4]:
                try:
                    raw = search_insmarket_products(
                        insurance_type=t, gender=("남" if sex == 1 else "여"),
                        age_group=ag, top_n=3, budget_max=budget_max_won,
                    )
                    products[t] = json.loads(raw) if isinstance(raw, str) else raw
                except Exception as e:
                    products[t] = {"error": str(e)}

            result["insmarket_products"] = products
        except Exception as e:
            result["insmarket_products"] = {"error": f"상품 조회 실패: {e}"}

    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    # 간단 자체 테스트: 48세 남성, 비만+고혈압 경향
    print(assess_health_risk(
        age=48, gender="남", height=172, weight=82, waist=95,
        sbp=145, dbp=92, triglyceride=230, hdl=38, ggt=85, smoke=3, drink=1,
        include_products=False,
    ))
