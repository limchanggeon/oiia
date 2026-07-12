"""승객 유형별 요금 계산 (FR-5, §0 승객 유형 정의).

원칙:
- 노약자 = 만 65세 이상. 사업자별 경로우대 할인율을 적용한다.
- 학생 할인은 **확인된 사업자 규칙이 있을 때만** 적용하고,
  규칙이 없으면 성인 운임을 적용하고 "학생 할인 미적용"을 표시한다 (§0).
- 요금 판단은 코드가 한다 — LLM은 요금을 만들거나 바꾸지 않는다 (§4 LLM 비고).

[실연동 교체 지점] 아래 할인율은 각 사업자 공표 기준으로 검증·갱신해야 한다.
현재 값은 시연용 근사치이며, 확인되지 않은 규칙은 None으로 두어 자동으로
'미적용 + 성인 운임'이 되도록 설계했다.
"""
from typing import Any, Dict, List, Optional

# mode → {senior: 할인율, student: 할인율 or None(=규칙 미확인)}
# 할인율 0.3 = 30% 할인
DISCOUNTS: Dict[str, Dict[str, Optional[float]]] = {
    "KTX": {"senior": 0.3, "student": None},        # 코레일 경로우대 30% (주중 기준), 학생 정기권 외 상시 할인 규칙 미확인
    "ITX-새마을": {"senior": 0.3, "student": None},
    "SRT": {"senior": 0.3, "student": None},
    "고속버스": {"senior": 0.0, "student": 0.1},     # 고속버스 학생(중고생) 10% — 사업자 공통 규칙
    "시외버스": {"senior": 0.0, "student": 0.2},     # 시외버스 학생(중고생) 20%
}

_DEFAULT = {"senior": 0.0, "student": None}


def _apply(base: int, rate: Optional[float]) -> int:
    if not rate:
        return base
    return int(round(base * (1 - rate) / 100) * 100)  # 100원 단위 반올림


def compute(legs: List[Dict[str, Any]], passengers: Dict[str, int]) -> Dict[str, Any]:
    """구간별 정가(성인 기준)를 승객 유형별로 환산해 총요금을 계산한다."""
    senior_n = passengers.get("senior", 0)
    adult_n = passengers.get("adult", 0)
    student_n = passengers.get("student", 0)

    senior_each = adult_each = student_each = 0
    student_rule_known = True
    notes: List[str] = []

    for leg in legs:
        base = leg["fare"]
        rules = DISCOUNTS.get(leg["mode"], _DEFAULT)
        adult_each += base
        senior_each += _apply(base, rules.get("senior"))
        s_rate = rules.get("student")
        if s_rate is None:
            student_rule_known = False
            student_each += base            # 규칙 미확인 → 성인 운임
        else:
            student_each += _apply(base, s_rate)

    if student_n > 0 and not student_rule_known:
        notes.append("학생 할인 미적용")     # §0 — 화면에 그대로 표시
    if senior_n > 0:
        senior_modes = {l["mode"] for l in legs if (DISCOUNTS.get(l["mode"], _DEFAULT).get("senior") or 0) > 0}
        if not senior_modes:
            notes.append("노약자 할인 미적용")

    senior_total = senior_each * senior_n
    adult_total = adult_each * adult_n
    student_total = student_each * student_n

    return {
        "seniorEach": senior_each,
        "adultEach": adult_each,
        "studentEach": student_each,
        "seniorTotal": senior_total,
        "adultTotal": adult_total,
        "studentTotal": student_total,
        "total": senior_total + adult_total + student_total,
        "studentDiscountApplied": student_rule_known and student_n > 0,
        "notes": notes,
    }
