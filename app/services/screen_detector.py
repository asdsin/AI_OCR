"""
PLC 화면 자동 감지
촬영 이미지에서 PLC 화면 영역(사각형)을 자동으로 찾아서 크롭
베젤, 배경, 반사 등을 제거하고 순수 화면만 추출
"""
import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)


def detect_screen(img: np.ndarray, min_area_ratio: float = 0.15) -> tuple[np.ndarray, tuple]:
    """
    촬영 이미지에서 PLC 화면 영역을 자동 감지하여 크롭

    Args:
        img: 원본 촬영 이미지 (BGR)
        min_area_ratio: 전체 이미지 대비 최소 화면 비율

    Returns:
        (cropped_screen, (x, y, w, h)) - 크롭된 화면, 원본 좌표
    """
    h, w = img.shape[:2]
    total_area = h * w

    # 1. 그레이스케일 + 블러
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 2. 에지 검출 (Canny)
    edges = cv2.Canny(blurred, 30, 100)

    # 3. 모폴로지 연산으로 에지 연결
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=3)

    # 4. 윤곽선 검출
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_rect = None
    best_area = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < total_area * min_area_ratio:
            continue

        # 근사 다각형
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)

        # 4각형에 가까운 것
        if len(approx) >= 4:
            x, y, rw, rh = cv2.boundingRect(approx)
            aspect = rw / rh if rh > 0 else 0

            # PLC 화면은 보통 가로:세로 = 1.0~1.6 (4:3 또는 16:10)
            if 0.7 < aspect < 2.0 and area > best_area:
                best_area = area
                best_rect = (x, y, rw, rh)

    # 5. 화면을 못 찾으면 밝기 기반 fallback
    if best_rect is None:
        best_rect = _detect_by_brightness(gray, total_area, min_area_ratio)

    if best_rect is None:
        logger.warning("PLC 화면 감지 실패, 원본 사용")
        return img, (0, 0, w, h)

    x, y, rw, rh = best_rect
    # 약간의 마진 제거 (베젤 안쪽)
    margin = int(min(rw, rh) * 0.02)
    x += margin
    y += margin
    rw -= margin * 2
    rh -= margin * 2

    logger.info(f"PLC 화면 감지: ({x},{y}) {rw}x{rh} (전체의 {best_area/total_area*100:.1f}%)")
    return img[y:y+rh, x:x+rw], (x, y, rw, rh)


def _detect_by_brightness(gray: np.ndarray, total_area: int, min_ratio: float) -> tuple | None:
    """밝기 기반 화면 감지 - PLC 화면은 주변보다 밝음"""
    # 임계값: 이미지 평균 밝기보다 높은 영역
    mean_val = np.mean(gray)
    _, thresh = cv2.threshold(gray, int(mean_val * 0.8), 255, cv2.THRESH_BINARY)

    # 모폴로지로 노이즈 제거
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=5)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=3)

    contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_rect = None
    best_area = 0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < total_area * min_ratio:
            continue
        x, y, rw, rh = cv2.boundingRect(cnt)
        aspect = rw / rh if rh > 0 else 0
        if 0.7 < aspect < 2.0 and area > best_area:
            best_area = area
            best_rect = (x, y, rw, rh)

    return best_rect
