"""정답 보정 이력 모델 — 오판정 수정 학습 데이터"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


class CorrectionLog(Base):
    """정답 보정 테이블 — 오판정을 사용자가 수정한 이력"""
    __tablename__ = "correction_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_result_id = Column(Integer, ForeignKey("inspection_results.id"), nullable=False)  # 원본 판정

    previous_result = Column(String(10), nullable=False)  # 수정 전 판정 (OK/NG/ERROR)
    corrected_result = Column(String(10), nullable=False)  # 수정 후 판정 (OK/NG)
    corrected_value = Column(Float)                        # 수정된 수치값 (수치형만)
    correction_reason = Column(String(200))                # 수정 사유 (예: "OCR 오인식", "기준 오류")
    corrected_by = Column(String(100))                     # 수정자 (선택)

    created_at = Column(DateTime, default=datetime.utcnow)

    # 관계
    inspection_result = relationship("InspectionResult", back_populates="corrections")
