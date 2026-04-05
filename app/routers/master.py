"""기준정보 마스터 API - 업체 > 사업부 > 라인 > 공정 > 설비 계층 CRUD"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import datetime
from app.database import get_db
from app.models import (
    Company, Division, ProductionLine, Process, Equipment,
    PlcTemplate, JudgmentHistory, AccuracyStats, QrPoint
)

router = APIRouter(prefix="/api/master", tags=["master"])


# ── Schemas ──

class CompanyIn(BaseModel):
    code: str; name: str; industry: str | None = None
    address: str | None = None; contact_name: str | None = None
    contact_phone: str | None = None; notes: str | None = None

class DivisionIn(BaseModel):
    company_id: str; code: str; name: str
    location: str | None = None; notes: str | None = None

class LineIn(BaseModel):
    division_id: str; code: str; name: str
    line_type: str | None = None; notes: str | None = None

class ProcessIn(BaseModel):
    line_id: str; code: str; name: str
    process_type: str | None = None; sequence: int = 0; notes: str | None = None

class EquipmentIn(BaseModel):
    process_id: str | None = None; template_id: str | None = None
    code: str; name: str
    equipment_type: str | None = None; plc_type: str | None = None
    manufacturer: str | None = None; model: str | None = None


# ── 업체 ──

@router.post("/companies")
async def create_company(data: CompanyIn, db: AsyncSession = Depends(get_db)):
    obj = Company(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj.__dict__

@router.get("/companies")
async def list_companies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Company).where(Company.is_active == True))
    companies = result.scalars().all()
    out = []
    for c in companies:
        div_cnt = (await db.execute(
            select(func.count()).where(Division.company_id == c.id, Division.is_active == True)
        )).scalar() or 0
        d = {k: v for k, v in c.__dict__.items() if not k.startswith('_')}
        d['division_count'] = div_cnt
        out.append(d)
    return out

@router.put("/companies/{id}")
async def update_company(id: str, data: CompanyIn, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Company, id)
    if not obj: raise HTTPException(404)
    for k, v in data.model_dump().items(): setattr(obj, k, v)
    await db.commit()
    return {"ok": True}

@router.delete("/companies/{id}")
async def delete_company(id: str, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Company, id)
    if not obj: raise HTTPException(404)
    obj.is_active = False; await db.commit()
    return {"ok": True}


# ── 사업부 ──

@router.post("/divisions")
async def create_division(data: DivisionIn, db: AsyncSession = Depends(get_db)):
    obj = Division(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj.__dict__

@router.get("/divisions")
async def list_divisions(company_id: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Division).where(Division.is_active == True)
    if company_id: stmt = stmt.where(Division.company_id == company_id)
    result = await db.execute(stmt)
    divisions = result.scalars().all()
    out = []
    for d in divisions:
        line_cnt = (await db.execute(
            select(func.count()).where(ProductionLine.division_id == d.id, ProductionLine.is_active == True)
        )).scalar() or 0
        dd = {k: v for k, v in d.__dict__.items() if not k.startswith('_')}
        dd['line_count'] = line_cnt
        out.append(dd)
    return out


# ── 라인 ──

@router.post("/lines")
async def create_line(data: LineIn, db: AsyncSession = Depends(get_db)):
    obj = ProductionLine(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj.__dict__

@router.get("/lines")
async def list_lines(division_id: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(ProductionLine).where(ProductionLine.is_active == True)
    if division_id: stmt = stmt.where(ProductionLine.division_id == division_id)
    result = await db.execute(stmt)
    lines = result.scalars().all()
    out = []
    for l in lines:
        proc_cnt = (await db.execute(
            select(func.count()).where(Process.line_id == l.id, Process.is_active == True)
        )).scalar() or 0
        dd = {k: v for k, v in l.__dict__.items() if not k.startswith('_')}
        dd['process_count'] = proc_cnt
        out.append(dd)
    return out


# ── 공정 ──

@router.post("/processes")
async def create_process(data: ProcessIn, db: AsyncSession = Depends(get_db)):
    obj = Process(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj.__dict__

@router.get("/processes")
async def list_processes(line_id: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Process).where(Process.is_active == True)
    if line_id: stmt = stmt.where(Process.line_id == line_id)
    result = await db.execute(stmt.order_by(Process.sequence))
    procs = result.scalars().all()
    out = []
    for p in procs:
        eq_cnt = (await db.execute(
            select(func.count()).where(Equipment.process_id == p.id, Equipment.is_active == True)
        )).scalar() or 0
        dd = {k: v for k, v in p.__dict__.items() if not k.startswith('_')}
        dd['equipment_count'] = eq_cnt
        out.append(dd)
    return out


# ── 설비 (기존 equipment API를 여기로 통합) ──

@router.post("/equipments")
async def create_equipment(data: EquipmentIn, db: AsyncSession = Depends(get_db)):
    obj = Equipment(**data.model_dump())
    db.add(obj); await db.commit(); await db.refresh(obj)
    return obj.__dict__

@router.get("/equipments")
async def list_equipments(process_id: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Equipment).where(Equipment.is_active == True)
    if process_id: stmt = stmt.where(Equipment.process_id == process_id)
    result = await db.execute(stmt)
    return [{k: v for k, v in e.__dict__.items() if not k.startswith('_')} for e in result.scalars().all()]

@router.get("/equipments/{id}")
async def get_equipment(id: str, db: AsyncSession = Depends(get_db)):
    eq = await db.get(Equipment, id)
    if not eq: raise HTTPException(404)
    return {k: v for k, v in eq.__dict__.items() if not k.startswith('_')}


# ── 전체 트리 (계층 조회) ──

@router.get("/tree")
async def get_full_tree(company_id: str | None = None, db: AsyncSession = Depends(get_db)):
    """전체 계층 트리 반환: 업체 > 사업부 > 라인 > 공정 > 설비"""
    stmt = select(Company).where(Company.is_active == True)
    if company_id: stmt = stmt.where(Company.id == company_id)
    companies = (await db.execute(stmt)).scalars().all()

    tree = []
    for comp in companies:
        divs_r = await db.execute(
            select(Division).where(Division.company_id == comp.id, Division.is_active == True))
        divs = divs_r.scalars().all()

        div_list = []
        for div in divs:
            lines_r = await db.execute(
                select(ProductionLine).where(ProductionLine.division_id == div.id, ProductionLine.is_active == True))
            lines = lines_r.scalars().all()

            line_list = []
            for line in lines:
                procs_r = await db.execute(
                    select(Process).where(Process.line_id == line.id, Process.is_active == True).order_by(Process.sequence))
                procs = procs_r.scalars().all()

                proc_list = []
                for proc in procs:
                    equips_r = await db.execute(
                        select(Equipment).where(Equipment.process_id == proc.id, Equipment.is_active == True))
                    equips = equips_r.scalars().all()

                    proc_list.append({
                        "id": proc.id, "code": proc.code, "name": proc.name,
                        "process_type": proc.process_type, "sequence": proc.sequence,
                        "equipments": [
                            {"id": e.id, "code": e.code, "name": e.name,
                             "equipment_type": e.equipment_type, "plc_type": e.plc_type,
                             "template_id": e.template_id}
                            for e in equips
                        ]
                    })
                line_list.append({
                    "id": line.id, "code": line.code, "name": line.name,
                    "line_type": line.line_type, "processes": proc_list
                })
            div_list.append({
                "id": div.id, "code": div.code, "name": div.name,
                "location": div.location, "lines": line_list
            })
        tree.append({
            "id": comp.id, "code": comp.code, "name": comp.name,
            "industry": comp.industry, "divisions": div_list
        })
    return tree


# ── 통합 검색 ──

@router.get("/search")
async def search_all(q: str, db: AsyncSession = Depends(get_db)):
    """
    모든 계층에서 키워드 검색 (업체/사업부/라인/공정/설비 통합)
    결과에 전체 경로(breadcrumb)를 포함하여 바로 선택 가능
    """
    if not q or len(q) < 1:
        return []

    keyword = f"%{q}%"
    results = []

    # QR 포인트 검색 (최우선 — 현장에서 QR 코드로 빠르게 찾기)
    qr_stmt = select(QrPoint).where(
        QrPoint.is_active == True,
        (QrPoint.qr_code.ilike(keyword)) |
        (QrPoint.screen_name.ilike(keyword))
    )
    qr_points = (await db.execute(qr_stmt)).scalars().all()
    for qp in qr_points:
        eq = await db.get(Equipment, qp.equipment_id) if qp.equipment_id else None
        if eq:
            path = await _build_path_from_equipment(db, eq)
            results.append({
                **path,
                "match_level": "qr_point",
                "match_field": f"{qp.screen_name} (QR: {qp.qr_code})",
                "qr_point": {"id": qp.id, "qr_code": qp.qr_code, "screen_name": qp.screen_name,
                              "has_profile": bool(qp.profile_data and qp.profile_data.get('rules'))},
                "equipment": {"id": eq.id, "code": eq.code, "name": eq.name,
                              "plc_type": eq.plc_type, "equipment_type": eq.equipment_type}
            })

    # 설비 검색 (가장 하위 → 경로 전체 역추적)
    eq_stmt = select(Equipment).where(
        Equipment.is_active == True,
        (Equipment.name.ilike(keyword)) |
        (Equipment.code.ilike(keyword)) |
        (Equipment.plc_type.ilike(keyword)) |
        (Equipment.equipment_type.ilike(keyword))
    )
    equips = (await db.execute(eq_stmt)).scalars().all()
    for e in equips:
        path = await _build_path_from_equipment(db, e)
        results.append({**path, "match_level": "equipment", "match_field": e.name,
                        "equipment": {"id": e.id, "code": e.code, "name": e.name,
                                      "plc_type": e.plc_type, "equipment_type": e.equipment_type}})

    # 공정 검색
    pr_stmt = select(Process).where(
        Process.is_active == True,
        (Process.name.ilike(keyword)) | (Process.code.ilike(keyword)) | (Process.process_type.ilike(keyword))
    )
    procs = (await db.execute(pr_stmt)).scalars().all()
    for p in procs:
        path = await _build_path_from_process(db, p)
        results.append({**path, "match_level": "process", "match_field": p.name})

    # 라인 검색
    ln_stmt = select(ProductionLine).where(
        ProductionLine.is_active == True,
        (ProductionLine.name.ilike(keyword)) | (ProductionLine.code.ilike(keyword)) | (ProductionLine.line_type.ilike(keyword))
    )
    lines = (await db.execute(ln_stmt)).scalars().all()
    for l in lines:
        path = await _build_path_from_line(db, l)
        results.append({**path, "match_level": "line", "match_field": l.name})

    # 사업부 검색
    dv_stmt = select(Division).where(
        Division.is_active == True,
        (Division.name.ilike(keyword)) | (Division.code.ilike(keyword)) | (Division.location.ilike(keyword))
    )
    divs = (await db.execute(dv_stmt)).scalars().all()
    for d in divs:
        comp = await db.get(Company, d.company_id)
        results.append({
            "path": [{"level": "company", "id": comp.id, "name": comp.name},
                     {"level": "division", "id": d.id, "name": d.name}],
            "breadcrumb": f"{comp.name} > {d.name}",
            "match_level": "division", "match_field": d.name
        })

    # 업체 검색
    co_stmt = select(Company).where(
        Company.is_active == True,
        (Company.name.ilike(keyword)) | (Company.code.ilike(keyword)) | (Company.industry.ilike(keyword))
    )
    comps = (await db.execute(co_stmt)).scalars().all()
    for c in comps:
        results.append({
            "path": [{"level": "company", "id": c.id, "name": c.name}],
            "breadcrumb": c.name,
            "match_level": "company", "match_field": c.name
        })

    return results


async def _build_path_from_equipment(db: AsyncSession, eq: Equipment) -> dict:
    path = []
    proc = await db.get(Process, eq.process_id) if eq.process_id else None
    line = await db.get(ProductionLine, proc.line_id) if proc else None
    div = await db.get(Division, line.division_id) if line else None
    comp = await db.get(Company, div.company_id) if div else None

    if comp: path.append({"level": "company", "id": comp.id, "name": comp.name})
    if div: path.append({"level": "division", "id": div.id, "name": div.name})
    if line: path.append({"level": "line", "id": line.id, "name": line.name})
    if proc: path.append({"level": "process", "id": proc.id, "name": proc.name})
    path.append({"level": "equipment", "id": eq.id, "name": eq.name})

    names = [p["name"] for p in path]
    return {"path": path, "breadcrumb": " > ".join(names)}


async def _build_path_from_process(db: AsyncSession, proc: Process) -> dict:
    path = []
    line = await db.get(ProductionLine, proc.line_id) if proc.line_id else None
    div = await db.get(Division, line.division_id) if line else None
    comp = await db.get(Company, div.company_id) if div else None

    if comp: path.append({"level": "company", "id": comp.id, "name": comp.name})
    if div: path.append({"level": "division", "id": div.id, "name": div.name})
    if line: path.append({"level": "line", "id": line.id, "name": line.name})
    path.append({"level": "process", "id": proc.id, "name": proc.name})

    return {"path": path, "breadcrumb": " > ".join(p["name"] for p in path)}


async def _build_path_from_line(db: AsyncSession, line: ProductionLine) -> dict:
    path = []
    div = await db.get(Division, line.division_id) if line.division_id else None
    comp = await db.get(Company, div.company_id) if div else None

    if comp: path.append({"level": "company", "id": comp.id, "name": comp.name})
    if div: path.append({"level": "division", "id": div.id, "name": div.name})
    path.append({"level": "line", "id": line.id, "name": line.name})

    return {"path": path, "breadcrumb": " > ".join(p["name"] for p in path)}


# ── 정확도 통계 ──

@router.get("/stats/accuracy")
async def get_accuracy_stats(
    company_id: str | None = None,
    equipment_id: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """판정 정확도 통계"""
    stmt = select(JudgmentHistory)
    if company_id: stmt = stmt.where(JudgmentHistory.company_id == company_id)
    if equipment_id: stmt = stmt.where(JudgmentHistory.equipment_id == equipment_id)

    result = await db.execute(stmt)
    histories = result.scalars().all()

    total = len(histories)
    verified = [h for h in histories if h.user_verified]
    correct = [h for h in verified if h.user_overall_result == h.overall_result]

    return {
        "total_judgments": total,
        "verified_count": len(verified),
        "correct_count": len(correct),
        "accuracy_pct": (len(correct) / len(verified) * 100) if verified else 0,
        "unverified_count": total - len(verified)
    }
