"""
예외 사유 Enum + 트리거 조건 + 한글 메시지

설계 원칙:
- 전체 판정의 10~20% 이하만 AI 호출 (보수적 기준)
- 기존 rule 판정은 절대 덮어쓰지 않음
- Gemma는 참고용 보조 의견만 제공
"""
from enum import Enum


# ═══════════════════════════════════
# 1. 예외 사유 Enum (DB 저장 + API 응답용)
# ═══════════════════════════════════

class ExceptionReason(str, Enum):
    """AI 보조 호출 트리거 사유 — inspection_results.exception_reason에 저장"""

    # ── 수치형 (numeric) ──
    OCR_CONFIDENCE_LOW = "ocr_confidence_low"            # OCR 신뢰도 기준 이하
    NUMERIC_PARSE_FAILED = "numeric_parse_failed"        # 숫자 파싱 실패
    NEAR_THRESHOLD_BOUNDARY = "near_threshold_boundary"  # 기준값 경계 근처
    REPEATED_CAPTURE_FAILURE = "repeated_capture_failure" # 연속 촬영 실패

    # ── 신호형 (signal) ──
    BRIGHTNESS_AMBIGUOUS = "brightness_ambiguous"        # ON/OFF 밝기 경계
    CHANNEL_CONFLICT = "channel_conflict"                # RGB 채널 간 충돌
    ROI_VARIANCE_HIGH = "roi_variance_high"              # ROI 내 밝기 편차 큼

    # ── 색상형 (color) ──
    COLOR_BOUNDARY_AMBIGUOUS = "color_boundary_ambiguous" # 색상 경계 애매
    HSV_CONFLICT = "hsv_conflict"                        # HSV 분류 충돌
    UNSTABLE_COLOR_DEVIATION = "unstable_color_deviation" # 색상 편차 불안정


class FinalResultSource(str, Enum):
    """최종 판정 결과 출처 — inspection_results.final_result_source"""
    RULE = "rule"                       # 규칙 기반 (기본값, Gemma 미개입)
    AI_ASSIST = "ai_assist"             # 규칙 판정 유지 + Gemma 보조 참조
    MANUAL_CORRECTION = "manual_correction"  # 사용자 수동 보정


# ═══════════════════════════════════
# 2. 한글 설명 매핑 (UI 표시용)
# ═══════════════════════════════════

EXCEPTION_REASON_LABELS = {
    # 수치형
    "ocr_confidence_low": "OCR 인식 신뢰도가 낮습니다",
    "numeric_parse_failed": "숫자를 인식하지 못했습니다",
    "near_threshold_boundary": "기준값 경계 근처입니다 (애매한 값)",
    "repeated_capture_failure": "연속으로 인식에 실패했습니다",
    # 신호형
    "brightness_ambiguous": "밝기가 ON/OFF 경계에 있습니다",
    "channel_conflict": "색상 채널 간 충돌이 감지되었습니다",
    "roi_variance_high": "판독 영역 내 밝기 편차가 큽니다",
    # 색상형
    "color_boundary_ambiguous": "색상 경계가 애매합니다",
    "hsv_conflict": "색상 분류 결과가 불확실합니다",
    "unstable_color_deviation": "색상 값의 편차가 불안정합니다",
}


# ═══════════════════════════════════
# 3. 트리거 조건 (임계값 기준)
# ═══════════════════════════════════
# 보수적 설정: 전체 판정의 약 10~20%만 트리거
# 실운영 데이터로 튜닝 필요

EXCEPTION_THRESHOLDS = {
    # ── 수치형 ──
    "ocr_confidence_low": {
        "threshold": 0.4,       # OCR confidence < 0.4 (40%) 일 때 트리거
        "description": "OCR 신뢰도가 40% 미만",
    },
    "numeric_parse_failed": {
        "threshold": None,      # parsed_value가 None일 때 항상 트리거
        "description": "숫자 파싱 결과가 null",
    },
    "near_threshold_boundary": {
        "margin_pct": 0.08,     # 기준 범위의 8% 이내일 때 트리거
        "description": "값이 min 또는 max의 8% 이내",
        # 예: min=20, max=80 → 범위=60, 마진=4.8
        # 20~24.8 또는 75.2~80 일 때 트리거
    },
    "repeated_capture_failure": {
        "threshold": 3,         # 동일 설비에서 연속 3회 ERROR 시 트리거
        "description": "동일 설비에서 연속 3회 이상 ERROR",
    },

    # ── 신호형 ──
    "brightness_ambiguous": {
        "zone_pct": 0.25,       # ON/OFF 임계값 사이의 중간 25% 구간
        "description": "밝기가 ON/OFF 경계의 중간 25% 구간",
        # 예: off=50, on=150 → 중간=100, zone=25 → 75~125 일 때 트리거
    },
    "channel_conflict": {
        "threshold": 0.15,      # 1위 채널과 2위 채널의 차이가 15% 이내
        "description": "지배 색상 채널 간 차이가 15% 이내",
    },
    "roi_variance_high": {
        "std_threshold": 60,    # ROI 내 밝기 표준편차 > 60
        "description": "ROI 내 밝기 표준편차가 60 초과",
    },

    # ── 색상형 ──
    "color_boundary_ambiguous": {
        "hue_margin": 15,       # H값이 색상 경계에서 ±15° 이내
        "description": "H값이 색상 경계에서 ±15° 이내",
        # 경계: 30(빨/노), 90(노/녹), 150(녹/청), 210(청/파), 270(파/보), 330(보/빨)
    },
    "hsv_conflict": {
        "sat_threshold": 20,    # 채도(S) < 20% 이면 색상 분류 불확실
        "description": "채도(S)가 20% 미만 (무채색에 가까움)",
    },
    "unstable_color_deviation": {
        "h_std_threshold": 30,  # ROI 내 H값 표준편차 > 30°
        "description": "ROI 내 색상(H) 표준편차가 30° 초과",
    },
}


# ═══════════════════════════════════
# 4. 예외 감지 함수 (프론트/백엔드 공용 로직)
# ═══════════════════════════════════

def detect_numeric_exception(
    parsed_value: float | None,
    confidence: float | None,
    rule_min: float | None,
    rule_max: float | None,
) -> str | None:
    """수치형 예외 감지 — 첫 번째 매칭된 사유 반환, 없으면 None"""

    # 1. 파싱 실패
    if parsed_value is None:
        return ExceptionReason.NUMERIC_PARSE_FAILED.value

    # 2. OCR 신뢰도 낮음
    if confidence is not None and confidence < EXCEPTION_THRESHOLDS["ocr_confidence_low"]["threshold"]:
        return ExceptionReason.OCR_CONFIDENCE_LOW.value

    # 3. 경계 근처
    if rule_min is not None and rule_max is not None:
        range_val = rule_max - rule_min
        if range_val > 0:
            margin = range_val * EXCEPTION_THRESHOLDS["near_threshold_boundary"]["margin_pct"]
            if abs(parsed_value - rule_min) <= margin or abs(parsed_value - rule_max) <= margin:
                return ExceptionReason.NEAR_THRESHOLD_BOUNDARY.value

    return None


def detect_signal_exception(
    brightness: int,
    avg_r: int, avg_g: int, avg_b: int,
    on_threshold: int = 150,
    off_threshold: int = 50,
) -> str | None:
    """신호형 예외 감지"""

    # 1. 밝기 경계
    mid = (on_threshold + off_threshold) / 2
    zone = (on_threshold - off_threshold) * EXCEPTION_THRESHOLDS["brightness_ambiguous"]["zone_pct"]
    if mid - zone <= brightness <= mid + zone:
        return ExceptionReason.BRIGHTNESS_AMBIGUOUS.value

    # 2. 채널 충돌 (1위와 2위 색상 채널 차이가 작음) — 밝은 경우만 체크
    if brightness > off_threshold:  # 어두운 영역은 채널 비교 무의미
        channels = sorted([avg_r, avg_g, avg_b], reverse=True)
        if channels[0] > 30:  # 최소 밝기 보장
            diff_ratio = (channels[0] - channels[1]) / channels[0]
            if diff_ratio < EXCEPTION_THRESHOLDS["channel_conflict"]["threshold"]:
                return ExceptionReason.CHANNEL_CONFLICT.value

    return None


def detect_color_exception(
    h: int, s: int, v: int,
    color_mapping: dict | None = None,
) -> str | None:
    """색상형 예외 감지"""

    # 1. 채도 낮음 → 색상 분류 불확실
    if s < EXCEPTION_THRESHOLDS["hsv_conflict"]["sat_threshold"]:
        return ExceptionReason.HSV_CONFLICT.value

    # 2. 색상 경계 근처
    boundaries = [30, 90, 150, 210, 270, 330]
    margin = EXCEPTION_THRESHOLDS["color_boundary_ambiguous"]["hue_margin"]
    for b in boundaries:
        if abs(h - b) <= margin or abs(h - b + 360) <= margin or abs(h - b - 360) <= margin:
            return ExceptionReason.COLOR_BOUNDARY_AMBIGUOUS.value

    return None
