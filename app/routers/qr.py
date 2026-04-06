"""QR 포인트 관리 + QR 기반 판정 API"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.database import get_db
from app.models import QrPoint, Equipment

router = APIRouter(prefix="/api/qr", tags=["qr"])


class QrPointIn(BaseModel):
    equipment_id: str
    qr_code: str
    screen_name: str
    description: str | None = None


class QrProfileIn(BaseModel):
    """기준설정 결과 저장"""
    qr_point_id: str
    profile_data: dict       # {rules: [...], created_at, total_items, ...}
    reference_image: str | None = None  # 기준 이미지 파일명


# ── QR 포인트 CRUD ──

@router.post("/points")
async def create_qr_point(data: QrPointIn, db: AsyncSession = Depends(get_db)):
    eq = await db.get(Equipment, data.equipment_id)
    if not eq: raise HTTPException(404, "설비를 찾을 수 없습니다")
    # 중복 QR 체크
    existing = await db.execute(select(QrPoint).where(QrPoint.qr_code == data.qr_code))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"QR '{data.qr_code}'가 이미 등록되어 있습니다")
    obj = QrPoint(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return _qr_dict(obj)


@router.get("/points/all")
async def list_all_qr_points(
    company_id: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """전체 QR 포인트 목록 (경로 포함) — 테이블 뷰용"""
    stmt = select(QrPoint).where(QrPoint.is_active == True)
    qr_points = (await db.execute(stmt)).scalars().all()

    results = []
    for qp in qr_points:
        eq = await db.get(Equipment, qp.equipment_id) if qp.equipment_id else None
        if not eq or not eq.is_active: continue

        # 경로 역추적
        proc_name = line_name = div_name = comp_name = comp_id = ""
        if eq.process_id:
            from app.models import Process, ProductionLine, Division, Company
            proc = await db.get(Process, eq.process_id)
            if proc:
                proc_name = proc.name
                line = await db.get(ProductionLine, proc.line_id) if proc.line_id else None
                if line:
                    line_name = line.name
                    div = await db.get(Division, line.division_id) if line.division_id else None
                    if div:
                        div_name = div.name
                        comp = await db.get(Company, div.company_id) if div.company_id else None
                        if comp:
                            comp_name = comp.name
                            comp_id = comp.id

        if company_id and comp_id != company_id: continue

        profile = qp.profile_data or {}
        results.append({
            "id": qp.id,
            "qr_code": qp.qr_code,
            "screen_name": qp.screen_name,
            "description": qp.description,
            "has_profile": bool(profile.get('rules')),
            "rules_count": len(profile.get('rules', [])),
            "equipment_name": eq.name,
            "equipment_code": eq.code,
            "equipment_type": eq.equipment_type,
            "plc_type": eq.plc_type,
            "process": proc_name,
            "line": line_name,
            "division": div_name,
            "company": comp_name,
        })
    return results


@router.get("/points/equipment/{equipment_id}")
async def list_qr_points(equipment_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(QrPoint).where(
        QrPoint.equipment_id == equipment_id, QrPoint.is_active == True
    ).order_by(QrPoint.created_at)
    result = await db.execute(stmt)
    return [_qr_dict(q) for q in result.scalars().all()]


@router.get("/points/{qr_point_id}")
async def get_qr_point(qr_point_id: str, db: AsyncSession = Depends(get_db)):
    qp = await db.get(QrPoint, qr_point_id)
    if not qp: raise HTTPException(404)
    return _qr_dict(qp)


@router.get("/scan/{qr_code}")
async def scan_qr(qr_code: str, db: AsyncSession = Depends(get_db)):
    """
    QR 스캔 → QR 포인트 + 설비 정보 + 판정 프로필 반환
    현장에서 QR 찍으면 바로 판정 가능한 상태로 응답
    """
    stmt = select(QrPoint).where(QrPoint.qr_code == qr_code, QrPoint.is_active == True)
    qp = (await db.execute(stmt)).scalar_one_or_none()
    if not qp:
        raise HTTPException(404, f"QR '{qr_code}' 미등록. 기준정보에서 먼저 등록하세요.")

    eq = await db.get(Equipment, qp.equipment_id) if qp.equipment_id else None
    has_profile = bool(qp.profile_data and qp.profile_data.get('rules'))

    return {
        "qr_point": _qr_dict(qp),
        "equipment": {
            "id": eq.id, "code": eq.code, "name": eq.name,
            "plc_type": eq.plc_type, "equipment_type": eq.equipment_type
        } if eq else None,
        "has_profile": has_profile,
        "profile_rules_count": len(qp.profile_data.get('rules', [])) if qp.profile_data else 0,
    }


@router.put("/points/{qr_point_id}")
async def update_qr_point(qr_point_id: str, data: QrPointIn, db: AsyncSession = Depends(get_db)):
    qp = await db.get(QrPoint, qr_point_id)
    if not qp: raise HTTPException(404)
    qp.screen_name = data.screen_name
    qp.description = data.description
    await db.commit()
    return {"ok": True}


@router.delete("/points/{qr_point_id}")
async def delete_qr_point(qr_point_id: str, db: AsyncSession = Depends(get_db)):
    qp = await db.get(QrPoint, qr_point_id)
    if not qp: raise HTTPException(404)
    qp.is_active = False; await db.commit()
    return {"ok": True}


# ── 프로필 저장/조회 ──

@router.post("/profile")
async def save_profile(data: QrProfileIn, db: AsyncSession = Depends(get_db)):
    """기준설정 결과(판정 프로필)를 QR 포인트에 저장"""
    qp = await db.get(QrPoint, data.qr_point_id)
    if not qp: raise HTTPException(404, "QR 포인트를 찾을 수 없습니다")
    qp.profile_data = data.profile_data
    if data.reference_image:
        qp.reference_image_path = data.reference_image
    await db.commit()
    return {
        "ok": True,
        "qr_code": qp.qr_code,
        "rules_count": len(data.profile_data.get('rules', []))
    }


@router.get("/profile/{qr_code}")
async def get_profile_by_qr(qr_code: str, db: AsyncSession = Depends(get_db)):
    """QR 코드로 판정 프로필 조회"""
    stmt = select(QrPoint).where(QrPoint.qr_code == qr_code, QrPoint.is_active == True)
    qp = (await db.execute(stmt)).scalar_one_or_none()
    if not qp: raise HTTPException(404, f"QR '{qr_code}' 미등록")
    if not qp.profile_data or not qp.profile_data.get('rules'):
        raise HTTPException(404, "이 QR에 판정 프로필이 설정되지 않았습니다. 기준설정을 먼저 하세요.")
    return {
        "qr_code": qp.qr_code,
        "screen_name": qp.screen_name,
        "profile": qp.profile_data,
        "reference_image": qp.reference_image_path,
    }


def _qr_dict(qp: QrPoint) -> dict:
    profile = qp.profile_data or {}
    return {
        "id": qp.id,
        "equipment_id": qp.equipment_id,
        "qr_code": qp.qr_code,
        "screen_name": qp.screen_name,
        "description": qp.description,
        "has_profile": bool(profile.get('rules')),
        "rules_count": len(profile.get('rules', [])),
        "reference_image": qp.reference_image_path,
        "created_at": str(qp.created_at) if qp.created_at else None,
    }
