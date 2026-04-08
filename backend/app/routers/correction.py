"""정답 보정 API — 오판정 수정 학습 데이터"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db import get_db
from app.models import InspectionResult, CorrectionLog

router = APIRouter(tags=["정답 보정"])


class CorrectionRequest(BaseModel):
    corrected_result: str               # OK / NG
    corrected_value: float | None = None  # 수치형: 올바른 값
    correction_reason: str | None = None  # 보정 사유
    corrected_by: str | None = None       # 보정자


@router.post("/inspection-results/{result_id}/correct", status_code=201)
def correct_result(result_id: int, data: CorrectionRequest, db: Session = Depends(get_db)):
    """판정 결과 보정 — correction_logs에 저장 + corrected_yn 업데이트"""
    result = db.query(InspectionResult).filter(InspectionResult.id == result_id).first()
    if not result:
        raise HTTPException(404, "판정 결과를 찾을 수 없습니다")

    # 보정 로그 저장
    log = CorrectionLog(
        inspection_result_id=result_id,
        previous_result=result.judgment_result,
        corrected_result=data.corrected_result,
        corrected_value=data.corrected_value,
        correction_reason=data.correction_reason,
        corrected_by=data.corrected_by,
    )
    db.add(log)

    # 원본 결과에 보정 플래그
    result.corrected_yn = True
    db.commit()
    db.refresh(log)

    return {
        "id": log.id,
        "previous": log.previous_result,
        "corrected": log.corrected_result,
        "message": "보정 완료",
    }


@router.get("/correction-logs")
def list_corrections(limit: int = 50, db: Session = Depends(get_db)):
    """보정 이력 전체 조회"""
    logs = db.query(CorrectionLog).order_by(CorrectionLog.created_at.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "inspection_result_id": l.inspection_result_id,
            "previous_result": l.previous_result,
            "corrected_result": l.corrected_result,
            "corrected_value": l.corrected_value,
            "correction_reason": l.correction_reason,
            "corrected_by": l.corrected_by,
            "created_at": str(l.created_at),
        }
        for l in logs
    ]


@router.get("/correction-logs/by-inspection/{result_id}")
def get_corrections_by_inspection(result_id: int, db: Session = Depends(get_db)):
    """특정 판정 결과의 보정 이력"""
    logs = db.query(CorrectionLog).filter(
        CorrectionLog.inspection_result_id == result_id
    ).order_by(CorrectionLog.created_at.desc()).all()
    return [
        {
            "id": l.id,
            "previous_result": l.previous_result,
            "corrected_result": l.corrected_result,
            "corrected_value": l.corrected_value,
            "correction_reason": l.correction_reason,
            "corrected_by": l.corrected_by,
            "created_at": str(l.created_at),
        }
        for l in logs
    ]
