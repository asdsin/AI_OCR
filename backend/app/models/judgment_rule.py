"""판정 규칙 모델 — 항목별 OK/NG 기준"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


class JudgmentRule(Base):
    """판정 규칙 테이블 — 각 검사 항목의 합격/불합격 기준"""
    __tablename__ = "judgment_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    equipment_id = Column(Integer, ForeignKey("equipments.id"), nullable=False)          # 소속 설비
    template_id = Column(Integer, ForeignKey("inspection_templates.id"), nullable=False)  # 소속 템플릿
    judgment_type = Column(String(20), nullable=False)  # 판정 유형: numeric / signal / color

    # ── 수치형 판정 기준 ──
    min_value = Column(Float)       # OK 최소값 (이상)
    max_value = Column(Float)       # OK 최대값 (이하)

    # ── 신호형 판정 기준 ──
    target_text = Column(String)                # 목표 텍스트 (예: "OK,RUN,ON")
    signal_on_threshold = Column(Integer)       # ON 판정 밝기 임계값 (0~255, 선택)
    signal_off_threshold = Column(Integer)      # OFF 판정 밝기 임계값 (0~255, 선택)

    # ── 색상형 판정 기준 ──
    color_mapping_json = Column(String)  # 색상→상태 매핑 JSON (예: {"green":"ok","red":"ng"})

    # ── 공통 ──
    unit = Column(String(20))  # 단위 (예: ℃, A, MPa)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 관계
    equipment = relationship("Equipment", back_populates="rules")
    template = relationship("InspectionTemplate", back_populates="rules")
