"""검사 템플릿 모델 — 설비별 ROI(판독 영역) 정의"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


class InspectionTemplate(Base):
    """검사 템플릿 테이블 — 설비 화면에서 읽을 영역(ROI) 정의"""
    __tablename__ = "inspection_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False)  # 소속 설비
    template_name = Column(String(200), nullable=False)       # 템플릿명 (예: #1-2 히터 온도 PV)
    judgment_type = Column(String(20), nullable=False)        # 판정 유형: numeric / signal / color
    roi_x = Column(Integer, nullable=False, default=0)        # ROI 좌상단 X (%)
    roi_y = Column(Integer, nullable=False, default=0)        # ROI 좌상단 Y (%)
    roi_width = Column(Integer, nullable=False, default=100)  # ROI 너비 (%)
    roi_height = Column(Integer, nullable=False, default=100) # ROI 높이 (%)
    preprocess_type = Column(String(50))                      # 전처리 방식 (예: grayscale+threshold)
    color_reference_json = Column(String)                     # 색상형: 기준 색상 JSON (선택)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계
    equipment = relationship("Equipment", back_populates="templates")
    rules = relationship("JudgmentRule", back_populates="template", cascade="all, delete-orphan")
    results = relationship("InspectionResult", back_populates="template")
