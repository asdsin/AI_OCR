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

    def preprocess_image(self, img: np.ndarray, options: dict | None = None) -> np.ndarray:
        """PLC 화면 전처리 파이프라인"""
        opts = options or {}

        # 1. 리사이즈 (너무 크면 축소)
        h, w = img.shape[:2]
        max_dim = opts.get("max_dim", 1500)
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

        # 2. 그레이스케일
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        # 3. 대비 향상 (CLAHE - PLC 화면에 효과적)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 4. 이진화 (Otsu)
        if opts.get("binarize", True):
            _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            # PLC 화면은 보통 밝은 배경 + 어두운 글자 or 그 반대
            if opts.get("invert", False):
                binary = cv2.bitwise_not(binary)
            return binary

        return enhanced

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

    def _run_easyocr(self, img: np.ndarray) -> OcrResult:
        """EasyOCR 실행"""
        start = time.time()
        results = self._easyocr_reader.readtext(img)
        elapsed = int((time.time() - start) * 1000)

        if not results:
            return OcrResult("", 0.0, "easyocr", None, [], elapsed)

        # 결과 조합
        texts = []
        confidences = []
        boxes = []
        for bbox, text, conf in results:
            texts.append(text)
            confidences.append(conf)
            boxes.append({"bbox": bbox, "text": text, "confidence": conf})

        full_text = " ".join(texts)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0
        value = self._extract_number(full_text)

        return OcrResult(full_text, avg_conf, "easyocr", value, boxes, elapsed)

    def _run_easyocr_enhanced(self, img: np.ndarray) -> OcrResult:
        """EasyOCR 강화 모드 - 다른 전처리 적용 후 재시도"""
        # 전처리 변형: 반전 + 샤프닝
        enhanced = img.copy()
        if len(enhanced.shape) == 2:
            # 이미 그레이스케일이면 반전
            enhanced = cv2.bitwise_not(enhanced)
        else:
            # 컬러면 그레이 → 반전 → 샤프닝
            gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
            enhanced = cv2.bitwise_not(gray)

        # 샤프닝 커널
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        enhanced = cv2.filter2D(enhanced, -1, kernel)

        return self._run_easyocr(enhanced)

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
        """동기 OCR 실행 (스레드풀에서 호출) → (primary_result, fallback_result)"""
        processed = self.preprocess_image(img, preprocess)

        primary_result = None
        fallback_result = None

        if self._easyocr_reader:
            primary_result = self._run_easyocr(processed)

        need_fallback = (
            primary_result is None
            or primary_result.confidence < settings.OCR_CONFIDENCE_THRESHOLD
            or not primary_result.text.strip()
        )

        if need_fallback and self._easyocr_reader:
            fallback_result = self._run_easyocr_enhanced(img)

        return primary_result, fallback_result

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
