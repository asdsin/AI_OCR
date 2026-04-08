"""OCR 인식 + 판정 API - 핵심 엔드포인트"""
import os
import time
import uuid
import logging
import asyncio
import base64
import cv2
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.config import settings
from app.services.screen_detector import detect_screen
from app.models import (
    Equipment, PlcTemplate, OcrZone, JudgmentHistory,
    JudgmentLevel, OcrEngine, MetricType, QrPoint
)
from app.services.ocr_engine import ocr_engine
from app.services.judgment_engine import judgment_engine
from app.services.correction_service import correction_service
from app.schemas import JudgmentResponse, OcrZoneResult, CorrectionCreate, CorrectionResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ocr"])

# 공유 스레드풀 (모듈 레벨, 리소스 누수 방지)
_ocr_thread_pool = ThreadPoolExecutor(max_workers=2)
from app.services.smart_ocr import smart_ocr


@router.post("/ocr/recognize")
async def recognize_image(
    image: UploadFile = File(...),
    equipment_id: str | None = Form(None),
    qr_code: str | None = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    이미지 업로드 → 듀얼 OCR → 영역별 판정 → 결과 반환

    Flow:
    1. 이미지 수신 + 저장
    2. QR/설비ID로 설비 조회 → 템플릿 + 영역 로드
    3. 영역별 크롭 → OCR → 보정 체크 → 판정
    4. 이력 저장 + 결과 반환
    """
    total_start = time.time()

    # 1. 이미지 로드
    contents = await image.read()
    if len(contents) > settings.MAX_IMAGE_SIZE:
        raise HTTPException(413, "이미지 크기 초과 (최대 10MB)")

    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "이미지 디코딩 실패")

    # PLC 화면 자동 감지 (베젤/배경 제거)
    screen, screen_rect = detect_screen(img)
    logger.info(f"화면 감지: {screen_rect}, 원본={img.shape[:2]}, 화면={screen.shape[:2]}")

    # 이미지 저장 (원본 + 화면 크롭)
    filename = f"{uuid.uuid4()}.jpg"
    filepath = os.path.join(settings.UPLOAD_DIR, filename)
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    cv2.imwrite(filepath, img)

    # 이후 OCR은 크롭된 화면 기준으로 수행
    img = screen

    # 2. 설비 조회 (QR코드는 QrPoint 테이블에서 검색)
    equip = None
    if equipment_id:
        equip = await db.get(Equipment, equipment_id)
    elif qr_code:
        qr_stmt = select(QrPoint).where(QrPoint.qr_code == qr_code, QrPoint.is_active == True)
        qr_point = (await db.execute(qr_stmt)).scalar_one_or_none()
        if qr_point and qr_point.equipment_id:
            equip = await db.get(Equipment, qr_point.equipment_id)

    if not equip:
        # 설비 없이 전체 이미지 OCR만 수행
        result = await ocr_engine.recognize(img)
        return {
            "mode": "raw_ocr",
            "ocr_text": result.text,
            "ocr_confidence": result.confidence,
            "ocr_engine": result.engine,
            "extracted_value": result.value,
            "processing_time_ms": result.processing_ms
        }

    # 3. 템플릿 + 영역 로드
    if not equip.template_id:
        raise HTTPException(400, f"설비 '{equip.name}'에 PLC 템플릿이 지정되지 않았습니다")

    zone_stmt = select(OcrZone).where(
        OcrZone.template_id == equip.template_id, OcrZone.is_active == True
    ).order_by(OcrZone.sort_order)
    zones = (await db.execute(zone_stmt)).scalars().all()

    if not zones:
        raise HTTPException(400, "OCR 영역이 설정되지 않았습니다")

    # 4. 영역별 OCR + 판정
    zone_results = []
    for zone in zones:
        # 크롭
        cropped = ocr_engine.crop_zone(
            img, zone.x_pct, zone.y_pct, zone.w_pct, zone.h_pct
        )

        # OCR
        preprocessing = zone.preprocessing or {}
        ocr_result = await ocr_engine.recognize(cropped, preprocessing)

        # 보정 체크
        was_corrected = False
        correction_value = None
        correction = await correction_service.find_correction(
            db, equip.id, zone.id, ocr_result.text
        )
        if correction and correction.correct_value is not None:
            was_corrected = True
            correction_value = correction.correct_value
            await correction_service.apply_correction(db, correction)
            # 보정된 값으로 판정
            final_value = correction.correct_value
        else:
            final_value = ocr_result.value

        # 판정
        zone_config = {
            "metric_type": zone.metric_type,
            "target_value": zone.target_value,
            "tolerance_pct": zone.tolerance_pct,
            "warn_min": zone.warn_min,
            "warn_max": zone.warn_max,
            "error_min": zone.error_min,
            "error_max": zone.error_max,
            "ok_patterns": zone.ok_patterns,
            "ng_patterns": zone.ng_patterns,
        }
        judgment = judgment_engine.judge_zone(
            ocr_result.text, final_value, cropped, zone_config
        )

        zone_results.append(OcrZoneResult(
            zone_id=zone.id,
            zone_label=zone.label,
            ocr_text=ocr_result.text,
            ocr_confidence=ocr_result.confidence,
            ocr_engine=ocr_result.engine,
            extracted_value=final_value,
            judgment_level=judgment.level.value,
            judgment_reason=judgment.reason,
            was_corrected=was_corrected,
            correction_value=correction_value
        ))

    # 5. 전체 판정 (가장 심각한 레벨 채택)
    levels = [JudgmentLevel(zr.judgment_level) for zr in zone_results]
    if JudgmentLevel.NG in levels:
        overall = JudgmentLevel.NG
    elif JudgmentLevel.WARNING in levels:
        overall = JudgmentLevel.WARNING
    elif JudgmentLevel.OK in levels:
        overall = JudgmentLevel.OK
    else:
        overall = JudgmentLevel.UNKNOWN

    total_ms = int((time.time() - total_start) * 1000)

    # 6. 이력 저장
    history = JudgmentHistory(
        equipment_id=equip.id,
        image_path=filepath,
        overall_result=overall,
        zone_results=[zr.model_dump() for zr in zone_results],
        ocr_engine_used=OcrEngine.EASYOCR,  # primary
        processing_time_ms=total_ms
    )
    db.add(history)
    await db.commit()

    return JudgmentResponse(
        equipment_id=equip.id,
        equipment_name=equip.name,
        overall_result=overall.value,
        zone_results=zone_results,
        processing_time_ms=total_ms,
        image_path=filepath,
        captured_at=datetime.utcnow()
    )


@router.post("/ocr/test")
async def test_ocr(image: UploadFile = File(...)):
    """이미지 전체 OCR 테스트 (설비 무관)"""
    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, "이미지 디코딩 실패")

        result = await ocr_engine.recognize(img)

        # bbox 직렬화 (numpy array → list 변환)
        safe_boxes = []
        for b in result.raw_boxes[:20]:
            box = {}
            for k, v in b.items():
                if hasattr(v, 'tolist'):
                    box[k] = v.tolist()
                elif isinstance(v, (list, tuple)):
                    box[k] = [[float(c) for c in pt] if isinstance(pt, (list, tuple)) else pt for pt in v]
                else:
                    box[k] = v
            safe_boxes.append(box)

        return {
            "text": result.text,
            "confidence": float(result.confidence),
            "engine": result.engine,
            "value": float(result.value) if result.value is not None else None,
            "processing_ms": result.processing_ms,
            "boxes": safe_boxes
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OCR 테스트 에러: {e}", exc_info=True)
        raise HTTPException(500, f"OCR 처리 실패: {str(e)}")


# ── 기준 사진 분석 (설정 단계) ──

@router.post("/ocr/analyze")
async def analyze_reference(image: UploadFile = File(...)):
    """
    기준 사진 분석 — 설정 단계에서 사용
    1. 화면 자동 감지 (베젤 제거)
    2. 전체 OCR → 감지된 모든 텍스트+수치+위치 반환
    3. 프론트에서 사용자가 판정 항목을 시각적으로 선택

    반환: 감지된 값 목록 [{text, value, cx_pct, cy_pct, confidence, bbox_pct}]
    """

    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, "이미지 디코딩 실패")

        # 화면 감지
        screen, rect = detect_screen(img)
        sh, sw = screen.shape[:2]

        # 크롭된 화면을 base64로 (UI에서 오버레이 표시용)
        _, buf = cv2.imencode('.jpg', screen, [cv2.IMWRITE_JPEG_QUALITY, 80])
        screen_b64 = base64.b64encode(buf).decode('utf-8')

        # 원본 이미지도 저장
        filename = f"ref_{uuid.uuid4()}.jpg"
        filepath = os.path.join(settings.UPLOAD_DIR, filename)
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        cv2.imwrite(filepath, img)

        # 스마트 OCR (공유 스레드풀)
        loop = asyncio.get_event_loop()
        ocr_result = await loop.run_in_executor(_ocr_thread_pool, smart_ocr.extract_all, screen)

        # 감지된 항목을 UI에서 선택할 수 있는 형태로 반환
        items = []
        for i, det in enumerate(ocr_result):
            items.append({
                "idx": i,
                "text": det["text"],
                "value": det.get("value"),
                "is_numeric": det.get("is_numeric", False),
                "cx_pct": det["cx_pct"],
                "cy_pct": det["cy_pct"],
                "w_pct": det.get("w_pct", 3),
                "h_pct": det.get("h_pct", 2),
                "confidence": det["confidence"],
            })

        # 화면 유형/제조사 추정
        from app.services.plc_patterns import suggest_screen_type, detect_manufacturer, PLC_SCREEN_TYPES
        all_texts = [it["text"] for it in items]
        screen_type = suggest_screen_type(all_texts)
        manufacturer = detect_manufacturer(all_texts)
        numeric_count = sum(1 for it in items if it.get("is_numeric"))
        noise_count = sum(1 for it in items if it.get("is_noise"))

        return {
            "screen_image": screen_b64,
            "screen_size": {"w": sw, "h": sh},
            "original_image": filename,
            "screen_rect": rect,
            "detected_items": items,
            "total_detected": len(items),
            "numeric_count": numeric_count,
            "noise_filtered": noise_count,
            "screen_type": screen_type,
            "screen_type_name": PLC_SCREEN_TYPES.get(screen_type, {}).get("name", ""),
            "manufacturer": manufacturer,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"기준 사진 분석 에러: {e}", exc_info=True)
        raise HTTPException(500, f"분석 실패: {str(e)}")


@router.post("/ocr/test-zone")
async def test_zone_ocr(
    image: UploadFile = File(...),
    x_pct: float = Form(0), y_pct: float = Form(0),
    w_pct: float = Form(100), h_pct: float = Form(100),
):
    """
    특정 영역만 크롭하여 OCR 테스트
    기준설정에서 영역 범위를 조정하며 실시간 인식 확인용
    """
    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, "이미지 디코딩 실패")

        screen, _ = detect_screen(img)
        h, w = screen.shape[:2]

        # 영역 크롭 (여유 마진 포함 — 가장자리 숫자 잘림 방지)
        margin_x = max(5, int(w * 0.01))  # 1% 또는 최소 5px
        margin_y = max(5, int(h * 0.01))
        x = max(0, int(w * x_pct / 100) - margin_x)
        y = max(0, int(h * y_pct / 100) - margin_y)
        cw = min(w - x, int(w * w_pct / 100) + margin_x * 2)
        ch = min(h - y, int(h * h_pct / 100) + margin_y * 2)
        cropped = screen[y:y+ch, x:x+cw]

        # 업스케일링 + 흰색 패딩 (가장자리 문자 감지↑)
        crop_h, crop_w = cropped.shape[:2]
        if max(crop_h, crop_w) < 500:
            scale = 800 / max(crop_h, crop_w)
            cropped = cv2.resize(cropped, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        # 패딩 추가 (EasyOCR CRAFT는 에지 텍스트를 놓침)
        pad = 15
        cropped = cv2.copyMakeBorder(cropped, pad, pad, pad, pad,
                                      cv2.BORDER_CONSTANT, value=[255, 255, 255] if len(cropped.shape) == 3 else 255)

        # OCR
        loop = asyncio.get_event_loop()
        ocr_result = await loop.run_in_executor(
            _ocr_thread_pool, smart_ocr.extract_all, cropped
        )

        # 크롭 이미지 base64
        _, buf = cv2.imencode('.jpg', cropped, [cv2.IMWRITE_JPEG_QUALITY, 85])
        crop_b64 = base64.b64encode(buf).decode('utf-8')

        return {
            "crop_image": crop_b64,
            "crop_size": {"w": cw, "h": ch},
            "zone": {"x_pct": x_pct, "y_pct": y_pct, "w_pct": w_pct, "h_pct": h_pct},
            "detected_items": ocr_result,
            "total_detected": len(ocr_result),
            "numeric_count": sum(1 for it in ocr_result if it.get("is_numeric")),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"영역 OCR 테스트 에러: {e}", exc_info=True)
        raise HTTPException(500, f"테스트 실패: {str(e)}")


# ── 고정밀 영역 OCR (3중 전처리 × 다수결) ──

@router.post("/ocr/precision-zone")
async def precision_zone_ocr(
    image: UploadFile = File(...),
    x_pct: float = Form(0), y_pct: float = Form(0),
    w_pct: float = Form(100), h_pct: float = Form(100),
):
    """
    고정밀 영역 OCR — 3가지 전처리 × 다수결 투표
    98%+ 정확도 목표
    """
    from app.services.precision_ocr import precision_ocr_zone
    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, "이미지 디코딩 실패")

        screen, _ = detect_screen(img)
        h, w = screen.shape[:2]

        # 크롭 (마진 포함)
        margin_x = max(5, int(w * 0.01))
        margin_y = max(5, int(h * 0.01))
        x = max(0, int(w * x_pct / 100) - margin_x)
        y = max(0, int(h * y_pct / 100) - margin_y)
        cw = min(w - x, int(w * w_pct / 100) + margin_x * 2)
        ch = min(h - y, int(h * h_pct / 100) + margin_y * 2)
        cropped = screen[y:y+ch, x:x+cw]

        # 크롭 이미지 base64
        _, buf = cv2.imencode('.jpg', cropped, [cv2.IMWRITE_JPEG_QUALITY, 85])
        crop_b64 = base64.b64encode(buf).decode('utf-8')

        # 고정밀 OCR (스레드풀)
        reader = smart_ocr._get_reader()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _ocr_thread_pool, precision_ocr_zone, reader, cropped
        )

        return {
            "crop_image": crop_b64,
            **result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"고정밀 OCR 에러: {e}", exc_info=True)
        raise HTTPException(500, f"OCR 실패: {str(e)}")


# ── Smart OCR (영역 좌표 없이 자동 판정) ──

@router.post("/ocr/smart")
async def smart_recognize(
    image: UploadFile = File(...),
    warn_max: float = Form(45.0),
    error_max: float = Form(50.0),
    warn_min: float = Form(20.0),
    error_min: float = Form(15.0),
):
    """
    스마트 OCR - 영역 좌표 없이 PLC 화면에서 수치값 자동 추출 + 판정
    1. 화면 자동 감지 (베젤 제거)
    2. 전체 OCR로 수치값 위치 자동 탐지
    3. 임계값 기반 일괄 판정
    """
    try:
        contents = await image.read()
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise HTTPException(400, "이미지 디코딩 실패")

        # 화면 감지
        screen, rect = detect_screen(img)

        # 스마트 OCR (공유 스레드풀)
        loop = asyncio.get_event_loop()
        ocr_result = await loop.run_in_executor(_ocr_thread_pool, smart_ocr.extract_values, screen)

        # 판정
        judgment = smart_ocr.judge_values(
            ocr_result, warn_max, error_max, warn_min, error_min
        )

        return {
            "mode": "smart",
            "screen_detected": rect != (0, 0, img.shape[1], img.shape[0]),
            "screen_rect": rect,
            **judgment
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Smart OCR 에러: {e}", exc_info=True)
        raise HTTPException(500, f"Smart OCR 실패: {str(e)}")


# ── Corrections ──

@router.post("/corrections", response_model=CorrectionResponse)
async def create_correction(data: CorrectionCreate, db: AsyncSession = Depends(get_db)):
    """보정 데이터 저장"""
    correction = await correction_service.save_correction(
        db, data.equipment_id, data.zone_id,
        data.ocr_text, data.ocr_value,
        data.correct_value, data.correct_text,
        created_by=data.created_by
    )
    return CorrectionResponse(**correction.__dict__)


@router.get("/corrections/stats")
async def get_correction_stats(
    equipment_id: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """보정 통계"""
    return await correction_service.get_stats(db, equipment_id)


# ── History ──

@router.get("/history")
async def list_history(
    equipment_id: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """판정 이력 조회"""
    stmt = select(JudgmentHistory).order_by(JudgmentHistory.created_at.desc()).limit(limit)
    if equipment_id:
        stmt = stmt.where(JudgmentHistory.equipment_id == equipment_id)
    result = await db.execute(stmt)
    histories = result.scalars().all()
    return [
        {
            "id": h.id,
            "equipment_id": h.equipment_id,
            "overall_result": h.overall_result.value if h.overall_result else "unknown",
            "zone_results": h.zone_results,
            "processing_time_ms": h.processing_time_ms,
            "captured_at": h.captured_at
        }
        for h in histories
    ]
