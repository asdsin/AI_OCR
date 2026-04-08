"""모델 패키지 — 전체 테이블 모델 import"""
from app.models.equipment import Equipment
from app.models.inspection_template import InspectionTemplate
from app.models.judgment_rule import JudgmentRule
from app.models.inspection_result import InspectionResult
from app.models.correction_log import CorrectionLog

__all__ = [
    "Equipment",
    "InspectionTemplate",
    "JudgmentRule",
    "InspectionResult",
    "CorrectionLog",
]
