"""AI 보조 판정 결과 모델 — Gemma 등 AI 엔진의 분석 결과"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


class AiAssistResult(Base):
    """AI 보조 결과 테이블 — 예외 케이스에서 AI가 제공한 보조 분석"""
    __tablename__ = "ai_assist_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_result_id = Column(Integer, ForeignKey("inspection_results.id"), nullable=False)  # 원본 판정

    # ── AI 엔진 정보 ──
    model_name = Column(String(50), nullable=False)     # 모델명 (예: "gemma3:4b")
    prompt_version = Column(String(20), default="v1.0") # 프롬프트 버전

    # ── AI 응답 ──
    ai_raw_response = Column(String)     # Gemma 원문 응답 (전체 텍스트)
    ai_parsed_result = Column(String)    # 파싱된 JSON 결과 (suggested_value, suggested_judgment 등)
    ai_confidence = Column(Float)        # AI 신뢰도 (0~1)
    ai_reason = Column(String(500))      # AI 판정 사유

    # ── 성능 ──
    latency_ms = Column(Integer)         # 응답 소요시간 (밀리초)
    status = Column(String(20), nullable=False)  # success / failed / timeout / parse_error

    created_at = Column(DateTime, default=datetime.utcnow)

    # 관계
    inspection_result = relationship("InspectionResult", back_populates="ai_assists")
