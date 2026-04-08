"""
멀티엔진 OCR — EasyOCR + Tesseract 병행 + 다수결

전략:
1. EasyOCR (3가지 전처리) → 3개 후보
2. Tesseract (3가지 전처리) → 3개 후보
3. 총 6개 후보 중 다수결 투표 → 최종값
4. 보정 사전 자동 적용
"""
import re
import time
import logging
import numpy as np
import cv2

logger = logging.getLogger(__name__)

_FIX = str.maketrans({
    'O':'0','o':'0','D':'0','I':'1','l':'1','i':'1','|':'1',
    'S':'5','s':'5','B':'8','b':'8','G':'6','Z':'2','z':'2',
    '_':'.', ',':'.',
})

def _fix(text):
    t = text.strip()
    if not t: return t
    t = t.translate(_FIX)
    t = re.sub(r'(\d)[_,](\d)', r'\1.\2', t)
    t = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', t)
    t = re.sub(r'(\d{1,3})\s+(\d{1})(?!\d)', r'\1.\2', t)
    t = re.sub(r'[AaVvCc°%\s]+$', '', t)
    t = re.sub(r'^[^0-9\-\.]+', '', t)
    return t.strip()

def _num(text):
    nums = re.findall(r'-?\d+\.?\d*', text)
    return float(nums[0]) if nums else None

def _variants(img):
    """3가지 전처리 변형"""
    h, w = img.shape[:2]
    if h < 60:
        s = max(3.0, 80/h)
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape)==3 else img.copy()
    pad = 12

    # V0: 원본 컬러
    v0 = cv2.copyMakeBorder(img, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=[255,255,255] if len(img.shape)==3 else 255)
    # V1: 적응 이진화
    v1 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8)
    v1 = cv2.copyMakeBorder(v1, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    # V2: 반전 이진화
    v2 = cv2.adaptiveThreshold(cv2.bitwise_not(gray), 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 8)
    v2 = cv2.copyMakeBorder(v2, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)

    return [v0, v1, v2]


def _run_tesseract(img):
    """Tesseract OCR (숫자 전용)"""
    try:
        import pytesseract
        # Windows 경로
        tess_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        import os
        if os.path.exists(tess_path):
            pytesseract.pytesseract.tesseract_cmd = tess_path

        config = '--psm 7 -c tessedit_char_whitelist=0123456789.,-'
        text = pytesseract.image_to_string(img, config=config).strip()
        # 신뢰도 계산
        data = pytesseract.image_to_data(img, config=config, output_type=pytesseract.Output.DICT)
        confs = [int(c) for c in data['conf'] if int(c) > 0]
        conf = (sum(confs)/len(confs)/100) if confs else 0.3
        return text, conf
    except Exception as e:
        logger.debug(f"Tesseract 실패: {e}")
        return "", 0


def _run_easyocr(reader, img):
    """EasyOCR (숫자 전용)"""
    try:
        results = reader.readtext(img,
            allowlist="0123456789.,-",
            text_threshold=0.3, link_threshold=0.1, low_text=0.2,
            width_ths=1.0, mag_ratio=2.0, min_size=5,
            decoder="beamsearch", beamWidth=10)
        texts = [r[1] for r in results]
        confs = [r[2] for r in results]
        return " ".join(texts), (sum(confs)/len(confs)) if confs else 0
    except Exception as e:
        logger.debug(f"EasyOCR 실패: {e}")
        return "", 0


def _run_paddleocr(img):
    """PaddleOCR (Python 3.11 subprocess)"""
    try:
        from app.services.paddle_bridge import run_paddle_ocr, is_available
        if not is_available():
            return "", 0
        items = run_paddle_ocr(img, timeout=30)
        if not items:
            return "", 0
        # 가장 신뢰도 높은 것
        best = max(items, key=lambda x: x["confidence"])
        return best["text"], best["confidence"]
    except Exception as e:
        logger.debug(f"PaddleOCR 실패: {e}")
        return "", 0


def multi_engine_ocr(reader, img: np.ndarray) -> dict:
    """
    멀티엔진 OCR: EasyOCR(3) + Tesseract(3) + PaddleOCR(1) → 다수결

    Returns: {value, text, confidence, method, engines, all_attempts}
    """
    start = time.time()
    variants = _variants(img)
    attempts = []

    for i, v in enumerate(variants):
        # EasyOCR
        raw, conf = _run_easyocr(reader, v)
        fixed = _fix(raw)
        val = _num(fixed)
        attempts.append({"engine":"easyocr","variant":i,"raw":raw,"fixed":fixed,"value":val,"confidence":conf})

        # Tesseract
        tess_img = v if len(v.shape)==2 else cv2.cvtColor(v, cv2.COLOR_BGR2GRAY)
        raw_t, conf_t = _run_tesseract(tess_img)
        fixed_t = _fix(raw_t)
        val_t = _num(fixed_t)
        attempts.append({"engine":"tesseract","variant":i,"raw":raw_t,"fixed":fixed_t,"value":val_t,"confidence":conf_t})

    # PaddleOCR (원본 이미지 1회 — 가장 정확한 엔진)
    raw_p, conf_p = _run_paddleocr(img)
    fixed_p = _fix(raw_p)
    val_p = _num(fixed_p)
    if val_p is not None:
        # PaddleOCR 결과에 신뢰도 가중치 (가장 정확한 엔진이므로)
        attempts.append({"engine":"paddleocr","variant":0,"raw":raw_p,"fixed":fixed_p,"value":val_p,"confidence":min(1.0, conf_p+0.1)})
        # PaddleOCR 결과를 2표로 (가중 투표)
        attempts.append({"engine":"paddleocr","variant":1,"raw":raw_p,"fixed":fixed_p,"value":val_p,"confidence":min(1.0, conf_p+0.1)})

    elapsed = int((time.time() - start) * 1000)

    # 다수결 투표
    value_votes = {}
    for a in attempts:
        if a["value"] is not None:
            key = round(a["value"], 1)
            if key not in value_votes: value_votes[key] = []
            value_votes[key].append(a)

    if value_votes:
        sorted_v = sorted(value_votes.items(), key=lambda x: (-len(x[1]), -max(a["confidence"] for a in x[1])))
        best_val, best_group = sorted_v[0]
        best_a = max(best_group, key=lambda a: a["confidence"])
        vote = len(best_group)
        total = len([a for a in attempts if a["value"] is not None])
        # 신뢰도 보정: 투표 비율에 따라
        bonus = min(0.3, vote / total * 0.4) if total > 0 else 0
        engines_used = list(set(a["engine"] for a in best_group))

        return {
            "value": best_val,
            "text": best_a["fixed"],
            "confidence": min(1.0, best_a["confidence"] + bonus),
            "method": f"vote_{vote}/{total}",
            "engines": engines_used,
            "elapsed_ms": elapsed,
            "all_attempts": attempts,
        }

    # 실패
    return {
        "value": None, "text": "", "confidence": 0,
        "method": "none", "engines": [], "elapsed_ms": elapsed,
        "all_attempts": attempts,
    }
