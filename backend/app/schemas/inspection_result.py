"""판정 결과 스키마 — 촬영·OCR·판정 이력 요청/응답"""
from pydantic import BaseModel
from datetime import datetime


class InspectionResultCreate(BaseModel):
    """판정 결과 등록 요청"""
    equipment_id: int
    template_id: int
    judgment_type: str                      # numeric / signal / color
    raw_text: str | None = None             # OCR 원본 텍스트
    parsed_value: float | None = None       # 파싱된 수치값
    raw_color_json: str | None = None       # 색상형 원본 JSON
    judgment_result: str                    # OK / NG / ERROR
    confidence: float | None = None         # OCR 신뢰도
    image_path: str | None = None           # 이미지 경로
    operator_note: str | None = None        # 작업자 메모
    # 2단계: 예외 + AI 보조
    exception_flag: bool = False
    exception_reason: str | None = None
    ai_assist_requested: bool = False
    final_result_source: str = 'rule'       # rule / ai_assist / manual_correction


class InspectionResultUpdate(BaseModel):
    """판정 결과 수정 요청 — 보정 시 사용"""
    judgment_result: str | None = None
    parsed_value: float | None = None
    operator_note: str | None = None
    corrected_yn: bool | None = None


class InspectionResultResponse(BaseModel):
    """판정 결과 응답"""
    id: int
    equipment_id: int
    template_id: int
    judgment_type: str
    raw_text: str | None
    parsed_value: float | None
    raw_color_json: str | None
    judgment_result: str
    confidence: float | None
    image_path: str | None
    operator_note: str | None
    corrected_yn: bool
    # 2단계
    exception_flag: bool | None
    exception_reason: str | None
    ai_assist_requested: bool | None
    ai_assist_completed: bool | None
    final_result_source: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
