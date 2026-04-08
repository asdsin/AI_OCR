"""모델 패키지 — 전체 테이블 모델 import"""
# 1단계 테이블
from app.models.equipment import Equipment
from app.models.inspection_template import InspectionTemplate
from app.models.judgment_rule import JudgmentRule
from app.models.inspection_result import InspectionResult
from app.models.correction_log import CorrectionLog

# 2단계 테이블 (AI 보조)
from app.models.ai_assist_result import AiAssistResult
from app.models.ai_call_log import AiCallLog

__all__ = [
    "Equipment", "InspectionTemplate", "JudgmentRule",
    "InspectionResult", "CorrectionLog",
    "AiAssistResult", "AiCallLog",
]
