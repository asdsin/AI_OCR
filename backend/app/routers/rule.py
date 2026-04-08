"""판정 규칙(Rule) 관리 API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import JudgmentRule, InspectionTemplate
from app.schemas import JudgmentRuleCreate, JudgmentRuleUpdate, JudgmentRuleResponse

router = APIRouter(prefix="/rules", tags=["판정 규칙"])


@router.get("", response_model=list[JudgmentRuleResponse])
def list_rules(db: Session = Depends(get_db)):
    """전체 규칙 목록"""
    return db.query(JudgmentRule).all()


@router.get("/{rule_id}", response_model=JudgmentRuleResponse)
def get_rule(rule_id: int, db: Session = Depends(get_db)):
    """규칙 상세"""
    rule = db.query(JudgmentRule).filter(JudgmentRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "규칙을 찾을 수 없습니다")
    return rule


@router.get("/by-template/{template_id}", response_model=list[JudgmentRuleResponse])
def list_rules_by_template(template_id: int, db: Session = Depends(get_db)):
    """템플릿별 규칙 목록"""
    return db.query(JudgmentRule).filter(JudgmentRule.template_id == template_id).all()


@router.post("", response_model=JudgmentRuleResponse, status_code=201)
def create_rule(data: JudgmentRuleCreate, db: Session = Depends(get_db)):
    """규칙 등록"""
    # 템플릿 존재 확인
    if not db.query(InspectionTemplate).filter(InspectionTemplate.id == data.template_id).first():
        raise HTTPException(404, f"템플릿 ID {data.template_id}를 찾을 수 없습니다")
    rule = JudgmentRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=JudgmentRuleResponse)
def update_rule(rule_id: int, data: JudgmentRuleUpdate, db: Session = Depends(get_db)):
    """규칙 수정"""
    rule = db.query(JudgmentRule).filter(JudgmentRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "규칙을 찾을 수 없습니다")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(rule, k, v)
    db.commit()
    db.refresh(rule)
    return rule
