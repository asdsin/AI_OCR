"""설비 기본정보 모델"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db import Base


class Equipment(Base):
    """설비 테이블 — PLC가 설치된 개별 설비 정보"""
    __tablename__ = "equipments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    equipment_code = Column(String(50), unique=True, nullable=False)   # 설비 코드 (예: EQ-A01-001)
    equipment_name = Column(String(200), nullable=False)               # 설비명 (예: NIR 건조로 #1)
    line_name = Column(String(100))                                    # 라인명 (예: 건조 A라인)
    location_name = Column(String(200))                                # 위치 (예: A동 1층)
    qr_value = Column(String(200), unique=True)                        # QR 코드 고유값 (스캔 시 식별)
    is_active = Column(Boolean, default=True)                          # 사용 여부
    created_at = Column(DateTime, default=datetime.utcnow)             # 등록일시
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)  # 수정일시

    # 관계: 설비 → 검사 템플릿 (1:N)
    templates = relationship("InspectionTemplate", back_populates="equipment", cascade="all, delete-orphan")
    # 관계: 설비 → 판정 규칙 (1:N)
    rules = relationship("JudgmentRule", back_populates="equipment", cascade="all, delete-orphan")
    # 관계: 설비 → 판정 결과 (1:N)
    results = relationship("InspectionResult", back_populates="equipment")
