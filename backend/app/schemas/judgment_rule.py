"""판정 규칙 스키마 — OK/NG 기준 요청/응답"""
from pydantic import BaseModel
from datetime import datetime


class JudgmentRuleCreate(BaseModel):
    """판정 규칙 등록 요청"""
    equipment_id: int           # 소속 설비
    template_id: int            # 소속 템플릿
    judgment_type: str          # numeric / signal / color
    min_value: float | None = None       # 수치형: OK 최소
    max_value: float | None = None       # 수치형: OK 최대
    target_text: str | None = None       # 신호형: OK 키워드 (쉼표 구분)
    signal_on_threshold: int | None = None   # 신호형: ON 밝기 임계값
    signal_off_threshold: int | None = None  # 신호형: OFF 밝기 임계값
    color_mapping_json: str | None = None    # 색상형: 매핑 JSON
    unit: str | None = None              # 단위


class JudgmentRuleUpdate(BaseModel):
    """판정 규칙 수정 요청 — 모든 필드 선택적"""
    judgment_type: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    target_text: str | None = None
    signal_on_threshold: int | None = None
    signal_off_threshold: int | None = None
    color_mapping_json: str | None = None
    unit: str | None = None


class JudgmentRuleResponse(BaseModel):
    """판정 규칙 응답"""
    id: int
    equipment_id: int
    template_id: int
    judgment_type: str
    min_value: float | None
    max_value: float | None
    target_text: str | None
    signal_on_threshold: int | None
    signal_off_threshold: int | None
    color_mapping_json: str | None
    unit: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
