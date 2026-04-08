"""
예외 라우팅 서비스 — Gemma 보조 판정 필요 여부 판단

절대 원칙:
- 기존 rule 판정 결과(judgment_result)를 변경하지 않음
- 예외 조건에 해당하는 경우만 should_call_ai=True 반환
- Gemma 호출은 이 서비스 이후 별도 단계에서 수행

흐름:
  [촬영] → [OCR] → [규칙 판정] → [결과 저장]
                                      ↓
                               [exception_router]
                                      ↓
                              should_call_ai? → YES → Gemma 호출
                                              → NO  → 종료
"""
import json
import logging
from dataclasses import dataclass
from app.models.enums import (
    ExceptionReason, EXCEPTION_THRESHOLDS, EXCEPTION_REASON_LABELS,
    detect_numeric_exception, detect_signal_exception, detect_color_exception,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════
# 설정값 (하드코딩 대신 분리 — 추후 API로 변경 가능)
# ═══════════════════════════════════

EXCEPTION_CONFIG = {
    # 전역 설정
    "enabled": True,                    # 예외 라우팅 활성화 여부
    "max_ai_call_ratio": 0.20,         # AI 호출 비율 상한 (20%)

    # 수치형 임계값
    "numeric": {
        "confidence_threshold": EXCEPTION_THRESHOLDS["ocr_confidence_low"]["threshold"],       # 0.4
        "boundary_margin_pct": EXCEPTION_THRESHOLDS["near_threshold_boundary"]["margin_pct"],   # 0.08
        "repeated_failure_count": EXCEPTION_THRESHOLDS["repeated_capture_failure"]["threshold"], # 3
    },

    # 신호형 임계값
    "signal": {
        "ambiguous_zone_pct": EXCEPTION_THRESHOLDS["brightness_ambiguous"]["zone_pct"],   # 0.25
        "channel_conflict_threshold": EXCEPTION_THRESHOLDS["channel_conflict"]["threshold"], # 0.15
        "roi_variance_std": EXCEPTION_THRESHOLDS["roi_variance_high"]["std_threshold"],    # 60
    },

    # 색상형 임계값
    "color": {
        "hue_boundary_margin": EXCEPTION_THRESHOLDS["color_boundary_ambiguous"]["hue_margin"],  # 15
        "sat_threshold": EXCEPTION_THRESHOLDS["hsv_conflict"]["sat_threshold"],                  # 20
        "h_std_threshold": EXCEPTION_THRESHOLDS["unstable_color_deviation"]["h_std_threshold"],  # 30
    },
}


# ═══════════════════════════════════
# 응답 데이터 구조
# ═══════════════════════════════════

@dataclass
class ExceptionRouteResult:
    """예외 라우팅 결과"""
    exception_flag: bool          # 예외 조건 해당 여부
    exception_reason: str | None  # 예외 사유 코드 (ExceptionReason 값)
    exception_message: str | None # 한글 메시지 (UI 표시용)
    should_call_ai: bool          # Gemma 호출 필요 여부
    context: dict                 # 추가 컨텍스트 (Gemma 프롬프트용)

    def to_dict(self) -> dict:
        return {
            "exception_flag": self.exception_flag,
            "exception_reason": self.exception_reason,
            "exception_message": self.exception_message,
            "should_call_ai": self.should_call_ai,
            "context": self.context,
        }


# ═══════════════════════════════════
# 판정 타입별 예외 체크 함수
# ═══════════════════════════════════

def check_numeric_exception(
    parsed_value: float | None,
    confidence: float | None,
    min_val: float | None,
    max_val: float | None,
) -> ExceptionRouteResult:
    """수치형 예외 체크"""
    reason = detect_numeric_exception(parsed_value, confidence, min_val, max_val)

    if reason is None:
        return ExceptionRouteResult(
            exception_flag=False, exception_reason=None,
            exception_message=None, should_call_ai=False,
            context={"parsed_value": parsed_value, "confidence": confidence},
        )

    return ExceptionRouteResult(
        exception_flag=True,
        exception_reason=reason,
        exception_message=EXCEPTION_REASON_LABELS.get(reason, reason),
        should_call_ai=True,
        context={
            "parsed_value": parsed_value,
            "confidence": confidence,
            "rule_min": min_val,
            "rule_max": max_val,
            "trigger": reason,
        },
    )


def check_signal_exception(
    avg_brightness: int,
    rgb_values: dict,  # {"r": int, "g": int, "b": int}
    on_threshold: int = 150,
    off_threshold: int = 50,
) -> ExceptionRouteResult:
    """신호형 예외 체크"""
    reason = detect_signal_exception(
        brightness=avg_brightness,
        avg_r=rgb_values.get("r", 0),
        avg_g=rgb_values.get("g", 0),
        avg_b=rgb_values.get("b", 0),
        on_threshold=on_threshold,
        off_threshold=off_threshold,
    )

    if reason is None:
        return ExceptionRouteResult(
            exception_flag=False, exception_reason=None,
            exception_message=None, should_call_ai=False,
            context={"brightness": avg_brightness},
        )

    return ExceptionRouteResult(
        exception_flag=True,
        exception_reason=reason,
        exception_message=EXCEPTION_REASON_LABELS.get(reason, reason),
        should_call_ai=True,
        context={
            "brightness": avg_brightness,
            "rgb": rgb_values,
            "on_threshold": on_threshold,
            "off_threshold": off_threshold,
            "trigger": reason,
        },
    )


def check_color_exception(
    detected_color: str,
    hsv_values: dict,  # {"h": int, "s": int, "v": int}
    color_mapping: dict | None = None,
) -> ExceptionRouteResult:
    """색상형 예외 체크"""
    reason = detect_color_exception(
        h=hsv_values.get("h", 0),
        s=hsv_values.get("s", 0),
        v=hsv_values.get("v", 0),
        color_mapping=color_mapping,
    )

    if reason is None:
        return ExceptionRouteResult(
            exception_flag=False, exception_reason=None,
            exception_message=None, should_call_ai=False,
            context={"detected_color": detected_color},
        )

    return ExceptionRouteResult(
        exception_flag=True,
        exception_reason=reason,
        exception_message=EXCEPTION_REASON_LABELS.get(reason, reason),
        should_call_ai=True,
        context={
            "detected_color": detected_color,
            "hsv": hsv_values,
            "color_mapping": color_mapping,
            "trigger": reason,
        },
    )


# ═══════════════════════════════════
# 메인 라우터: 판정 결과 → 예외 체크
# ═══════════════════════════════════

def route_exception(
    judgment_type: str,
    judgment_result: str,
    parsed_value: float | None = None,
    confidence: float | None = None,
    rule: dict | None = None,
    signal_data: dict | None = None,
) -> ExceptionRouteResult:
    """
    메인 예외 라우터 — 판정 결과를 받아 Gemma 호출 필요 여부 판단

    Args:
        judgment_type: "numeric" / "signal" / "color"
        judgment_result: "OK" / "NG" / "ERROR"
        parsed_value: OCR 파싱 값 (수치형)
        confidence: OCR 신뢰도
        rule: 판정 규칙 dict (min_value, max_value, signal_on_threshold 등)
        signal_data: 신호/색상 분석 데이터 (avgR, avgG, avgB, brightness, hsv 등)

    Returns:
        ExceptionRouteResult
    """
    # 비활성화 시 항상 통과
    if not EXCEPTION_CONFIG["enabled"]:
        return ExceptionRouteResult(
            exception_flag=False, exception_reason=None,
            exception_message=None, should_call_ai=False,
            context={},
        )

    rule = rule or {}

    # ERROR 판정은 항상 예외
    if judgment_result == "ERROR":
        reason = ExceptionReason.NUMERIC_PARSE_FAILED.value if judgment_type == "numeric" else "error_judgment"
        return ExceptionRouteResult(
            exception_flag=True,
            exception_reason=reason,
            exception_message=EXCEPTION_REASON_LABELS.get(reason, "판정 오류가 발생했습니다"),
            should_call_ai=True,
            context={"judgment_result": judgment_result, "trigger": "error_judgment"},
        )

    # 타입별 분기
    if judgment_type == "numeric":
        return check_numeric_exception(
            parsed_value=parsed_value,
            confidence=confidence,
            min_val=rule.get("min_value"),
            max_val=rule.get("max_value"),
        )

    elif judgment_type == "signal":
        sd = signal_data or {}
        return check_signal_exception(
            avg_brightness=sd.get("brightness", 0),
            rgb_values={"r": sd.get("avgR", 0), "g": sd.get("avgG", 0), "b": sd.get("avgB", 0)},
            on_threshold=rule.get("signal_on_threshold", 150),
            off_threshold=rule.get("signal_off_threshold", 50),
        )

    elif judgment_type == "color":
        sd = signal_data or {}
        hsv = sd.get("hsv", {})
        mapping = {}
        if rule.get("color_mapping_json"):
            try:
                mapping = json.loads(rule["color_mapping_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        return check_color_exception(
            detected_color=sd.get("dominantColor", "unknown"),
            hsv_values={"h": hsv.get("h", 0), "s": hsv.get("s", 0), "v": hsv.get("v", 0)},
            color_mapping=mapping,
        )

    # 알 수 없는 타입
    return ExceptionRouteResult(
        exception_flag=False, exception_reason=None,
        exception_message=None, should_call_ai=False,
        context={"judgment_type": judgment_type},
    )
