"""검사 템플릿(ROI) 관리 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import InspectionTemplate, Equipment
from app.schemas import InspectionTemplateCreate, InspectionTemplateUpdate, InspectionTemplateResponse

router = APIRouter(prefix="/templates", tags=["검사 템플릿"])


@router.get("", response_model=list[InspectionTemplateResponse])
def list_templates(db: Session = Depends(get_db)):
    """전체 템플릿 목록"""
    return db.query(InspectionTemplate).all()


@router.get("/{template_id}", response_model=InspectionTemplateResponse)
def get_template(template_id: int, db: Session = Depends(get_db)):
    """템플릿 상세"""
    tmpl = db.query(InspectionTemplate).filter(InspectionTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다")
    return tmpl


@router.get("/by-equipment/{equipment_id}", response_model=list[InspectionTemplateResponse])
def list_templates_by_equipment(equipment_id: int, db: Session = Depends(get_db)):
    """설비별 템플릿 목록"""
    return db.query(InspectionTemplate).filter(InspectionTemplate.equipment_id == equipment_id).all()


@router.post("", response_model=InspectionTemplateResponse, status_code=201)
def create_template(data: InspectionTemplateCreate, db: Session = Depends(get_db)):
    """템플릿 등록"""
    # 설비 존재 확인
    if not db.query(Equipment).filter(Equipment.id == data.equipment_id).first():
        raise HTTPException(404, f"설비 ID {data.equipment_id}를 찾을 수 없습니다")
    # judgment_type 검증
    if data.judgment_type not in ("numeric", "signal", "color"):
        raise HTTPException(400, "judgment_type은 numeric/signal/color 중 하나여야 합니다")
    tmpl = InspectionTemplate(**data.model_dump())
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.put("/{template_id}", response_model=InspectionTemplateResponse)
def update_template(template_id: int, data: InspectionTemplateUpdate, db: Session = Depends(get_db)):
    """템플릿 수정"""
    tmpl = db.query(InspectionTemplate).filter(InspectionTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(404, "템플릿을 찾을 수 없습니다")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(tmpl, k, v)
    db.commit()
    db.refresh(tmpl)
    return tmpl
