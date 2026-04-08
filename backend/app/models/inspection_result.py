"""판정 결과 모델 — 촬영·OCR·판정 이력"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


class InspectionResult(Base):
    """판정 결과 테이블 — 매 촬영/판정마다 1건씩 저장"""
    __tablename__ = "inspection_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False)          # 설비
    template_id = Column(Integer, ForeignKey("inspection_templates.id"), nullable=False)  # 템플릿

    judgment_type = Column(String(20), nullable=False)  # 판정 유형: numeric / signal / color

    # ── OCR 결과 ──
    raw_text = Column(String)          # OCR 원본 텍스트 (예: "168")
    parsed_value = Column(Float)       # 파싱된 수치값 (예: 168.0)
    raw_color_json = Column(String)    # 색상형: 감지된 색상 정보 JSON

    # ── 판정 결과 ──
    judgment_result = Column(String(10), nullable=False)  # OK / NG / ERROR
    confidence = Column(Float)                            # OCR 신뢰도 (0~1)

    # ── 이미지 ──
    image_path = Column(String(500))  # 촬영 이미지 저장 경로

    # ── 사용자 입력 ──
    operator_note = Column(String)          # 작업자 메모
    corrected_yn = Column(Boolean, default=False)  # 정답 보정 여부

    created_at = Column(DateTime, default=datetime.utcnow)

    # 관계
    equipment = relationship("Equipment", back_populates="results")
    template = relationship("InspectionTemplate", back_populates="results")
    corrections = relationship("CorrectionLog", back_populates="inspection_result", cascade="all, delete-orphan")
