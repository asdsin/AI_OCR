"""AI 보조 결과 + 호출 로그 스키마"""
from pydantic import BaseModel
from datetime import datetime


# ── AI 보조 결과 ──

class AiAssistResultResponse(BaseModel):
    """AI 보조 분석 결과 응답"""
    id: int
    inspection_result_id: int
    model_name: str
    prompt_version: str
    ai_raw_response: str | None
    ai_parsed_result: str | None    # JSON 문자열
    ai_confidence: float | None
    ai_reason: str | None
    latency_ms: int | None
    status: str                      # success / failed / timeout / parse_error
    created_at: datetime

    model_config = {"from_attributes": True}


# ── AI 호출 로그 ──

class AiCallLogResponse(BaseModel):
    """AI 호출 로그 응답"""
    id: int
    inspection_result_id: int | None
    trigger_reason: str
    model_name: str
    prompt_version: str
    status: str                      # success / failed / timeout / parse_error
    error_message: str | None
    latency_ms: int | None
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}
