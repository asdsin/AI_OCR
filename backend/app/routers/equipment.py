"""설비(Equipment) 관리 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.db import get_db
from app.models import Equipment
from app.schemas import EquipmentCreate, EquipmentUpdate, EquipmentResponse, EquipmentDetailResponse

router = APIRouter(prefix="/equipments", tags=["설비"])


@router.get("", response_model=list[EquipmentResponse])
def list_equipments(db: Session = Depends(get_db)):
    """전체 설비 목록 (활성 상태만)"""
    return db.query(Equipment).filter(Equipment.is_active == True).all()


@router.get("/{equipment_id}", response_model=EquipmentDetailResponse)
def get_equipment(equipment_id: int, db: Session = Depends(get_db)):
    """설비 상세 (템플릿 목록 포함)"""
    eq = db.query(Equipment).options(joinedload(Equipment.templates)).filter(Equipment.id == equipment_id).first()
    if not eq:
        raise HTTPException(404, "설비를 찾을 수 없습니다")
    return eq


@router.get("/by-qr/{qr_value}", response_model=EquipmentDetailResponse)
def get_equipment_by_qr(qr_value: str, db: Session = Depends(get_db)):
    """QR값으로 설비 조회 (템플릿 포함) — 현장 스캔용 핵심 API"""
    eq = db.query(Equipment).options(joinedload(Equipment.templates)).filter(
        Equipment.qr_value == qr_value, Equipment.is_active == True
    ).first()
    if not eq:
        raise HTTPException(404, f"QR '{qr_value}'에 해당하는 설비가 없습니다")
    return eq


@router.post("", response_model=EquipmentResponse, status_code=201)
def create_equipment(data: EquipmentCreate, db: Session = Depends(get_db)):
    """설비 등록"""
    # 중복 체크
    if db.query(Equipment).filter(Equipment.equipment_code == data.equipment_code).first():
        raise HTTPException(409, f"설비코드 '{data.equipment_code}'가 이미 존재합니다")
    if data.qr_value and db.query(Equipment).filter(Equipment.qr_value == data.qr_value).first():
        raise HTTPException(409, f"QR값 '{data.qr_value}'가 이미 존재합니다")
    eq = Equipment(**data.model_dump())
    db.add(eq)
    db.commit()
    db.refresh(eq)
    return eq


@router.put("/{equipment_id}", response_model=EquipmentResponse)
def update_equipment(equipment_id: int, data: EquipmentUpdate, db: Session = Depends(get_db)):
    """설비 수정"""
    eq = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not eq:
        raise HTTPException(404, "설비를 찾을 수 없습니다")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(eq, k, v)
    db.commit()
    db.refresh(eq)
    return eq


@router.delete("/{equipment_id}")
def delete_equipment(equipment_id: int, db: Session = Depends(get_db)):
    """설비 비활성화 (소프트 삭제)"""
    eq = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not eq:
        raise HTTPException(404, "설비를 찾을 수 없습니다")
    eq.is_active = False
    db.commit()
    return {"message": "비활성화 완료", "id": equipment_id}
