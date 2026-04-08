"""검사 템플릿 스키마 — ROI 정의 요청/응답"""
from pydantic import BaseModel
from datetime import datetime


class InspectionTemplateCreate(BaseModel):
    """검사 템플릿 등록 요청"""
    equipment_id: int                    # 소속 설비 ID
    template_name: str                   # 템플릿명 (예: #1-2 히터 온도 PV)
    judgment_type: str                   # 판정 유형: numeric / signal / color
    roi_x: int = 0                       # ROI X 좌표 (%)
    roi_y: int = 0                       # ROI Y 좌표 (%)
    roi_width: int = 100                 # ROI 너비 (%)
    roi_height: int = 100                # ROI 높이 (%)
    preprocess_type: str | None = None   # 전처리 방식
    color_reference_json: str | None = None  # 색상 기준 JSON


class InspectionTemplateUpdate(BaseModel):
    """검사 템플릿 수정 요청 — 모든 필드 선택적"""
    template_name: str | None = None
    judgment_type: str | None = None
    roi_x: int | None = None
    roi_y: int | None = None
    roi_width: int | None = None
    roi_height: int | None = None
    preprocess_type: str | None = None
    color_reference_json: str | None = None


class InspectionTemplateResponse(BaseModel):
    """검사 템플릿 응답"""
    id: int
    equipment_id: int
    template_name: str
    judgment_type: str
    roi_x: int
    roi_y: int
    roi_width: int
    roi_height: int
    preprocess_type: str | None
    color_reference_json: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
