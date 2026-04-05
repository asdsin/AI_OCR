"""
PLC OCR Agent - DB Models

계층구조: 업체(Company) > 사업부(Division) > 라인(Line) > 공정(Process) > 설비(Equipment) > PLC 화면(Template) > 판정영역(Zone)
판정유형: 수치(NUMERIC), 신호(SIGNAL), 색상(COLOR), SV/PV비교(TABLE)
학습구조: 판정이력 + 보정데이터 → 정확도 추적 → 고객사 납품 데이터
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, Text,
    ForeignKey, JSON, Enum as SqlEnum
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


def gen_uuid():
    return str(uuid.uuid4())


# ── Enums ──

class MetricType(str, enum.Enum):
    NUMERIC = "numeric"     # 수치형: 온도, 전류, 압력 등
    SIGNAL = "signal"       # 신호형: OK/NG, PASS/FAIL
    COLOR = "color"         # 색상형: LED 상태 (녹/황/적)
    TABLE = "table"         # 테이블형: SV vs PV 비교

class JudgmentLevel(str, enum.Enum):
    OK = "ok"
    WARNING = "warning"
    NG = "ng"
    UNKNOWN = "unknown"

class OcrEngine(str, enum.Enum):
    EASYOCR = "easyocr"
    PADDLEOCR = "paddleocr"
    TESSERACT = "tesseract"


# ═══════════════════════════════════════════
# 기준정보 계층구조 (업체 → 사업부 → 라인 → 공정)
# ═══════════════════════════════════════════

class Company(Base):
    """고객사 (최상위)"""
    __tablename__ = "companies"

    id = Column(String, primary_key=True, default=gen_uuid)
    code = Column(String(50), unique=True, nullable=False)   # "LGE", "DK"
    name = Column(String(200), nullable=False)                # "LG전자", "디케이"
    industry = Column(String(100))                            # "전자", "자동차부품"
    address = Column(String(300))
    contact_name = Column(String(100))
    contact_phone = Column(String(50))
    contact_email = Column(String(200))
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    divisions = relationship("Division", back_populates="company", cascade="all, delete-orphan")


class Division(Base):
    """사업부 / 공장"""
    __tablename__ = "divisions"

    id = Column(String, primary_key=True, default=gen_uuid)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    code = Column(String(50), nullable=False)                 # "창원1공장", "구미사업부"
    name = Column(String(200), nullable=False)
    location = Column(String(300))                            # "경남 창원시 성산구..."
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="divisions")
    lines = relationship("ProductionLine", back_populates="division", cascade="all, delete-orphan")


class ProductionLine(Base):
    """생산라인"""
    __tablename__ = "production_lines"

    id = Column(String, primary_key=True, default=gen_uuid)
    division_id = Column(String, ForeignKey("divisions.id"), nullable=False)
    code = Column(String(50), nullable=False)                 # "A라인", "SMT-1"
    name = Column(String(200), nullable=False)
    line_type = Column(String(50))                            # "조립", "SMT", "프레스", "건조"
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    division = relationship("Division", back_populates="lines")
    processes = relationship("Process", back_populates="line", cascade="all, delete-orphan")


class Process(Base):
    """공정"""
    __tablename__ = "processes"

    id = Column(String, primary_key=True, default=gen_uuid)
    line_id = Column(String, ForeignKey("production_lines.id"), nullable=False)
    code = Column(String(50), nullable=False)                 # "PR-001", "건조공정"
    name = Column(String(200), nullable=False)
    process_type = Column(String(50))                         # "가공", "건조", "검사", "조립"
    sequence = Column(Integer, default=0)                     # 공정 순서
    notes = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    line = relationship("ProductionLine", back_populates="processes")
    equipments = relationship("Equipment", back_populates="process", cascade="all, delete-orphan")


# ═══════════════════════════════════════════
# PLC 화면 구조 (템플릿 + 영역)
# ═══════════════════════════════════════════

class PlcTemplate(Base):
    """PLC 화면 템플릿 - 제조사/모델별 화면 레이아웃 정의"""
    __tablename__ = "plc_templates"

    id = Column(String, primary_key=True, default=gen_uuid)
    name = Column(String(200), nullable=False)
    manufacturer = Column(String(100))                        # "LS", "LG", "Siemens", "Mitsubishi"
    model = Column(String(100))                               # "XGT", "NIR 건조로"
    screen_type = Column(String(50))                          # "heater_setting", "current_monitor"
    description = Column(Text)
    reference_image_path = Column(String(500))
    layout_fingerprint = Column(String(500))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    zones = relationship("OcrZone", back_populates="template", cascade="all, delete-orphan")
    equipments = relationship("Equipment", back_populates="template")


class OcrZone(Base):
    """PLC 화면 내 개별 OCR 인식 영역"""
    __tablename__ = "ocr_zones"

    id = Column(String, primary_key=True, default=gen_uuid)
    template_id = Column(String, ForeignKey("plc_templates.id"), nullable=False)
    label = Column(String(100), nullable=False)
    metric_name = Column(String(100), nullable=False)
    metric_type = Column(SqlEnum(MetricType), default=MetricType.NUMERIC)
    unit = Column(String(20), default="")

    # 영역 좌표 (% 기준, 0~100)
    x_pct = Column(Float, nullable=False)
    y_pct = Column(Float, nullable=False)
    w_pct = Column(Float, nullable=False)
    h_pct = Column(Float, nullable=False)

    # 판정 규칙
    warn_min = Column(Float)
    warn_max = Column(Float)
    error_min = Column(Float)
    error_max = Column(Float)
    target_value = Column(Float)
    tolerance_pct = Column(Float)

    # 신호형 판정용
    ok_patterns = Column(JSON)
    ng_patterns = Column(JSON)

    # OCR 힌트
    value_pattern = Column(String(100))
    ocr_lang = Column(String(20), default="en")
    preprocessing = Column(JSON)

    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    template = relationship("PlcTemplate", back_populates="zones")


# ═══════════════════════════════════════════
# 설비 (공정에 속하고, PLC 템플릿을 사용)
# ═══════════════════════════════════════════

class Equipment(Base):
    """개별 설비 (PLC 장비) - 공정 내 위치, 여러 QR 포인트를 가질 수 있음"""
    __tablename__ = "equipments"

    id = Column(String, primary_key=True, default=gen_uuid)
    process_id = Column(String, ForeignKey("processes.id"))
    template_id = Column(String, ForeignKey("plc_templates.id"))
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    location = Column(String(200))
    manufacturer = Column(String(100))
    model = Column(String(100))
    process_code = Column(String(50))
    equipment_type = Column(String(50))
    plc_type = Column(String(100))
    metadata_ = Column("metadata", JSON)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    process = relationship("Process", back_populates="equipments")
    template = relationship("PlcTemplate", back_populates="equipments")
    judgments = relationship("JudgmentHistory", back_populates="equipment")
    criteria = relationship("JudgmentCriteria", back_populates="equipment", cascade="all, delete-orphan")
    qr_points = relationship("QrPoint", back_populates="equipment", cascade="all, delete-orphan")


# ═══════════════════════════════════════════
# QR 포인트 (1설비 : N개 QR/화면, 판정은 QR 단위)
# ═══════════════════════════════════════════

class QrPoint(Base):
    """
    QR 포인트 — 설비에 부착된 개별 QR 코드 + 해당 PLC 화면
    하나의 PLC 장비에 여러 QR 포인트가 있을 수 있음 (화면별, 패널별)
    판정은 항상 QR 포인트 단위로 실행됨

    예: NIR 건조로 #1
      ├── QR "NIR001-SCR"  → SCR 전류 화면
      ├── QR "NIR001-TEMP" → 히터 온도 화면
      └── QR "NIR001-PRES" → 유압 압력 화면
    """
    __tablename__ = "qr_points"

    id = Column(String, primary_key=True, default=gen_uuid)
    equipment_id = Column(String, ForeignKey("equipments.id"), nullable=False)
    qr_code = Column(String(200), unique=True, nullable=False)  # QR 고유값 (스캔값)
    screen_name = Column(String(200), nullable=False)            # "SCR 전류 화면", "히터 온도"
    description = Column(Text)                                    # "상단/하단 8개 히터 그룹 전류 모니터링"

    # 기준 사진 + 판정 프로필
    reference_image_path = Column(String(500))                   # 기준 사진 파일 경로
    profile_data = Column(JSON)                                  # 판정 프로필 (시각 설정 결과)
    # profile_data 구조:
    # {
    #   "rules": [{name, text, value, is_numeric, cx_pct, cy_pct, w_pct, h_pct,
    #              condition:"range|min|max|equal|text",
    #              ok_min, ok_max, threshold, tolerance, ok_text, ng_text, ...}],
    #   "screen_image": "base64...", (선택)
    #   "created_at": "ISO",
    #   "total_items": 5,
    #   "detected_items_count": 30,
    # }

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    equipment = relationship("Equipment", back_populates="qr_points")
    judgments = relationship("JudgmentHistory", back_populates="qr_point")


# ═══════════════════════════════════════════
# 판정항목 + 판정기준 (설비별 — 하위호환)
# ═══════════════════════════════════════════

class JudgmentCriteria(Base):
    """
    설비별 판정항목 + 판정기준
    예: NIR 건조로 #1의 "SCR 전류" 항목 → 정상: 20~45A, 경고: 15~20 or 45~50A, 이상: <15 or >50A
    """
    __tablename__ = "judgment_criteria"

    id = Column(String, primary_key=True, default=gen_uuid)
    equipment_id = Column(String, ForeignKey("equipments.id"), nullable=False)

    # 판정항목 정보
    name = Column(String(200), nullable=False)                # "SCR 전류", "히터 온도", "유압 압력"
    metric_type = Column(SqlEnum(MetricType), default=MetricType.NUMERIC)
    unit = Column(String(20), default="")                     # "A", "°C", "MPa"
    description = Column(Text)                                # "상단 4개 히터 그룹 전류값"

    # 수치형 판정기준
    normal_min = Column(Float)                                # 정상 하한
    normal_max = Column(Float)                                # 정상 상한
    warn_min = Column(Float)                                  # 경고 하한 (이하면 경고)
    warn_max = Column(Float)                                  # 경고 상한
    error_min = Column(Float)                                 # 이상 하한
    error_max = Column(Float)                                 # 이상 상한
    target_value = Column(Float)                              # 목표값 (SV)
    tolerance_pct = Column(Float)                             # 허용 오차%

    # 신호형 판정기준
    ok_keywords = Column(JSON)                                # ["OK", "PASS", "RUN"]
    ng_keywords = Column(JSON)                                # ["NG", "FAIL", "STOP"]

    # OCR 수치 필터 (이 항목의 값 범위 힌트)
    value_range_min = Column(Float)                           # OCR에서 이 범위만 이 항목으로 매칭
    value_range_max = Column(Float)

    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    equipment = relationship("Equipment", back_populates="criteria")


# ═══════════════════════════════════════════
# 판정 이력 + 보정 + 정확도 추적
# ═══════════════════════════════════════════

class JudgmentHistory(Base):
    """OCR 판정 이력 - 모든 촬영/판정 결과 저장"""
    __tablename__ = "judgment_history"

    id = Column(String, primary_key=True, default=gen_uuid)
    equipment_id = Column(String, ForeignKey("equipments.id"))
    qr_point_id = Column(String, ForeignKey("qr_points.id"))    # 판정 대상 QR 포인트
    company_id = Column(String, ForeignKey("companies.id"))
    process_id = Column(String, ForeignKey("processes.id"))

    image_path = Column(String(500))
    captured_at = Column(DateTime, default=datetime.utcnow)
    overall_result = Column(SqlEnum(JudgmentLevel), default=JudgmentLevel.UNKNOWN)
    zone_results = Column(JSON)
    smart_results = Column(JSON)                              # 스마트OCR 결과 (영역 없이)
    ocr_engine_used = Column(SqlEnum(OcrEngine))
    processing_time_ms = Column(Integer)
    total_values_detected = Column(Integer, default=0)
    ok_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    ng_count = Column(Integer, default=0)

    # 정확도 추적 (사용자 검증 후)
    user_verified = Column(Boolean, default=False)            # 사람이 검증했는지
    user_overall_result = Column(SqlEnum(JudgmentLevel))      # 사람이 판정한 실제 결과
    accuracy_score = Column(Float)                            # 이 판정의 정확도 (0~1)

    user_id = Column(String(100))
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    equipment = relationship("Equipment", back_populates="judgments")
    qr_point = relationship("QrPoint", back_populates="judgments")
    corrections = relationship("JudgmentCorrection", back_populates="judgment", cascade="all, delete-orphan")


class JudgmentCorrection(Base):
    """
    오판정 수정 기록 - 사용자가 개별 수치의 판정 결과를 수정
    학습 데이터로 축적되어 판정 정확도 향상에 사용
    """
    __tablename__ = "judgment_corrections"

    id = Column(String, primary_key=True, default=gen_uuid)
    judgment_id = Column(String, ForeignKey("judgment_history.id"), nullable=False)
    value_index = Column(Integer)                             # smart_results 내 수치 인덱스
    ocr_text = Column(String(200))                            # OCR이 읽은 원본
    ocr_value = Column(Float)                                 # OCR 추출값
    system_level = Column(SqlEnum(JudgmentLevel))             # 시스템 판정
    correct_value = Column(Float)                             # 사용자 입력 실제값
    correct_level = Column(SqlEnum(JudgmentLevel))            # 사용자 판정
    correction_type = Column(String(20))                      # "value" (값 오류), "level" (판정 오류), "noise" (노이즈)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100))

    judgment = relationship("JudgmentHistory", back_populates="corrections")


class OcrCorrection(Base):
    """OCR 보정 데이터 - 오인식 시 사용자가 입력한 실제값"""
    __tablename__ = "ocr_corrections"

    id = Column(String, primary_key=True, default=gen_uuid)
    equipment_id = Column(String, ForeignKey("equipments.id"), nullable=False)
    zone_id = Column(String, ForeignKey("ocr_zones.id"), nullable=False)
    ocr_text = Column(String(200))
    ocr_value = Column(Float)
    correct_value = Column(Float)
    correct_text = Column(String(200))
    image_crop_path = Column(String(500))
    applied_count = Column(Integer, default=0)
    confidence = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100))


# ═══════════════════════════════════════════
# 판정 정확도 통계 (고객사 납품용)
# ═══════════════════════════════════════════

class AccuracyStats(Base):
    """판정 정확도 일별/월별 통계"""
    __tablename__ = "accuracy_stats"

    id = Column(String, primary_key=True, default=gen_uuid)
    company_id = Column(String, ForeignKey("companies.id"))
    equipment_id = Column(String, ForeignKey("equipments.id"))
    period_type = Column(String(10))                          # "daily", "weekly", "monthly"
    period_date = Column(String(10))                          # "2026-04-05", "2026-W14", "2026-04"
    total_judgments = Column(Integer, default=0)
    verified_count = Column(Integer, default=0)               # 사용자 검증 수
    correct_count = Column(Integer, default=0)                # 정확 판정 수
    accuracy_pct = Column(Float)                              # 정확도 %
    avg_processing_ms = Column(Integer)
    total_values_detected = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
