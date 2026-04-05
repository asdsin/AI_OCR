"""PLC 템플릿 + OCR Zone + 설비 CRUD API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models import PlcTemplate, OcrZone, Equipment, MetricType
from app.schemas import (
    PlcTemplateCreate, PlcTemplateResponse,
    OcrZoneCreate, OcrZoneResponse,
    EquipmentCreate, EquipmentResponse
)

router = APIRouter(prefix="/api", tags=["templates"])


# ── PLC Templates ──

@router.post("/templates", response_model=PlcTemplateResponse)
async def create_template(data: PlcTemplateCreate, db: AsyncSession = Depends(get_db)):
    template = PlcTemplate(**data.model_dump())
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return PlcTemplateResponse(**template.__dict__, zone_count=0)


@router.get("/templates", response_model=list[PlcTemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db)):
    stmt = select(PlcTemplate).where(PlcTemplate.is_active == True)
    result = await db.execute(stmt)
    templates = result.scalars().all()

    responses = []
    for t in templates:
        zone_stmt = select(func.count()).where(OcrZone.template_id == t.id)
        zone_count = (await db.execute(zone_stmt)).scalar() or 0
        responses.append(PlcTemplateResponse(**t.__dict__, zone_count=zone_count))
    return responses


@router.get("/templates/{template_id}")
async def get_template(template_id: str, db: AsyncSession = Depends(get_db)):
    template = await db.get(PlcTemplate, template_id)
    if not template:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다")

    zone_stmt = select(OcrZone).where(
        OcrZone.template_id == template_id, OcrZone.is_active == True
    ).order_by(OcrZone.sort_order)
    zones = (await db.execute(zone_stmt)).scalars().all()

    def _clean(obj):
        return {k: v for k, v in obj.__dict__.items() if not k.startswith('_')}
    return {
        "template": _clean(template),
        "zones": [_clean(z) for z in zones]
    }


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, db: AsyncSession = Depends(get_db)):
    template = await db.get(PlcTemplate, template_id)
    if not template:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다")
    template.is_active = False
    await db.commit()
    return {"message": "삭제 완료"}


# ── OCR Zones ──

@router.post("/zones", response_model=OcrZoneResponse)
async def create_zone(data: OcrZoneCreate, db: AsyncSession = Depends(get_db)):
    template = await db.get(PlcTemplate, data.template_id)
    if not template:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다")

    zone_data = data.model_dump()
    zone_data["metric_type"] = MetricType(zone_data["metric_type"])
    zone = OcrZone(**zone_data)
    db.add(zone)
    await db.commit()
    await db.refresh(zone)
    resp = zone.__dict__.copy()
    resp["metric_type"] = resp["metric_type"].value
    return OcrZoneResponse(**resp)


@router.get("/zones/{template_id}", response_model=list[OcrZoneResponse])
async def list_zones(template_id: str, db: AsyncSession = Depends(get_db)):
    stmt = select(OcrZone).where(
        OcrZone.template_id == template_id, OcrZone.is_active == True
    ).order_by(OcrZone.sort_order)
    result = await db.execute(stmt)
    zones = result.scalars().all()
    responses = []
    for z in zones:
        d = z.__dict__.copy()
        d["metric_type"] = d["metric_type"].value if hasattr(d["metric_type"], 'value') else d["metric_type"]
        responses.append(OcrZoneResponse(**d))
    return responses


@router.put("/zones/{zone_id}")
async def update_zone(zone_id: str, data: OcrZoneCreate, db: AsyncSession = Depends(get_db)):
    zone = await db.get(OcrZone, zone_id)
    if not zone:
        raise HTTPException(404, "영역을 찾을 수 없습니다")
    for k, v in data.model_dump().items():
        if k == "metric_type":
            v = MetricType(v)
        setattr(zone, k, v)
    await db.commit()
    return {"message": "수정 완료"}


@router.delete("/zones/{zone_id}")
async def delete_zone(zone_id: str, db: AsyncSession = Depends(get_db)):
    zone = await db.get(OcrZone, zone_id)
    if not zone:
        raise HTTPException(404, "영역을 찾을 수 없습니다")
    zone.is_active = False
    await db.commit()
    return {"message": "삭제 완료"}


# ── Equipment ──

@router.post("/equipments", response_model=EquipmentResponse)
async def create_equipment(data: EquipmentCreate, db: AsyncSession = Depends(get_db)):
    equip = Equipment(**data.model_dump())
    db.add(equip)
    await db.commit()
    await db.refresh(equip)
    return EquipmentResponse(**equip.__dict__)


@router.get("/equipments", response_model=list[EquipmentResponse])
async def list_equipments(db: AsyncSession = Depends(get_db)):
    stmt = select(Equipment).where(Equipment.is_active == True)
    result = await db.execute(stmt)
    return [EquipmentResponse(**e.__dict__) for e in result.scalars().all()]


@router.get("/equipments/qr/{qr_code}")
async def get_equipment_by_qr(qr_code: str, db: AsyncSession = Depends(get_db)):
    stmt = select(Equipment).where(Equipment.qr_code == qr_code, Equipment.is_active == True)
    result = await db.execute(stmt)
    equip = result.scalar_one_or_none()
    if not equip:
        raise HTTPException(404, f"QR '{qr_code}' 설비를 찾을 수 없습니다")

    # 템플릿+영역 함께 반환
    template = None
    zones = []
    if equip.template_id:
        template = await db.get(PlcTemplate, equip.template_id)
        zone_stmt = select(OcrZone).where(
            OcrZone.template_id == equip.template_id, OcrZone.is_active == True
        ).order_by(OcrZone.sort_order)
        zones = (await db.execute(zone_stmt)).scalars().all()

    return {
        "equipment": equip.__dict__,
        "template": template.__dict__ if template else None,
        "zones": [z.__dict__ for z in zones]
    }
