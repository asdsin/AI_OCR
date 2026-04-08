"""설비 스키마 — 요청/응답 데이터 형식"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class EquipmentCreate(BaseModel):
    """설비 등록 요청"""
    equipment_code: str       # 설비 코드 (필수)
    equipment_name: str       # 설비명 (필수)
    line_name: str | None = None        # 라인명
    location_name: str | None = None    # 위치
    qr_value: str | None = None         # QR 코드값


class EquipmentUpdate(BaseModel):
    """설비 수정 요청 — 모든 필드 선택적"""
    equipment_code: str | None = None
    equipment_name: str | None = None
    line_name: str | None = None
    location_name: str | None = None
    qr_value: str | None = None
    is_active: bool | None = None


class EquipmentResponse(BaseModel):
    """설비 응답 — 기본 정보"""
    id: int
    equipment_code: str
    equipment_name: str
    line_name: str | None
    location_name: str | None
    qr_value: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EquipmentDetailResponse(EquipmentResponse):
    """설비 상세 응답 — 템플릿 목록 포함"""
    templates: list["InspectionTemplateResponse"] = []

    model_config = {"from_attributes": True}


# 순환 참조 방지 — 아래에서 import
from app.schemas.inspection_template import InspectionTemplateResponse  # noqa: E402
EquipmentDetailResponse.model_rebuild()
