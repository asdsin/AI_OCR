"""정답 보정 스키마 — 오판정 수정 요청/응답"""
from pydantic import BaseModel
from datetime import datetime


class CorrectionLogCreate(BaseModel):
    """정답 보정 등록 요청"""
    inspection_result_id: int         # 원본 판정 결과 ID
    previous_result: str              # 수정 전 판정 (OK/NG/ERROR)
    corrected_result: str             # 수정 후 판정 (OK/NG)
    corrected_value: float | None = None      # 수정된 수치값
    correction_reason: str | None = None      # 수정 사유
    corrected_by: str | None = None           # 수정자


class CorrectionLogResponse(BaseModel):
    """정답 보정 응답"""
    id: int
    inspection_result_id: int
    previous_result: str
    corrected_result: str
    corrected_value: float | None
    correction_reason: str | None
    corrected_by: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
