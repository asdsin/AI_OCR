"""AI 보조 판정 API — 예외 케이스에 대한 Gemma 분석 요청"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.db import get_db
from app.models import InspectionResult, JudgmentRule
from app.services.exception_router import route_exception
from app.services.ai_assist_service import execute_ai_assist, check_ollama_health

router = APIRouter(tags=["AI 보조 판정"])


class EvaluateExceptionResponse(BaseModel):
    inspection_result_id: int
    exception_flag: bool
    exception_reason: str | None
    exception_message: str | None
    ai_assist_requested: bool
    ai_assist_status: str | None     # success / failed / timeout / parse_error / skipped
    rule_result: str                  # 기존 규칙 판정 (변경 불가)
    ai_result: str | None            # AI 추천 판정 (참고용)
    ai_confidence: float | None
    ai_reason: str | None
    latency_ms: int | None


@router.post("/inspection-results/{result_id}/evaluate-exception", response_model=EvaluateExceptionResponse)
async def evaluate_exception(result_id: int, db: Session = Depends(get_db)):
    """
    특정 판정 결과에 대해 예외 평가 + Gemma 보조 판정 요청

    흐름:
    1. inspection_result 조회
    2. 관련 rule 조회
    3. exception_router로 예외 여부 판단
    4. should_call_ai=True면 Gemma 호출 (실패해도 200 반환)
    5. 결과를 ai_assist_results + ai_call_logs에 저장
    6. ★ judgment_result는 절대 변경하지 않음 ★
    """

    # 1. 판정 결과 조회
    result = db.query(InspectionResult).filter(InspectionResult.id == result_id).first()
    if not result:
        raise HTTPException(404, "판정 결과를 찾을 수 없습니다")

    # 2. 관련 규칙 조회
    rule_obj = db.query(JudgmentRule).filter(
        JudgmentRule.template_id == result.template_id
    ).first()

    rule_dict = {}
    if rule_obj:
        rule_dict = {
            "min_value": rule_obj.min_value,
            "max_value": rule_obj.max_value,
            "unit": rule_obj.unit,
            "signal_on_threshold": rule_obj.signal_on_threshold,
            "signal_off_threshold": rule_obj.signal_off_threshold,
            "color_mapping_json": rule_obj.color_mapping_json,
            "target_text": rule_obj.target_text,
        }

    # signal_data 복원 (raw_color_json에서)
    signal_data = None
    if result.raw_color_json:
        import json
        try:
            signal_data = json.loads(result.raw_color_json)
        except (json.JSONDecodeError, TypeError):
            pass

    # 3. 예외 라우팅
    exc = route_exception(
        judgment_type=result.judgment_type,
        judgment_result=result.judgment_result,
        parsed_value=result.parsed_value,
        confidence=result.confidence,
        rule=rule_dict,
        signal_data=signal_data,
    )

    # inspection_result에 예외 플래그 업데이트
    result.exception_flag = exc.exception_flag
    result.exception_reason = exc.exception_reason

    # 4. AI 호출 여부 결정
    if not exc.should_call_ai:
        db.commit()
        return EvaluateExceptionResponse(
            inspection_result_id=result.id,
            exception_flag=exc.exception_flag,
            exception_reason=exc.exception_reason,
            exception_message=exc.exception_message,
            ai_assist_requested=False,
            ai_assist_status="skipped",
            rule_result=result.judgment_result,
            ai_result=None,
            ai_confidence=None,
            ai_reason="예외 조건에 해당하지 않아 AI 호출을 건너뛰었습니다",
            latency_ms=None,
        )

    # AI 보조 요청
    result.ai_assist_requested = True

    # 컨텍스트에 원본 데이터 추가
    context = exc.context.copy()
    context["raw_text"] = result.raw_text
    context["parsed_value"] = result.parsed_value
    context["confidence"] = result.confidence

    # 5. Gemma 호출 + 저장
    ai_data = await execute_ai_assist(
        db=db,
        result=result,
        exception_reason=exc.exception_reason,
        context=context,
        rule=rule_dict,
    )

    return EvaluateExceptionResponse(
        inspection_result_id=result.id,
        exception_flag=True,
        exception_reason=exc.exception_reason,
        exception_message=exc.exception_message,
        ai_assist_requested=True,
        ai_assist_status=ai_data["status"],
        rule_result=result.judgment_result,  # ★ 규칙 결과 — 변경 불가 ★
        ai_result=ai_data.get("ai_judgment"),
        ai_confidence=ai_data.get("ai_confidence"),
        ai_reason=ai_data.get("ai_reason"),
        latency_ms=ai_data.get("latency_ms"),
    )


@router.get("/ai/health")
async def ai_health():
    """Ollama + Gemma 모델 상태 확인"""
    return await check_ollama_health()
