"""스키마 패키지 — 전체 Pydantic 스키마 import"""
from app.schemas.equipment import EquipmentCreate, EquipmentUpdate, EquipmentResponse, EquipmentDetailResponse
from app.schemas.inspection_template import InspectionTemplateCreate, InspectionTemplateUpdate, InspectionTemplateResponse
from app.schemas.judgment_rule import JudgmentRuleCreate, JudgmentRuleUpdate, JudgmentRuleResponse
from app.schemas.inspection_result import InspectionResultCreate, InspectionResultUpdate, InspectionResultResponse
from app.schemas.correction_log import CorrectionLogCreate, CorrectionLogResponse
