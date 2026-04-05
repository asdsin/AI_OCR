"""
스마트 OCR - 영역 좌표 없이도 PLC 화면에서 수치값을 자동 추출
EasyOCR의 바운딩 박스를 활용하여 수치값 위치를 자동 매핑

전략:
1. 화면 전체 OCR 실행
2. 수치값(XX.X 패턴) 감지
3. 레이블(MAX, 현재, SV 등) 감지
4. 근접한 레이블-값 쌍 매칭
5. 임계값과 비교하여 판정
"""
import re
import logging
import time
import numpy as np
import cv2
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DetectedValue:
    text: str
    value: float
    confidence: float
    cx_pct: float  # 중심 x (% of screen width)
    cy_pct: float  # 중심 y (% of screen height)
    bbox: list     # 원본 바운딩 박스


@dataclass
class SmartOcrResult:
    values: list[DetectedValue]
    labels: list[dict]
    screen_shape: tuple
    processing_ms: int
    engine: str


class SmartOcrService:
    def __init__(self):
        self._reader = None

    def _get_reader(self):
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(['ko', 'en'], gpu=False, verbose=False)
        return self._reader

    def extract_values(self, screen_img: np.ndarray) -> SmartOcrResult:
        """화면 이미지에서 모든 수치값을 자동 추출"""
        start = time.time()
        h, w = screen_img.shape[:2]

        reader = self._get_reader()
        results = reader.readtext(screen_img)

        values = []
        labels = []

        for bbox, text, conf in results:
            pts = np.array(bbox)
            cx = float(np.mean(pts[:, 0])) / w * 100
            cy = float(np.mean(pts[:, 1])) / h * 100

            # 노이즈 필터: 레이블/날짜/시간 제외
            text_clean = text.strip()
            is_noise = (
                re.search(r'#\d+-\d+', text_clean) or      # #1-2 HEATER 등
                re.search(r'\d{4}[/\-]\d{2}', text_clean) or  # 날짜 2026/03/13
                re.search(r'\d{1,2}\s*:\s*\d{2}', text_clean) or  # 시간 11:05, 11 : 05
                re.search(r'HEATER|MAIN|LIST|PANEL', text_clean, re.I) or
                re.search(r'^[A-Z]상$', text_clean) or      # S상, T상 등 레이블
                re.search(r'^[RST]상', text_clean)
            )

            # 수치값 검출 (XX.X 패턴 우선)
            nums = re.findall(r'(\d{1,3}\.\d+)', text_clean)
            if not nums:
                # 정수형 (2~3자리만, 1자리는 노이즈)
                nums = re.findall(r'(?<!\d)(\d{2,3})(?!\d)', text_clean)

            if nums and conf > 0.2 and not is_noise:
                val = float(nums[0])
                # PLC 전류/온도 범위 필터 (10 ~ 300)
                if 10 <= val <= 300:
                    values.append(DetectedValue(
                        text=text_clean,
                        value=val,
                        confidence=conf,
                        cx_pct=round(cx, 1),
                        cy_pct=round(cy, 1),
                        bbox=bbox
                    ))

            # 레이블 검출
            text_upper = text.strip().upper()
            for pattern in ['MAX', 'MIN', 'SV', 'PV', 'FV', 'HEATER', '#']:
                if pattern in text_upper:
                    labels.append({
                        'text': text.strip(),
                        'cx_pct': round(cx, 1),
                        'cy_pct': round(cy, 1),
                        'type': pattern
                    })
                    break

        elapsed = int((time.time() - start) * 1000)
        return SmartOcrResult(
            values=values,
            labels=labels,
            screen_shape=(h, w),
            processing_ms=elapsed,
            engine='easyocr'
        )

    def extract_all(self, screen_img: np.ndarray) -> list[dict]:
        """
        기준 사진 분석용 — 감지된 모든 텍스트를 위치+크기와 함께 반환
        수치/텍스트/레이블 구분하여 사용자가 시각적으로 선택할 수 있게
        """
        h, w = screen_img.shape[:2]
        reader = self._get_reader()
        results = reader.readtext(screen_img)

        items = []
        for bbox, text, conf in results:
            if conf < 0.15 or not text.strip():
                continue

            pts = np.array(bbox)
            x_min, y_min = float(pts[:, 0].min()), float(pts[:, 1].min())
            x_max, y_max = float(pts[:, 0].max()), float(pts[:, 1].max())
            cx = (x_min + x_max) / 2 / w * 100
            cy = (y_min + y_max) / 2 / h * 100
            bw = (x_max - x_min) / w * 100
            bh = (y_max - y_min) / h * 100

            text_clean = text.strip()

            # 수치 추출 시도
            nums = re.findall(r'(\d{1,4}\.?\d*)', text_clean)
            value = float(nums[0]) if nums else None
            is_numeric = value is not None and 0.1 <= value <= 9999

            items.append({
                "text": text_clean,
                "value": value if is_numeric else None,
                "is_numeric": is_numeric,
                "cx_pct": round(cx, 1),
                "cy_pct": round(cy, 1),
                "w_pct": round(bw, 1),
                "h_pct": round(bh, 1),
                "confidence": round(conf, 3),
            })

        return items

    def judge_with_profile(self, ocr_result: SmartOcrResult, profile_items: list[dict]) -> dict:
        """
        저장된 프로필 기반 판정
        profile_items: [{value_range_min, value_range_max, condition, condition_value, ...}]
        """
        results = []
        overall = 'ok'

        for v in ocr_result.values:
            matched_rule = None
            for rule in profile_items:
                vmin = rule.get('value_range_min')
                vmax = rule.get('value_range_max')
                if vmin is not None and vmax is not None:
                    if vmin <= v.value <= vmax:
                        matched_rule = rule
                        break

            if not matched_rule:
                # 매칭되는 규칙 없음 → 무시
                continue

            cond = matched_rule.get('condition', 'range')
            level = 'ok'
            reason = ''

            if cond == 'range':
                ok_min = matched_rule.get('ok_min', float('-inf'))
                ok_max = matched_rule.get('ok_max', float('inf'))
                if ok_min <= v.value <= ok_max:
                    level = 'ok'
                    reason = f'{v.value:.1f} 정상범위 ({ok_min}~{ok_max})'
                else:
                    level = 'ng'
                    reason = f'{v.value:.1f} 범위이탈 ({ok_min}~{ok_max})'
            elif cond == 'min':
                threshold = matched_rule.get('threshold', 0)
                if v.value >= threshold:
                    level = 'ok'; reason = f'{v.value:.1f} >= {threshold}'
                else:
                    level = 'ng'; reason = f'{v.value:.1f} < {threshold}'
            elif cond == 'max':
                threshold = matched_rule.get('threshold', 999)
                if v.value <= threshold:
                    level = 'ok'; reason = f'{v.value:.1f} <= {threshold}'
                else:
                    level = 'ng'; reason = f'{v.value:.1f} > {threshold}'
            elif cond == 'equal':
                target = matched_rule.get('threshold', 0)
                tol = matched_rule.get('tolerance', 1)
                if abs(v.value - target) <= tol:
                    level = 'ok'; reason = f'{v.value:.1f} ≈ {target} (±{tol})'
                else:
                    level = 'ng'; reason = f'{v.value:.1f} ≠ {target} (±{tol})'

            if level == 'ng': overall = 'ng'
            elif level == 'warning' and overall != 'ng': overall = 'warning'

            results.append({
                'text': v.text, 'value': v.value, 'confidence': v.confidence,
                'position': f'({v.cx_pct:.1f}%, {v.cy_pct:.1f}%)',
                'level': level, 'reason': reason,
                'rule_name': matched_rule.get('name', ''),
            })

        return {'overall': overall, 'values': results, 'total_detected': len(results)}

    def judge_values(self, ocr_result: SmartOcrResult,
                     warn_max: float = 45.0, error_max: float = 50.0,
                     warn_min: float = 20.0, error_min: float = 15.0) -> dict:
        """추출된 수치값에 대해 일괄 판정"""
        results = []
        overall = 'ok'

        for v in ocr_result.values:
            if v.value >= error_max:
                level = 'ng'
                reason = f'{v.value:.1f} >= 이상상한 {error_max}'
            elif v.value <= error_min:
                level = 'ng'
                reason = f'{v.value:.1f} <= 이상하한 {error_min}'
            elif v.value >= warn_max:
                level = 'warning'
                reason = f'{v.value:.1f} >= 경고상한 {warn_max}'
            elif v.value <= warn_min:
                level = 'warning'
                reason = f'{v.value:.1f} <= 경고하한 {warn_min}'
            else:
                level = 'ok'
                reason = f'{v.value:.1f} 정상 범위'

            if level == 'ng':
                overall = 'ng'
            elif level == 'warning' and overall != 'ng':
                overall = 'warning'

            results.append({
                'text': v.text,
                'value': v.value,
                'confidence': v.confidence,
                'position': f'({v.cx_pct:.1f}%, {v.cy_pct:.1f}%)',
                'level': level,
                'reason': reason
            })

        return {
            'overall': overall,
            'values': results,
            'total_detected': len(results),
            'processing_ms': ocr_result.processing_ms
        }


smart_ocr = SmartOcrService()
