"""API 요청/응답 스키마"""
from pydantic import BaseModel
from datetime import datetime


# ── PLC Template ──

class PlcTemplateCreate(BaseModel):
    name: str
    manufacturer: str | None = None
    model: str | None = None
    screen_type: str | None = None
    description: str | None = None


class PlcTemplateResponse(BaseModel):
    id: str
    name: str
    manufacturer: str | None
    model: str | None
    screen_type: str | None
    description: str | None
    is_active: bool
    created_at: datetime
    zone_count: int = 0


# ── OCR Zone ──

class OcrZoneCreate(BaseModel):
    template_id: str
    label: str
    metric_name: str
    metric_type: str = "numeric"
    unit: str = ""
    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float
    warn_min: float | None = None
    warn_max: float | None = None
    error_min: float | None = None
    error_max: float | None = None
    target_value: float | None = None
    tolerance_pct: float | None = None
    ok_patterns: list[str] | None = None
    ng_patterns: list[str] | None = None
    value_pattern: str | None = None
    preprocessing: dict | None = None
    sort_order: int = 0


class OcrZoneResponse(BaseModel):
    id: str
    template_id: str
    label: str
    metric_name: str
    metric_type: str
    unit: str
    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float
    warn_min: float | None
    warn_max: float | None
    error_min: float | None
    error_max: float | None
    target_value: float | None
    tolerance_pct: float | None


# ── Equipment ──

class EquipmentCreate(BaseModel):
    code: str
    name: str
    qr_code: str | None = None
    template_id: str | None = None
    location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    process_code: str | None = None
    equipment_type: str | None = None


class EquipmentResponse(BaseModel):
    id: str
    code: str
    name: str
    qr_code: str | None
    template_id: str | None
    location: str | None
    is_active: bool


# ── OCR & Judgment ──

class OcrZoneResult(BaseModel):
    zone_id: str
    zone_label: str
    ocr_text: str
    ocr_confidence: float
    ocr_engine: str
    extracted_value: float | None
    judgment_level: str
    judgment_reason: str
    was_corrected: bool = False
    correction_value: float | None = None


class JudgmentResponse(BaseModel):
    equipment_id: str
    equipment_name: str
    overall_result: str
    zone_results: list[OcrZoneResult]
    processing_time_ms: int
    image_path: str | None = None
    captured_at: datetime


# ── Correction ──

class CorrectionCreate(BaseModel):
    equipment_id: str
    zone_id: str
    ocr_text: str
    ocr_value: float | None = None
    correct_value: float | None = None
    correct_text: str | None = None
    created_by: str | None = None


class CorrectionResponse(BaseModel):
    id: str
    equipment_id: str
    zone_id: str
    ocr_text: str
    correct_value: float | None
    applied_count: int
    created_at: datetime
