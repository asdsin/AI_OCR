"""판정항목/기준 설정 + 오판정 수정/학습 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.models import (
    JudgmentCriteria, Equipment, MetricType,
    JudgmentHistory, JudgmentCorrection, JudgmentLevel
)

router = APIRouter(prefix="/api", tags=["criteria"])


def _safe_level(val: str | None) -> JudgmentLevel | None:
    """문자열을 JudgmentLevel로 안전 변환 (noise 등 비표준값은 None)"""
    if not val:
        return None
    try:
        return JudgmentLevel(val)
    except ValueError:
        return None


# ── Schemas ──

class CriteriaIn(BaseModel):
    equipment_id: str
    name: str                               # "SCR 전류", "히터 온도"
    metric_type: str = "numeric"            # numeric, signal, color
    unit: str = ""
    description: str | None = None
    normal_min: float | None = None
    normal_max: float | None = None
    warn_min: float | None = None
    warn_max: float | None = None
    error_min: float | None = None
    error_max: float | None = None
    target_value: float | None = None
    tolerance_pct: float | None = None
    ok_keywords: list[str] | None = None
    ng_keywords: list[str] | None = None
    value_range_min: float | None = None    # OCR 수치 범위 필터
    value_range_max: float | None = None
    sort_order: int = 0

class CorrectionIn(BaseModel):
    judgment_id: str
    value_index: int                        # 수치 인덱스
    ocr_text: str | None = None
    ocr_value: float | None = None
    system_level: str | None = None         # ok, warning, ng
    correct_value: float | None = None
    correct_level: str | None = None        # ok, warning, ng, noise
    correction_type: str = "value"          # value, level, noise
    notes: str | None = None
    created_by: str | None = None

class VerifyIn(BaseModel):
    judgment_id: str
    user_overall_result: str                # ok, warning, ng
    notes: str | None = None


# ── 판정항목 CRUD ──

@router.post("/criteria")
async def create_criteria(data: CriteriaIn, db: AsyncSession = Depends(get_db)):
    eq = await db.get(Equipment, data.equipment_id)
    if not eq: raise HTTPException(404, "설비를 찾을 수 없습니다")
    obj = JudgmentCriteria(**{
        **data.model_dump(),
        "metric_type": MetricType(data.metric_type)
    })
    db.add(obj); await db.commit(); await db.refresh(obj)
    d = {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
    d['metric_type'] = d['metric_type'].value if hasattr(d['metric_type'], 'value') else d['metric_type']
    return d

@router.get("/criteria/{equipment_id}")
async def list_criteria(equipment_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(JudgmentCriteria).where(
        JudgmentCriteria.equipment_id == equipment_id,
        JudgmentCriteria.is_active == True
    ).order_by(JudgmentCriteria.sort_order)
    result = await db.execute(stmt)
    out = []
    for c in result.scalars().all():
        d = {k: v for k, v in c.__dict__.items() if not k.startswith('_')}
        d['metric_type'] = d['metric_type'].value if hasattr(d['metric_type'], 'value') else d['metric_type']
        out.append(d)
    return out

@router.put("/criteria/{criteria_id}")
async def update_criteria(criteria_id: str, data: CriteriaIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(JudgmentCriteria, criteria_id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump().items():
        if k == 'metric_type': v = MetricType(v)
        setattr(obj, k, v)
    await db.commit()
    return {"ok": True}

@router.delete("/criteria/{criteria_id}")
async def delete_criteria(criteria_id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(JudgmentCriteria, criteria_id)
    if not obj: raise HTTPException(404)
    obj.is_active = False; await db.commit()
    return {"ok": True}


# ── 오판정 수정/학습 ──

@router.post("/corrections/judgment")
async def create_judgment_correction(data: CorrectionIn, db: AsyncSession = Depends(get_db)):
    """개별 수치의 오판정을 수정 (학습 데이터 축적)"""
    judgment = await db.get(JudgmentHistory, data.judgment_id)
    if not judgment: raise HTTPException(404, "판정 이력을 찾을 수 없습니다")

    obj = JudgmentCorrection(
        judgment_id=data.judgment_id,
        value_index=data.value_index,
        ocr_text=data.ocr_text,
        ocr_value=data.ocr_value,
        system_level=_safe_level(data.system_level),
        correct_value=data.correct_value,
        correct_level=_safe_level(data.correct_level),
        correction_type=data.correction_type,
        notes=data.notes,
        created_by=data.created_by
    )
    db.add(obj); await db.commit(); await db.refresh(obj)
    return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}

@router.post("/verify")
async def verify_judgment(data: VerifyIn, db: AsyncSession = Depends(get_db)):
    """판정 전체 결과를 사용자가 검증 (정확/오판정)"""
    judgment = await db.get(JudgmentHistory, data.judgment_id)
    if not judgment: raise HTTPException(404, "판정 이력을 찾을 수 없습니다")

    judgment.user_verified = True
    judgment.user_overall_result = JudgmentLevel(data.user_overall_result)
    judgment.accuracy_score = 1.0 if judgment.overall_result == judgment.user_overall_result else 0.0
    if data.notes: judgment.notes = data.notes
    await db.commit()

    return {
        "ok": True,
        "system_result": judgment.overall_result.value if judgment.overall_result else None,
        "user_result": data.user_overall_result,
        "accurate": judgment.accuracy_score == 1.0
    }

@router.get("/corrections/{judgment_id}")
async def list_corrections(judgment_id: str, db: AsyncSession = Depends(get_db)):
    """특정 판정의 수정 이력 조회"""
    stmt = select(JudgmentCorrection).where(
        JudgmentCorrection.judgment_id == judgment_id
    ).order_by(JudgmentCorrection.value_index)
    result = await db.execute(stmt)
    return [{k: v for k, v in c.__dict__.items() if not k.startswith('_')} for c in result.scalars().all()]

@router.get("/learning/stats")
async def learning_stats(equipment_id: str | None = None, db: AsyncSession = Depends(get_db)):
    """학습 데이터 축적 현황"""
    # 전체 보정 수
    corr_stmt = select(JudgmentCorrection)
    total_corrections = len((await db.execute(corr_stmt)).scalars().all())

    # 검증된 판정 수
    ver_stmt = select(JudgmentHistory).where(JudgmentHistory.user_verified == True)
    if equipment_id: ver_stmt = ver_stmt.where(JudgmentHistory.equipment_id == equipment_id)
    verified = (await db.execute(ver_stmt)).scalars().all()

    correct = sum(1 for v in verified if v.accuracy_score == 1.0)

    # 노이즈로 표시된 수
    noise_stmt = select(JudgmentCorrection).where(JudgmentCorrection.correction_type == "noise")
    noise_count = len((await db.execute(noise_stmt)).scalars().all())

    return {
        "total_corrections": total_corrections,
        "noise_marked": noise_count,
        "verified_judgments": len(verified),
        "correct_judgments": correct,
        "accuracy_pct": (correct / len(verified) * 100) if verified else 0,
        "learning_data_size": total_corrections + len(verified)
    }
