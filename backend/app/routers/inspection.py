"""판정 결과 저장/조회 API"""
import os
import base64
import uuid
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import InspectionResult

router = APIRouter(prefix="/inspection-results", tags=["판정 결과"])

# 이미지 저장 경로
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGE_DIR = os.path.join(BASE_DIR, "data", "images")


# ── 요청 스키마 (인라인 — base64 이미지 포함) ──
from pydantic import BaseModel

class InspectionResultSave(BaseModel):
    equipment_id: int
    template_id: int
    judgment_type: str
    raw_text: str | None = None
    parsed_value: float | None = None
    raw_color_json: str | None = None
    judgment_result: str              # OK / NG / ERROR
    confidence: float | None = None
    operator_note: str | None = None
    image_base64: str | None = None   # base64 인코딩 이미지 (data:image/jpeg;base64,... 형태)


@router.post("", status_code=201)
def save_result(data: InspectionResultSave, db: Session = Depends(get_db)):
    """판정 결과 저장 — 이미지는 파일로 저장, DB에는 경로만"""
    image_path = None

    # 이미지 저장
    if data.image_base64:
        today = datetime.now().strftime("%Y%m%d")
        day_dir = os.path.join(IMAGE_DIR, today)
        os.makedirs(day_dir, exist_ok=True)

        # base64 디코딩
        b64 = data.image_base64
        if "," in b64:
            b64 = b64.split(",", 1)[1]  # data:image/jpeg;base64, 제거
        img_bytes = base64.b64decode(b64)

        filename = f"{uuid.uuid4().hex[:12]}.jpg"
        filepath = os.path.join(day_dir, filename)
        with open(filepath, "wb") as f:
            f.write(img_bytes)

        image_path = f"/images/{today}/{filename}"  # 상대 경로

    result = InspectionResult(
        equipment_id=data.equipment_id,
        template_id=data.template_id,
        judgment_type=data.judgment_type,
        raw_text=data.raw_text,
        parsed_value=data.parsed_value,
        raw_color_json=data.raw_color_json,
        judgment_result=data.judgment_result,
        confidence=data.confidence,
        operator_note=data.operator_note,
        image_path=image_path,
    )
    db.add(result)
    db.commit()
    db.refresh(result)

    return {
        "id": result.id,
        "judgment_result": result.judgment_result,
        "image_path": result.image_path,
        "created_at": str(result.created_at),
        "message": "저장 완료",
    }


@router.get("")
def list_results(
    equipment_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """판정 결과 목록 조회 (최신순)"""
    q = db.query(InspectionResult).order_by(InspectionResult.created_at.desc())

    if equipment_id:
        q = q.filter(InspectionResult.equipment_id == equipment_id)
    if date_from:
        q = q.filter(InspectionResult.created_at >= date_from)
    if date_to:
        q = q.filter(InspectionResult.created_at <= date_to + " 23:59:59")

    results = q.limit(limit).all()
    return [
        {
            "id": r.id,
            "equipment_id": r.equipment_id,
            "template_id": r.template_id,
            "judgment_type": r.judgment_type,
            "raw_text": r.raw_text,
            "parsed_value": r.parsed_value,
            "judgment_result": r.judgment_result,
            "confidence": r.confidence,
            "image_path": r.image_path,
            "corrected_yn": r.corrected_yn,
            "created_at": str(r.created_at),
        }
        for r in results
    ]


@router.get("/{result_id}")
def get_result(result_id: int, db: Session = Depends(get_db)):
    """판정 결과 상세 조회"""
    r = db.query(InspectionResult).filter(InspectionResult.id == result_id).first()
    if not r:
        raise HTTPException(404, "결과를 찾을 수 없습니다")
    return {
        "id": r.id,
        "equipment_id": r.equipment_id,
        "template_id": r.template_id,
        "judgment_type": r.judgment_type,
        "raw_text": r.raw_text,
        "parsed_value": r.parsed_value,
        "raw_color_json": r.raw_color_json,
        "judgment_result": r.judgment_result,
        "confidence": r.confidence,
        "image_path": r.image_path,
        "operator_note": r.operator_note,
        "corrected_yn": r.corrected_yn,
        "created_at": str(r.created_at),
    }


@router.get("/{result_id}/image")
def get_result_image(result_id: int, db: Session = Depends(get_db)):
    """판정 결과 원본 이미지 반환"""
    r = db.query(InspectionResult).filter(InspectionResult.id == result_id).first()
    if not r or not r.image_path:
        raise HTTPException(404, "이미지를 찾을 수 없습니다")

    # /images/YYYYMMDD/xxx.jpg → 실제 파일 경로
    rel_path = r.image_path.lstrip("/")  # images/YYYYMMDD/xxx.jpg
    file_path = os.path.join(BASE_DIR, "data", rel_path)

    if not os.path.exists(file_path):
        raise HTTPException(404, f"이미지 파일이 없습니다: {r.image_path}")

    return FileResponse(file_path, media_type="image/jpeg")
