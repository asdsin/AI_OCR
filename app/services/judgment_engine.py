"""
판정 엔진 - PLC 화면 분석 결과에서 정상/경고/이상 판정

판정 전략 (PLC 화면 분석 기반):
1. NUMERIC: SV vs PV 비교 (허용 오차%), 또는 절대 임계값
2. SIGNAL: OK/NG 텍스트 패턴 매칭
3. COLOR: 배경색 HSL 분석 (녹=정상, 주황=경고, 빨강=이상)
4. TABLE: 여러 셀의 SV-PV 편차 종합 판정
"""
import re
import logging
import numpy as np
import cv2
from app.models import MetricType, JudgmentLevel

logger = logging.getLogger(__name__)


class JudgmentResult:
    def __init__(self, level: JudgmentLevel, reason: str,
                 value: float | None = None, details: dict | None = None):
        self.level = level
        self.reason = reason
        self.value = value
        self.details = details or {}

    def to_dict(self):
        return {
            "level": self.level.value,
            "reason": self.reason,
            "value": self.value,
            "details": self.details
        }


class JudgmentEngine:

    def judge_numeric(self, value: float | None, zone_config: dict) -> JudgmentResult:
        """
        수치형 판정
        - target_value + tolerance_pct: SV 대비 PV 편차 판정
        - warn_min/max, error_min/max: 절대 임계값 판정
        """
        if value is None:
            return JudgmentResult(JudgmentLevel.UNKNOWN, "OCR 수치 추출 실패")

        # SV vs PV 비교 (우선)
        target = zone_config.get("target_value")
        tolerance = zone_config.get("tolerance_pct")
        if target is not None and tolerance is not None and target != 0:
            deviation_pct = abs(value - target) / abs(target) * 100
            if deviation_pct <= tolerance:
                return JudgmentResult(
                    JudgmentLevel.OK,
                    f"PV={value}, SV={target}, 편차={deviation_pct:.1f}% (허용 {tolerance}%)",
                    value,
                    {"target": target, "deviation_pct": deviation_pct}
                )
            elif deviation_pct <= tolerance * 1.5:
                return JudgmentResult(
                    JudgmentLevel.WARNING,
                    f"PV={value}, SV={target}, 편차={deviation_pct:.1f}% (허용 {tolerance}% 초과)",
                    value,
                    {"target": target, "deviation_pct": deviation_pct}
                )
            else:
                return JudgmentResult(
                    JudgmentLevel.NG,
                    f"PV={value}, SV={target}, 편차={deviation_pct:.1f}% (허용의 1.5배 초과)",
                    value,
                    {"target": target, "deviation_pct": deviation_pct}
                )

        # 절대 임계값 판정
        error_min = zone_config.get("error_min")
        error_max = zone_config.get("error_max")
        warn_min = zone_config.get("warn_min")
        warn_max = zone_config.get("warn_max")

        # NG 판정
        if error_max is not None and value >= error_max:
            return JudgmentResult(JudgmentLevel.NG, f"값 {value} >= 이상상한 {error_max}", value)
        if error_min is not None and value <= error_min:
            return JudgmentResult(JudgmentLevel.NG, f"값 {value} <= 이상하한 {error_min}", value)

        # WARNING 판정
        if warn_max is not None and value >= warn_max:
            return JudgmentResult(JudgmentLevel.WARNING, f"값 {value} >= 경고상한 {warn_max}", value)
        if warn_min is not None and value <= warn_min:
            return JudgmentResult(JudgmentLevel.WARNING, f"값 {value} <= 경고하한 {warn_min}", value)

        return JudgmentResult(JudgmentLevel.OK, f"값 {value} 정상 범위", value)

    def judge_signal(self, text: str, zone_config: dict) -> JudgmentResult:
        """신호형 판정 - OK/NG 패턴 매칭"""
        if not text:
            return JudgmentResult(JudgmentLevel.UNKNOWN, "OCR 텍스트 없음")

        normalized = text.strip().upper()
        ok_patterns = zone_config.get("ok_patterns", ["OK", "PASS", "RUN", "ON", "정상", "합격"])
        ng_patterns = zone_config.get("ng_patterns", ["NG", "FAIL", "STOP", "OFF", "이상", "불합격", "ERROR"])

        for pat in ng_patterns:
            if pat.upper() in normalized:
                return JudgmentResult(JudgmentLevel.NG, f"NG 패턴 '{pat}' 감지: {text}")

        for pat in ok_patterns:
            if pat.upper() in normalized:
                return JudgmentResult(JudgmentLevel.OK, f"OK 패턴 '{pat}' 감지: {text}")

        return JudgmentResult(JudgmentLevel.UNKNOWN, f"판정 불가 텍스트: {text}")

    def judge_color(self, img_crop: np.ndarray) -> JudgmentResult:
        """색상형 판정 - 영역의 지배 색상으로 상태 판정"""
        if img_crop is None or img_crop.size == 0:
            return JudgmentResult(JudgmentLevel.UNKNOWN, "이미지 영역 없음")

        # BGR → HSV
        hsv = cv2.cvtColor(img_crop, cv2.COLOR_BGR2HSV)
        avg_h = float(np.mean(hsv[:, :, 0]))
        avg_s = float(np.mean(hsv[:, :, 1]))
        avg_v = float(np.mean(hsv[:, :, 2]))

        details = {"avg_hue": avg_h, "avg_sat": avg_s, "avg_val": avg_v}

        # 채도 낮으면 무채색 (회색/흰/검) → 판정 불가
        if avg_s < 30:
            return JudgmentResult(JudgmentLevel.UNKNOWN, "무채색 영역 (판정 불가)", details=details)

        # HSV Hue 기반 판정 (OpenCV: 0~180)
        # 녹색: 35~85 → OK
        if 35 <= avg_h <= 85:
            return JudgmentResult(JudgmentLevel.OK, f"녹색 감지 (H={avg_h:.0f})", details=details)
        # 노랑/주황: 15~35 → WARNING
        elif 15 <= avg_h < 35:
            return JudgmentResult(JudgmentLevel.WARNING, f"주황/노랑 감지 (H={avg_h:.0f})", details=details)
        # 빨강: 0~15 or 160~180 → NG
        elif avg_h < 15 or avg_h > 160:
            return JudgmentResult(JudgmentLevel.NG, f"빨강 감지 (H={avg_h:.0f})", details=details)
        # 파랑: 85~130 → 보통 정보 표시
        elif 85 <= avg_h <= 130:
            return JudgmentResult(JudgmentLevel.OK, f"파랑 감지 (H={avg_h:.0f}, 정보)", details=details)
        else:
            return JudgmentResult(JudgmentLevel.UNKNOWN, f"미분류 색상 (H={avg_h:.0f})", details=details)

    def judge_zone(self, ocr_text: str, ocr_value: float | None,
                   img_crop: np.ndarray | None, zone_config: dict) -> JudgmentResult:
        """영역 종합 판정 - 타입에 따라 적절한 판정 로직 호출"""
        metric_type = zone_config.get("metric_type", MetricType.NUMERIC)

        if metric_type == MetricType.NUMERIC or metric_type == MetricType.TABLE:
            result = self.judge_numeric(ocr_value, zone_config)
        elif metric_type == MetricType.SIGNAL:
            result = self.judge_signal(ocr_text, zone_config)
        elif metric_type == MetricType.COLOR:
            result = self.judge_color(img_crop)
        else:
            result = self.judge_numeric(ocr_value, zone_config)

        # 색상 보조 판정: 수치 판정 + 색상 교차 검증
        if metric_type in (MetricType.NUMERIC, MetricType.TABLE) and img_crop is not None:
            color_result = self.judge_color(img_crop)
            if color_result.level != JudgmentLevel.UNKNOWN:
                result.details["color_check"] = color_result.to_dict()
                # 색상이 NG인데 수치가 OK면 경고로 올림
                if color_result.level == JudgmentLevel.NG and result.level == JudgmentLevel.OK:
                    result.level = JudgmentLevel.WARNING
                    result.reason += f" (색상 이상 감지: {color_result.reason})"

        return result

    def judge_overall(self, zone_results: list[JudgmentResult]) -> JudgmentLevel:
        """전체 판정 - 가장 심각한 레벨"""
        levels = [r.level for r in zone_results]
        if JudgmentLevel.NG in levels:
            return JudgmentLevel.NG
        if JudgmentLevel.WARNING in levels:
            return JudgmentLevel.WARNING
        if JudgmentLevel.OK in levels:
            return JudgmentLevel.OK
        return JudgmentLevel.UNKNOWN


judgment_engine = JudgmentEngine()
