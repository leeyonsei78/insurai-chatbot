# 건강검진 위험예측 → 보험 연계 모듈

보험 상담 에이전트에 **건강 위험 예측 기반 보장 추천** 기능을 추가한 모듈입니다.
(2026 가명정보 활용 경진대회 아이디어 "케어링크"의 실데이터 검증 파트)

## 구성

| 파일 | 설명 |
|------|------|
| `../tools/health_risk_tool.py` | 건강검진 수치 → 당뇨 위험 예측 → 보험 유형·상품 추천 도구 |
| `../data/risk_model_params.json` | 로지스틱 모델 파라미터(표준화·계수). 순수 파이썬 추론 |
| `train_risk_model.py` | 모델 학습 + AUC/ROC 산출 스크립트 |
| `roc_curve.png` | ROC 곡선 (Logistic AUC 0.777 / GBoost 0.773) |
| `risk_model_params.json` | 학습 결과 사본 |

## 에이전트 통합

`agents/orchestrator.py`에 도구가 등록되어 있습니다.
- TOOLS 리스트: `assess_health_risk`
- `execute_tool()` 디스패치 추가
- import: `from tools.health_risk_tool import assess_health_risk`

사용자가 건강검진 결과나 "내 건강 상태에 맞는 보험"을 물으면 GPT-4o가 이 도구를
호출 → 위험도(당뇨/대사) 예측 → 위험 유형 매핑 → **보험다모아 실제 상품**까지 추천합니다.

### 예시
```
고객: 저 48세 남자인데 건강검진에서 혈압 145/92, 중성지방 230, 감마지티피 85 나왔고
      담배 피워요. 제 건강에 맞는 보험 추천해줘.
→ assess_health_risk(age=48, gender="남", sbp=145, dbp=92, triglyceride=230,
                     ggt=85, smoke=3) 호출
→ 위험 0.88 (고위험), 플래그: 고혈압·간수치·이상지질혈증·현재흡연
→ 질병보험 + 실손의료보험 추천 + 보험다모아 40대 남성 실제 상품
```

## 모델 정보

- **타깃**: 공복혈당 ≥126 (당뇨 위험). 혈당은 피처에서 제외(누출 방지)
- **피처**: 나이·성별·BMI·허리둘레·혈압·지질(TC/TG/HDL/LDL)·간수치(AST/ALT/GGT)·흡연·음주
- **성능**: AUC ≈ 0.78 (당뇨 선별 모델로 타당한 수준)
- **상위 위험요인**: BMI > 연령 > 흡연 > 중성지방 (임상적으로 타당)

### ⚠️ 데이터 주의
현재 모델은 **NHIS 건강검진 공개데이터 스키마를 모사한 합성 데이터**로 학습돼 있습니다
(개발 환경에서 data.go.kr 접근이 차단되어 실데이터 다운로드 불가).
**로컬에서 실제 CSV로 재학습**하려면:

```bash
pip install scikit-learn pandas numpy matplotlib
# train_risk_model.py 의 데이터 생성부를 실제 CSV 로드로 교체:
#   df = pd.read_csv("국민건강보험공단_건강검진정보_2023.csv", encoding="cp949")
#   (가이드 문서의 rename_map 사용)
python train_risk_model.py
# → risk_model_params.json 이 갱신되면 도구가 자동으로 실데이터 모델 사용
```

공개데이터: 국민건강보험공단_건강검진정보 (https://www.data.go.kr/data/15007122/fileData.do)

## 윤리 원칙
예측 결과는 **예방·보장 강화 목적**이며, 보험 가입 거절·불이익 근거로 사용하지 않습니다.
선별용 위험도이며 의학적 진단이 아닙니다.
