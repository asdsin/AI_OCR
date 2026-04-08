"""
PaddleOCR 브릿지 — Python 3.11 가상환경에서 PaddleOCR 실행

메인 서버(Python 3.14)에서 subprocess로 호출하여 결과를 JSON으로 받음
PaddleOCR는 Python 3.14를 지원하지 않으므로 별도 venv 필요
"""
import subprocess
import json
import os
import logging
import tempfile
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Python 3.11 가상환경 경로
VENV_PYTHON = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                            "venv311", "Scripts", "python.exe")

# PaddleOCR 실행 스크립트
_PADDLE_SCRIPT = '''
import sys, json, os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["HOME"] = "C:/paddleocr_cache"
os.environ["USERPROFILE"] = "C:/paddleocr_cache"

from paddleocr import PaddleOCR
import cv2
import numpy as np

img_path = sys.argv[1]
img = cv2.imread(img_path)
if img is None:
    print(json.dumps({"error": "Image load failed"}))
    sys.exit(1)

# 이미지 축소 (PaddleOCR 최적 크기)
h, w = img.shape[:2]
if max(h, w) > 1500:
    s = 1500 / max(h, w)
    img = cv2.resize(img, None, fx=s, fy=s)

ocr = PaddleOCR(use_angle_cls=True, lang="korean", use_gpu=False, show_log=False)
result = ocr.ocr(img, cls=True)

items = []
if result and result[0]:
    for line in result[0]:
        bbox, (text, conf) = line
        pts = np.array(bbox)
        cx = float(np.mean(pts[:, 0]))
        cy = float(np.mean(pts[:, 1]))
        w = float(np.max(pts[:, 0]) - np.min(pts[:, 0]))
        h = float(np.max(pts[:, 1]) - np.min(pts[:, 1]))
        items.append({
            "text": text, "confidence": round(float(conf), 4),
            "cx": round(cx, 1), "cy": round(cy, 1),
            "w": round(w, 1), "h": round(h, 1),
        })

print(json.dumps({"items": items, "count": len(items)}, ensure_ascii=False))
'''


def run_paddle_ocr(img: np.ndarray, timeout: int = 60) -> list[dict]:
    """
    PaddleOCR 실행 (subprocess → Python 3.11 venv)

    Returns: [{text, confidence, cx, cy, w, h}]
    """
    if not os.path.exists(VENV_PYTHON):
        logger.warning(f"Python 3.11 venv not found: {VENV_PYTHON}")
        return []

    # 이미지를 임시 파일로 저장
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
        cv2.imwrite(f.name, img)
        tmp_path = f.name

    try:
        # PaddleOCR 스크립트를 임시 파일로
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as sf:
            sf.write(_PADDLE_SCRIPT)
            script_path = sf.name

        result = subprocess.run(
            [VENV_PYTHON, script_path, tmp_path],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "KMP_DUPLICATE_LIB_OK": "TRUE"}
        )

        os.unlink(script_path)

        if result.returncode != 0:
            logger.error(f"PaddleOCR error: {result.stderr[:500]}")
            return []

        data = json.loads(result.stdout)
        if "error" in data:
            logger.error(f"PaddleOCR: {data['error']}")
            return []

        return data.get("items", [])

    except subprocess.TimeoutExpired:
        logger.error("PaddleOCR timeout")
        return []
    except Exception as e:
        logger.error(f"PaddleOCR bridge error: {e}")
        return []
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass


def is_available() -> bool:
    """PaddleOCR 사용 가능 여부"""
    return os.path.exists(VENV_PYTHON)
