"""AI 호출 로그 모델 — Ollama/Gemma 호출 이력 (성공/실패/타임아웃 전부 기록)"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


class AiCallLog(Base):
    """AI 호출 로그 테이블 — 모든 Gemma 호출을 기록 (디버깅/모니터링용)"""
    __tablename__ = "ai_call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_result_id = Column(Integer, ForeignKey("inspection_results.id"))  # 연관 판정 (선택)

    # ── 호출 정보 ──
    trigger_reason = Column(String(100), nullable=False)  # 호출 사유 (low_confidence / near_boundary / error_judgment 등)
    model_name = Column(String(50), nullable=False)       # 모델명 (예: "gemma3:4b")
    prompt_version = Column(String(20), default="v1.0")   # 프롬프트 버전

    # ── 결과 ──
    status = Column(String(20), nullable=False)  # success / failed / timeout / parse_error
    error_message = Column(String)               # 실패 시 에러 메시지

    # ── 성능 ──
    latency_ms = Column(Integer)                 # 응답 소요시간 (밀리초)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)

    # 관계
    inspection_result = relationship("InspectionResult", back_populates="ai_call_logs")
