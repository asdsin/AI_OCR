"""
듀얼 OCR 엔진 서비스
- Primary: EasyOCR (설치 쉬움, 한국어 우수)
- Fallback: PaddleOCR (정확도 높음, 테이블 인식 강점)
- 전략: Primary 먼저 시도 → 신뢰도 낮으면 Fallback → 더 높은 결과 채택
"""
import logging
import time
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import cv2
from PIL import Image
from io import BytesIO
from dataclasses import dataclass
from app.config import settings

_ocr_executor = ThreadPoolExecutor(max_workers=2)

logger = logging.getLogger(__name__)


@dataclass
class OcrResult:
    text: str               # 인식된 전체 텍스트
    confidence: float       # 신뢰도 (0~1)
    engine: str             # 사용된 엔진
    value: float | None     # 추출된 수치값
    raw_boxes: list         # 원본 바운딩 박스
    processing_ms: int      # 처리 시간


class DualOcrEngine:
    """EasyOCR + PaddleOCR 듀얼 엔진"""

    def __init__(self):
        self._easyocr_reader = None
        self._paddleocr_engine = None
        self._initialized = False

    async def initialize(self):
        """엔진 초기화 (lazy loading)"""
        if self._initialized:
            return
        logger.info("OCR 엔진 초기화 시작...")
        try:
            import easyocr
            self._easyocr_reader = easyocr.Reader(
                settings.OCR_LANGUAGES,
                gpu=False,
                verbose=False
            )
            logger.info("EasyOCR 초기화 완료")
        except Exception as e:
            logger.warning(f"EasyOCR 초기화 실패: {e}")

        # PaddleOCR은 Python 3.14 미지원 — 향후 추가 예정
        # Fallback: EasyOCR 전처리 변형으로 대체

        self._initialized = True

    @staticmethod
    def load_image_file(filepath: str) -> np.ndarray | None:
        """한글 경로 호환 이미지 로드"""
        try:
            with open(filepath, 'rb') as f:
                data = f.read()
            nparr = np.frombuffer(data, np.uint8)
            return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def preprocess_plc(self, img: np.ndarray) -> np.ndarray:
        """
        PLC 화면 전용 전처리 파이프라인 (v2)
        색상 배경 제거 → 적응 이진화 → 모폴로지 → 패딩
        """
        h, w = img.shape[:2]

        # 1. 해상도 정규화 (1080p 타겟)
        if max(h, w) > 2000:
            scale = 1500 / max(h, w)
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        elif max(h, w) < 600:
            scale = 1000 / max(h, w)
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        if len(img.shape) < 3:
            return img

        # 2. 색상 배경 제거 (PLC 상태 색상: 녹/황/적)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        # 채도가 높은 영역 = 색상 배경 → 흰색으로 대체
        sat_mask = hsv[:, :, 1] > 60  # 채도 높은 영역
        result = img.copy()
        result[sat_mask] = [255, 255, 255]  # 색상 배경 → 흰색

        # 3. 그레이스케일
        gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)

        # 4. 적응 이진화 (Otsu 대신 — 로컬 대비 변화에 강함)
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, blockSize=15, C=8
        )

        # 5. 모폴로지 (소수점 보호 + 노이즈 제거)
        kernel = np.ones((2, 2), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        # 6. 흰색 패딩 (에지 텍스트 감지 개선)
        binary = cv2.copyMakeBorder(binary, 10, 10, 10, 10,
                                     cv2.BORDER_CONSTANT, value=255)
        return binary

    def preprocess_image(self, img: np.ndarray, options: dict | None = None) -> np.ndarray:
        """호환용 래퍼"""
        return self.preprocess_plc(img)

    def crop_zone(self, img: np.ndarray, x_pct: float, y_pct: float,
                  w_pct: float, h_pct: float) -> np.ndarray:
        """이미지에서 특정 영역(%) 크롭"""
        h, w = img.shape[:2]
        x = int(w * x_pct / 100)
        y = int(h * y_pct / 100)
        cw = int(w * w_pct / 100)
        ch = int(h * h_pct / 100)
        # 경계 체크
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        cw = max(1, min(cw, w - x))
        ch = max(1, min(ch, h - y))
        return img[y:y+ch, x:x+cw]

    # ── 수치 후처리 보정 ──
    _OCR_FIX = str.maketrans({'O':'0','o':'0','I':'1','l':'1','S':'5','B':'8','_':'.','|':'1'})

    @staticmethod
    def _postprocess_text(text: str) -> str:
        """OCR 결과 후처리 — 흔한 오인식 패턴 보정"""
        t = text.strip()
        # 숫자 컨텍스트에서 문자→숫자 치환
        if re.search(r'\d', t):
            t = t.translate(DualOcrEngine._OCR_FIX)
            # "43_0" → "43.0", "27,5" → "27.5"
            t = re.sub(r'(\d)[_,](\d)', r'\1.\2', t)
            # "43 .0" → "43.0" (공백 제거)
            t = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', t)
            # "43 0" → "43.0" (3자리 이하 숫자 사이 공백 → 소수점 가능성)
            t = re.sub(r'(\d{1,3})\s+(\d{1})(?!\d)', r'\1.\2', t)
        return t

    def _run_easyocr(self, img: np.ndarray, allowlist: str | None = None) -> OcrResult:
        """EasyOCR 실행 (최적 파라미터)"""
        start = time.time()
        kwargs = {
            "text_threshold": 0.5,     # 기본 0.7 → 약한 텍스트도 감지
            "link_threshold": 0.2,     # 기본 0.4 → 소수점 분리 방지
            "low_text": 0.3,           # 기본 0.4 → 문자 경계 확장
            "width_ths": 0.8,          # 기본 0.5 → "43.0"+"A" 병합
            "mag_ratio": 1.5,          # 내부 확대 → 작은 글자 인식↑
            "min_size": 10,            # 기본 20 → 작은 텍스트 감지
        }
        if allowlist:
            kwargs["allowlist"] = allowlist

        results = self._easyocr_reader.readtext(img, **kwargs)
        elapsed = int((time.time() - start) * 1000)

        if not results:
            return OcrResult("", 0.0, "easyocr", None, [], elapsed)

        texts = []
        confidences = []
        boxes = []
        for bbox, text, conf in results:
            fixed = self._postprocess_text(text)
            texts.append(fixed)
            confidences.append(conf)
            boxes.append({"bbox": bbox, "text": fixed, "confidence": conf})

        full_text = " ".join(texts)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0
        value = self._extract_number(full_text)

        return OcrResult(full_text, avg_conf, "easyocr", value, boxes, elapsed)

    def _run_easyocr_numeric(self, img: np.ndarray) -> OcrResult:
        """숫자 전용 패스 — allowlist로 인식 공간 제한 → 정확도↑↑"""
        return self._run_easyocr(img, allowlist="0123456789.,-+AV°C%")

    def _extract_number(self, text: str) -> float | None:
        """텍스트에서 수치 추출"""
        nums = re.findall(r'-?\d+\.?\d*', text)
        if nums:
            try:
                return float(nums[0])
            except ValueError:
                pass
        return None

    def _recognize_sync(self, img: np.ndarray, preprocess: dict | None = None) -> tuple:
        """
        듀얼패스 OCR (스레드풀에서 호출)
        Pass 1: 숫자 전용 (allowlist) → 높은 정확도
        Pass 2: 전체 문자 → 레이블 인식
        결과: (numeric_result, full_result)
        """
        processed = self.preprocess_plc(img)

        numeric_result = None
        full_result = None

        if self._easyocr_reader:
            # Pass 1: 숫자 전용 (핵심 — 정확도 최우선)
            numeric_result = self._run_easyocr_numeric(processed)

            # Pass 2: 전체 (신뢰도 낮으면 원본 이미지로)
            if numeric_result.confidence < settings.OCR_CONFIDENCE_THRESHOLD:
                full_result = self._run_easyocr(img)  # 원본 컬러 이미지

        return numeric_result, full_result

    async def recognize(self, img: np.ndarray, preprocess: dict | None = None) -> OcrResult:
        """
        듀얼 OCR 인식 실행 (스레드풀에서 비동기 실행)
        전략: Primary 먼저 → 신뢰도 부족 시 Fallback → 더 좋은 결과 채택
        """
        await self.initialize()

        loop = asyncio.get_event_loop()
        primary_result, fallback_result = await loop.run_in_executor(
            _ocr_executor, self._recognize_sync, img, preprocess
        )

        # 결과 선택: 신뢰도 높은 쪽
        if primary_result and fallback_result:
            if fallback_result.confidence > primary_result.confidence:
                logger.info(
                    f"Fallback({fallback_result.engine}) 채택: "
                    f"{fallback_result.confidence:.2f} > {primary_result.confidence:.2f}"
                )
                return fallback_result
            return primary_result
        elif fallback_result:
            return fallback_result
        elif primary_result:
            return primary_result
        else:
            return OcrResult("", 0.0, "none", None, [], 0)

    async def recognize_zone(self, full_img: np.ndarray,
                             x_pct: float, y_pct: float,
                             w_pct: float, h_pct: float,
                             preprocess: dict | None = None) -> OcrResult:
        """특정 영역만 크롭 후 OCR"""
        cropped = self.crop_zone(full_img, x_pct, y_pct, w_pct, h_pct)
        return await self.recognize(cropped, preprocess)


# 싱글톤 인스턴스
ocr_engine = DualOcrEngine()
