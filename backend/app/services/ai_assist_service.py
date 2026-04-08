"""
AI 보조 판정 서비스 — Gemma 3 4B via Ollama

절대 원칙:
- 기존 judgment_result를 덮어쓰지 않음
- Ollama 장애 시 graceful fallback (status='failed')
- 모든 호출을 ai_call_logs에 기록
"""
import json
import time
import logging
import httpx
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import InspectionResult, AiAssistResult, AiCallLog

logger = logging.getLogger(__name__)

# ── Ollama 설정 ──
OLLAMA_BASE = "http://localhost:11434"
OLLAMA_MODEL = "gemma3:4b"
OLLAMA_TIMEOUT = 30.0
PROMPT_VERSION = "v1.0"


# ═══════════════════════════════════
# 프롬프트 템플릿 (판정 타입별)
# ═══════════════════════════════════

def _build_prompt(judgment_type: str, context: dict, rule: dict) -> str:
    """판정 타입에 맞는 Gemma 프롬프트 생성"""

    if judgment_type == "numeric":
        return f"""You are a PLC inspection quality assistant. Analyze this OCR reading.

OCR raw text: "{context.get('raw_text', '')}"
Parsed value: {context.get('parsed_value')}
OCR confidence: {context.get('confidence')}
Rule: min={rule.get('min_value')}, max={rule.get('max_value')}, unit={rule.get('unit', '')}
Exception reason: {context.get('trigger', '')}

Tasks:
1. Is the OCR reading correct?
2. If wrong, suggest the correct numeric value.
3. Should this be OK or NG given the rule range?

Respond ONLY in JSON: {{"suggested_value": number_or_null, "suggested_judgment": "OK_or_NG", "confidence": 0.0_to_1.0, "reasoning": "brief_explanation"}}"""

    elif judgment_type == "signal":
        return f"""You are a PLC inspection quality assistant. Analyze this signal indicator.

Brightness: {context.get('brightness')}
RGB: R={context.get('rgb', {}).get('r')}, G={context.get('rgb', {}).get('g')}, B={context.get('rgb', {}).get('b')}
ON threshold: {rule.get('signal_on_threshold', 150)}, OFF threshold: {rule.get('signal_off_threshold', 50)}
Exception reason: {context.get('trigger', '')}

Is this signal ON or OFF? Is the indicator working correctly?

Respond ONLY in JSON: {{"suggested_value": "ON_or_OFF", "suggested_judgment": "OK_or_NG", "confidence": 0.0_to_1.0, "reasoning": "brief_explanation"}}"""

    elif judgment_type == "color":
        return f"""You are a PLC inspection quality assistant. Analyze this color indicator.

Detected color: {context.get('detected_color')}
HSV: H={context.get('hsv', {}).get('h')}, S={context.get('hsv', {}).get('s')}, V={context.get('hsv', {}).get('v')}
Color mapping: {json.dumps(context.get('color_mapping', {}), ensure_ascii=False)}
Exception reason: {context.get('trigger', '')}

What color is this? Does it match the mapping? Should it be OK or NG?

Respond ONLY in JSON: {{"suggested_value": "color_name", "suggested_judgment": "OK_or_NG", "confidence": 0.0_to_1.0, "reasoning": "brief_explanation"}}"""

    return "Respond in JSON: {}"


# ═══════════════════════════════════
# Ollama 호출
# ═══════════════════════════════════

async def _call_ollama(prompt: str) -> dict:
    """Ollama API 호출 — 실패 시 예외 발생"""
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        resp = await client.post(
            f"{OLLAMA_BASE}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "format": "json",
                "stream": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data


async def check_ollama_health() -> dict:
    """Ollama 상태 확인"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{OLLAMA_BASE}/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            has_gemma = any(OLLAMA_MODEL.split(":")[0] in n for n in model_names)
            return {"available": True, "model_loaded": has_gemma, "models": model_names}
    except Exception as e:
        return {"available": False, "model_loaded": False, "error": str(e)}


# ═══════════════════════════════════
# 메인 서비스: AI 보조 판정 실행
# ═══════════════════════════════════

async def execute_ai_assist(
    db: Session,
    result: InspectionResult,
    exception_reason: str,
    context: dict,
    rule: dict,
) -> dict:
    """
    AI 보조 판정 실행 — Gemma 호출 + 결과 저장

    절대: result.judgment_result를 변경하지 않음
    반환: {status, ai_judgment, ai_confidence, ai_reason, latency_ms}
    """
    started_at = datetime.utcnow()
    start_ms = time.time()

    # 프롬프트 생성
    prompt = _build_prompt(result.judgment_type, context, rule)

    # AI 호출 로그 준비
    call_log = AiCallLog(
        inspection_result_id=result.id,
        trigger_reason=exception_reason,
        model_name=OLLAMA_MODEL,
        prompt_version=PROMPT_VERSION,
        status="pending",
        started_at=started_at,
    )
    db.add(call_log)
    db.flush()

    ai_result_data = {
        "status": "failed",
        "ai_judgment": None,
        "ai_confidence": None,
        "ai_reason": None,
        "latency_ms": 0,
    }

    try:
        # Ollama 호출
        ollama_resp = await _call_ollama(prompt)
        latency_ms = int((time.time() - start_ms) * 1000)
        raw_response = ollama_resp.get("response", "")

        # JSON 파싱
        try:
            parsed = json.loads(raw_response)
            ai_judgment = parsed.get("suggested_judgment", "").upper()
            if ai_judgment not in ("OK", "NG"):
                ai_judgment = None
            ai_confidence = float(parsed.get("confidence", 0))
            ai_reason = parsed.get("reasoning", "")

            status = "success"
            ai_result_data = {
                "status": status,
                "ai_judgment": ai_judgment,
                "ai_confidence": ai_confidence,
                "ai_reason": ai_reason,
                "latency_ms": latency_ms,
                "suggested_value": parsed.get("suggested_value"),
            }

            # ai_assist_results 저장
            assist = AiAssistResult(
                inspection_result_id=result.id,
                model_name=OLLAMA_MODEL,
                prompt_version=PROMPT_VERSION,
                ai_raw_response=raw_response,
                ai_parsed_result=json.dumps(parsed, ensure_ascii=False),
                ai_confidence=ai_confidence,
                ai_reason=ai_reason,
                latency_ms=latency_ms,
                status=status,
            )
            db.add(assist)

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            status = "parse_error"
            latency_ms = int((time.time() - start_ms) * 1000)
            ai_result_data["status"] = status
            ai_result_data["latency_ms"] = latency_ms
            ai_result_data["ai_reason"] = f"JSON 파싱 실패: {str(e)[:100]}"

            assist = AiAssistResult(
                inspection_result_id=result.id,
                model_name=OLLAMA_MODEL,
                prompt_version=PROMPT_VERSION,
                ai_raw_response=raw_response,
                ai_parsed_result=None,
                ai_confidence=None,
                ai_reason=ai_result_data["ai_reason"],
                latency_ms=latency_ms,
                status=status,
            )
            db.add(assist)

    except httpx.TimeoutException:
        latency_ms = int((time.time() - start_ms) * 1000)
        ai_result_data["status"] = "timeout"
        ai_result_data["latency_ms"] = latency_ms
        ai_result_data["ai_reason"] = f"Ollama 응답 시간 초과 ({OLLAMA_TIMEOUT}초)"
        call_log.error_message = "timeout"

    except httpx.ConnectError:
        latency_ms = int((time.time() - start_ms) * 1000)
        ai_result_data["status"] = "failed"
        ai_result_data["latency_ms"] = latency_ms
        ai_result_data["ai_reason"] = "Ollama 서버에 연결할 수 없습니다"
        call_log.error_message = "connection_refused"

    except Exception as e:
        latency_ms = int((time.time() - start_ms) * 1000)
        ai_result_data["status"] = "failed"
        ai_result_data["latency_ms"] = latency_ms
        ai_result_data["ai_reason"] = str(e)[:200]
        call_log.error_message = str(e)[:500]
        logger.error(f"AI assist error: {e}", exc_info=True)

    # 호출 로그 완료
    call_log.status = ai_result_data["status"]
    call_log.latency_ms = ai_result_data["latency_ms"]
    call_log.finished_at = datetime.utcnow()

    # inspection_result 플래그 업데이트 (judgment_result는 절대 변경 안 함!)
    result.ai_assist_completed = (ai_result_data["status"] == "success")
    if ai_result_data["status"] == "success":
        result.final_result_source = "ai_assist"

    db.commit()

    return ai_result_data
